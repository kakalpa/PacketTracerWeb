#!/usr/bin/env python3
"""
Environment Configuration API Routes
Handles REST endpoints for reading and updating .env configuration
"""

import logging
import re
from flask import Blueprint, request, jsonify, current_app
from ptmanagement.api.auth import require_admin
from ptmanagement.api.env_config import EnvConfigManager

logger = logging.getLogger(__name__)

# Initialize environment manager
env_manager = EnvConfigManager()


def _extract_user_ids(data: dict):
    """Validate and extract positive integer user IDs from user_id / user_ids payload."""
    if 'user_id' in data and data['user_id'] is not None:
        raw_ids = [data['user_id']]
    elif 'user_ids' in data and data['user_ids'] is not None:
        if not isinstance(data['user_ids'], list):
            return None, (jsonify({'success': False, 'message': 'user_ids must be a list of integers'}), 400)
        raw_ids = data['user_ids']
    else:
        raw_ids = []

    if not raw_ids:
        return None, (jsonify({'success': False, 'message': 'No user IDs provided'}), 400)

    parsed_ids = []
    for uid in raw_ids:
        if isinstance(uid, (bool, float)):
            return None, (jsonify({'success': False, 'message': f'Invalid user ID: {uid}'}), 400)
        if isinstance(uid, str) and not re.fullmatch(r'[0-9]+', uid.strip()):
            return None, (jsonify({'success': False, 'message': f'Invalid user ID: {uid}'}), 400)
        try:
            uid_int = int(uid)
        except (TypeError, ValueError):
            return None, (jsonify({'success': False, 'message': f'Invalid user ID: {uid}'}), 400)
        if uid_int <= 0:
            return None, (jsonify({'success': False, 'message': f'Invalid user ID: {uid}'}), 400)
        parsed_ids.append(uid_int)
    return parsed_ids, None


