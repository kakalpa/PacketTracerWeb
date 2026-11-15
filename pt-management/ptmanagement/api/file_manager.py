"""File management API for shared folder"""

import os
import io
import zipfile
import logging
from pathlib import Path
from flask import Blueprint, request, jsonify, session, send_file
from functools import wraps

logger = logging.getLogger(__name__)

# Shared folder path - must match the Docker mount point
SHARED_FOLDER = '/shared'


def require_auth(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function


def validate_path(requested_path):
    """
    Validate that requested path is within /shared to prevent path traversal attacks.
    Returns the safe absolute path or None if invalid.
    """
    try:
        # Resolve to absolute path
        safe_path = Path(SHARED_FOLDER).resolve()
        requested = Path(requested_path).resolve()
        
        # Check if requested path is within SHARED_FOLDER
        requested.relative_to(safe_path)
        return requested
    except (ValueError, RuntimeError):
        # Path is outside SHARED_FOLDER
        return None


def create_file_manager_blueprint():
    """Create and configure the file manager API blueprint"""
    fm = Blueprint('file_manager', __name__, url_prefix='/api/files')
    
    @fm.route('/', methods=['GET'])
    @fm.route('/list', methods=['GET'])
    @fm.route('/list/<path:sub_path>', methods=['GET'])
    @require_auth
    def list_files(sub_path=''):
        """List files and directories in /shared or a subfolder"""
        try:
            if not os.path.exists(SHARED_FOLDER):
                os.makedirs(SHARED_FOLDER, exist_ok=True)
            
            # Ensure standard folders exist
            for sub in ('common', 'instances', 'archive'):
                os.makedirs(os.path.join(SHARED_FOLDER, sub), exist_ok=True)

            target_folder = validate_path(os.path.join(SHARED_FOLDER, sub_path)) if sub_path else Path(SHARED_FOLDER).resolve()
            if not target_folder or not target_folder.exists():
                return jsonify({'error': 'Directory not found'}), 404
            
            if not target_folder.is_dir():
                return jsonify({'error': 'Path is not a directory'}), 400

            items = []
            for item in sorted(os.listdir(str(target_folder))):
                item_path = target_folder / item
                is_dir = item_path.is_dir()
                
                try:
                    stat = item_path.stat()
                    size = stat.st_size if not is_dir else 0
                    modified = stat.st_mtime
                except OSError:
                    size = 0
                    modified = 0
                
                rel_path = str(item_path.relative_to(Path(SHARED_FOLDER).resolve()))
                items.append({
                    'name': item,
                    'path': rel_path,
                    'type': 'directory' if is_dir else 'file',
                    'size': size,
                    'modified': modified,
                    'readable': os.access(str(item_path), os.R_OK),
                    'writable': os.access(str(item_path), os.W_OK)
                })
            
            # Sort: directories first, then alphabetically
            items.sort(key=lambda x: (x['type'] != 'directory', x['name']))
            
            return jsonify({
                'success': True,
                'path': str(target_folder.relative_to(Path(SHARED_FOLDER).resolve())) if sub_path else '',
                'items': items
            }), 200
        except Exception as e:
            logger.error(f"✗ Failed to list files: {e}")
            return jsonify({'error': str(e)}), 500
    
    @fm.route('/<path:file_path>', methods=['GET'])
    @fm.route('/read/<path:file_path>', methods=['GET'])
    @require_auth
    def read_file(file_path):
        """Read file contents"""
        try:
            if file_path.startswith('read/'):
                file_path = file_path[len('read/'):]
            safe_path = validate_path(os.path.join(SHARED_FOLDER, file_path))
            if not safe_path:
                return jsonify({'error': 'Invalid path'}), 400
            
            if not os.path.exists(safe_path):
                return jsonify({'error': 'File not found'}), 404
            
            if os.path.isdir(safe_path):
                return jsonify({'error': 'Path is a directory'}), 400
            
            if not os.access(safe_path, os.R_OK):
                return jsonify({'error': 'Permission denied'}), 403
            
            # Check file size (limit to 10MB for safety)
            file_size = os.path.getsize(safe_path)
            if file_size > 10 * 1024 * 1024:
                return jsonify({'error': 'File too large (max 10MB)'}), 413
            
            # Try to read as text
            try:
                with open(safe_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                is_binary = False
            except UnicodeDecodeError:
                # Binary file - read as base64
                import base64
                with open(safe_path, 'rb') as f:
                    content = base64.b64encode(f.read()).decode('ascii')
                is_binary = True
            
            return jsonify({
                'success': True,
                'path': file_path,
                'content': content,
                'is_binary': is_binary,
                'size': file_size
            }), 200
        except Exception as e:
            logger.error(f"✗ Failed to read file {file_path}: {e}")
            return jsonify({'error': str(e)}), 500
    
    @fm.route('/write', methods=['POST'])
    @fm.route('/<path:file_path>', methods=['POST'])
    @fm.route('/write/<path:file_path>', methods=['POST'])
    @require_auth
    def write_file(file_path=''):
        """Create or update a file"""
        try:
            data = request.get_json(silent=True) or {}
            if not file_path or file_path == 'write':
                file_path = data.get('path', '')
            elif file_path.startswith('write/'):
                file_path = file_path[len('write/'):]

            if not file_path:
                return jsonify({'error': 'Missing file path'}), 400

            safe_path = validate_path(os.path.join(SHARED_FOLDER, file_path))
            if not safe_path:
                return jsonify({'error': 'Invalid path'}), 400
            
            if 'content' not in data:
                return jsonify({'error': 'Missing content'}), 400
            
            content = data['content']
            mode = data.get('mode', 'w')  # 'w' for overwrite, 'a' for append
            
            # Create parent directories if they don't exist
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if we're trying to overwrite without permission
            if safe_path.exists() and not os.access(safe_path, os.W_OK):
                return jsonify({'error': 'Permission denied'}), 403
            
            # Write file
            with open(safe_path, mode, encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"✓ File written: {safe_path}")
            
            return jsonify({
                'success': True,
                'path': file_path,
                'message': 'File saved successfully',
                'size': os.path.getsize(safe_path)
            }), 200
        except Exception as e:
            logger.error(f"✗ Failed to write file {file_path}: {e}")
            return jsonify({'error': str(e)}), 500
    
    @fm.route('/<path:file_path>', methods=['DELETE'])
    @fm.route('/delete/<path:file_path>', methods=['DELETE'])
    @require_auth
    def delete_file(file_path):
        """Delete a file or directory"""
        try:
            if file_path.startswith('delete/'):
                file_path = file_path[len('delete/'):]

            if file_path in ('common', 'instances', 'archive', ''):
                return jsonify({'error': 'Cannot delete root system directory'}), 400

            safe_path = validate_path(os.path.join(SHARED_FOLDER, file_path))
            if not safe_path:
                return jsonify({'error': 'Invalid path'}), 400
            
            if not os.path.exists(safe_path):
                return jsonify({'error': 'File not found'}), 404
            
            if not os.access(safe_path, os.W_OK):
                return jsonify({'error': 'Permission denied'}), 403
            
            if os.path.isdir(safe_path):
                import shutil
                shutil.rmtree(safe_path)
                logger.info(f"✓ Directory deleted: {safe_path}")
            else:
                os.remove(safe_path)
                logger.info(f"✓ File deleted: {safe_path}")
            
            return jsonify({
                'success': True,
                'path': file_path,
                'message': 'File/directory deleted successfully'
            }), 200
        except Exception as e:
            logger.error(f"✗ Failed to delete file {file_path}: {e}")
            return jsonify({'error': str(e)}), 500
    
    @fm.route('/mkdir', methods=['POST'])
    @fm.route('/mkdir/<path:dir_path>', methods=['POST'])
    @require_auth
    def create_directory(dir_path=''):
        """Create a new directory"""
        try:
            data = request.get_json(silent=True) or {}
            if not dir_path or dir_path == 'mkdir':
                dir_path = data.get('path', '')
            elif dir_path.startswith('mkdir/'):
                dir_path = dir_path[len('mkdir/'):]

            if not dir_path:
                return jsonify({'error': 'Missing directory path'}), 400

            safe_path = validate_path(os.path.join(SHARED_FOLDER, dir_path))
            if not safe_path:
                return jsonify({'error': 'Invalid path'}), 400
            
            if os.path.exists(safe_path):
                return jsonify({'error': 'Directory already exists'}), 409
            
            safe_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"✓ Directory created: {safe_path}")
            
            return jsonify({
                'success': True,
                'path': dir_path,
                'message': 'Directory created successfully'
            }), 201
        except Exception as e:
            logger.error(f"✗ Failed to create directory {dir_path}: {e}")
            return jsonify({'error': str(e)}), 500
    
    @fm.route('/rename', methods=['POST'])
    @require_auth
    def rename_file():
        """Rename a file or directory"""
        try:
            data = request.get_json()
            if not data or 'old_path' not in data or 'new_path' not in data:
                return jsonify({'error': 'Missing old_path or new_path'}), 400
            
            old_path = validate_path(os.path.join(SHARED_FOLDER, data['old_path']))
            new_path = validate_path(os.path.join(SHARED_FOLDER, data['new_path']))
            
            if not old_path or not new_path:
                return jsonify({'error': 'Invalid path'}), 400
            
            if not os.path.exists(old_path):
                return jsonify({'error': 'Source path not found'}), 404
            
            if os.path.exists(new_path):
                return jsonify({'error': 'Destination already exists'}), 409
            
            if not os.access(old_path, os.W_OK):
                return jsonify({'error': 'Permission denied'}), 403
            
            os.rename(old_path, new_path)
            logger.info(f"✓ File renamed: {old_path} → {new_path}")
            
            return jsonify({
                'success': True,
                'old_path': data['old_path'],
                'new_path': data['new_path'],
                'message': 'File renamed successfully'
            }), 200
        except Exception as e:
            logger.error(f"✗ Failed to rename file: {e}")
            return jsonify({'error': str(e)}), 500
    
    @fm.route('/upload', methods=['POST'])
    @require_auth
    def upload_file():
        """Upload a file to /shared"""
        try:
            # Check if file is in request
            if 'file' not in request.files:
                return jsonify({'error': 'No file provided'}), 400
            
            file = request.files['file']
            if file.filename == '':
                return jsonify({'error': 'No file selected'}), 400
            
            # Get target directory from form data
            target_dir = request.form.get('target_dir', '').strip()
            if target_dir:
                target_path = validate_path(os.path.join(SHARED_FOLDER, target_dir))
            else:
                target_path = Path(SHARED_FOLDER).resolve()
            
            if not target_path:
                return jsonify({'error': 'Invalid directory path'}), 400
            
            # Ensure target directory exists
            target_path.mkdir(parents=True, exist_ok=True)
            
            # Sanitize filename to prevent path traversal
            filename = os.path.basename(file.filename)
            if not filename or filename.startswith('.'):
                return jsonify({'error': 'Invalid filename'}), 400
            
            # Full path for saving
            full_path = target_path / filename
            
            # Check if file already exists
            if full_path.exists():
                return jsonify({'error': 'File already exists'}), 409
            
            # Check file size (limit to 100MB)
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            if file_size > 100 * 1024 * 1024:  # 100MB limit
                return jsonify({'error': 'File too large (max 100MB)'}), 413
            
            # Reset file pointer to beginning
            file.seek(0)
            
            # Save file
            file.save(str(full_path))
            logger.info(f"✓ File uploaded: {full_path}")
            
            return jsonify({
                'success': True,
                'filename': filename,
                'path': str(full_path.relative_to(SHARED_FOLDER)),
                'size': file_size,
                'message': 'File uploaded successfully'
            }), 201
        except Exception as e:
            logger.error(f"✗ Failed to upload file: {e}")
            return jsonify({'error': str(e)}), 500

    @fm.route('/download/<path:file_path>', methods=['GET'])
    @require_auth
    def download_file(file_path):
        """Download raw file as attachment"""
        try:
            safe_path = validate_path(os.path.join(SHARED_FOLDER, file_path))
            if not safe_path or not safe_path.exists() or safe_path.is_dir():
                return jsonify({'error': 'File not found'}), 404
            
            return send_file(
                str(safe_path),
                as_attachment=True,
                download_name=safe_path.name
            )
        except Exception as e:
            logger.error(f"✗ Failed to download file {file_path}: {e}")
            return jsonify({'error': str(e)}), 500

    @fm.route('/download-zip', methods=['GET'])
    @fm.route('/download-zip/<path:sub_path>', methods=['GET'])
    @require_auth
    def download_zip(sub_path=''):
        """Download a directory or the entire shared folder as a zip archive"""
        try:
            target_path = validate_path(os.path.join(SHARED_FOLDER, sub_path)) if sub_path else Path(SHARED_FOLDER).resolve()
            if not target_path or not target_path.exists():
                return jsonify({'error': 'Directory not found'}), 404
            
            archive_name = f"{target_path.name or 'shared'}.zip"
            memory_file = io.BytesIO()
            
            with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
                if target_path.is_file():
                    zf.write(str(target_path), arcname=target_path.name)
                else:
                    for root, dirs, files in os.walk(str(target_path)):
                        for file in files:
                            abs_file = os.path.join(root, file)
                            rel_file = os.path.relpath(abs_file, str(target_path))
                            zf.write(abs_file, arcname=rel_file)
            
            memory_file.seek(0)
            return send_file(
                memory_file,
                mimetype='application/zip',
                as_attachment=True,
                download_name=archive_name
            )
        except Exception as e:
            logger.error(f"✗ Failed to create zip archive: {e}")
            return jsonify({'error': str(e)}), 500

    @fm.route('/storage', methods=['GET'])
    @require_auth
    def get_storage_stats():
        """Get storage usage statistics for /shared and subdirectories"""
        try:
            stat = os.statvfs(SHARED_FOLDER)
            free_bytes = stat.f_bavail * stat.f_frsize
            total_bytes = stat.f_blocks * stat.f_frsize
            disk_used_bytes = total_bytes - free_bytes

            def dir_size(p):
                total = 0
                if os.path.exists(p):
                    for entry in os.scandir(p):
                        if entry.is_file(follow_symlinks=False):
                            total += entry.stat().st_size
                        elif entry.is_dir(follow_symlinks=False):
                            total += dir_size(entry.path)
                return total

            common_bytes = dir_size(os.path.join(SHARED_FOLDER, 'common'))
            instances_bytes = dir_size(os.path.join(SHARED_FOLDER, 'instances'))
            total_shared_bytes = common_bytes + instances_bytes

            return jsonify({
                'success': True,
                'total_disk_bytes': total_bytes,
                'free_disk_bytes': free_bytes,
                'used_disk_bytes': disk_used_bytes,
                'shared_total_bytes': total_shared_bytes,
                'common_bytes': common_bytes,
                'instances_bytes': instances_bytes
            }), 200
        except Exception as e:
            logger.error(f"✗ Failed to calculate storage stats: {e}")
            return jsonify({'error': str(e)}), 500
    
    return fm
