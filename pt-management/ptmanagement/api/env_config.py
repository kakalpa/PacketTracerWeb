#!/usr/bin/env python3
"""
Environment Configuration Manager (.env file management)
Handles reading, writing, and validating .env configuration for nginx and deployment
"""

import os
import posixpath
import re
import fcntl
import logging
import shutil
import subprocess
from typing import Dict, Any, Tuple, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

ENV_LOCK_PATH = '/tmp/pt_env.lock'
FORBIDDEN_ENV_CHARS = set("\r\n`$;|&'\"<>()\\#*?[]{}")
STRICT_FQDN_RE = re.compile(
    r'^(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$'
)
EMAIL_RE = re.compile(
    r'^[^@\s;\'"`$&|<>]+@[^@\s;\'"`$&|<>]+\.[^@\s;\'"`$&|<>]+$'
)
_ENV_KEY_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_SERVER_NAME_TOKEN_RE = re.compile(r'^[A-Za-z0-9._*-]+$')
_DNS_LABEL_RE = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$')

ALLOWED_TLS_MODES = ('self-signed', 'manual', 'certbot')
ALLOWED_CHALLENGE_TYPES = ('http-01', 'dns-01')

_ENV_LINE_FORBIDDEN_NO_STAR = set("\r\n`$;|&'\"<>()\\#?[]{}")
_RATE_RE = re.compile(r'^[1-9]\d*r/[smh]\Z')
_ZONE_SIZE_RE = re.compile(r'^[1-9]\d*[kKmMgG]\Z')
_WEBROOT_RE = re.compile(r'^/[A-Za-z0-9._/-]+\Z')
_TRUE_STRINGS = frozenset({'true', '1', 'yes', 'on'})
_FALSE_STRINGS = frozenset({'false', '0', 'no', 'off'})
_BOOL_ENV_KEYS = frozenset({
    'ENABLE_HTTPS',
    'NGINX_GEOIP_ALLOW',
    'NGINX_GEOIP_BLOCK',
    'NGINX_RATE_LIMIT_ENABLE',
    'PRODUCTION_MODE',
    'CERTBOT_ENABLED',
    'CERTBOT_STAGING',
    'CERTBOT_AUTO_RENEW',
})
_NON_BOOL_STRING_KEYS = frozenset({
    'SSL_CERT_PATH',
    'SSL_KEY_PATH',
    'PUBLIC_IP',
    'CERTBOT_DOMAIN',
    'CERTBOT_EMAIL',
    'CERTBOT_WEBROOT',
    'TLS_MODE',
    'CERTBOT_CHALLENGE_TYPE',
    'SERVER_NAME',
    'NGINX_RATE_LIMIT_RATE',
    'NGINX_RATE_LIMIT_ZONE_SIZE',
})


def _coerce_strict_bool(value: Any) -> Tuple[bool, Optional[bool]]:
    """Parse strict boolean (native bool or recognized boolean string)."""
    if isinstance(value, bool):
        return True, value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUE_STRINGS:
            return True, True
        if lowered in _FALSE_STRINGS:
            return True, False
    return False, None


def validate_certbot_webroot(value: Any) -> Tuple[bool, str, str]:
    """Validate CERTBOT_WEBROOT path (aligned with generate-nginx-conf.sh:90)."""
    if isinstance(value, bool) or not isinstance(value, str):
        return False, f"Invalid certbot.webroot: {value}", ""
    wr = value.strip()
    if not wr or '..' in wr or not _WEBROOT_RE.match(wr):
        return False, f"Invalid certbot.webroot: {wr}", ""
    if '//' in wr or wr == '/.' or '/./' in wr or wr.endswith('/.'):
        return False, f"Invalid certbot.webroot: {wr}", ""
    norm = posixpath.normpath(wr)
    if not norm.startswith('/') or norm == '/' or '..' in norm.split('/'):
        return False, f"Invalid certbot.webroot: {wr}", ""
    return True, "OK", norm


def validate_server_name(value: str) -> Tuple[bool, str, str]:
    """
    Validate and normalize SERVER_NAME (single or space/comma-separated hostnames).

    Returns:
        Tuple (is_valid, message, space_joined_normalized_value)
    """
    if value is None:
        return True, "OK", ""
    if not isinstance(value, str):
        return False, "SERVER_NAME must be a string", ""

    stripped = value.strip()
    if not stripped:
        return True, "OK", ""

    if any(c in stripped for c in ("\r", "\n", "`", "$", ";", "|", "&", "'", '"', "<", ">", "(", ")", "\\", "#", "?", "[", "]", "{", "}")):
        return False, "SERVER_NAME contains forbidden characters", ""

    tokens = [t for t in re.split(r'[,\s]+', stripped) if t]
    if not tokens:
        return True, "OK", ""

    for token in tokens:
        if len(token) > 253:
            return False, f"Hostname exceeds 253 characters: {token}", ""
        if not _SERVER_NAME_TOKEN_RE.match(token):
            return False, f"Invalid characters in hostname token: {token}", ""
        if token.startswith('-') or token.endswith('-') or token.startswith('.') or token.endswith('.') or '..' in token:
            return False, f"Malformed hostname token: {token}", ""
        if token.lower() == 'localhost':
            continue
        if '*' in token:
            if not token.startswith('*.') or '*' in token[2:] or not STRICT_FQDN_RE.match(token[2:]):
                return False, f"Invalid wildcard hostname token: {token}", ""
            continue
        if '.' not in token:
            return False, f"Single-label non-localhost token is not permitted: {token}", ""
        labels = token.split('.')
        if not all(_DNS_LABEL_RE.match(lbl) for lbl in labels):
            return False, f"Invalid DNS label in hostname: {token}", ""

    return True, "OK", " ".join(tokens)