def create_env_config_blueprint(manager=None):
    """Create and configure the environment config API blueprint"""
    env_api = Blueprint('env_api', __name__, url_prefix='/api/env')
    mgr = manager or env_manager
    
    # ========================================================================
    # Configuration Read Endpoints
    # ========================================================================
    
    @env_api.route('/config', methods=['GET'])
    @require_admin
    def get_config():
        """
        Get current environment configuration
        
        Returns:
            JSON with current config structured by section (https, certbot, geoip, rate_limit, production)
        """
        try:
            config = mgr.get_config()
            cookie_secure = bool(current_app.config.get('SESSION_COOKIE_SECURE', False))
            return jsonify({
                'success': True,
                'config': config,
                'env_path': mgr.env_path,
                'session_cookie_secure': cookie_secure,
                'session_cookie_restart_needed': (bool(config['https']['enabled']) != cookie_secure),
            })
        except Exception as e:
            logger.error(f"✗ Error getting config: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @env_api.route('/raw', methods=['GET'])
    @require_admin
    def get_raw_env():
        """
        Get raw .env file content (for expert users)
        
        Returns:
            JSON with raw .env content
        """
        try:
            with open(mgr.env_path, 'r') as f:
                content = f.read()
            
            return jsonify({
                'success': True,
                'content': content,
                'path': mgr.env_path,
            })
        except Exception as e:
            logger.error(f"✗ Error reading raw .env: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @env_api.route('/defaults', methods=['GET'])
    def get_defaults():
        """
        Get default configuration values (no auth required for UI initialization)
        
        Returns:
            JSON with default values for all config options
        """
        defaults = {
            'https': {
                'enabled': False,
                'cert_path': '/etc/ssl/ptweb/server.crt',
                'key_path': '/etc/ssl/ptweb/server.key',
                'tls_mode': 'self-signed',
                'server_name': 'localhost',
            },
            'certbot': {
                'enabled': False,
                'domain': '',
                'extra_domains': '',
                'email': '',
                'challenge_type': 'http-01',
                'staging': False,
                'auto_renew': True,
                'webroot': '/var/www/certbot',
            },
            'geoip': {
                'allow_enabled': False,
                'allow_countries': ['US', 'CA', 'GB', 'AU', 'FI'],
                'block_enabled': False,
                'block_countries': ['CN', 'RU', 'IR'],
            },
            'rate_limit': {
                'enabled': False,
                'rate': '100r/s',
                'burst': 200,
                'zone_size': '10m',
                'rate_examples': ['10r/s', '100r/s', '10r/m', '100r/m'],
                'zone_examples': ['10m', '20m', '50m'],
            },
            'production': {
                'mode': False,
                'public_ip': '',
            },
        }
        
        return jsonify({
            'success': True,
            'defaults': defaults,
        })
    
    # ========================================================================
    # Configuration Update Endpoints
    # ========================================================================
    
    @env_api.route('/config', methods=['POST'])
    @require_admin
    def update_config():
        """
        Update environment configuration and apply changes
        
        Returns:
            JSON with success status and message
        """
        try:
            updates = request.get_json(silent=True)
            if not isinstance(updates, dict) or not updates:
                return jsonify({'success': False, 'message': 'No valid JSON configuration provided'}), 400
            
            # Validate configuration
            is_valid, msg = mgr.validate_config(updates)
            if not is_valid:
                return jsonify({'success': False, 'message': f'Validation failed: {msg}'}), 400
            
            # Apply changes
            success, msg = mgr.apply_config_changes(updates)
            
            return jsonify({
                'success': success,
                'message': msg,
            }), 200 if success else 500
        
        except Exception as e:
            logger.error(f"✗ Error updating config: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    # ========================================================================
    # Validation & Preview Endpoints
    # ========================================================================
    
    @env_api.route('/validate', methods=['POST'])
    @require_admin
    def validate_config():
        """
        Validate configuration without applying changes
        
        Returns:
            JSON with validation result
        """
        try:
            config = request.get_json(silent=True)
            if not isinstance(config, dict) or not config:
                return jsonify({'success': False, 'message': 'No valid JSON configuration provided'}), 400
            
            is_valid, msg = mgr.validate_config(config)
            
            return jsonify({
                'success': is_valid,
                'valid': is_valid,
                'message': msg,
            })
        
        except Exception as e:
            logger.error(f"✗ Error validating config: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @env_api.route('/preview', methods=['POST'])
    @require_admin
    def preview_changes():
        """
        Preview what would change with new configuration
        
        Returns:
            JSON with preview of changes
        """
        try:
            updates = request.get_json(silent=True)
            if not isinstance(updates, dict) or not updates:
                return jsonify({'success': False, 'message': 'No valid JSON configuration provided'}), 400
            
            preview = mgr.preview_changes(updates)
            if isinstance(preview, dict) and 'error' in preview:
                return jsonify({'success': False, 'message': preview['error']}), 400
            
            return jsonify({
                'success': True,
                'preview': preview,
            })
        
        except Exception as e:
            logger.error(f"✗ Error previewing changes: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    # ========================================================================
    # Backup & Restore Endpoints
    # ========================================================================
    
    @env_api.route('/backup', methods=['POST'])
    @require_admin
    def create_backup():
        """
        Create a backup of current .env file
        
        Returns:
            JSON with backup path
        """
        try:
            backup_path = mgr.backup_env()
            if not backup_path:
                return jsonify({'success': False, 'message': 'Failed to create backup'}), 500
            
            return jsonify({
                'success': True,
                'message': 'Backup created successfully',
                'backup_path': backup_path,
            })
        
        except Exception as e:
            logger.error(f"✗ Error creating backup: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @env_api.route('/restore', methods=['POST'])
    @require_admin
    def restore_backup():
        """
        Restore .env from a backup
        
        Expected JSON:
        {"backup_path": "path/to/backup/file"}
        
        Returns:
            JSON with restore result
        """
        try:
            data = request.get_json(silent=True)
            if not isinstance(data, dict) or not isinstance(data.get('backup_path'), str) or not data['backup_path'].strip():
                return jsonify({'success': False, 'message': 'No backup path provided'}), 400
            
            success, msg = mgr.restore_env(data['backup_path'])
            if not success:
                return jsonify({'success': False, 'message': msg}), 400

            # Regenerate and reload nginx
            success, msg = mgr.regenerate_nginx_config()
            if success:
                success, msg = mgr.reload_nginx()
            
            return jsonify({
                'success': success,
                'message': msg,
            }), 200 if success else 500
        
        except Exception as e:
            logger.error(f"✗ Error restoring backup: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @env_api.route('/backups', methods=['GET'])
    @require_admin
    def list_backups():
        """
        List all available backups
        
        Returns:
            JSON with list of backup files
        """
        try:
            import os
            backups = []
            
            if os.path.exists(mgr.backup_dir):
                for filename in sorted(os.listdir(mgr.backup_dir), reverse=True):
                    if filename.startswith('.env.backup.'):
                        filepath = os.path.join(mgr.backup_dir, filename)
                        backups.append({
                            'filename': filename,
                            'path': filepath,
                            'timestamp': filename.replace('.env.backup.', ''),
                        })
            
            return jsonify({
                'success': True,
                'backups': backups[:10],  # Last 10 backups
                'count': len(backups),
            })
        
        except Exception as e:
            logger.error(f"✗ Error listing backups: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    # ========================================================================
    # Nginx Integration Endpoints
    # ========================================================================
    
    @env_api.route('/nginx/regenerate', methods=['POST'])
    @require_admin
    def regenerate_nginx():
        """
        Regenerate nginx configuration from current .env
        
        Returns:
            JSON with regeneration result
        """
        try:
            success, msg = mgr.regenerate_nginx_config()
            
            return jsonify({
                'success': success,
                'message': msg,
            }), 200 if success else 500
        
        except Exception as e:
            logger.error(f"✗ Error regenerating nginx: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @env_api.route('/nginx/reload', methods=['POST'])
    @require_admin
    def reload_nginx():
        """
        Reload nginx (hot reload, no downtime)
        
        Returns:
            JSON with reload result
        """
        try:
            success, msg = mgr.reload_nginx()
            
            return jsonify({
                'success': success,
                'message': msg,
            }), 200 if success else 500
        
        except Exception as e:
            logger.error(f"✗ Error reloading nginx: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @env_api.route('/nginx-config', methods=['GET'])
    @require_admin
    def get_nginx_config():
        """
        Get the current running nginx configuration from the pt-nginx1 container
        
        Returns:
            JSON with nginx configuration file content
        """
        try:
            import subprocess
            
            # Execute cat command in the pt-nginx1 container to get the main nginx.conf
            result = subprocess.run(
                ['docker', 'exec', 'pt-nginx1', 'cat', '/etc/nginx/nginx.conf'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                logger.warning(f"⚠ Failed to retrieve nginx config: {result.stderr}")
                return jsonify({
                    'success': False,
                    'message': 'Failed to retrieve nginx configuration from container'
                }), 500
            
            config_content = result.stdout
            
            return jsonify({
                'success': True,
                'config': config_content,
                'config_path': '/etc/nginx/nginx.conf',
                'container': 'pt-nginx1'
            }), 200
        
        except subprocess.TimeoutExpired:
            logger.error("✗ Timeout retrieving nginx config")
            return jsonify({'success': False, 'message': 'Timeout retrieving configuration'}), 500
        except Exception as e:
            logger.error(f"✗ Error retrieving nginx config: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    # ========================================================================
    # User Lockout Management Endpoints
    # ========================================================================
    
    @env_api.route('/users/locked', methods=['GET'])
    @require_admin
    def get_locked_users():
        """
        Get all currently locked-out users
        
        Returns:
            JSON with list of locked users and their lockout details
        """
        try:
            locked_users = mgr.get_locked_users()
            
            return jsonify({
                'success': True,
                'locked_users': locked_users,
                'count': len(locked_users),
            })
        
        except Exception as e:
            logger.error(f"✗ Error retrieving locked users: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @env_api.route('/users/unlock', methods=['POST'])
    @require_admin
    def unlock_users():
        """
        Unlock one or more users
        
        Expected JSON:
        {
            "user_ids": [1, 2, 3]  or "user_id": 1
        }
        
        Returns:
            JSON with unlock results
        """
        try:
            data = request.get_json(silent=True)
            if not isinstance(data, dict) or not data:
                return jsonify({'success': False, 'message': 'No data provided'}), 400
            
            user_ids, err_resp = _extract_user_ids(data)
            if err_resp is not None:
                return err_resp
            
            results = []
            for user_id in user_ids:
                success, msg = mgr.unlock_user(user_id)
                results.append({
                    'user_id': user_id,
                    'success': success,
                    'message': msg,
                })
            
            all_success = all(r['success'] for r in results)
            
            return jsonify({
                'success': all_success,
                'message': f'Unlocked {sum(1 for r in results if r["success"])} of {len(results)} users',
                'results': results,
            }), 200 if all_success else 207
        
        except Exception as e:
            logger.error(f"✗ Error unlocking users: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @env_api.route('/users/reset-attempts', methods=['POST'])
    @require_admin
    def reset_failed_attempts():
        """
        Reset failed login attempts for one or more users
        
        Expected JSON:
        {
            "user_ids": [1, 2, 3]  or "user_id": 1
        }
        
        Returns:
            JSON with reset results
        """
        try:
            data = request.get_json(silent=True)
            if not isinstance(data, dict) or not data:
                return jsonify({'success': False, 'message': 'No data provided'}), 400
            
            user_ids, err_resp = _extract_user_ids(data)
            if err_resp is not None:
                return err_resp
            
            results = []
            for user_id in user_ids:
                success, msg = mgr.reset_failed_attempts(user_id)
                results.append({
                    'user_id': user_id,
                    'success': success,
                    'message': msg,
                })
            
            all_success = all(r['success'] for r in results)
            
            return jsonify({
                'success': all_success,
                'message': f'Reset attempts for {sum(1 for r in results if r["success"])} of {len(results)} users',
                'results': results,
            }), 200 if all_success else 207
        
        except Exception as e:
            logger.error(f"✗ Error resetting attempts: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @env_api.route('/users/lockout-status/<int:user_id>', methods=['GET'])
    @require_admin
    def get_lockout_status(user_id):
        """
        Get lockout status for a specific user
        
        Args:
            user_id: User ID (from URL path)
        
        Returns:
            JSON with user's lockout status
        """
        try:
            status = mgr.get_user_lockout_status(user_id)
            
            if status is None:
                return jsonify({
                    'success': True,
                    'locked': False,
                    'message': 'User not found in lockout table (not locked)',
                })
            
            return jsonify({
                'success': True,
                'locked': status.get('locked', False),
                'status': status,
            })
        
        except Exception as e:
            logger.error(f"✗ Error getting lockout status: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    return env_api
