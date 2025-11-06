#!/usr/bin/env python3
"""
PROOF OF CONCEPT: Nginx Configuration API
This demonstrates how to implement runtime nginx configuration management
"""

import os
import json
import subprocess
import logging
import re
from typing import Dict, Any, Tuple, Optional
from datetime import datetime
import shutil

logger = logging.getLogger(__name__)


class NginxConfigManager:
    """Manages nginx configuration generation and application"""
    
    def __init__(self):
        self.nginx_container = os.environ.get('NGINX_CONTAINER', 'pt-nginx1')
        self.config_path = '/etc/nginx/conf.d/ptweb.conf'
        self.env_path = os.environ.get('ENV_PATH', '/app/.env')
        self.backup_dir = '/tmp/nginx-backups'
        os.makedirs(self.backup_dir, exist_ok=True)
    
    # ========================================================================
    # READ CONFIGURATION
    # ========================================================================
    
    def read_current_config(self) -> Optional[str]:
        """
        Read current nginx configuration from container
        
        Returns:
            str: Current nginx config content, or None if failed
        """
        try:
            cmd = ['docker', 'exec', self.nginx_container, 'cat', self.config_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                logger.info(f"✓ Read nginx config from {self.nginx_container}")
                return result.stdout
            else:
                logger.error(f"✗ Failed to read config: {result.stderr}")
                return None
        except Exception as e:
            logger.error(f"✗ Exception reading config: {e}")
            return None
    
    def parse_config(self, config_text: str) -> Dict[str, Any]:
        """
        Parse nginx configuration into structured format
        
        Args:
            config_text: Raw nginx config content
        
        Returns:
            dict: Structured configuration
        """
        settings = {
            'https_enabled': False,
            'ssl_cert_path': '',
            'ssl_key_path': '',
            'geoip_allow_enabled': False,
            'geoip_allow_countries': '',
            'geoip_block_enabled': False,
            'geoip_block_countries': '',
            'rate_limit_enabled': False,
            'rate_limit_rate': '',
            'rate_limit_burst': '',
            'rate_limit_zone_size': '',
        }
        
        try:
            # Check for HTTPS
            if re.search(r'listen\s+443\s+ssl', config_text):
                settings['https_enabled'] = True
            
            # Extract SSL paths
            cert_match = re.search(r'ssl_certificate\s+([^;]+);', config_text)
            if cert_match:
                settings['ssl_cert_path'] = cert_match.group(1).strip()
            
            key_match = re.search(r'ssl_certificate_key\s+([^;]+);', config_text)
            if key_match:
                settings['ssl_key_path'] = key_match.group(1).strip()
            
            # Extract rate limiting
            if re.search(r'limit_req_zone', config_text):
                settings['rate_limit_enabled'] = True
                
                rate_match = re.search(r'rate=(\S+)', config_text)
                if rate_match:
                    settings['rate_limit_rate'] = rate_match.group(1)
                
                burst_match = re.search(r'burst=(\d+)', config_text)
                if burst_match:
                    settings['rate_limit_burst'] = burst_match.group(1)
                
                zone_match = re.search(r'zone=pt_req_zone:(\S+)', config_text)
                if zone_match:
                    settings['rate_limit_zone_size'] = zone_match.group(1)
            
            # Extract GeoIP settings (simplified - would need actual parsing)
            if 'if ($allowed_country = 0)' in config_text:
                settings['geoip_allow_enabled'] = True
            
            if 'if ($blocked_country = 1)' in config_text:
                settings['geoip_block_enabled'] = True
            
            logger.info(f"✓ Parsed nginx config: {json.dumps(settings, indent=2)}")
            return settings
        
        except Exception as e:
            logger.error(f"✗ Exception parsing config: {e}")
            return settings
    
    # ========================================================================
    # GENERATE CONFIGURATION
    # ========================================================================
    
    def generate_config(self, settings: Dict[str, Any]) -> str:
        """
        Generate nginx configuration from settings
        
        Args:
            settings: Configuration parameters
        
        Returns:
            str: Generated nginx config content
        """
        config_parts = []
        
        # Rate limiting zone
        if settings.get('rate_limit_enabled'):
            rate = settings.get('rate_limit_rate', '100r/s')
            zone_size = settings.get('rate_limit_zone_size', '10m')
            config_parts.append(
                f'limit_req_zone $binary_remote_addr zone=pt_req_zone:{zone_size} rate={rate};'
            )
        
        # HTTP to HTTPS redirect
        if settings.get('https_enabled'):
            config_parts.append('''
server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
}
''')
        
        # Main HTTPS server block
        if settings.get('https_enabled'):
            cert = settings.get('ssl_cert_path', '/etc/ssl/certs/server.crt')
            key = settings.get('ssl_key_path', '/etc/ssl/private/server.key')
            
            config_parts.append(f'''
server {{
    listen 443 ssl http2;
    server_name _;
    
    ssl_certificate {cert};
    ssl_certificate_key {key};
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
''')
        else:
            config_parts.append('''
server {
    listen 80;
    server_name _;
''')
        
        # Location blocks
        config_parts.append('''
    location / {
''')
        
        if settings.get('rate_limit_enabled'):
            burst = settings.get('rate_limit_burst', '200')
            config_parts.append(f'        limit_req zone=pt_req_zone burst={burst} nodelay;')
        
        config_parts.append('''
        proxy_pass http://guacamole:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /downloads/ {
        alias /shared/;
        autoindex on;
''')
        
        if settings.get('rate_limit_enabled'):
            burst = settings.get('rate_limit_burst', '200')
            config_parts.append(f'        limit_req zone=pt_req_zone burst={burst} nodelay;')
        
        config_parts.append('''
    }
}
''')
        
        return '\n'.join(config_parts)
    
    # ========================================================================
    # VALIDATION
    # ========================================================================
    
    def validate_config(self, config_text: str) -> Tuple[bool, str]:
        """
        Validate nginx configuration syntax
        
        Args:
            config_text: Nginx config to validate
        
        Returns:
            tuple: (is_valid, message)
        """
        try:
            # Write to temporary file
            temp_config = '/tmp/ptweb.conf.test'
            with open(temp_config, 'w') as f:
                f.write(config_text)
            
            # Copy to container and test
            copy_cmd = ['docker', 'cp', temp_config, f'{self.nginx_container}:{temp_config}']
            subprocess.run(copy_cmd, check=True, capture_output=True)
            
            test_cmd = ['docker', 'exec', self.nginx_container, 'nginx', '-t', '-c', temp_config]
            result = subprocess.run(test_cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info("✓ Nginx config validation passed")
                return True, "Configuration is valid"
            else:
                error_msg = result.stderr or result.stdout
                logger.error(f"✗ Nginx config validation failed: {error_msg}")
                return False, error_msg
        
        except Exception as e:
            logger.error(f"✗ Exception validating config: {e}")
            return False, str(e)
    
    # ========================================================================
    # APPLY CONFIGURATION
    # ========================================================================
    
    def backup_config(self) -> str:
        """
        Backup current configuration and .env
        
        Returns:
            str: Backup directory path
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(self.backup_dir, f'backup_{timestamp}')
        os.makedirs(backup_path, exist_ok=True)
        
        try:
            # Backup current nginx config from container
            current_config = self.read_current_config()
            if current_config:
                with open(os.path.join(backup_path, 'ptweb.conf'), 'w') as f:
                    f.write(current_config)
            
            # Backup current .env
            if os.path.exists(self.env_path):
                shutil.copy2(self.env_path, os.path.join(backup_path, '.env'))
            
            logger.info(f"✓ Config backed up to {backup_path}")
            return backup_path
        
        except Exception as e:
            logger.error(f"✗ Exception backing up config: {e}")
            return None
    
    def apply_config(self, config_text: str) -> Tuple[bool, str]:
        """
        Apply new nginx configuration
        
        Args:
            config_text: New nginx config content
        
        Returns:
            tuple: (success, message)
        """
        try:
            # Backup first
            backup_path = self.backup_config()
            if not backup_path:
                return False, "Failed to create backup"
            
            # Validate
            is_valid, msg = self.validate_config(config_text)
            if not is_valid:
                return False, f"Config validation failed: {msg}"
            
            # Write new config to temporary location
            temp_config = '/tmp/ptweb.conf.new'
            with open(temp_config, 'w') as f:
                f.write(config_text)
            
            # Copy to container
            copy_cmd = ['docker', 'cp', temp_config, f'{self.nginx_container}:{self.config_path}']
            subprocess.run(copy_cmd, check=True, capture_output=True)
            
            # Reload nginx
            reload_cmd = ['docker', 'exec', self.nginx_container, 'nginx', '-s', 'reload']
            result = subprocess.run(reload_cmd, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                logger.info("✓ Nginx reloaded successfully")
                return True, "Configuration applied successfully"
            else:
                # Rollback on failure
                logger.error(f"✗ Nginx reload failed: {result.stderr}")
                self.rollback_config(backup_path)
                return False, f"Nginx reload failed: {result.stderr}"
        
        except Exception as e:
            logger.error(f"✗ Exception applying config: {e}")
            return False, str(e)
    
    def rollback_config(self, backup_path: str) -> Tuple[bool, str]:
        """
        Rollback to previous configuration
        
        Args:
            backup_path: Path to backup directory
        
        Returns:
            tuple: (success, message)
        """
        try:
            backup_config = os.path.join(backup_path, 'ptweb.conf')
            if not os.path.exists(backup_config):
                return False, "Backup config not found"
            
            with open(backup_config, 'r') as f:
                config_text = f.read()
            
            # Apply backup config
            return self.apply_config(config_text)
        
        except Exception as e:
            logger.error(f"✗ Exception rolling back config: {e}")
            return False, str(e)
    
    # ========================================================================
    # CHANGE PREVIEW
    # ========================================================================
    
    def preview_changes(self, new_settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a preview of what would change
        
        Args:
            new_settings: New configuration settings
        
        Returns:
            dict: Preview information
        """
        try:
            # Get current settings
            current_config = self.read_current_config()
            current_settings = self.parse_config(current_config)
            
            # Compare
            changes = {}
            for key in new_settings:
                if current_settings.get(key) != new_settings.get(key):
                    changes[key] = {
                        'from': current_settings.get(key),
                        'to': new_settings.get(key)
                    }
            
            return {
                'changes': changes,
                'change_count': len(changes),
                'message': f"{len(changes)} setting(s) will change"
            }
        
        except Exception as e:
            logger.error(f"✗ Exception generating preview: {e}")
            return {'error': str(e)}


# ============================================================================
# FLASK API ENDPOINTS
# ============================================================================

def create_nginx_config_api(app):
    """
    Register nginx configuration API endpoints with Flask app
    
    Args:
        app: Flask application instance
    """
    
    manager = NginxConfigManager()
    
    @app.route('/api/nginx/config', methods=['GET'])
    def get_nginx_config():
        """Get current nginx configuration"""
        config = manager.read_current_config()
        if not config:
            return {'success': False, 'message': 'Failed to read config'}, 500
        
        settings = manager.parse_config(config)
        return {
            'success': True,
            'settings': settings,
            'raw_config': config
        }
    
    @app.route('/api/nginx/config', methods=['POST'])
    def update_nginx_config():
        """Update nginx configuration"""
        try:
            new_settings = request.json
            
            # Validate input
            if not new_settings:
                return {'success': False, 'message': 'No settings provided'}, 400
            
            # Generate new config
            new_config = manager.generate_config(new_settings)
            
            # Apply
            success, msg = manager.apply_config(new_config)
            
            return {
                'success': success,
                'message': msg,
                'timestamp': datetime.now().isoformat()
            }, 200 if success else 500
        
        except Exception as e:
            logger.error(f"✗ Exception in update_nginx_config: {e}")
            return {'success': False, 'message': str(e)}, 500
    
    @app.route('/api/nginx/preview', methods=['POST'])
    def preview_nginx_config():
        """Preview proposed changes"""
        try:
            new_settings = request.json
            if not new_settings:
                return {'success': False, 'message': 'No settings provided'}, 400
            
            preview = manager.preview_changes(new_settings)
            return {'success': True, 'preview': preview}
        
        except Exception as e:
            logger.error(f"✗ Exception in preview_nginx_config: {e}")
            return {'success': False, 'message': str(e)}, 500
    
    @app.route('/api/nginx/validate', methods=['POST'])
    def validate_nginx_config():
        """Validate configuration without applying"""
        try:
            new_settings = request.json
            if not new_settings:
                return {'success': False, 'message': 'No settings provided'}, 400
            
            new_config = manager.generate_config(new_settings)
            is_valid, msg = manager.validate_config(new_config)
            
            return {
                'success': is_valid,
                'message': msg,
                'config': new_config if is_valid else None
            }
        
        except Exception as e:
            logger.error(f"✗ Exception in validate_nginx_config: {e}")
            return {'success': False, 'message': str(e)}, 500
    
    @app.route('/api/nginx/status', methods=['GET'])
    def nginx_status():
        """Check nginx container status"""
        try:
            cmd = ['docker', 'ps', '--filter', f'name={manager.nginx_container}']
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            is_running = manager.nginx_container in result.stdout
            
            return {
                'success': True,
                'container': manager.nginx_container,
                'running': is_running,
                'timestamp': datetime.now().isoformat()
            }
        
        except Exception as e:
            return {'success': False, 'message': str(e)}, 500
    
    logger.info("✓ Nginx configuration API endpoints registered")


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    manager = NginxConfigManager()
    
    # Example: Read and parse current config
    print("\n=== Reading Current Config ===")
    current = manager.read_current_config()
    if current:
        settings = manager.parse_config(current)
        print(json.dumps(settings, indent=2))
    
    # Example: Generate new config
    print("\n=== Generating New Config ===")
    new_settings = {
        'https_enabled': True,
        'ssl_cert_path': '/etc/ssl/certs/server.crt',
        'ssl_key_path': '/etc/ssl/private/server.key',
        'rate_limit_enabled': True,
        'rate_limit_rate': '200r/s',
        'rate_limit_burst': '400',
        'rate_limit_zone_size': '20m',
    }
    new_config = manager.generate_config(new_settings)
    print(new_config[:200] + "...")
    
    # Example: Preview changes
    print("\n=== Previewing Changes ===")
    preview = manager.preview_changes(new_settings)
    print(json.dumps(preview, indent=2))
    
    # Example: Validate (don't apply)
    print("\n=== Validating ===")
    is_valid, msg = manager.validate_config(new_config)
    print(f"Valid: {is_valid}, Message: {msg}")
    
    print("\n✓ All examples completed successfully!")
