#!/usr/bin/env python3
"""
File Upload API Routes
Handles REST endpoints for uploading SSL certificates and keys
"""

import logging
from flask import Blueprint, request, jsonify
from ptmanagement.api.file_upload import FileUploadManager

logger = logging.getLogger(__name__)

# Initialize file upload manager
file_manager = FileUploadManager()


def create_file_upload_blueprint():
    """Create and configure the file upload API blueprint"""
    upload_api = Blueprint('upload_api', __name__, url_prefix='/api/upload')
    
    # ========================================================================
    # File Information Endpoints
    # ========================================================================
    
    @upload_api.route('/info/<file_type>', methods=['GET'])
    def get_file_info(file_type):
        """
        Get information about current certificate or key
        
        Args:
            file_type: 'crt' or 'key'
        
        Returns:
            JSON with file info
        """
        try:
            # Map short names to full names
            file_map = {'crt': 'server.crt', 'key': 'server.key'}
            full_name = file_map.get(file_type)
            
            if not full_name:
                return jsonify({'success': False, 'message': 'Invalid file type'}), 400
            
            info = file_manager.get_file_info(full_name)
            
            return jsonify({
                'success': True,
                'file_info': info if info else None,
                'exists': info is not None,
            })
        except Exception as e:
            logger.error(f"✗ Error getting file info: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @upload_api.route('/backups', methods=['GET'])
    def list_backups():
        """
        List all backup certificates and keys
        
        Returns:
            JSON with list of backups
        """
        try:
            backups = file_manager.list_backups()
            
            return jsonify({
                'success': True,
                'backups': backups,
                'total': len(backups),
            })
        except Exception as e:
            logger.error(f"✗ Error listing backups: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @upload_api.route('/backups/<file_type>', methods=['GET'])
    def list_file_backups(file_type):
        """
        List backups for specific file type
        
        Args:
            file_type: 'crt' or 'key'
        
        Returns:
            JSON with filtered backups
        """
        try:
            file_map = {'crt': 'server.crt', 'key': 'server.key'}
            full_name = file_map.get(file_type)
            
            if not full_name:
                return jsonify({'success': False, 'message': 'Invalid file type'}), 400
            
            backups = file_manager.list_backups(full_name)
            
            return jsonify({
                'success': True,
                'file_type': full_name,
                'backups': backups,
                'total': len(backups),
            })
        except Exception as e:
            logger.error(f"✗ Error listing backups: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    # ========================================================================
    # File Upload Endpoints
    # ========================================================================
    
    @upload_api.route('/certificate', methods=['POST'])
    def upload_certificate():
        """
        Upload server certificate (server.crt)
        
        Returns:
            JSON with upload result
        """
        try:
            if 'user' not in request.environ.get('session', {}):
                return jsonify({'success': False, 'message': 'Unauthorized'}), 401
            
            # Check if file is in request
            if 'file' not in request.files:
                return jsonify({'success': False, 'message': 'No file provided'}), 400
            
            file_obj = request.files['file']
            
            # Upload file
            success, message, filepath = file_manager.upload_file(file_obj, 'server.crt')
            
            status_code = 200 if success else 400
            
            return jsonify({
                'success': success,
                'message': message,
                'file_path': filepath,
            }), status_code
        
        except Exception as e:
            logger.error(f"✗ Error uploading certificate: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @upload_api.route('/key', methods=['POST'])
    def upload_key():
        """
        Upload server private key (server.key)
        
        Returns:
            JSON with upload result
        """
        try:
            if 'user' not in request.environ.get('session', {}):
                return jsonify({'success': False, 'message': 'Unauthorized'}), 401
            
            # Check if file is in request
            if 'file' not in request.files:
                return jsonify({'success': False, 'message': 'No file provided'}), 400
            
            file_obj = request.files['file']
            
            # Upload file
            success, message, filepath = file_manager.upload_file(file_obj, 'server.key')
            
            status_code = 200 if success else 400
            
            return jsonify({
                'success': success,
                'message': message,
                'file_path': filepath,
            }), status_code
        
        except Exception as e:
            logger.error(f"✗ Error uploading key: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    # ========================================================================
    # Backup Restore Endpoints
    # ========================================================================
    
    @upload_api.route('/restore', methods=['POST'])
    def restore_from_backup():
        """
        Restore certificate or key from backup
        
        Request JSON:
            - backup_path: Path to backup file
            - file_type: 'server.crt' or 'server.key'
        
        Returns:
            JSON with restore result
        """
        try:
            if 'user' not in request.environ.get('session', {}):
                return jsonify({'success': False, 'message': 'Unauthorized'}), 401
            
            data = request.json or {}
            backup_path = data.get('backup_path')
            file_type = data.get('file_type')
            
            if not backup_path or not file_type:
                return jsonify({'success': False, 'message': 'Missing backup_path or file_type'}), 400
            
            # Restore from backup
            success, message = file_manager.restore_backup(backup_path, file_type)
            
            status_code = 200 if success else 400
            
            return jsonify({
                'success': success,
                'message': message,
            }), status_code
        
        except Exception as e:
            logger.error(f"✗ Error restoring from backup: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    # ========================================================================
    # Backup Management Endpoints
    # ========================================================================
    
    @upload_api.route('/backup/delete', methods=['POST'])
    def delete_backup():
        """
        Delete a backup file
        
        Request JSON:
            - backup_path: Path to backup file to delete
        
        Returns:
            JSON with delete result
        """
        try:
            if 'user' not in request.environ.get('session', {}):
                return jsonify({'success': False, 'message': 'Unauthorized'}), 401
            
            data = request.json or {}
            backup_path = data.get('backup_path')
            
            if not backup_path:
                return jsonify({'success': False, 'message': 'Missing backup_path'}), 400
            
            # Delete backup
            success, message = file_manager.delete_backup(backup_path)
            
            status_code = 200 if success else 400
            
            return jsonify({
                'success': success,
                'message': message,
            }), status_code
        
        except Exception as e:
            logger.error(f"✗ Error deleting backup: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    return upload_api
