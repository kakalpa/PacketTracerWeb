#!/usr/bin/env python3
"""
Environment Configuration Manager (.env file management)
Handles reading, writing, and validating .env configuration for nginx and deployment
"""

import os
import re
import logging
import shutil
import subprocess
from typing import Dict, Any, Tuple, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class EnvConfigManager:
    """Manages .env file configuration for nginx and deployment settings"""
    
    def __init__(self, env_path: Optional[str] = None):
        """
        Initialize the environment config manager
        
        Args:
            env_path: Path to .env file (defaults to project root or /app/.env)
        """
        # Try multiple paths
        possible_paths = [
            env_path or os.environ.get('ENV_PATH'),
            '/app/.env',
            os.path.expanduser('~/.env'),
            os.path.join(os.getcwd(), '.env'),
            '/root/project/.env',
        ]
        
        self.env_path = None
        for path in possible_paths:
            if path and os.path.exists(path):
                self.env_path = path
                logger.info(f"✓ Found .env at: {self.env_path}")
                break
        
        if not self.env_path:
            logger.warning(f"⚠ No .env file found in: {possible_paths}")
            self.env_path = '/app/.env'  # Default fallback
        
        self.backup_dir = os.path.join(os.path.dirname(self.env_path), '.env_backups')
        os.makedirs(self.backup_dir, exist_ok=True)
    
    # ========================================================================
    # READ CONFIGURATION
    # ========================================================================
    
    def read_env_file(self) -> Dict[str, str]:
        """
        Read .env file and return as dictionary
        
        Returns:
            dict: Key-value pairs from .env file
        """
        config = {}
        
        if not os.path.exists(self.env_path):
            logger.warning(f"⚠ .env file not found at {self.env_path}")
            return config
        
        try:
            with open(self.env_path, 'r') as f:
                for line in f:
                    # Skip comments and empty lines
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    # Parse key=value
                    if '=' in line:
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()
            
            logger.info(f"✓ Read {len(config)} settings from {self.env_path}")
            return config
        
        except Exception as e:
            logger.error(f"✗ Error reading .env file: {e}")
            return config
    
    def get_config(self) -> Dict[str, Any]:
        """
        Get structured nginx configuration from .env file
        
        Returns:
            dict: Structured configuration with type conversion
        """
        env_vars = self.read_env_file()
        
        config = {
            # HTTPS Configuration
            'https': {
                'enabled': self._parse_bool(env_vars.get('ENABLE_HTTPS', 'false')),
                'cert_path': env_vars.get('SSL_CERT_PATH', '/etc/ssl/certs/server.crt'),
                'key_path': env_vars.get('SSL_KEY_PATH', '/etc/ssl/private/server.key'),
            },
            
            # GeoIP Configuration
            'geoip': {
                'allow_enabled': self._parse_bool(env_vars.get('NGINX_GEOIP_ALLOW', 'false')),
                'allow_countries': self._parse_countries(env_vars.get('GEOIP_ALLOW_COUNTRIES', '')),
                'block_enabled': self._parse_bool(env_vars.get('NGINX_GEOIP_BLOCK', 'false')),
                'block_countries': self._parse_countries(env_vars.get('GEOIP_BLOCK_COUNTRIES', '')),
            },
            
            # Rate Limiting Configuration
            'rate_limit': {
                'enabled': self._parse_bool(env_vars.get('NGINX_RATE_LIMIT_ENABLE', 'false')),
                'rate': env_vars.get('NGINX_RATE_LIMIT_RATE', '100r/s'),
                'burst': int(env_vars.get('NGINX_RATE_LIMIT_BURST', '200')),
                'zone_size': env_vars.get('NGINX_RATE_LIMIT_ZONE_SIZE', '10m'),
            },
            
            # Production Configuration
            'production': {
                'mode': self._parse_bool(env_vars.get('PRODUCTION_MODE', 'false')),
                'public_ip': env_vars.get('PUBLIC_IP', ''),
            },
        }
        
        logger.info(f"✓ Parsed nginx configuration: {self._sanitize_for_logging(config)}")
        return config
    
    # ========================================================================
    # WRITE CONFIGURATION
    # ========================================================================
    
    def update_config(self, updates: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Update .env file with new configuration
        
        Args:
            updates: Configuration updates in structured format
        
        Returns:
            tuple: (success, message)
        """
        try:
            # Backup current file
            backup_path = self.backup_env()
            if not backup_path:
                return False, "Failed to backup .env file"
            
            # Read current file (preserve comments and structure)
            current_content = self._read_file_raw()
            
            # Update values
            new_content = self._update_env_content(current_content, updates)
            
            # Validate before writing
            validation_ok, validation_msg = self._validate_env_content(new_content)
            if not validation_ok:
                return False, f"Validation failed: {validation_msg}"
            
            # Write new content
            with open(self.env_path, 'w') as f:
                f.write(new_content)
            
            logger.info(f"✓ Updated .env file successfully")
            return True, "Configuration updated successfully"
        
        except Exception as e:
            logger.error(f"✗ Error updating .env file: {e}")
            return False, str(e)
    
    def backup_env(self) -> Optional[str]:
        """
        Create timestamped backup of .env file
        
        Returns:
            str: Path to backup file, or None if failed
        """
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = os.path.join(self.backup_dir, f'.env.backup.{timestamp}')
            shutil.copy2(self.env_path, backup_path)
            logger.info(f"✓ Backed up .env to {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"✗ Error backing up .env: {e}")
            return None
    
    def restore_env(self, backup_path: str) -> Tuple[bool, str]:
        """
        Restore .env from backup
        
        Args:
            backup_path: Path to backup file
        
        Returns:
            tuple: (success, message)
        """
        try:
            if not os.path.exists(backup_path):
                return False, f"Backup file not found: {backup_path}"
            
            shutil.copy2(backup_path, self.env_path)
            logger.info(f"✓ Restored .env from {backup_path}")
            return True, "Configuration restored successfully"
        
        except Exception as e:
            logger.error(f"✗ Error restoring .env: {e}")
            return False, str(e)
    
    # ========================================================================
    # NGINX INTEGRATION
    # ========================================================================
    
    def regenerate_nginx_config(self) -> Tuple[bool, str]:
        """
        Regenerate nginx config from updated .env file
        1. Executes generate-nginx-conf.sh from the mounted project root
        2. The generated config is bind-mounted, so container sees it automatically
        
        Returns:
            tuple: (success, message)
        """
        try:
            logger.info("🔄 Starting nginx config regeneration...")
            
            # The project root is mounted at /project inside the container
            # Or, if running on host, use the .env directory
            project_root = os.environ.get('PROJECT_ROOT', '/project')
            
            # Fallback: try to derive from .env path if not explicitly set
            if not os.path.exists(project_root) or not os.path.isdir(project_root):
                # We're likely running from host, not container
                env_dir = os.path.dirname(os.path.abspath(self.env_path))
                project_root = env_dir
            
            script_path = os.path.join(project_root, 'ptweb-vnc/pt-nginx/generate-nginx-conf.sh')
            
            if not os.path.exists(script_path):
                logger.error(f"✗ Generate script not found at: {script_path}")
                logger.error(f"  Project root: {project_root}")
                logger.error(f"  .env path: {self.env_path}")
                
                # Try alternative locations
                alternatives = [
                    '/project/ptweb-vnc/pt-nginx/generate-nginx-conf.sh',
                    '/root/project/ptweb-vnc/pt-nginx/generate-nginx-conf.sh',
                    os.path.join(os.path.dirname(os.path.dirname(self.env_path)), 'ptweb-vnc/pt-nginx/generate-nginx-conf.sh'),
                ]
                
                for alt_path in alternatives:
                    if os.path.exists(alt_path):
                        logger.info(f"✓ Found script at alternative location: {alt_path}")
                        script_path = alt_path
                        project_root = os.path.dirname(os.path.dirname(os.path.dirname(alt_path)))
                        break
                else:
                    return False, f"Generate script not found. Looked in: {project_root}"
            
            logger.info(f"✓ Found generate script at: {script_path}")
            logger.info(f"  Executing from directory: {project_root}")
            
            try:
                # Execute the script from the project root directory
                cmd = ['bash', script_path]
                result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    logger.info("✓ Nginx config regenerated successfully")
                    logger.info("✓ Configuration will be loaded when nginx container restarts")
                    if result.stdout:
                        logger.debug(f"Script output:\n{result.stdout}")
                    return True, "Nginx config regenerated successfully"
                else:
                    logger.error(f"✗ Script failed with exit code {result.returncode}")
                    logger.error(f"  Error output: {result.stderr}")
                    return False, f"Script failed: {result.stderr or 'No error message'}"
            
            except subprocess.TimeoutExpired:
                logger.error("✗ Script execution timed out (>30s)")
                return False, "Script execution timed out"
            except Exception as e:
                logger.error(f"✗ Error executing script: {e}")
                return False, f"Execution error: {str(e)}"
        
        except Exception as e:
            logger.error(f"✗ Exception in regenerate_nginx_config: {e}")
            return False, f"Error: {str(e)}"
    
    def reload_nginx(self) -> Tuple[bool, str]:
        """
        Reload nginx in container (hot reload)
        
        Returns:
            tuple: (success, message)
        """
        try:
            nginx_container = os.environ.get('NGINX_CONTAINER', 'pt-nginx1')
            
            cmd = ['docker', 'exec', nginx_container, 'nginx', '-s', 'reload']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                logger.info(f"✓ Nginx reloaded successfully in {nginx_container}")
                return True, "Nginx reloaded successfully"
            else:
                logger.error(f"✗ Error reloading nginx: {result.stderr}")
                return False, result.stderr or "Unknown error"
        
        except Exception as e:
            logger.error(f"✗ Exception reloading nginx: {e}")
            return False, str(e)
    
    def restart_nginx_container(self) -> Tuple[bool, str]:
        """
        Restart nginx container to reload config from bind-mounts
        (Required when GeoIP maps or other config changes need to be picked up)
        
        Returns:
            tuple: (success, message)
        """
        try:
            nginx_container = os.environ.get('NGINX_CONTAINER', 'pt-nginx1')
            
            logger.info(f"⏹ Stopping nginx container {nginx_container}...")
            stop_cmd = ['docker', 'restart', nginx_container]
            result = subprocess.run(stop_cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                logger.info(f"✓ Nginx container restarted successfully in {nginx_container}")
                return True, "Nginx container restarted successfully"
            else:
                logger.error(f"✗ Error restarting nginx container: {result.stderr}")
                return False, result.stderr or "Unknown error"
        
        except Exception as e:
            logger.error(f"✗ Exception restarting nginx container: {e}")
            return False, str(e)
    
    def apply_config_changes(self, updates: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Apply configuration changes: update .env, regenerate nginx config, and restart nginx
        
        Args:
            updates: Configuration updates
        
        Returns:
            tuple: (success, message)
        """
        try:
            # Step 1: Update .env
            success, msg = self.update_config(updates)
            if not success:
                return False, f"Failed to update .env: {msg}"
            
            # Step 2: Regenerate nginx config
            success, msg = self.regenerate_nginx_config()
            if not success:
                return False, f"Failed to regenerate nginx config: {msg}"
            
            # Step 3: Restart nginx container to pick up config changes from bind-mounts
            # (Required for GeoIP maps and other static config changes)
            success, msg = self.restart_nginx_container()
            if not success:
                logger.warning(f"⚠ Failed to restart nginx container, attempting hot reload instead: {msg}")
                # Fallback to hot reload if restart fails
                success, msg = self.reload_nginx()
                if not success:
                    return False, f"Failed to reload nginx: {msg}"
            
            logger.info("✓ All configuration changes applied successfully")
            return True, "Configuration changes applied successfully"
        
        except Exception as e:
            logger.error(f"✗ Exception applying config changes: {e}")
            return False, str(e)
    
    # ========================================================================
    # PREVIEW & VALIDATION
    # ========================================================================
    
    def preview_changes(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Preview what would change
        
        Args:
            updates: Configuration updates
        
        Returns:
            dict: Preview information
        """
        try:
            current_config = self.get_config()
            
            changes = {
                'https': self._diff_sections(current_config['https'], updates.get('https', {})),
                'geoip': self._diff_sections(current_config['geoip'], updates.get('geoip', {})),
                'rate_limit': self._diff_sections(current_config['rate_limit'], updates.get('rate_limit', {})),
                'production': self._diff_sections(current_config['production'], updates.get('production', {})),
            }
            
            # Count total changes
            total_changes = sum(len(v) for v in changes.values() if v)
            
            return {
                'changes': changes,
                'total_changes': total_changes,
                'message': f"{total_changes} setting(s) will change",
                'can_apply': total_changes > 0,
            }
        
        except Exception as e:
            logger.error(f"✗ Exception previewing changes: {e}")
            return {'error': str(e)}
    
    def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate configuration
        
        Args:
            config: Configuration to validate
        
        Returns:
            tuple: (is_valid, message)
        """
        try:
            # Validate HTTPS settings
            if config.get('https', {}).get('enabled'):
                if not config.get('https', {}).get('cert_path'):
                    return False, "HTTPS enabled but no certificate path provided"
                if not config.get('https', {}).get('key_path'):
                    return False, "HTTPS enabled but no key path provided"
            
            # Validate rate limit settings
            if config.get('rate_limit', {}).get('enabled'):
                rate = config.get('rate_limit', {}).get('rate', '')
                if not re.match(r'^\d+r/[smh]$', rate):
                    return False, f"Invalid rate format: {rate} (use format like 100r/s or 10r/m)"
                
                burst = config.get('rate_limit', {}).get('burst', 0)
                if not isinstance(burst, int) or burst <= 0:
                    return False, f"Invalid burst value: {burst}"
            
            # Validate GeoIP settings
            if config.get('geoip', {}).get('allow_enabled'):
                if not config.get('geoip', {}).get('allow_countries'):
                    return False, "GeoIP ALLOW enabled but no countries specified"
            
            if config.get('geoip', {}).get('block_enabled'):
                if not config.get('geoip', {}).get('block_countries'):
                    return False, "GeoIP BLOCK enabled but no countries specified"
            
            logger.info("✓ Configuration validation passed")
            return True, "Configuration is valid"
        
        except Exception as e:
            logger.error(f"✗ Exception validating config: {e}")
            return False, str(e)
    
    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    
    def _read_file_raw(self) -> str:
        """Read raw .env file content preserving comments"""
        try:
            with open(self.env_path, 'r') as f:
                return f.read()
        except Exception as e:
            logger.error(f"✗ Error reading .env file: {e}")
            return ""
    
    def _update_env_content(self, content: str, updates: Dict[str, Any]) -> str:
        """Update .env file content preserving structure"""
        lines = content.split('\n')
        updated_lines = []
        updated_keys = set()
        
        # Mapping of config keys to .env variable names
        key_mapping = {
            ('https', 'enabled'): 'ENABLE_HTTPS',
            ('https', 'cert_path'): 'SSL_CERT_PATH',
            ('https', 'key_path'): 'SSL_KEY_PATH',
            ('geoip', 'allow_enabled'): 'NGINX_GEOIP_ALLOW',
            ('geoip', 'allow_countries'): 'GEOIP_ALLOW_COUNTRIES',
            ('geoip', 'block_enabled'): 'NGINX_GEOIP_BLOCK',
            ('geoip', 'block_countries'): 'GEOIP_BLOCK_COUNTRIES',
            ('rate_limit', 'enabled'): 'NGINX_RATE_LIMIT_ENABLE',
            ('rate_limit', 'rate'): 'NGINX_RATE_LIMIT_RATE',
            ('rate_limit', 'burst'): 'NGINX_RATE_LIMIT_BURST',
            ('rate_limit', 'zone_size'): 'NGINX_RATE_LIMIT_ZONE_SIZE',
            ('production', 'mode'): 'PRODUCTION_MODE',
            ('production', 'public_ip'): 'PUBLIC_IP',
        }
        
        for line in lines:
            updated_line = line
            
            # Check each potential update
            for (section, key), env_var in key_mapping.items():
                if section in updates and key in updates[section]:
                    pattern = rf'^{env_var}='
                    if re.match(pattern, line):
                        value = updates[section][key]
                        
                        # Handle different value types
                        if isinstance(value, bool):
                            value = 'true' if value else 'false'
                        elif isinstance(value, list):
                            # Countries list - convert to comma-separated string
                            value = ','.join(str(v) for v in value if v)
                        elif isinstance(value, int):
                            value = str(value)
                        
                        updated_line = f"{env_var}={value}"
                        updated_keys.add(env_var)
                        break
            
            updated_lines.append(updated_line)
        
        return '\n'.join(updated_lines)
    
    def _validate_env_content(self, content: str) -> Tuple[bool, str]:
        """Validate .env file content"""
        # Basic validation - check for syntax errors
        for line in content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                return False, f"Invalid line format: {line}"
        
        return True, "Content validation passed"
    
    def _parse_bool(self, value: str) -> bool:
        """Parse boolean value from string"""
        return value.lower() in ('true', '1', 'yes', 'on')
    
    def _parse_countries(self, value: str) -> list:
        """Parse comma-separated country codes"""
        if not value:
            return []
        return [c.strip().upper() for c in value.split(',') if c.strip()]
    
    def _diff_sections(self, current: Dict, updates: Dict) -> Dict:
        """Get differences between current and updated config"""
        changes = {}
        for key in set(list(current.keys()) + list(updates.keys())):
            if current.get(key) != updates.get(key):
                changes[key] = {
                    'from': current.get(key),
                    'to': updates.get(key),
                }
        return changes
    
    def _sanitize_for_logging(self, config: Dict) -> Dict:
        """Remove sensitive data from config for logging"""
        sanitized = {}
        for key, value in config.items():
            if isinstance(value, dict):
                sanitized[key] = {k: '***' if 'path' in k.lower() else v 
                                 for k, v in value.items()}
            else:
                sanitized[key] = value
        return sanitized
