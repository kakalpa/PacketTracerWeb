#!/usr/bin/env python3
"""
Environment Configuration API Routes
Handles REST endpoints for reading and updating .env configuration
"""

import logging
from functools import wraps
from flask import Blueprint, request, jsonify, session
from ptmanagement.api.env_config import EnvConfigManager

logger = logging.getLogger(__name__)

# Initialize environment manager
env_manager = EnvConfigManager()


def require_admin(f):
    """Decorator to require admin authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        # Note: In production, also check if user is admin
        return f(*args, **kwargs)
    return decorated_function


def create_env_config_blueprint():
    """Create and configure the environment config API blueprint"""
    env_api = Blueprint('env_api', __name__, url_prefix='/api/env')
    
    # ========================================================================
    # Configuration Read Endpoints
    # ========================================================================
    
    @env_api.route('/config', methods=['GET'])
    @require_admin
    def get_config():
        """
        Get current environment configuration
        
        Returns:
            JSON with current config structured by section (https, geoip, rate_limit, production)
        """
        try:
            config = env_manager.get_config()
            return jsonify({
                'success': True,
                'config': config,
                'env_path': env_manager.env_path,
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
            with open(env_manager.env_path, 'r') as f:
                content = f.read()
            
            return jsonify({
                'success': True,
                'content': content,
                'path': env_manager.env_path,
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
                'cert_path': '/etc/ssl/certs/server.crt',
                'key_path': '/etc/ssl/private/server.key',
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
        
        Expected JSON:
        {
            "https": {"enabled": true, "cert_path": "...", "key_path": "..."},
            "geoip": {"allow_enabled": true, "allow_countries": [...], ...},
            "rate_limit": {"enabled": true, "rate": "100r/s", ...},
            "production": {"mode": true, "public_ip": "..."}
        }
        
        Returns:
            JSON with success status and message
        """
        try:
            updates = request.json
            if not updates:
                return jsonify({'success': False, 'message': 'No configuration provided'}), 400
            
            # Validate configuration
            is_valid, msg = env_manager.validate_config(updates)
            if not is_valid:
                return jsonify({'success': False, 'message': f'Validation failed: {msg}'}), 400
            
            # Apply changes
            success, msg = env_manager.apply_config_changes(updates)
            
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
        
        Expected JSON:
        Configuration to validate (same format as /config POST)
        
        Returns:
            JSON with validation result
        """
        try:
            config = request.json
            if not config:
                return jsonify({'success': False, 'message': 'No configuration provided'}), 400
            
            is_valid, msg = env_manager.validate_config(config)
            
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
        
        Expected JSON:
        Configuration to preview (same format as /config POST)
        
        Returns:
            JSON with preview of changes
        """
        try:
            updates = request.json
            if not updates:
                return jsonify({'success': False, 'message': 'No configuration provided'}), 400
            
            preview = env_manager.preview_changes(updates)
            
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
            backup_path = env_manager.backup_env()
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
            data = request.json
            if not data or not data.get('backup_path'):
                return jsonify({'success': False, 'message': 'No backup path provided'}), 400
            
            success, msg = env_manager.restore_env(data['backup_path'])
            
            if success:
                # Regenerate and reload nginx
                success, msg = env_manager.regenerate_nginx_config()
                if success:
                    success, msg = env_manager.reload_nginx()
            
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
            
            if os.path.exists(env_manager.backup_dir):
                for filename in sorted(os.listdir(env_manager.backup_dir), reverse=True):
                    if filename.startswith('.env.backup.'):
                        filepath = os.path.join(env_manager.backup_dir, filename)
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
            success, msg = env_manager.regenerate_nginx_config()
            
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
            success, msg = env_manager.reload_nginx()
            
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
            locked_users = env_manager.get_locked_users()
            
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
            data = request.json
            if not data:
                return jsonify({'success': False, 'message': 'No data provided'}), 400
            
            # Handle both single user and multiple users
            user_ids = data.get('user_ids') or []
            single_user = data.get('user_id')
            if single_user:
                user_ids = [single_user]
            
            if not user_ids:
                return jsonify({'success': False, 'message': 'No user IDs provided'}), 400
            
            results = []
            for user_id in user_ids:
                success, msg = env_manager.unlock_user(int(user_id))
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
            data = request.json
            if not data:
                return jsonify({'success': False, 'message': 'No data provided'}), 400
            
            # Handle both single user and multiple users
            user_ids = data.get('user_ids') or []
            single_user = data.get('user_id')
            if single_user:
                user_ids = [single_user]
            
            if not user_ids:
                return jsonify({'success': False, 'message': 'No user IDs provided'}), 400
            
            results = []
            for user_id in user_ids:
                success, msg = env_manager.reset_failed_attempts(int(user_id))
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
            status = env_manager.get_user_lockout_status(user_id)
            
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
