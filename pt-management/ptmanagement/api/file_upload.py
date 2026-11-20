#!/usr/bin/env python3
"""
File Upload Handler for SSL Certificates and Keys
Handles secure upload and management of server.key and server.crt files
"""

import os
import re
import fcntl
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

# Allowed file types and extensions
ALLOWED_FILES = {
    'server.crt': ['crt', 'cert', 'pem'],
    'server.key': ['key', 'pem'],
}

# File size limit (10MB)
MAX_FILE_SIZE = 10 * 1024 * 1024

SSL_LOCK_PATH = '/tmp/pt_ssl_upload.lock'


class FileUploadManager:
    """Manages file uploads, X.509 validation, .pending staging, and backups for SSL certificates and keys"""

    def __init__(
        self,
        ssl_dir: Optional[str] = None,
        key_dir: Optional[str] = None,
        backup_dir: Optional[str] = None,
        pending_dir: Optional[str] = None,
        env_manager: Optional[Any] = None,
        lock_path: Optional[str] = None,
    ):
        """Initialize file upload manager with configurable RW storage paths."""
        project_root = os.environ.get('PROJECT_ROOT', '/project')
        self.ssl_dir = ssl_dir or os.environ.get('SSL_DIR') or os.path.join(project_root, 'ssl')
        self.key_dir = key_dir or os.environ.get('SSL_KEY_DIR') or self.ssl_dir
        self.backup_dir = backup_dir or os.path.join(self.ssl_dir, '.backups')
        self.pending_dir = pending_dir or os.path.join(self.ssl_dir, '.pending')
        self.env_manager = env_manager
        self.lock_path = lock_path or os.environ.get('SSL_LOCK_PATH') or SSL_LOCK_PATH

        self._ensure_dirs(raise_on_error=False)

    def _ensure_dirs(self, raise_on_error: bool = True) -> None:
        """Create SSL, backup, and pending staging directories with secure permissions."""
        try:
            os.makedirs(self.ssl_dir, exist_ok=True)
            os.makedirs(self.key_dir, exist_ok=True)
            os.makedirs(self.backup_dir, mode=0o700, exist_ok=True)
            os.chmod(self.backup_dir, 0o700)
            os.makedirs(self.pending_dir, mode=0o700, exist_ok=True)
            os.chmod(self.pending_dir, 0o700)
        except OSError as e:
            if raise_on_error:
                raise
            logger.warning(f"⚠ Could not initialize SSL directories at import time: {e}")

    def _get_env_manager(self):
        """Lazily resolve EnvConfigManager instance."""
        if self.env_manager is None:
            from ptmanagement.api.env_config import EnvConfigManager
            self.env_manager = EnvConfigManager()
        return self.env_manager

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
        Validate file content cryptographically via openssl CLI (shell=False).
        Rejects malformed PEMs, non-X.509 certificates, and passphrase-encrypted private keys.
        
        Args:
            file_content: Bytes content of uploaded file
            file_type: 'server.crt' or 'server.key'
        
        Returns:
            Tuple (is_valid, message)
        """
        try:
            content_str = file_content.decode('utf-8', errors='strict')
        except Exception as e:
            return False, f"File is not valid text: {e}"
        
        if file_type == 'server.crt':
            if re.search(r'-----\s*(?:BEGIN|END)\b[^-\r\n]*PRIVATE\s+KEY[^-\r\n]*-----', content_str, re.IGNORECASE):
                return False, "Certificate upload must not contain a private key"
            if '-----BEGIN CERTIFICATE-----' not in content_str or '-----END CERTIFICATE-----' not in content_str:
                return False, "Not a valid certificate (missing PEM CERTIFICATE markers)"
        elif file_type == 'server.key':
            if '-----BEGIN' not in content_str or '-----END' not in content_str:
                return False, "Not a valid key (missing PEM markers)"
            if 'PRIVATE KEY' not in content_str:
                return False, "Not a valid private key"
        else:
            return False, "Unknown file type"

        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(prefix='pt_ssl_val_', suffix='.pem')
            os.chmod(tmp_path, 0o600)
            with os.fdopen(fd, 'wb') as tmp_f:
                tmp_f.write(file_content)

            if file_type == 'server.crt':
                res = subprocess.run(
                    ['openssl', 'x509', '-in', tmp_path, '-noout', '-subject', '-issuer', '-dates', '-ext', 'subjectAltName'],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if res.returncode != 0:
                    err = (res.stderr or res.stdout or 'OpenSSL x509 validation failed').strip()
                    return False, f"Invalid X.509 certificate: {err}"
                return True, "Valid certificate"
            else:
                res = subprocess.run(
                    ['openssl', 'pkey', '-in', tmp_path, '-pubout', '-passin', 'pass:'],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if res.returncode != 0:
                    err = (res.stderr or res.stdout or 'OpenSSL pkey validation failed').strip()
                    return False, f"Invalid or passphrase-encrypted private key: {err}"
                return True, "Valid private key"
        except subprocess.TimeoutExpired:
            return False, "Cryptographic validation timed out"
        except Exception as e:
            return False, f"Validation error: {e}"
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def verify_cert_key_pair(self, cert_path: str, key_path: str) -> Tuple[bool, str]:
        """
        Verify that an X.509 certificate and private key share the exact same public key.
        Supports RSA, ECDSA, and Ed25519 keys.
        """
        if not os.path.isfile(cert_path) or not os.path.isfile(key_path):
            return False, "Certificate or key file missing"

        try:
            cert_res = subprocess.run(
                ['openssl', 'x509', '-in', cert_path, '-pubkey', '-noout'],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if cert_res.returncode != 0 or not cert_res.stdout.strip():
                err = (cert_res.stderr or cert_res.stdout or 'Failed to extract certificate public key').strip()
                return False, f"Invalid certificate: {err}"

            key_res = subprocess.run(
                ['openssl', 'pkey', '-in', key_path, '-pubout', '-passin', 'pass:'],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if key_res.returncode != 0 or not key_res.stdout.strip():
                err = (key_res.stderr or key_res.stdout or 'Failed to extract private key public key').strip()
                return False, f"Invalid or encrypted private key: {err}"

            if cert_res.stdout.strip() == key_res.stdout.strip():
                return True, "Certificate and private key match"
            return False, "Certificate and private key public keys do not match"
        except subprocess.TimeoutExpired:
            return False, "Pair verification timed out"
        except Exception as e:
            return False, f"Pair verification error: {e}"

    def _active_path(self, file_type: str) -> str:
        if file_type == 'server.crt':
            return os.path.join(self.ssl_dir, 'server.crt')
        return os.path.join(self.key_dir, 'server.key')

    def _atomic_write_bytes(self, dest_path: str, content: bytes, mode: int) -> None:
        dest_dir = os.path.dirname(os.path.abspath(dest_path))
        os.makedirs(dest_dir, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix='.tmp_ssl_', dir=dest_dir)
        try:
            os.chmod(tmp_path, mode)
            with os.fdopen(fd, 'wb') as tmp_f:
                tmp_f.write(content)
            os.chmod(tmp_path, mode)
            os.replace(tmp_path, dest_path)
            os.chmod(dest_path, mode)
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise

    def _atomic_promote_file(self, src_path: str, dest_path: str, mode: int) -> None:
        dest_dir = os.path.dirname(os.path.abspath(dest_path))
        os.makedirs(dest_dir, exist_ok=True)
        if os.stat(src_path).st_dev == os.stat(dest_dir).st_dev:
            os.chmod(src_path, mode)
            os.replace(src_path, dest_path)
            os.chmod(dest_path, mode)
        else:
            with open(src_path, 'rb') as f:
                data = f.read()
            self._atomic_write_bytes(dest_path, data, mode)
            os.unlink(src_path)

    def backup_existing_file(self, file_type):
        """
        Backup existing certificate or key
        
        Args:
            file_type: 'server.crt' or 'server.key'
        
        Returns:
            Tuple (success, message, backup_path)
        """
        if file_type not in ('server.crt', 'server.key'):
            return False, f"Invalid file type: {file_type}", None

        src_path = self._active_path(file_type)

        # If file doesn't exist, nothing to backup
        if not os.path.exists(src_path):
            logger.info(f"⚠ No existing {file_type} to backup")
            return True, f"No existing {file_type} found", None
        
        try:
            self._ensure_dirs(raise_on_error=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            backup_filename = f"{file_type}.backup.{timestamp}"
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            shutil.copy2(src_path, backup_path)
            os.chmod(backup_path, 0o600 if file_type == 'server.key' else 0o644)
            logger.info(f"✓ Backed up {file_type} to {backup_path}")
            
            return True, "Backup created successfully", backup_path
        except Exception as e:
            logger.error(f"✗ Error backing up {file_type}: {e}")
            return False, f"Backup failed: {e}", None

    def _try_promote_pending(self, just_staged_type: str, just_staged_path: str) -> Dict[str, Any]:
        """
        Evaluate .pending/ staged files against staged or active counterpart.
        Only activates when verify_cert_key_pair() passes.
        """
        pending_crt = os.path.join(self.pending_dir, 'server.crt')
        pending_key = os.path.join(self.pending_dir, 'server.key')
        active_crt = self._active_path('server.crt')
        active_key = self._active_path('server.key')

        cand_crt = pending_crt if os.path.isfile(pending_crt) else (active_crt if os.path.isfile(active_crt) else None)
        cand_key = pending_key if os.path.isfile(pending_key) else (active_key if os.path.isfile(active_key) else None)

        if not (cand_crt and cand_key):
            return {
                'success': True,
                'staged': True,
                'pair_matched': False,
                'reloaded': False,
                'file_path': just_staged_path,
                'warning': 'File staged in .pending/; upload or restore matching counterpart to activate',
                'message': f"{just_staged_type} staged in .pending/ (awaiting matching counterpart)",
                'status_code': 200,
            }

        matched, match_msg = self.verify_cert_key_pair(cand_crt, cand_key)
        if not matched:
            return {
                'success': True,
                'staged': True,
                'pair_matched': False,
                'reloaded': False,
                'file_path': just_staged_path,
                'warning': f"File staged in .pending/; {match_msg}. Upload or restore matching counterpart to activate.",
                'message': f"{just_staged_type} staged in .pending/ (awaiting matching counterpart)",
                'status_code': 200,
            }

        # Pair matched -> back up replaced active files, atomically promote, update .env & reload nginx
        for ftype, ppath in (('server.crt', pending_crt), ('server.key', pending_key)):
            if os.path.isfile(ppath):
                backup_ok, backup_msg, _ = self.backup_existing_file(ftype)
                if not backup_ok:
                    return {
                        'success': False,
                        'staged': True,
                        'pair_matched': True,
                        'reloaded': False,
                        'file_path': just_staged_path,
                        'message': f"Could not backup existing {ftype}: {backup_msg}",
                        'status_code': 500,
                    }

        if os.path.isfile(pending_crt):
            self._atomic_promote_file(pending_crt, active_crt, 0o644)
        if os.path.isfile(pending_key):
            self._atomic_promote_file(pending_key, active_key, 0o600)

        active_dest_path = self._active_path(just_staged_type)
        env_mgr = self._get_env_manager()
        env_ok, env_msg = env_mgr.update_env_vars({
            'TLS_MODE': 'manual',
            'SSL_CERT_PATH': '/etc/ssl/ptweb/server.crt',
            'SSL_KEY_PATH': '/etc/ssl/ptweb/server.key',
        })
        if not env_ok:
            return {
                'success': False,
                'staged': False,
                'pair_matched': True,
                'reloaded': False,
                'tls_mode': 'manual',
                'file_path': active_dest_path,
                'message': f"Certificate/key activated, but failed to update .env: {env_msg}",
                'status_code': 500,
            }

        regen_ok, regen_msg = env_mgr.regenerate_nginx_config()
        if regen_ok:
            reload_ok, reload_msg = env_mgr.reload_nginx()
        else:
            reload_ok, reload_msg = False, regen_msg

        result: Dict[str, Any] = {
            'success': True,
            'staged': False,
            'pair_matched': True,
            'reloaded': reload_ok,
            'tls_mode': 'manual',
            'file_path': active_dest_path,
            'message': (
                f"{just_staged_type} activated and Nginx reloaded"
                if reload_ok
                else f"{just_staged_type} activated (Nginx reload warning: {reload_msg})"
            ),
            'status_code': 200,
        }
        if not reload_ok:
            result['warning'] = reload_msg
        return result

    def upload_and_stage(self, file_obj, file_type) -> Dict[str, Any]:
        """
        Validate, stage in .pending/, and promote certificate/key if pair matches.
        """
        if not file_obj or not getattr(file_obj, 'filename', ''):
            return {'success': False, 'message': "No file selected", 'file_path': None, 'status_code': 400}

        try:
            original_filename = secure_filename(file_obj.filename)

            is_valid, msg = self.validate_file_extension(original_filename, file_type)
            if not is_valid:
                return {'success': False, 'message': msg, 'file_path': None, 'status_code': 400}

            file_content = file_obj.read()
            if len(file_content) > MAX_FILE_SIZE:
                return {
                    'success': False,
                    'message': f"File too large (max {MAX_FILE_SIZE / 1024 / 1024}MB)",
                    'file_path': None,
                    'status_code': 400,
                }

            is_valid, msg = self.validate_file_content(file_content, file_type)
            if not is_valid:
                return {'success': False, 'message': msg, 'file_path': None, 'status_code': 400}

            lock_dir = os.path.dirname(os.path.abspath(self.lock_path))
            if lock_dir:
                os.makedirs(lock_dir, exist_ok=True)
            with open(self.lock_path, 'a+') as lock_f:
                try:
                    fcntl.flock(lock_f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return {
                        'success': False,
                        'message': "Another SSL upload/restore operation is currently in progress",
                        'file_path': None,
                        'status_code': 409,
                    }
                try:
                    self._ensure_dirs(raise_on_error=True)
                    pending_target = os.path.join(self.pending_dir, file_type)
                    mode = 0o600 if file_type == 'server.key' else 0o644
                    self._atomic_write_bytes(pending_target, file_content, mode)
                    return self._try_promote_pending(file_type, pending_target)
                finally:
                    fcntl.flock(lock_f, fcntl.LOCK_UN)

        except Exception as e:
            logger.error(f"✗ Error uploading {file_type}: {e}")
            return {'success': False, 'message': f"Upload failed: {e}", 'file_path': None, 'status_code': 500}

    def upload_file(self, file_obj, file_type):
        """
        Backward-compatible wrapper returning (success, message, file_path).
        """
        res = self.upload_and_stage(file_obj, file_type)
        return res['success'], res['message'], res.get('file_path')
    
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

    def _validate_backup_path(self, backup_path: str) -> Tuple[bool, str, Optional[Path]]:
        """Validate backup_path strictly resides directly inside self.backup_dir and is a regular file."""
        if not backup_path or not isinstance(backup_path, str):
            return False, "Invalid backup path", None
        try:
            resolved = Path(backup_path).resolve()
            backup_root = Path(self.backup_dir).resolve()
            resolved.relative_to(backup_root)
        except (ValueError, OSError):
            return False, "Invalid backup path (security check failed)", None

        if resolved == backup_root or resolved.parent != backup_root:
            return False, "Invalid backup path (security check failed)", None
        if not resolved.exists() or not resolved.is_file():
            return False, f"Backup file not found: {backup_path}", None
        return True, "OK", resolved

    def restore_and_stage(self, backup_path: str, file_type: str) -> Dict[str, Any]:
        """
        Restore a validated backup file into .pending/ and promote only when cert/key pair matches.
        """
        if file_type not in ('server.crt', 'server.key'):
            return {'success': False, 'message': f"Invalid file type: {file_type}", 'status_code': 400}

        ok, msg, resolved = self._validate_backup_path(backup_path)
        if not ok or resolved is None:
            return {'success': False, 'message': msg, 'status_code': 400}

        try:
            with open(resolved, 'rb') as f:
                content = f.read()

            is_valid, val_msg = self.validate_file_content(content, file_type)
            if not is_valid:
                return {'success': False, 'message': f"Backup validation failed: {val_msg}", 'status_code': 400}

            lock_dir = os.path.dirname(os.path.abspath(self.lock_path))
            if lock_dir:
                os.makedirs(lock_dir, exist_ok=True)
            with open(self.lock_path, 'a+') as lock_f:
                try:
                    fcntl.flock(lock_f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return {
                        'success': False,
                        'message': "Another SSL upload/restore operation is currently in progress",
                        'status_code': 409,
                    }
                try:
                    self._ensure_dirs(raise_on_error=True)
                    pending_target = os.path.join(self.pending_dir, file_type)
                    mode = 0o600 if file_type == 'server.key' else 0o644
                    self._atomic_write_bytes(pending_target, content, mode)
                    return self._try_promote_pending(file_type, pending_target)
                finally:
                    fcntl.flock(lock_f, fcntl.LOCK_UN)
        except Exception as e:
            logger.error(f"✗ Error restoring backup: {e}")
            return {'success': False, 'message': f"Restore failed: {e}", 'status_code': 500}

    def restore_backup(self, backup_path, file_type):
        """
        Backward-compatible wrapper returning (success, message).
        """
        res = self.restore_and_stage(backup_path, file_type)
        return res['success'], res['message']
    
    def get_file_info(self, file_type):
        """
        Get information about current certificate or key
        
        Args:
            file_type: 'server.crt' or 'server.key'
        
        Returns:
            Dictionary with file info or None if not found
        """
        try:
            if file_type not in ('server.crt', 'server.key'):
                return None
            filepath = self._active_path(file_type)
            
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
            ok, msg, resolved = self._validate_backup_path(backup_path)
            if not ok or resolved is None:
                return False, msg
            
            os.remove(resolved)
            logger.info(f"✓ Deleted backup: {resolved}")
            
            return True, "Backup deleted successfully"
        
        except Exception as e:
            logger.error(f"✗ Error deleting backup: {e}")
            return False, f"Delete failed: {e}"
