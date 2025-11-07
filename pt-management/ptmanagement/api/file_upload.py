#!/usr/bin/env python3
"""
File Upload Handler for SSL Certificates and Keys
Handles secure upload and management of server.key and server.crt files
"""

import os
import logging
import shutil
from pathlib import Path
from datetime import datetime
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

# Allowed file types and extensions
ALLOWED_FILES = {
    'server.crt': ['crt', 'cert', 'pem'],
    'server.key': ['key'],
}

# File size limit (10MB)
MAX_FILE_SIZE = 10 * 1024 * 1024

# SSL paths
SSL_DIR = '/etc/ssl/certs'
SSL_KEY_DIR = '/etc/ssl/private'


class FileUploadManager:
    """Manages file uploads for SSL certificates and keys"""
    
    def __init__(self):
        """Initialize file upload manager"""
        self.ssl_dir = SSL_DIR
        self.key_dir = SSL_KEY_DIR
        self.backup_dir = os.path.join(self.ssl_dir, '.backups')
        
        # Ensure directories exist
        os.makedirs(self.ssl_dir, exist_ok=True)
        os.makedirs(self.key_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def get_allowed_extensions(self, file_type):
        """
        Get allowed extensions for file type
        
        Args:
            file_type: 'server.crt' or 'server.key'
        
        Returns:
            List of allowed extensions
        """
        return ALLOWED_FILES.get(file_type, [])
    
    def validate_file_extension(self, filename, file_type):
        """
        Validate file extension
        
        Args:
            filename: Name of uploaded file
            file_type: 'server.crt' or 'server.key'
        
        Returns:
            Tuple (is_valid, message)
        """
        if file_type not in ALLOWED_FILES:
            return False, f"Invalid file type: {file_type}"
        
        allowed_exts = ALLOWED_FILES[file_type]
        file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
        if not file_ext or file_ext not in allowed_exts:
            return False, f"Invalid extension. Allowed: {', '.join(allowed_exts)}"
        
        return True, "Valid extension"
    
    def validate_file_content(self, file_content, file_type):
        """
        Validate file content
        
        Args:
            file_content: Content of uploaded file
            file_type: 'server.crt' or 'server.key'
        
        Returns:
            Tuple (is_valid, message)
        """
        try:
            content_str = file_content.decode('utf-8', errors='strict')
        except Exception as e:
            return False, f"File is not valid text: {e}"
        
        if file_type == 'server.crt':
            if '-----BEGIN CERTIFICATE-----' not in content_str:
                return False, "Not a valid certificate (missing BEGIN CERTIFICATE marker)"
            if '-----END CERTIFICATE-----' not in content_str:
                return False, "Not a valid certificate (missing END CERTIFICATE marker)"
            return True, "Valid certificate"
        
        elif file_type == 'server.key':
            if '-----BEGIN' not in content_str or '-----END' not in content_str:
                return False, "Not a valid key (missing PEM markers)"
            if 'PRIVATE KEY' not in content_str and 'RSA' not in content_str:
                return False, "Not a valid private key"
            return True, "Valid private key"
        
        return False, "Unknown file type"
    
    def backup_existing_file(self, file_type):
        """
        Backup existing certificate or key
        
        Args:
            file_type: 'server.crt' or 'server.key'
        
        Returns:
            Tuple (success, message, backup_path)
        """
        if file_type == 'server.crt':
            src_path = os.path.join(self.ssl_dir, 'server.crt')
        elif file_type == 'server.key':
            src_path = os.path.join(self.key_dir, 'server.key')
        else:
            return False, f"Invalid file type: {file_type}", None
        
        # If file doesn't exist, nothing to backup
        if not os.path.exists(src_path):
            logger.info(f"⚠ No existing {file_type} to backup")
            return True, f"No existing {file_type} found", None
        
        try:
            # Create timestamped backup
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"{file_type}.backup.{timestamp}"
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            shutil.copy2(src_path, backup_path)
            logger.info(f"✓ Backed up {file_type} to {backup_path}")
            
            return True, f"Backup created successfully", backup_path
        except Exception as e:
            logger.error(f"✗ Error backing up {file_type}: {e}")
            return False, f"Backup failed: {e}", None
    
    def upload_file(self, file_obj, file_type):
        """
        Upload and save certificate or key file
        
        Args:
            file_obj: Flask file object
            file_type: 'server.crt' or 'server.key'
        
        Returns:
            Tuple (success, message, file_path)
        """
        if not file_obj or file_obj.filename == '':
            return False, "No file selected", None
        
        try:
            # Get original filename
            original_filename = secure_filename(file_obj.filename)
            
            # Validate extension
            is_valid, msg = self.validate_file_extension(original_filename, file_type)
            if not is_valid:
                return False, msg, None
            
            # Read file content
            file_content = file_obj.read()
            
            # Check file size
            if len(file_content) > MAX_FILE_SIZE:
                return False, f"File too large (max {MAX_FILE_SIZE / 1024 / 1024}MB)", None
            
            # Validate file content
            is_valid, msg = self.validate_file_content(file_content, file_type)
            if not is_valid:
                return False, msg, None
            
            # Backup existing file
            backup_success, backup_msg, backup_path = self.backup_existing_file(file_type)
            if not backup_success:
                return False, f"Could not backup existing file: {backup_msg}", None
            
            # Determine destination path
            if file_type == 'server.crt':
                dest_path = os.path.join(self.ssl_dir, 'server.crt')
            else:  # server.key
                dest_path = os.path.join(self.key_dir, 'server.key')
            
            # Write file with restricted permissions
            with open(dest_path, 'wb') as f:
                f.write(file_content)
            
            # Set proper permissions
            if file_type == 'server.key':
                os.chmod(dest_path, 0o600)  # Read/write for owner only
                logger.info(f"✓ Set restrictive permissions (600) on {dest_path}")
            else:
                os.chmod(dest_path, 0o644)  # Read-only for others
                logger.info(f"✓ Set permissions (644) on {dest_path}")
            
            logger.info(f"✓ Uploaded {file_type} to {dest_path}")
            
            return True, f"{file_type} uploaded successfully", dest_path
        
        except Exception as e:
            logger.error(f"✗ Error uploading {file_type}: {e}")
            return False, f"Upload failed: {e}", None
    
    def list_backups(self, file_type=None):
        """
        List all backup files
        
        Args:
            file_type: Optional filter by 'server.crt' or 'server.key'
        
        Returns:
            List of backup file info
        """
        try:
            backups = []
            
            if not os.path.exists(self.backup_dir):
                return backups
            
            for filename in sorted(os.listdir(self.backup_dir), reverse=True):
                if file_type and file_type not in filename:
                    continue
                
                filepath = os.path.join(self.backup_dir, filename)
                
                if os.path.isfile(filepath):
                    stat = os.stat(filepath)
                    backups.append({
                        'filename': filename,
                        'path': filepath,
                        'size': stat.st_size,
                        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        'type': 'server.crt' if 'server.crt' in filename else 'server.key',
                    })
            
            return backups
        except Exception as e:
            logger.error(f"✗ Error listing backups: {e}")
            return []
    
    def restore_backup(self, backup_path, file_type):
        """
        Restore certificate or key from backup
        
        Args:
            backup_path: Path to backup file
            file_type: 'server.crt' or 'server.key'
        
        Returns:
            Tuple (success, message)
        """
        try:
            # Validate backup path (security check)
            backup_path = os.path.abspath(backup_path)
            backup_dir = os.path.abspath(self.backup_dir)
            
            if not backup_path.startswith(backup_dir):
                return False, "Invalid backup path (security check failed)"
            
            if not os.path.exists(backup_path):
                return False, f"Backup file not found: {backup_path}"
            
            # Backup current file before restore
            backup_success, backup_msg, _ = self.backup_existing_file(file_type)
            if not backup_success:
                logger.warning(f"⚠ Could not backup current {file_type}: {backup_msg}")
            
            # Determine destination
            if file_type == 'server.crt':
                dest_path = os.path.join(self.ssl_dir, 'server.crt')
            else:
                dest_path = os.path.join(self.key_dir, 'server.key')
            
            # Restore from backup
            shutil.copy2(backup_path, dest_path)
            
            # Set permissions
            if file_type == 'server.key':
                os.chmod(dest_path, 0o600)
            else:
                os.chmod(dest_path, 0o644)
            
            logger.info(f"✓ Restored {file_type} from {backup_path}")
            
            return True, f"{file_type} restored successfully"
        
        except Exception as e:
            logger.error(f"✗ Error restoring backup: {e}")
            return False, f"Restore failed: {e}"
    
    def get_file_info(self, file_type):
        """
        Get information about current certificate or key
        
        Args:
            file_type: 'server.crt' or 'server.key'
        
        Returns:
            Dictionary with file info or None if not found
        """
        try:
            if file_type == 'server.crt':
                filepath = os.path.join(self.ssl_dir, 'server.crt')
            else:
                filepath = os.path.join(self.key_dir, 'server.key')
            
            if not os.path.exists(filepath):
                return None
            
            stat = os.stat(filepath)
            
            return {
                'type': file_type,
                'path': filepath,
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'exists': True,
            }
        except Exception as e:
            logger.error(f"✗ Error getting file info: {e}")
            return None
    
    def delete_backup(self, backup_path):
        """
        Delete a specific backup file
        
        Args:
            backup_path: Path to backup file
        
        Returns:
            Tuple (success, message)
        """
        try:
            # Validate path
            backup_path = os.path.abspath(backup_path)
            backup_dir = os.path.abspath(self.backup_dir)
            
            if not backup_path.startswith(backup_dir):
                return False, "Invalid backup path"
            
            if not os.path.exists(backup_path):
                return False, "Backup file not found"
            
            os.remove(backup_path)
            logger.info(f"✓ Deleted backup: {backup_path}")
            
            return True, "Backup deleted successfully"
        
        except Exception as e:
            logger.error(f"✗ Error deleting backup: {e}")
            return False, f"Delete failed: {e}"
