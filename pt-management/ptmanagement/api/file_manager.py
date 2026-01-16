"""File management API for shared folder"""

import os
import logging
from pathlib import Path
from flask import Blueprint, request, jsonify, session
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
    @require_auth
    def list_files():
        """List files and directories in /shared"""
        try:
            if not os.path.exists(SHARED_FOLDER):
                os.makedirs(SHARED_FOLDER, exist_ok=True)
            
            items = []
            for item in os.listdir(SHARED_FOLDER):
                item_path = os.path.join(SHARED_FOLDER, item)
                is_dir = os.path.isdir(item_path)
                
                try:
                    stat = os.stat(item_path)
                    size = stat.st_size if not is_dir else 0
                    modified = stat.st_mtime
                except OSError:
                    size = 0
                    modified = 0
                
                items.append({
                    'name': item,
                    'path': item,
                    'type': 'directory' if is_dir else 'file',
                    'size': size,
                    'modified': modified,
                    'readable': os.access(item_path, os.R_OK),
                    'writable': os.access(item_path, os.W_OK)
                })
            
            # Sort: directories first, then alphabetically
            items.sort(key=lambda x: (x['type'] != 'directory', x['name']))
            
            return jsonify({
                'success': True,
                'path': SHARED_FOLDER,
                'items': items
            }), 200
        except Exception as e:
            logger.error(f"✗ Failed to list files: {e}")
            return jsonify({'error': str(e)}), 500
    
    @fm.route('/<path:file_path>', methods=['GET'])
    @require_auth
    def read_file(file_path):
        """Read file contents"""
        try:
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
    
    @fm.route('/<path:file_path>', methods=['POST'])
    @require_auth
    def write_file(file_path):
        """Create or update a file"""
        try:
            safe_path = validate_path(os.path.join(SHARED_FOLDER, file_path))
            if not safe_path:
                return jsonify({'error': 'Invalid path'}), 400
            
            data = request.get_json()
            if not data or 'content' not in data:
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
    @require_auth
    def delete_file(file_path):
        """Delete a file or directory"""
        try:
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
    
    @fm.route('/mkdir/<path:dir_path>', methods=['POST'])
    @require_auth
    def create_directory(dir_path):
        """Create a new directory"""
        try:
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
    
    return fm
