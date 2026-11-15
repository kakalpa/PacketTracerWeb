"""
Secure Student File Download API
Handles HMAC token generation, path traversal validation, and Nginx X-Accel-Redirect zero-copy delivery.
"""
import os
import time
import hmac
import hashlib
from pathlib import Path
from flask import Blueprint, request, jsonify, Response, current_app, session
from ptmanagement.db.connection import get_db_connection
from ptmanagement.api.auth import verify_user_credentials

student_api = Blueprint('student_api', __name__, url_prefix='/api/student/files')

# Host-mounted storage root inside pt-management container
STORAGE_BASE = Path("/shared/instances").resolve()
COMMON_BASE = Path("/shared/common").resolve()


def get_secret_key() -> bytes:
    """Retrieve secret key as bytes."""
    secret = current_app.config.get('SECRET_KEY', 'default-pt-secret-key')
    if isinstance(secret, str):
        return secret.encode('utf-8')
    return secret


def generate_download_token(container_name: str, filename: str, ttl_seconds: int = 600) -> dict:
    """Generate a time-limited HMAC-SHA256 download signature."""
    secret = get_secret_key()
    expires = int(time.time()) + ttl_seconds
    payload = f"{container_name}:{filename}:{expires}".encode('utf-8')
    signature = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return {
        'container': container_name,
        'file': filename,
        'expires': expires,
        'sig': signature
    }


def verify_download_token(container_name: str, filename: str, expires_str: str, signature: str) -> bool:
    """Validate signature authenticity and expiration timestamp."""
    try:
        expires = int(expires_str)
        if time.time() > expires:
            return False  # Token expired

        secret = get_secret_key()
        payload = f"{container_name}:{filename}:{expires}".encode('utf-8')
        expected_sig = hmac.new(secret, payload, hashlib.sha256).hexdigest()

        # Constant-time comparison prevents cryptographic timing attacks
        return hmac.compare_digest(expected_sig, signature)
    except (ValueError, TypeError):
        return False


@student_api.route('/download', methods=['GET'])
def download_file():
    """
    Zero-copy student file download endpoint via Nginx X-Accel-Redirect.
    Accepts:
      Option 1: Cryptographic parameters: container, file, expires, sig
      Option 2: Authenticated session: container, file (when logged in)
    """
    container_name = request.args.get('container', '').strip()
    filename = request.args.get('file', '').strip()
    expires = request.args.get('expires', '').strip()
    signature = request.args.get('sig', '').strip()

    if not container_name or not filename:
        return jsonify({'error': 'Missing container or file parameter'}), 400

    # Authentication check: valid HMAC token OR authenticated session
    authenticated = False
    if expires and signature:
        if verify_download_token(container_name, filename, expires, signature):
            authenticated = True
        else:
            return jsonify({'error': 'Invalid or expired download signature'}), 403
    elif 'user' in session:
        # Admin is logged in
        authenticated = True
    elif session.get('student_user') and (session.get('student_container') == container_name or container_name == 'common'):
        # Student is logged in and requesting their own container's file or common materials
        authenticated = True

    if not authenticated:
        return jsonify({'error': 'Authentication required. Valid token or session needed.'}), 401

    # Multi-Tenant Path Traversal Defense
    if container_name == 'common':
        container_dir = COMMON_BASE
        internal_uri = f"/internal/common/{filename}"
    else:
        container_dir = (STORAGE_BASE / container_name).resolve()
        internal_uri = f"/internal/downloads/{container_name}/{filename}"

    target_path = (container_dir / filename).resolve()

    try:
        # Enforce that target_path is strictly within container_dir
        target_path.relative_to(container_dir)
    except ValueError:
        return jsonify({'error': 'Access denied: Path traversal detected'}), 403

    # File Verification
    if not target_path.exists() or not target_path.is_file():
        return jsonify({'error': 'Requested file not found'}), 404

    # Emit Zero-Copy Nginx X-Accel-Redirect Header
    # Nginx will map /internal/downloads/<container>/<filename> to /shared/instances/<container>/<filename>
    # and /internal/common/<filename> to /shared/common/<filename>
    response = Response("", status=200)
    response.headers['X-Accel-Redirect'] = f"/internal/common/{target_path.name}" if container_name == 'common' else f"/internal/downloads/{container_name}/{target_path.name}"
    response.headers['Content-Type'] = 'application/octet-stream'
    response.headers['Content-Disposition'] = f'attachment; filename="{target_path.name}"'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@student_api.route('/list', methods=['GET'])
def list_files():
    """
    List available files in the student instance's isolated directory.
    Returns filenames, sizes, and signed download URLs for direct client retrieval.
    """
    container_name = request.args.get('container', '').strip()
    if not container_name:
        return jsonify({'error': 'Container identifier required'}), 400

    if container_name == 'common':
        container_dir = COMMON_BASE
    else:
        container_dir = (STORAGE_BASE / container_name).resolve()
        try:
            container_dir.relative_to(STORAGE_BASE)
        except ValueError:
            return jsonify({'error': 'Invalid container identifier'}), 403

    if not container_dir.exists() or not container_dir.is_dir():
        return jsonify({'container': container_name, 'count': 0, 'files': []}), 200

    results = []
    for entry in container_dir.iterdir():
        if entry.is_file() and not entry.name.startswith('.'):
            try:
                stat = entry.stat()
                token_meta = generate_download_token(container_name, entry.name, ttl_seconds=600)
                download_url = (
                    f"/api/student/files/download?"
                    f"container={token_meta['container']}&"
                    f"file={token_meta['file']}&"
                    f"expires={token_meta['expires']}&"
                    f"sig={token_meta['sig']}"
                )
                results.append({
                    'name': entry.name,
                    'size_bytes': stat.st_size,
                    'modified_epoch': stat.st_mtime,
                    'download_url': download_url
                })
            except OSError:
                continue

    return jsonify({
        'container': container_name,
        'count': len(results),
        'files': sorted(results, key=lambda x: x['modified_epoch'], reverse=True)
    }), 200