def validate_env_value(key: str, raw_val: Any) -> Tuple[bool, str, str]:
    """
    Validate and format a single .env value safely for bash source & key-value parsers.

    Returns:
        Tuple (is_valid, message, formatted_env_value)
    """
    if isinstance(raw_val, bool):
        if key == 'NGINX_RATE_LIMIT_BURST':
            return False, "NGINX_RATE_LIMIT_BURST must be a positive integer", ""
        if key in _NON_BOOL_STRING_KEYS:
            return False, f"{key} must be a string, not a boolean", ""
        if key in ('GEOIP_ALLOW_COUNTRIES', 'GEOIP_BLOCK_COUNTRIES', 'CERTBOT_EXTRA_DOMAINS'):
            return False, f"{key} must be a list or comma-separated string, not a boolean", ""
        val_str = 'true' if raw_val else 'false'
    elif isinstance(raw_val, list):
        if key in ('GEOIP_ALLOW_COUNTRIES', 'GEOIP_BLOCK_COUNTRIES'):
            cleaned_items = []
            for item in raw_val:
                if not isinstance(item, str):
                    return False, f"{key} entries must be strings", ""
                c = item.strip().upper()
                if not re.fullmatch(r'[A-Z0-9]{2}', c):
                    return False, f"Invalid country code in {key}: {item!r}", ""
                cleaned_items.append(c)
            val_str = ','.join(cleaned_items)
        else:
            val_str = ','.join(str(v).strip() for v in raw_val if str(v).strip())
    elif isinstance(raw_val, int):
        if key in ('GEOIP_ALLOW_COUNTRIES', 'GEOIP_BLOCK_COUNTRIES'):
            return False, f"{key} must be a list or comma-separated string, not an integer", ""
        val_str = str(raw_val)
    elif raw_val is None:
        val_str = ''
    else:
        val_str = str(raw_val).strip()

    if key in _BOOL_ENV_KEYS and val_str != '':
        ok_bool, parsed_bool = _coerce_strict_bool(raw_val)
        if not ok_bool:
            return False, f"Invalid boolean value for {key}: {raw_val}", ""
        return True, "OK", ('true' if parsed_bool else 'false')

    if key == 'SERVER_NAME':
        ok, msg, normalized = validate_server_name(val_str)
        if not ok:
            return False, msg, ""
        if ' ' in normalized:
            return True, "OK", f'"{normalized}"'
        return True, "OK", normalized

    if key in ('GEOIP_ALLOW_COUNTRIES', 'GEOIP_BLOCK_COUNTRIES', 'CERTBOT_EXTRA_DOMAINS'):
        items = [p.strip() for p in val_str.split(',') if p.strip()]
        cleaned = ','.join(items)
        if any(c in FORBIDDEN_ENV_CHARS for c in cleaned) or any(c.isspace() for c in cleaned):
            return False, f"Forbidden characters or whitespace in {key}", ""
        if key == 'CERTBOT_EXTRA_DOMAINS':
            seen = set()
            deduped = []
            for item in items:
                lowered = item.lower()
                if not STRICT_FQDN_RE.match(lowered):
                    return False, f"Invalid FQDN in CERTBOT_EXTRA_DOMAINS: {item}", ""
                if lowered not in seen:
                    seen.add(lowered)
                    deduped.append(lowered)
            cleaned = ','.join(deduped)
        return True, "OK", cleaned

    if any(c in FORBIDDEN_ENV_CHARS for c in val_str):
        return False, f"Value for {key} contains forbidden shell metacharacters", ""
    if any(c.isspace() for c in val_str):
        return False, f"Value for {key} cannot contain unquoted whitespace", ""

    if key == 'TLS_MODE' and val_str and val_str not in ALLOWED_TLS_MODES:
        return False, f"Invalid TLS_MODE: {val_str}", ""
    if key == 'CERTBOT_CHALLENGE_TYPE' and val_str and val_str not in ALLOWED_CHALLENGE_TYPES:
        return False, f"Invalid CERTBOT_CHALLENGE_TYPE: {val_str}", ""
    if key == 'CERTBOT_DOMAIN' and val_str and not STRICT_FQDN_RE.match(val_str):
        return False, f"Invalid FQDN for CERTBOT_DOMAIN: {val_str}", ""
    if key == 'CERTBOT_EMAIL' and val_str and (len(val_str) > 254 or not EMAIL_RE.match(val_str)):
        return False, f"Invalid email for CERTBOT_EMAIL: {val_str}", ""
    if key == 'CERTBOT_WEBROOT' and raw_val is not None and raw_val != '':
        ok, msg, wr = validate_certbot_webroot(val_str)
        if not ok:
            return False, msg, ""
        val_str = wr
    if key == 'NGINX_RATE_LIMIT_BURST' and val_str:
        if not (re.fullmatch(r'[0-9]+', val_str) and int(val_str) > 0):
            return False, f"Invalid NGINX_RATE_LIMIT_BURST: {val_str}", ""
    if key == 'NGINX_RATE_LIMIT_RATE' and val_str:
        if not _RATE_RE.match(val_str):
            return False, f"Invalid NGINX_RATE_LIMIT_RATE: {val_str}", ""
    if key == 'NGINX_RATE_LIMIT_ZONE_SIZE' and val_str:
        if not _ZONE_SIZE_RE.match(val_str):
            return False, f"Invalid NGINX_RATE_LIMIT_ZONE_SIZE: {val_str}", ""

    return True, "OK", val_str