@student_api.route('/token', methods=['GET'])
def get_token():
    """Mint a signed token for a specific container and file."""
    container_name = request.args.get('container', '').strip()
    filename = request.args.get('file', '').strip()

    if not container_name or not filename:
        return jsonify({'error': 'container and file parameters are required'}), 400

    token_meta = generate_download_token(container_name, filename, ttl_seconds=600)
    download_url = (
        f"/api/student/files/download?"
        f"container={token_meta['container']}&"
        f"file={token_meta['file']}&"
        f"expires={token_meta['expires']}&"
        f"sig={token_meta['sig']}"
    )
    return jsonify({
        'success': True,
        'token': token_meta,
        'download_url': download_url
    }), 200


def get_user_container_name(username: str) -> str:
    """Find the container assigned to a user from Guacamole database."""
    try:
        db = get_db_connection()
        if not db:
            return None
        cursor = db.cursor()
        cursor.execute("""
            SELECT c.connection_name
            FROM guacamole_entity e
            JOIN guacamole_connection_permission cp ON e.entity_id = cp.entity_id
            JOIN guacamole_connection c ON cp.connection_id = c.connection_id
            WHERE e.name = %s AND e.type = 'USER'
        """, (username,))
        row = cursor.fetchone()
        cursor.close()
        db.close()
        if row and row[0]:
            conn = str(row[0]).strip()
            if conn.startswith('ptvnc'):
                return conn
            elif conn.startswith('pt'):
                num = conn[2:].lstrip('0') or '0'
                return f"ptvnc{num}"
            return conn
        return None
    except Exception as e:
        current_app.logger.error(f"Error querying container for {username}: {e}")
        return None


@student_api.route('/auth/login', methods=['POST'])
def student_auth_login():
    """Authenticate student against Guacamole credentials and assign their session container."""
    data = request.get_json(silent=True) or request.form
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    # Verify credentials in Guacamole MariaDB
    success, is_admin = verify_user_credentials(username, password)
    # Also permit ptadmin if admin uses portal
    if not success and username == 'ptadmin' and password == os.environ.get('PTADMIN_PASSWORD', 'admin'):
        success = True

    if not success:
        return jsonify({'error': 'Invalid student username or password'}), 401

    container = get_user_container_name(username)
    if not container:
        container = 'ptvnc1'

    session['student_user'] = username
    session['student_container'] = container

    return jsonify({
        'success': True,
        'username': username,
        'container': container,
        'message': 'Login successful'
    }), 200


@student_api.route('/auth/session', methods=['GET'])
def student_auth_session():
    """Return active student session status."""
    user = session.get('student_user')
    container = session.get('student_container')
    if not user or not container:
        return jsonify({'authenticated': False}), 200
    return jsonify({
        'authenticated': True,
        'username': user,
        'container': container
    }), 200


@student_api.route('/auth/logout', methods=['POST'])
def student_auth_logout():
    """Clear student session."""
    session.pop('student_user', None)
    session.pop('student_container', None)
    return jsonify({'success': True, 'message': 'Logged out'}), 200


@student_api.route('/my-files', methods=['GET'])
def get_my_files():
    """List student personal files and course materials for logged in student."""
    user = session.get('student_user')
    container = session.get('student_container')

    if not user or not container:
        return jsonify({'error': 'Please log in to view your files'}), 401

    container_dir = (STORAGE_BASE / container).resolve()
    personal_files = []
    if container_dir.exists() and container_dir.is_dir():
        for entry in container_dir.iterdir():
            if entry.is_file() and not entry.name.startswith('.'):
                try:
                    stat = entry.stat()
                    token_meta = generate_download_token(container, entry.name, ttl_seconds=3600)
                    download_url = (
                        f"/api/student/files/download?"
                        f"container={token_meta['container']}&"
                        f"file={token_meta['file']}&"
                        f"expires={token_meta['expires']}&"
                        f"sig={token_meta['sig']}"
                    )
                    personal_files.append({
                        'name': entry.name,
                        'size_bytes': stat.st_size,
                        'modified_epoch': stat.st_mtime,
                        'download_url': download_url
                    })
                except OSError:
                    continue

    course_materials = []
    if COMMON_BASE.exists() and COMMON_BASE.is_dir():
        for entry in COMMON_BASE.iterdir():
            if entry.is_file() and not entry.name.startswith('.'):
                try:
                    stat = entry.stat()
                    token_meta = generate_download_token("common", entry.name, ttl_seconds=3600)
                    download_url = (
                        f"/api/student/files/download?"
                        f"container={token_meta['container']}&"
                        f"file={token_meta['file']}&"
                        f"expires={token_meta['expires']}&"
                        f"sig={token_meta['sig']}"
                    )
                    course_materials.append({
                        'name': entry.name,
                        'size_bytes': stat.st_size,
                        'modified_epoch': stat.st_mtime,
                        'download_url': download_url
                    })
                except OSError:
                    continue

    return jsonify({
        'success': True,
        'username': user,
        'container': container,
        'files': sorted(personal_files, key=lambda x: x['modified_epoch'], reverse=True),
        'course_materials': sorted(course_materials, key=lambda x: x['name'])
    }), 200