class EnvConfigManager:
    """Manages .env file configuration for nginx and deployment settings"""

    KEY_MAPPING = {
        ('https', 'enabled'): 'ENABLE_HTTPS',
        ('https', 'cert_path'): 'SSL_CERT_PATH',
        ('https', 'key_path'): 'SSL_KEY_PATH',
        ('https', 'tls_mode'): 'TLS_MODE',
        ('https', 'server_name'): 'SERVER_NAME',
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
        ('certbot', 'enabled'): 'CERTBOT_ENABLED',
        ('certbot', 'domain'): 'CERTBOT_DOMAIN',
        ('certbot', 'extra_domains'): 'CERTBOT_EXTRA_DOMAINS',
        ('certbot', 'email'): 'CERTBOT_EMAIL',
        ('certbot', 'challenge_type'): 'CERTBOT_CHALLENGE_TYPE',
        ('certbot', 'staging'): 'CERTBOT_STAGING',
        ('certbot', 'auto_renew'): 'CERTBOT_AUTO_RENEW',
        ('certbot', 'webroot'): 'CERTBOT_WEBROOT',
    }

    def __init__(
        self,
        env_path: Optional[str] = None,
        backup_dir: Optional[str] = None,
        lock_path: Optional[str] = None,
    ):
        """
        Initialize the environment config manager

        Args:
            env_path: Path to .env file (defaults to project root or /app/.env)
            backup_dir: Directory for .env backups
            lock_path: Lock file path for fcntl.flock serialization
        """
        if env_path:
            self.env_path = env_path
        else:
            possible_paths = [
                os.environ.get('ENV_PATH'),
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
                self.env_path = os.environ.get('ENV_PATH') or '/app/.env'

        self.backup_dir = backup_dir or os.path.join(
            os.path.dirname(os.path.abspath(self.env_path)), '.env_backups'
        )
        self.lock_path = lock_path or os.environ.get('ENV_LOCK_PATH') or ENV_LOCK_PATH

        try:
            os.makedirs(self.backup_dir, exist_ok=True)
        except OSError as e:
            logger.warning(f"⚠ Could not create .env backup directory {self.backup_dir}: {e}")
    
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
                        key = key.strip()
                        val = value.strip()
                        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                            val = val[1:-1]
                        if key:
                            config[key] = val
            
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
                'cert_path': env_vars.get('SSL_CERT_PATH', '/etc/ssl/ptweb/server.crt') or '/etc/ssl/ptweb/server.crt',
                'key_path': env_vars.get('SSL_KEY_PATH', '/etc/ssl/ptweb/server.key') or '/etc/ssl/ptweb/server.key',
                'tls_mode': env_vars.get('TLS_MODE', 'self-signed') or 'self-signed',
                'server_name': env_vars.get('SERVER_NAME', '') or 'localhost',
            },

            # Certbot Configuration
            'certbot': {
                'enabled': self._parse_bool(env_vars.get('CERTBOT_ENABLED', 'false')),
                'domain': env_vars.get('CERTBOT_DOMAIN', ''),
                'extra_domains': env_vars.get('CERTBOT_EXTRA_DOMAINS', ''),
                'email': env_vars.get('CERTBOT_EMAIL', ''),
                'challenge_type': env_vars.get('CERTBOT_CHALLENGE_TYPE', 'http-01') or 'http-01',
                'staging': self._parse_bool(env_vars.get('CERTBOT_STAGING', 'false')),
                'auto_renew': self._parse_bool(env_vars.get('CERTBOT_AUTO_RENEW', 'true')),
                'webroot': env_vars.get('CERTBOT_WEBROOT', '/var/www/certbot') or '/var/www/certbot',
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
                'rate': env_vars.get('NGINX_RATE_LIMIT_RATE', '100r/s') or '100r/s',
                'burst': self._parse_positive_int(env_vars.get('NGINX_RATE_LIMIT_BURST', '200'), default=200),
                'zone_size': env_vars.get('NGINX_RATE_LIMIT_ZONE_SIZE', '10m') or '10m',
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
    
    def _flatten_updates(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Convert nested config dict into flat .env key-value updates."""
        flat: Dict[str, Any] = {}
        for (section, key), env_var in self.KEY_MAPPING.items():
            if section in updates and isinstance(updates[section], dict) and key in updates[section]:
                flat[env_var] = updates[section][key]
        return flat

    def update_env_vars(self, raw_updates: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Atomically update flat .env variables in-place while preserving file inode.
        Protected by fcntl.flock across concurrent Gunicorn workers.
        """
        if not isinstance(raw_updates, dict):
            return False, "Updates must be a dictionary"

        try:
            lock_dir = os.path.dirname(os.path.abspath(self.lock_path))
            if lock_dir:
                os.makedirs(lock_dir, exist_ok=True)
            with open(self.lock_path, 'a+') as lock_f:
                fcntl.flock(lock_f, fcntl.LOCK_EX)
                try:
                    if os.path.exists(self.env_path):
                        backup_path = self.backup_env()
                        if not backup_path:
                            return False, "Failed to backup .env file"
                        current_content = self._read_file_raw()
                    else:
                        env_dir = os.path.dirname(os.path.abspath(self.env_path))
                        if env_dir:
                            os.makedirs(env_dir, exist_ok=True)
                        current_content = ""

                    new_content = self._update_env_content_flat(current_content, raw_updates)

                    validation_ok, validation_msg = self._validate_env_content(new_content)
                    if not validation_ok:
                        return False, f"Validation failed: {validation_msg}"

                    # Preserve single-file Docker bind-mount inode via in-place write
                    with open(self.env_path, 'w') as f:
                        f.write(new_content)

                    logger.info("✓ Updated .env file successfully")
                    return True, "Configuration updated successfully"
                finally:
                    fcntl.flock(lock_f, fcntl.LOCK_UN)
        except ValueError as e:
            logger.warning(f"✗ Invalid .env value: {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"✗ Error updating .env file: {e}")
            return False, str(e)

    def update_config(self, updates: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Update .env file with new configuration
        
        Args:
            updates: Configuration updates in structured format
        
        Returns:
            tuple: (success, message)
        """
        if not isinstance(updates, dict):
            return False, "Updates must be a dictionary"
        flat_updates = self._flatten_updates(updates)
        return self.update_env_vars(flat_updates)
    
    def backup_env(self) -> Optional[str]:
        """
        Create timestamped backup of .env file
        
        Returns:
            str: Path to backup file, or None if failed
        """
        try:
            if not os.path.exists(self.env_path):
                return None
            os.makedirs(self.backup_dir, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = os.path.join(self.backup_dir, f'.env.backup.{timestamp}')
            if os.path.exists(backup_path):
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
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
            resolved = Path(backup_path).resolve()
            backup_root = Path(self.backup_dir).resolve()
            try:
                resolved.relative_to(backup_root)
            except ValueError:
                return False, "Invalid backup path (security check failed)"

            if resolved == backup_root or not resolved.exists() or not resolved.is_file():
                return False, f"Backup file not found: {backup_path}"

            with open(resolved, 'r', newline='') as src:
                content = src.read()

            validation_ok, validation_msg = self._validate_env_content(content)
            if not validation_ok:
                return False, f"Backup validation failed: {validation_msg}"

            lock_dir = os.path.dirname(os.path.abspath(self.lock_path))
            if lock_dir:
                os.makedirs(lock_dir, exist_ok=True)
            with open(self.lock_path, 'a+') as lock_f:
                fcntl.flock(lock_f, fcntl.LOCK_EX)
                try:
                    with open(self.env_path, 'w') as dst:
                        dst.write(content)
                finally:
                    fcntl.flock(lock_f, fcntl.LOCK_UN)

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
        Validate Nginx configuration with `nginx -t` and hot-reload inside container.
        Never restarts the container on syntax error.
        
        Returns:
            tuple: (success, message)
        """
        try:
            nginx_container = os.environ.get('NGINX_CONTAINER', 'pt-nginx1')

            test_cmd = ['docker', 'exec', nginx_container, 'nginx', '-t']
            test_result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=10)
            if test_result.returncode != 0:
                err = (test_result.stderr or test_result.stdout or "Unknown nginx -t error").strip()
                logger.error(f"✗ nginx -t failed in {nginx_container}: {err}")
                return False, f"nginx -t failed: {err}"

            cmd = ['docker', 'exec', nginx_container, 'nginx', '-s', 'reload']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                logger.info(f"✓ Nginx reloaded successfully in {nginx_container}")
                return True, "Nginx reloaded successfully"
            else:
                err = (result.stderr or result.stdout or "Unknown error").strip()
                logger.error(f"✗ Error reloading nginx: {err}")
                return False, err
        
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
    
    def _resolve_project_root(self) -> str:
        """Resolve project root directory containing ptweb-vnc/pt-nginx/."""
        project_root = os.environ.get('PROJECT_ROOT', '/project')
        if not os.path.exists(project_root) or not os.path.isdir(project_root):
            project_root = os.path.dirname(os.path.abspath(self.env_path))
        script_path = os.path.join(project_root, 'ptweb-vnc/pt-nginx/generate-nginx-conf.sh')
        if not os.path.exists(script_path):
            alternatives = [
                '/project/ptweb-vnc/pt-nginx/generate-nginx-conf.sh',
                '/root/project/ptweb-vnc/pt-nginx/generate-nginx-conf.sh',
                os.path.join(os.path.dirname(os.path.dirname(self.env_path)), 'ptweb-vnc/pt-nginx/generate-nginx-conf.sh'),
            ]
            for alt_path in alternatives:
                if os.path.exists(alt_path):
                    project_root = os.path.dirname(os.path.dirname(os.path.dirname(alt_path)))
                    break
        return project_root

    def snapshot_state(self) -> Dict[str, Any]:
        """Snapshot .env and generated Nginx configs in memory for atomic in-place rollback."""
        project_root = self._resolve_project_root()
        nginx_conf_path = os.path.join(project_root, 'ptweb-vnc', 'pt-nginx', 'nginx.conf')
        ptweb_conf_path = os.path.join(project_root, 'ptweb-vnc', 'pt-nginx', 'conf', 'ptweb.conf')

        env_exists = os.path.exists(self.env_path)
        env_content = self._read_file_raw() if env_exists else ''

        def _snap_file(path: str) -> Tuple[bool, str]:
            if os.path.isfile(path):
                try:
                    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
                        return True, fh.read()
                except OSError:
                    return False, ''
            return False, ''

        nginx_exists, nginx_content = _snap_file(nginx_conf_path)
        ptweb_exists, ptweb_content = _snap_file(ptweb_conf_path)
        return {
            'env_exists': env_exists,
            'env_content': env_content,
            'nginx_conf_path': nginx_conf_path,
            'nginx_conf_exists': nginx_exists,
            'nginx_conf_content': nginx_content,
            'ptweb_conf_path': ptweb_conf_path,
            'ptweb_conf_exists': ptweb_exists,
            'ptweb_conf_content': ptweb_content,
        }

    def rollback_state(self, snapshot: Dict[str, Any]) -> Tuple[bool, str]:
        """Restore .env and Nginx config files in-place (preserving bind-mount inodes)."""
        if not snapshot:
            return False, "No snapshot available for rollback"
        try:
            lock_dir = os.path.dirname(os.path.abspath(self.lock_path))
            if lock_dir:
                os.makedirs(lock_dir, exist_ok=True)
            with open(self.lock_path, 'a+') as lock_f:
                fcntl.flock(lock_f, fcntl.LOCK_EX)
                try:
                    if snapshot.get('env_exists'):
                        with open(self.env_path, 'w') as dst:
                            dst.write(snapshot.get('env_content', ''))
                    elif os.path.exists(self.env_path):
                        os.unlink(self.env_path)
                finally:
                    fcntl.flock(lock_f, fcntl.LOCK_UN)

            for exists_key, path_key, content_key in (
                ('nginx_conf_exists', 'nginx_conf_path', 'nginx_conf_content'),
                ('ptweb_conf_exists', 'ptweb_conf_path', 'ptweb_conf_content'),
            ):
                target_path = snapshot.get(path_key)
                if not target_path:
                    continue
                if snapshot.get(exists_key):
                    with open(target_path, 'w', encoding='utf-8') as dst:
                        dst.write(snapshot.get(content_key, ''))
                elif os.path.exists(target_path):
                    os.unlink(target_path)

            logger.info("✓ Rolled back .env and Nginx configuration in-place")
            return True, "Rolled back .env and Nginx configuration"
        except Exception as e:
            logger.error(f"✗ Error during rollback_state: {e}")
            return False, str(e)

    def apply_config_changes(self, updates: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Apply configuration changes: update .env, regenerate nginx config, and reload nginx.
        Atomically rolls back .env and Nginx config in-place if regeneration or reload fails.
        """
        snapshot: Optional[Dict[str, Any]] = None
        try:
            snapshot = self.snapshot_state()

            # Step 1: Update .env
            success, msg = self.update_config(updates)
            if not success:
                return False, f"Failed to update .env: {msg}"

            # Step 2: Regenerate nginx config
            success, msg = self.regenerate_nginx_config()
            if not success:
                self.rollback_state(snapshot)
                return False, f"Failed to regenerate nginx config (rolled back .env): {msg}"

            # Step 3: Validated hot reload (never restart container on config error)
            success, msg = self.reload_nginx()
            if not success:
                self.rollback_state(snapshot)
                return False, f"Failed to reload nginx (rolled back .env): {msg}"

            logger.info("✓ All configuration changes applied successfully")
            return True, "Configuration changes applied successfully"

        except Exception as e:
            if snapshot is not None:
                self.rollback_state(snapshot)
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
            if not isinstance(updates, dict):
                return {'error': 'Updates must be a JSON object'}
            for sec in ('https', 'geoip', 'rate_limit', 'production', 'certbot'):
                if sec in updates and updates[sec] is not None and not isinstance(updates[sec], dict):
                    return {'error': f"Section '{sec}' must be a JSON object"}

            current_config = self.get_config()
            
            changes = {
                'https': self._diff_sections(current_config['https'], updates.get('https')) if 'https' in updates else {},
                'geoip': self._diff_sections(current_config['geoip'], updates.get('geoip')) if 'geoip' in updates else {},
                'rate_limit': self._diff_sections(current_config['rate_limit'], updates.get('rate_limit')) if 'rate_limit' in updates else {},
                'production': self._diff_sections(current_config['production'], updates.get('production')) if 'production' in updates else {},
                'certbot': self._diff_sections(current_config['certbot'], updates.get('certbot')) if 'certbot' in updates else {},
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
            if not isinstance(config, dict):
                return False, "Configuration must be a JSON object"

            for sec in ('https', 'certbot', 'geoip', 'rate_limit', 'production'):
                if sec in config and config[sec] is not None and not isinstance(config[sec], dict):
                    return False, f"Section '{sec}' must be a JSON object"

            https_cfg = config.get('https') or {}
            certbot_cfg = config.get('certbot') or {}
            rate_limit_cfg = config.get('rate_limit') or {}
            geoip_cfg = config.get('geoip') or {}
            prod_cfg = config.get('production') or {}

            # Validate boolean fields strictly before using them in conditional checks
            bool_checks = [
                (https_cfg, 'https', 'enabled'),
                (certbot_cfg, 'certbot', 'enabled'),
                (certbot_cfg, 'certbot', 'staging'),
                (certbot_cfg, 'certbot', 'auto_renew'),
                (geoip_cfg, 'geoip', 'allow_enabled'),
                (geoip_cfg, 'geoip', 'block_enabled'),
                (rate_limit_cfg, 'rate_limit', 'enabled'),
                (prod_cfg, 'production', 'mode'),
            ]
            parsed_bools: Dict[Tuple[str, str], bool] = {}
            for sec_dict, sec_name, field_name in bool_checks:
                if field_name in sec_dict and sec_dict[field_name] is not None:
                    ok_b, parsed_b = _coerce_strict_bool(sec_dict[field_name])
                    if not ok_b:
                        return False, f"Invalid boolean value for {sec_name}.{field_name}"
                    parsed_bools[(sec_name, field_name)] = bool(parsed_b)

            # Validate HTTPS settings (strip before checking non-empty)
            for path_key in ('cert_path', 'key_path'):
                if path_key in https_cfg and https_cfg[path_key] is not None:
                    if not isinstance(https_cfg[path_key], str):
                        return False, f"Invalid characters in https.{path_key}"
                    val_str = https_cfg[path_key].strip()
                    if any(c in FORBIDDEN_ENV_CHARS for c in val_str) or any(c.isspace() for c in val_str):
                        return False, f"Invalid characters in https.{path_key}"

            https_enabled = parsed_bools.get(('https', 'enabled'), False)
            if https_enabled:
                cert_raw = https_cfg.get('cert_path')
                key_raw = https_cfg.get('key_path')
                if not isinstance(cert_raw, str) or not cert_raw.strip():
                    return False, "HTTPS enabled but no certificate path provided"
                if not isinstance(key_raw, str) or not key_raw.strip():
                    return False, "HTTPS enabled but no key path provided"

            if 'tls_mode' in https_cfg and https_cfg['tls_mode'] is not None:
                if not isinstance(https_cfg['tls_mode'], str) or https_cfg['tls_mode'] not in ALLOWED_TLS_MODES:
                    return False, f"Invalid tls_mode: {https_cfg['tls_mode']}"

            if 'server_name' in https_cfg and https_cfg['server_name'] is not None:
                if not isinstance(https_cfg['server_name'], str):
                    return False, "https.server_name must be a string"
                ok, msg, _ = validate_server_name(https_cfg['server_name'])
                if not ok:
                    return False, msg

            # Validate Certbot settings if provided
            if 'domain' in certbot_cfg and certbot_cfg['domain']:
                if not isinstance(certbot_cfg['domain'], str):
                    return False, "certbot.domain must be a string"
                dom = certbot_cfg['domain'].strip()
                if not STRICT_FQDN_RE.match(dom):
                    return False, f"Invalid FQDN for certbot.domain: {dom}"

            if 'extra_domains' in certbot_cfg and certbot_cfg['extra_domains']:
                ok, msg, _ = validate_env_value('CERTBOT_EXTRA_DOMAINS', certbot_cfg['extra_domains'])
                if not ok:
                    return False, msg

            if 'email' in certbot_cfg and certbot_cfg['email']:
                if not isinstance(certbot_cfg['email'], str):
                    return False, "certbot.email must be a string"
                email = certbot_cfg['email'].strip()
                if len(email) > 254 or not EMAIL_RE.match(email):
                    return False, f"Invalid email for certbot.email: {email}"

            if 'challenge_type' in certbot_cfg and certbot_cfg['challenge_type']:
                if not isinstance(certbot_cfg['challenge_type'], str) or certbot_cfg['challenge_type'] not in ALLOWED_CHALLENGE_TYPES:
                    return False, f"Invalid certbot.challenge_type: {certbot_cfg['challenge_type']}"

            if 'webroot' in certbot_cfg and certbot_cfg['webroot'] is not None:
                if isinstance(certbot_cfg['webroot'], str) and certbot_cfg['webroot'] == '':
                    pass
                else:
                    ok, msg, _ = validate_certbot_webroot(certbot_cfg['webroot'])
                    if not ok:
                        return False, msg

            # Validate rate limit settings (always validate provided fields, even when disabled)
            rl_enabled = parsed_bools.get(('rate_limit', 'enabled'), False)
            if rl_enabled:
                if 'rate' not in rate_limit_cfg or rate_limit_cfg['rate'] is None or str(rate_limit_cfg['rate']).strip() == '':
                    return False, "Invalid rate format:  (use format like 100r/s or 10r/m)"
                if 'burst' not in rate_limit_cfg or rate_limit_cfg['burst'] is None:
                    return False, "Invalid burst value: None"

            if 'rate' in rate_limit_cfg:
                rate = rate_limit_cfg['rate']
                if isinstance(rate, bool) or not isinstance(rate, str) or not _RATE_RE.match(rate.strip()):
                    return False, f"Invalid rate format: {rate} (use format like 100r/s or 10r/m)"

            if 'burst' in rate_limit_cfg:
                burst = rate_limit_cfg['burst']
                if isinstance(burst, bool) or not isinstance(burst, int) or burst <= 0:
                    return False, f"Invalid burst value: {burst}"

            if 'zone_size' in rate_limit_cfg and rate_limit_cfg['zone_size'] is not None:
                zone_size = rate_limit_cfg['zone_size']
                if isinstance(zone_size, bool) or not isinstance(zone_size, str) or not _ZONE_SIZE_RE.match(zone_size.strip()):
                    return False, f"Invalid zone_size format: {zone_size} (use format like 10m)"

            # Validate GeoIP settings
            for country_field in ('allow_countries', 'block_countries'):
                if country_field in geoip_cfg:
                    countries = geoip_cfg[country_field]
                    if not isinstance(countries, list):
                        return False, f"geoip.{country_field} must be a list of valid country codes"
                    for item in countries:
                        if not isinstance(item, str):
                            return False, f"geoip.{country_field} entries must be strings"
                        cleaned_code = item.strip().upper()
                        if not re.fullmatch(r'[A-Z0-9]{2}', cleaned_code):
                            return False, f"Invalid country code in geoip.{country_field}: {item!r}"

            if parsed_bools.get(('geoip', 'allow_enabled'), False):
                if not geoip_cfg.get('allow_countries'):
                    return False, "GeoIP ALLOW enabled but no countries specified"

            if parsed_bools.get(('geoip', 'block_enabled'), False):
                if not geoip_cfg.get('block_countries'):
                    return False, "GeoIP BLOCK enabled but no countries specified"

            # Check shell-safety across all mapped values in payload
            for env_var, val in self._flatten_updates(config).items():
                ok, msg, _ = validate_env_value(env_var, val)
                if not ok:
                    return False, msg
            
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

    def _update_env_content_flat(self, content: str, flat_updates: Dict[str, Any]) -> str:
        """
        Update .env content from flat {ENV_VAR: value} mapping.
        - Validates all values against shell metacharacters and whitespace
        - Replaces only the first matching KEY= line and deduplicates duplicates
        - Appends missing keys cleanly with a single trailing newline
        """
        formatted: Dict[str, str] = {}
        for env_var, raw_value in flat_updates.items():
            if not isinstance(env_var, str) or not _ENV_KEY_RE.match(env_var):
                raise ValueError(f"Invalid environment variable name: {env_var}")
            ok, msg, formatted_val = validate_env_value(env_var, raw_value)
            if not ok:
                raise ValueError(f"{env_var}: {msg}")
            formatted[env_var] = formatted_val

        lines = content.splitlines() if content else []
        updated_lines = []
        seen_keys = set()

        for line in lines:
            m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=', line)
            if m and m.group(1) in formatted:
                key = m.group(1)
                if key in seen_keys:
                    # Drop duplicate occurrences
                    continue
                seen_keys.add(key)
                updated_lines.append(f"{key}={formatted[key]}")
            else:
                updated_lines.append(line)

        missing_keys = [k for k in formatted if k not in seen_keys]
        if missing_keys:
            needs_certbot_header = any(
                k in ('TLS_MODE', 'SERVER_NAME') or k.startswith('CERTBOT_')
                for k in missing_keys
            )
            if needs_certbot_header and '# Certbot & TLS Configuration' not in updated_lines:
                if updated_lines and updated_lines[-1].strip() != '':
                    updated_lines.append('')
                updated_lines.append('# Certbot & TLS Configuration')
            for k in missing_keys:
                updated_lines.append(f"{k}={formatted[k]}")

        return ('\n'.join(updated_lines) + '\n') if updated_lines else ''

    def _update_env_content(self, content: str, updates: Dict[str, Any]) -> str:
        """Update .env file content preserving structure and appending missing keys."""
        flat_updates = self._flatten_updates(updates)
        return self._update_env_content_flat(content, flat_updates)
    
    def _validate_env_content(self, content: str) -> Tuple[bool, str]:
        """Validate .env file content for bash source safety."""
        if '\r' in content:
            return False, "Carriage return characters are not permitted in .env content"

        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            if '=' not in stripped:
                return False, f"Invalid line format: {stripped}"
            raw_key, raw_val = stripped.split('=', 1)
            if not _ENV_KEY_RE.match(raw_key):
                return False, f"Invalid variable name: {raw_key.strip()}"
            if raw_val.strip() != '' and raw_val[0].isspace():
                return False, f"Leading whitespace after '=' is not allowed for {raw_key}"
            val = raw_val.strip()
            if not val:
                continue
            if val[0] in ('"', "'"):
                if len(val) < 2 or val[-1] != val[0]:
                    return False, f"Unbalanced or trailing characters in quoted value for {raw_key}"
                inner = val[1:-1]
                if any(c in _ENV_LINE_FORBIDDEN_NO_STAR for c in inner):
                    return False, f"Forbidden shell metacharacters in value for {raw_key}"
                if '*' in inner and raw_key != 'SERVER_NAME':
                    return False, f"Forbidden wildcard character in value for {raw_key}"
                if raw_key == 'SERVER_NAME':
                    ok, msg, _ = validate_server_name(inner)
                    if not ok:
                        return False, msg
            else:
                if any(c.isspace() for c in val):
                    return False, f"Unquoted whitespace in value for {raw_key}"
                if any(c in _ENV_LINE_FORBIDDEN_NO_STAR for c in val):
                    return False, f"Forbidden shell metacharacters in value for {raw_key}"
                if '*' in val and raw_key != 'SERVER_NAME':
                    return False, f"Forbidden wildcard character in value for {raw_key}"
                if raw_key == 'SERVER_NAME':
                    ok, msg, _ = validate_server_name(val)
                    if not ok:
                        return False, msg

        return True, "Content validation passed"
    
    def _parse_bool(self, value: str) -> bool:
        """Parse boolean value from string"""
        return str(value).lower() in ('true', '1', 'yes', 'on')

    def _parse_positive_int(self, value: Any, default: int = 200) -> int:
        """Parse positive integer from .env string, falling back to default if corrupt."""
        if value is None or str(value).strip() == '':
            return default
        try:
            parsed = int(str(value).strip())
            return parsed if parsed > 0 else default
        except (ValueError, TypeError):
            logger.warning(f"⚠ Invalid positive integer '{value}' in .env, using default {default}")
            return default
    
    def _parse_countries(self, value: str) -> list:
        """Parse comma-separated country codes"""
        if not value:
            return []
        return [c.strip().upper() for c in value.split(',') if c.strip()]
    
    def _diff_sections(self, current: Dict, updates: Optional[Dict]) -> Dict:
        """Get differences between current and updated config for provided keys."""
        if not updates:
            return {}
        changes = {}
        for key, new_val in updates.items():
            if current.get(key) != new_val:
                changes[key] = {
                    'from': current.get(key),
                    'to': new_val,
                }
        return changes
    
    def _sanitize_for_logging(self, config: Dict) -> Dict:
        """Remove sensitive data from config for logging"""
        sensitive_tokens = ('path', 'secret', 'token', 'password', 'key')
        sanitized = {}
        for key, value in config.items():
            if isinstance(value, dict):
                sanitized[key] = self._sanitize_for_logging(value)
            elif any(tok in str(key).lower() for tok in sensitive_tokens):
                sanitized[key] = '***'
            else:
                sanitized[key] = value
        return sanitized
    
    # ========================================================================
    # User Lockout Management Methods
    # ========================================================================
    
    def get_db_connection(self):
        """Get a connection to the Guacamole database"""
        try:
            import mysql.connector
            
            connection = mysql.connector.connect(
                host=os.environ.get('GUAC_DB_HOST', 'guacamole-mariadb'),
                user=os.environ.get('GUAC_DB_USER', 'ptdbuser'),
                password=os.environ.get('GUAC_DB_PASSWORD', 'ptdbpass'),
                database=os.environ.get('GUAC_DB_NAME', 'guacamole_db')
            )
            return connection
        except Exception as e:
            logger.error(f"✗ Failed to connect to Guacamole database: {e}")
            return None
    
    def get_locked_users(self) -> list:
        """
        Get all locked out users
        
        Returns:
            List of dictionaries with user lockout information
        """
        try:
            conn = self.get_db_connection()
            if not conn:
                return []
            
            cursor = conn.cursor(dictionary=True)
            
            query = """
                SELECT 
                    u.user_id,
                    e.name as username,
                    ul.failed_attempts,
                    ul.last_failed_login,
                    ul.locked_until,
                    ul.locked,
                    ul.reason,
                    ul.updated_at
                FROM guacamole_user_lockout ul
                JOIN guacamole_user u ON ul.user_id = u.user_id
                JOIN guacamole_entity e ON u.entity_id = e.entity_id
                WHERE ul.locked = 1 OR (ul.locked_until IS NOT NULL AND ul.locked_until > NOW())
                ORDER BY ul.updated_at DESC
            """
            
            cursor.execute(query)
            results = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            # Convert datetime objects to strings for JSON serialization
            for row in results:
                if row.get('last_failed_login'):
                    row['last_failed_login'] = row['last_failed_login'].isoformat()
                if row.get('locked_until'):
                    row['locked_until'] = row['locked_until'].isoformat()
                if row.get('updated_at'):
                    row['updated_at'] = row['updated_at'].isoformat()
            
            logger.info(f"✓ Retrieved {len(results)} locked users")
            return results
        
        except Exception as e:
            logger.error(f"✗ Error getting locked users: {e}")
            return []
    
    def unlock_user(self, user_id: int) -> Tuple[bool, str]:
        """
        Unlock a user account
        
        Args:
            user_id: The ID of the user to unlock
            
        Returns:
            Tuple of (success, message)
        """
        try:
            conn = self.get_db_connection()
            if not conn:
                return False, "Failed to connect to database"
            
            cursor = conn.cursor()
            
            query = """
                UPDATE guacamole_user_lockout
                SET locked = 0, locked_until = NULL, failed_attempts = 0, updated_at = NOW()
                WHERE user_id = %s
            """
            
            cursor.execute(query, (user_id,))
            conn.commit()
            
            affected = cursor.rowcount
            cursor.close()
            conn.close()
            
            logger.info(f"✓ Unlocked user {user_id}")
            return True, f"User {user_id} unlocked successfully"
        
        except Exception as e:
            logger.error(f"✗ Error unlocking user {user_id}: {e}")
            return False, str(e)
    
    def reset_failed_attempts(self, user_id: int) -> Tuple[bool, str]:
        """
        Reset failed login attempts for a user
        
        Args:
            user_id: The ID of the user
            
        Returns:
            Tuple of (success, message)
        """
        try:
            conn = self.get_db_connection()
            if not conn:
                return False, "Failed to connect to database"
            
            cursor = conn.cursor()
            
            query = """
                UPDATE guacamole_user_lockout
                SET failed_attempts = 0, locked = 0, locked_until = NULL, updated_at = NOW()
                WHERE user_id = %s
            """
            
            cursor.execute(query, (user_id,))
            conn.commit()
            
            cursor.close()
            conn.close()
            
            logger.info(f"✓ Reset failed attempts for user {user_id}")
            return True, f"Failed attempts reset for user {user_id}"
        
        except Exception as e:
            logger.error(f"✗ Error resetting attempts for user {user_id}: {e}")
            return False, str(e)
    
    def get_user_lockout_status(self, user_id: int) -> Optional[dict]:
        """
        Get lockout status for a specific user
        
        Args:
            user_id: The ID of the user
            
        Returns:
            Dictionary with lockout information or None
        """
        try:
            conn = self.get_db_connection()
            if not conn:
                return None
            
            cursor = conn.cursor(dictionary=True)
            
            query = """
                SELECT 
                    user_id,
                    failed_attempts,
                    last_failed_login,
                    locked_until,
                    locked,
                    reason,
                    updated_at
                FROM guacamole_user_lockout
                WHERE user_id = %s
            """
            
            cursor.execute(query, (user_id,))
            result = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if result:
                if result.get('last_failed_login'):
                    result['last_failed_login'] = result['last_failed_login'].isoformat()
                if result.get('locked_until'):
                    result['locked_until'] = result['locked_until'].isoformat()
                if result.get('updated_at'):
                    result['updated_at'] = result['updated_at'].isoformat()
            
            return result
        
        except Exception as e:
            logger.error(f"✗ Error getting lockout status for user {user_id}: {e}")
            return None
