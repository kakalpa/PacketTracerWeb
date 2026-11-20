#!/usr/bin/env python3
"""
Certbot TLS Manager
Manages Let's Encrypt ACME issuance, renewal, X.509 certificate inspection,
and TLS mode switching across self-signed, manual, and certbot modes.
"""

import fcntl
import glob
import logging
import os
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from ptmanagement.api.env_config import (
    ALLOWED_CHALLENGE_TYPES,
    ALLOWED_TLS_MODES,
    EMAIL_RE,
    EnvConfigManager,
    FORBIDDEN_ENV_CHARS,
    STRICT_FQDN_RE,
    validate_certbot_webroot,
    validate_server_name,
)

logger = logging.getLogger(__name__)

CERTBOT_TIMEOUT_SECONDS = 100
CERTBOT_LOCK_PATH = '/tmp/pt_certbot.lock'
RENEW_INTERVAL_SECONDS = 43200


class CertbotLockBusyError(Exception):
    """Raised when another Certbot operation already holds the worker flock."""


class CertbotManager:
    """Manages Let's Encrypt Certbot operations and active TLS certificate inspection."""

    def __init__(
        self,
        env_manager: Optional[EnvConfigManager] = None,
        project_root: Optional[str] = None,
        ssl_dir: Optional[str] = None,
        letsencrypt_dir: Optional[str] = None,
        webroot_dir: Optional[str] = None,
        certbot_container: Optional[str] = None,
        nginx_container: Optional[str] = None,
        lock_path: Optional[str] = None,
        runner: Optional[Callable[[List[str], int], Tuple[int, str, str]]] = None,
        container_checker: Optional[Callable[[], Dict[str, Any]]] = None,
    ):
        self.env_manager = env_manager or EnvConfigManager()
        self.project_root = project_root or os.environ.get('PROJECT_ROOT', '/project')
        self.ssl_dir = ssl_dir or os.environ.get('SSL_DIR') or os.path.join(self.project_root, 'ssl')

        if letsencrypt_dir:
            self.letsencrypt_dir = letsencrypt_dir
        elif os.environ.get('LETSENCRYPT_DIR'):
            self.letsencrypt_dir = os.environ['LETSENCRYPT_DIR']
        elif os.path.exists('/etc/letsencrypt'):
            self.letsencrypt_dir = '/etc/letsencrypt'
        else:
            self.letsencrypt_dir = os.path.join(self.project_root, 'certbot', 'conf')

        if webroot_dir:
            self.webroot_dir = webroot_dir
        elif os.environ.get('CERTBOT_WEBROOT_HOST'):
            self.webroot_dir = os.environ['CERTBOT_WEBROOT_HOST']
        elif os.path.exists('/var/www/certbot'):
            self.webroot_dir = '/var/www/certbot'
        else:
            self.webroot_dir = os.path.join(self.project_root, 'certbot', 'www')

        self.certbot_container = certbot_container or os.environ.get('CERTBOT_CONTAINER', 'pt-certbot')
        self.nginx_container = nginx_container or os.environ.get('NGINX_CONTAINER', 'pt-nginx1')
        self.lock_path = lock_path or os.environ.get('CERTBOT_LOCK_PATH', CERTBOT_LOCK_PATH)
        self._custom_runner = runner is not None
        self.runner = runner or self._default_runner
        self.container_checker = container_checker
        self._last_run_status: Optional[str] = None

    # ========================================================================
    # Internal Helpers: Runner, Locking, Validation, Path Mapping
    # ========================================================================

    def _default_runner(self, cmd: List[str], timeout: int) -> Tuple[int, str, str]:
        """Execute command safely with shell=False and explicit timeout."""
        try:
            res = subprocess.run(
                cmd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return res.returncode, res.stdout or '', res.stderr or ''
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode('utf-8', errors='replace') if isinstance(exc.stdout, bytes) else (exc.stdout or '')
            stderr = exc.stderr.decode('utf-8', errors='replace') if isinstance(exc.stderr, bytes) else (exc.stderr or '')
            msg = f"Command timed out after {timeout}s"
            combined_err = f"{stderr}\n{msg}".strip() if stderr else msg
            return -1, stdout, combined_err

    @contextmanager
    def _acquire_lock(self):
        """Acquire non-blocking exclusive flock across Gunicorn workers."""
        lock_dir = os.path.dirname(os.path.abspath(self.lock_path))
        if lock_dir:
            os.makedirs(lock_dir, exist_ok=True)
        lock_f = open(self.lock_path, 'a+')
        try:
            try:
                fcntl.flock(lock_f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise CertbotLockBusyError("Another certificate operation is currently in progress")
            yield
        finally:
            try:
                fcntl.flock(lock_f, fcntl.LOCK_UN)
            except OSError:
                pass
            lock_f.close()

    @staticmethod
    def _parse_bool(val: Any, default: bool = False) -> bool:
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        return str(val).strip().lower() in ('true', '1', 'yes', 'on')

    @staticmethod
    def _parse_extra_domains(raw: str) -> Tuple[bool, str, List[str]]:
        if not raw or not str(raw).strip():
            return True, "OK", []
        parts = [p.strip().lower() for p in str(raw).split(',') if p.strip()]
        seen = set()
        valid_domains: List[str] = []
        for dom in parts:
            if not STRICT_FQDN_RE.match(dom):
                return False, f"Invalid extra domain FQDN: {dom}", []
            if dom not in seen:
                seen.add(dom)
                valid_domains.append(dom)
        return True, "OK", valid_domains

    @staticmethod
    def _validate_domain(domain: str) -> Tuple[bool, str]:
        if not domain or not isinstance(domain, str):
            return False, "CERTBOT_DOMAIN is required"
        cleaned = domain.strip().lower()
        if not STRICT_FQDN_RE.match(cleaned):
            return False, f"Invalid CERTBOT_DOMAIN FQDN (localhost, IPs, wildcards, and special chars are not allowed): {domain}"
        return True, cleaned

    @staticmethod
    def _validate_email(email: str) -> Tuple[bool, str]:
        if not email or not isinstance(email, str):
            return False, "CERTBOT_EMAIL is required"
        cleaned = email.strip()
        if len(cleaned) > 254 or not EMAIL_RE.match(cleaned):
            return False, f"Invalid CERTBOT_EMAIL address: {email}"
        return True, cleaned

    @staticmethod
    def _validate_webroot(webroot: Any) -> Tuple[bool, str]:
        ok, msg, wr = validate_certbot_webroot(webroot)
        if not ok:
            return False, msg
        return True, wr

    @staticmethod
    def _is_lock_contention(rc: int, combined_output: str) -> bool:
        """Detect silent flock -n contention (rc=1, empty output), rc=75, or lock messages."""
        lower_out = (combined_output or '').lower()
        if (
            'pt_certbot_op.lock' in lower_out
            or 'resource temporarily unavailable' in lower_out
            or 'another instance of certbot is already running' in lower_out
            or 'lock contention' in lower_out
        ):
            return True
        if rc == 75:
            return True
        if rc == 1 and not (combined_output or '').strip():
            return True
        return False

    def _get_container_status(self) -> Dict[str, Any]:
        if self.container_checker is not None:
            try:
                return self.container_checker()
            except Exception as e:
                return {'name': self.certbot_container, 'running': False, 'status': f'error: {e}'}

        if self._custom_runner:
            return {'name': self.certbot_container, 'running': True, 'status': 'running'}

        try:
            res = subprocess.run(
                ['docker', 'inspect', '--format', '{{.State.Running}}|{{.State.Status}}', self.certbot_container],
                shell=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode != 0:
                return {'name': self.certbot_container, 'running': False, 'status': 'not-found'}
            out = (res.stdout or '').strip()
            parts = out.split('|', 1)
            running = parts[0].lower() == 'true' if parts else False
            status = parts[1] if len(parts) > 1 else ('running' if running else 'stopped')
            return {'name': self.certbot_container, 'running': running, 'status': status}
        except Exception as e:
            return {'name': self.certbot_container, 'running': False, 'status': f'unavailable: {e}'}

    def _resolve_local_cert_paths(self, cert_path_cfg: str, key_path_cfg: str) -> Tuple[str, str]:
        """Map Nginx container cert/key paths to pt-management local filesystem paths."""
        if cert_path_cfg.startswith('/etc/letsencrypt/'):
            local_cert = os.path.join(self.letsencrypt_dir, cert_path_cfg[len('/etc/letsencrypt/'):])
        elif cert_path_cfg in ('/etc/ssl/ptweb/server.crt', '/etc/ssl/certs/server.crt', '/etc/ssl/certs/ssl-cert.pem'):
            local_cert = os.path.join(self.ssl_dir, 'server.crt')
        elif os.path.exists(cert_path_cfg):
            local_cert = cert_path_cfg
        else:
            local_cert = os.path.join(self.ssl_dir, 'server.crt')

        if key_path_cfg.startswith('/etc/letsencrypt/'):
            local_key = os.path.join(self.letsencrypt_dir, key_path_cfg[len('/etc/letsencrypt/'):])
        elif key_path_cfg in ('/etc/ssl/ptweb/server.key', '/etc/ssl/private/server.key', '/etc/ssl/private/ssl-key.pem'):
            local_key = os.path.join(self.ssl_dir, 'server.key')
        elif os.path.exists(key_path_cfg):
            local_key = key_path_cfg
        else:
            local_key = os.path.join(self.ssl_dir, 'server.key')

        return local_cert, local_key

    @staticmethod
    def verify_cert_key_pair(cert_path: str, key_path: str) -> Tuple[bool, str]:
        """Verify X.509 certificate and private key match via openssl pubkey comparison."""
        if not cert_path or not key_path or not os.path.isfile(cert_path) or not os.path.isfile(key_path):
            return False, "Certificate or key file not found"
        try:
            cert_res = subprocess.run(
                ['openssl', 'x509', '-in', cert_path, '-pubkey', '-noout'],
                shell=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if cert_res.returncode != 0 or not cert_res.stdout.strip():
                err = (cert_res.stderr or cert_res.stdout or 'Failed to inspect certificate').strip()
                return False, f"Invalid certificate: {err}"

            key_res = subprocess.run(
                ['openssl', 'pkey', '-in', key_path, '-pubout', '-passin', 'pass:'],
                shell=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if key_res.returncode != 0 or not key_res.stdout.strip():
                err = (key_res.stderr or key_res.stdout or 'Failed to inspect key').strip()
                return False, f"Invalid or encrypted private key: {err}"

            if cert_res.stdout.strip() == key_res.stdout.strip():
                return True, "Certificate and private key match"
            return False, "Certificate and private key public keys do not match"
        except subprocess.TimeoutExpired:
            return False, "Pair verification timed out"
        except Exception as e:
            return False, f"Pair verification error: {e}"

    # ========================================================================
    # X.509 Inspection
    # ========================================================================

    def inspect_certificate(
        self,
        cert_path: str,
        key_path: Optional[str] = None,
        tls_mode: str = 'self-signed',
    ) -> Dict[str, Any]:
        """Inspect X.509 metadata (subject, SANs, issuer, dates, days_remaining, source, pair_matched)."""
        if not cert_path or not os.path.isfile(cert_path):
            return {
                'exists': False,
                'path': cert_path,
                'source': tls_mode,
                'subject': None,
                'sans': [],
                'issuer': None,
                'not_before': None,
                'not_after': None,
                'days_remaining': None,
                'is_self_signed': False,
                'is_staging': False,
                'pair_matched': False,
            }

        try:
            res = subprocess.run(
                ['openssl', 'x509', '-in', cert_path, '-noout', '-subject', '-issuer', '-dates', '-ext', 'subjectAltName'],
                shell=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception as e:
            logger.error(f"✗ Failed to inspect certificate {cert_path}: {e}")
            return {
                'exists': True,
                'path': cert_path,
                'source': tls_mode,
                'subject': None,
                'sans': [],
                'issuer': None,
                'not_before': None,
                'not_after': None,
                'days_remaining': None,
                'is_self_signed': False,
                'is_staging': False,
                'pair_matched': False,
                'error': str(e),
            }

        if res.returncode != 0:
            return {
                'exists': True,
                'path': cert_path,
                'source': tls_mode,
                'subject': None,
                'sans': [],
                'issuer': None,
                'not_before': None,
                'not_after': None,
                'days_remaining': None,
                'is_self_signed': False,
                'is_staging': False,
                'pair_matched': False,
                'error': (res.stderr or res.stdout or 'openssl x509 failed').strip(),
            }

        subject = None
        issuer = None
        not_before_iso = None
        not_after_iso = None
        days_remaining = None
        sans: List[str] = []

        lines = (res.stdout or '').splitlines()
        in_san = False
        for line in lines:
            stripped = line.strip()
            if in_san:
                if stripped and not stripped.startswith(('subject=', 'issuer=', 'notBefore=', 'notAfter=')):
                    for item in stripped.split(','):
                        tok = item.strip()
                        if tok.startswith('DNS:'):
                            sans.append(tok[4:].strip())
                        elif tok.startswith('IP Address:'):
                            sans.append(tok[len('IP Address:'):].strip())
                        elif tok.startswith('IP:'):
                            sans.append(tok[3:].strip())
                    continue
                in_san = False

            if line.startswith('subject='):
                subject = line[len('subject='):].strip()
            elif line.startswith('issuer='):
                issuer = line[len('issuer='):].strip()
            elif line.startswith('notBefore='):
                raw_dt = ' '.join(line[len('notBefore='):].strip().split())
                try:
                    dt = datetime.strptime(raw_dt, '%b %d %H:%M:%S %Y %Z').replace(tzinfo=timezone.utc)
                    not_before_iso = dt.isoformat()
                except ValueError:
                    not_before_iso = raw_dt
            elif line.startswith('notAfter='):
                raw_dt = ' '.join(line[len('notAfter='):].strip().split())
                try:
                    dt = datetime.strptime(raw_dt, '%b %d %H:%M:%S %Y %Z').replace(tzinfo=timezone.utc)
                    not_after_iso = dt.isoformat()
                    days_remaining = int((dt - datetime.now(timezone.utc)).total_seconds() // 86400)
                except ValueError:
                    not_after_iso = raw_dt
            elif stripped.startswith('X509v3 Subject Alternative Name:'):
                in_san = True

        is_self_signed = bool(subject and issuer and subject == issuer)
        is_staging = bool(issuer and ('STAGING' in issuer.upper() or 'FAKE LE' in issuer.upper()))

        if is_staging:
            source = 'letsencrypt-staging'
        elif issuer and "Let's Encrypt" in issuer:
            source = 'letsencrypt'
        elif tls_mode == 'certbot' and '/live/' in cert_path and not is_self_signed:
            source = 'letsencrypt'
        elif is_self_signed and tls_mode == 'self-signed':
            source = 'self-signed'
        elif tls_mode == 'manual':
            source = 'manual'
        elif is_self_signed:
            source = 'self-signed'
        else:
            source = 'manual'

        pair_matched = False
        if key_path and os.path.isfile(key_path):
            pair_matched, _ = self.verify_cert_key_pair(cert_path, key_path)

        return {
            'exists': True,
            'path': cert_path,
            'source': source,
            'subject': subject,
            'sans': sans,
            'issuer': issuer,
            'not_before': not_before_iso,
            'not_after': not_after_iso,
            'days_remaining': days_remaining,
            'is_self_signed': is_self_signed,
            'is_staging': is_staging,
            'pair_matched': pair_matched,
        }

    # ========================================================================
    # Public Operations
    # ========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Read fresh .env state, inspect active X.509 certificate, and report container/renewal status."""
        env_vars = self.env_manager.read_env_file()

        tls_mode = env_vars.get('TLS_MODE', 'self-signed') or 'self-signed'
        if tls_mode not in ALLOWED_TLS_MODES:
            tls_mode = 'self-signed'

        https_enabled = self._parse_bool(env_vars.get('ENABLE_HTTPS', 'false'))
        server_name = env_vars.get('SERVER_NAME', '') or 'localhost'
        ssl_cert_path = env_vars.get('SSL_CERT_PATH', '/etc/ssl/ptweb/server.crt') or '/etc/ssl/ptweb/server.crt'
        ssl_key_path = env_vars.get('SSL_KEY_PATH', '/etc/ssl/ptweb/server.key') or '/etc/ssl/ptweb/server.key'

        certbot_cfg = {
            'enabled': self._parse_bool(env_vars.get('CERTBOT_ENABLED', 'false')),
            'domain': env_vars.get('CERTBOT_DOMAIN', ''),
            'extra_domains': env_vars.get('CERTBOT_EXTRA_DOMAINS', ''),
            'email': env_vars.get('CERTBOT_EMAIL', ''),
            'challenge_type': env_vars.get('CERTBOT_CHALLENGE_TYPE', 'http-01') or 'http-01',
            'staging': self._parse_bool(env_vars.get('CERTBOT_STAGING', 'false')),
            'auto_renew': self._parse_bool(env_vars.get('CERTBOT_AUTO_RENEW', 'true'), default=True),
            'webroot': env_vars.get('CERTBOT_WEBROOT', '/var/www/certbot') or '/var/www/certbot',
        }

        local_cert, local_key = self._resolve_local_cert_paths(ssl_cert_path, ssl_key_path)
        cert_info = self.inspect_certificate(local_cert, key_path=local_key, tls_mode=tls_mode)

        renewal_dir = os.path.join(self.letsencrypt_dir, 'renewal')
        renewal_configs = glob.glob(os.path.join(renewal_dir, '*.conf')) if os.path.isdir(renewal_dir) else []
        renewal_info = {
            'auto_renew': certbot_cfg['auto_renew'],
            'interval_seconds': RENEW_INTERVAL_SECONDS,
            'renewal_configs_present': len(renewal_configs) > 0,
            'last_run_status': self._last_run_status,
            'next_check_note': (
                "pt-certbot checks every 12h when CERTBOT_AUTO_RENEW=true"
                if certbot_cfg['auto_renew']
                else "Automatic 12h renewal is currently disabled (CERTBOT_AUTO_RENEW=false)"
            ),
        }

        container_info = self._get_container_status()

        return {
            'success': True,
            'tls_mode': tls_mode,
            'https_enabled': https_enabled,
            'server_name': server_name,
            'ssl_cert_path': ssl_cert_path,
            'ssl_key_path': ssl_key_path,
            'certbot': certbot_cfg,
            'certificate': cert_info,
            'renewal': renewal_info,
            'container': container_info,
        }

    def save_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and persist Certbot configuration into .env.
        Regenerates and reloads Nginx when SERVER_NAME or ENABLE_HTTPS changes,
        or when TLS_MODE=certbot and CERTBOT_DOMAIN/CERTBOT_EXTRA_DOMAINS/CERTBOT_STAGING changes.
        """
        if not isinstance(payload, dict):
            return {'success': False, 'message': 'Invalid payload', 'status_code': 400}

        current_env = self.env_manager.read_env_file()
        current_tls_mode = current_env.get('TLS_MODE', 'self-signed') or 'self-signed'

        env_updates: Dict[str, Any] = {}

        if 'domain' in payload:
            raw_domain = str(payload['domain'] or '').strip().lower()
            if raw_domain:
                ok, res = self._validate_domain(raw_domain)
                if not ok:
                    return {'success': False, 'message': res, 'status_code': 400}
                env_updates['CERTBOT_DOMAIN'] = res
            else:
                env_updates['CERTBOT_DOMAIN'] = ''

        if 'extra_domains' in payload:
            ok, msg, extra_list = self._parse_extra_domains(str(payload['extra_domains'] or ''))
            if not ok:
                return {'success': False, 'message': msg, 'status_code': 400}
            primary_dom = env_updates.get('CERTBOT_DOMAIN', current_env.get('CERTBOT_DOMAIN', '')).strip().lower()
            filtered = [d for d in extra_list if d != primary_dom]
            if len(filtered) + (1 if primary_dom else 0) > 100:
                return {'success': False, 'message': 'Total domains exceed Let\'s Encrypt limit of 100', 'status_code': 400}
            env_updates['CERTBOT_EXTRA_DOMAINS'] = ','.join(filtered)

        if 'email' in payload:
            raw_email = str(payload['email'] or '').strip()
            if raw_email:
                ok, res = self._validate_email(raw_email)
                if not ok:
                    return {'success': False, 'message': res, 'status_code': 400}
                env_updates['CERTBOT_EMAIL'] = res
            else:
                env_updates['CERTBOT_EMAIL'] = ''

        if 'challenge_type' in payload:
            ctype = str(payload['challenge_type'] or 'http-01').strip().lower()
            if ctype not in ALLOWED_CHALLENGE_TYPES:
                return {'success': False, 'message': f"Invalid challenge_type: {ctype}", 'status_code': 400}
            env_updates['CERTBOT_CHALLENGE_TYPE'] = ctype

        if 'webroot' in payload and payload['webroot'] is not None:
            ok, res = self._validate_webroot(payload['webroot'])
            if not ok:
                return {'success': False, 'message': res, 'status_code': 400}
            env_updates['CERTBOT_WEBROOT'] = res

        if 'enabled' in payload:
            env_updates['CERTBOT_ENABLED'] = self._parse_bool(payload['enabled'])
        if 'staging' in payload:
            env_updates['CERTBOT_STAGING'] = self._parse_bool(payload['staging'])
        if 'auto_renew' in payload:
            env_updates['CERTBOT_AUTO_RENEW'] = self._parse_bool(payload['auto_renew'])
        if 'enable_https' in payload:
            env_updates['ENABLE_HTTPS'] = self._parse_bool(payload['enable_https'])

        if 'server_name' in payload and payload['server_name'] is not None:
            ok, msg, normalized_sn = validate_server_name(str(payload['server_name']))
            if not ok:
                return {'success': False, 'message': msg, 'status_code': 400}
            env_updates['SERVER_NAME'] = normalized_sn

        if not env_updates:
            return {'success': False, 'message': 'No valid configuration fields provided', 'status_code': 400}

        effective_enabled = (
            env_updates['CERTBOT_ENABLED']
            if 'CERTBOT_ENABLED' in env_updates
            else self._parse_bool(current_env.get('CERTBOT_ENABLED', 'false'))
        )
        effective_domain = (
            env_updates['CERTBOT_DOMAIN']
            if 'CERTBOT_DOMAIN' in env_updates
            else (current_env.get('CERTBOT_DOMAIN', '') or '')
        ).strip()
        if effective_enabled and not effective_domain:
            return {
                'success': False,
                'message': 'CERTBOT_DOMAIN is required when Certbot is enabled',
                'status_code': 400,
            }

        # Determine if Nginx regeneration & reload is needed
        def _norm_bool(v: Any) -> str:
            return 'true' if self._parse_bool(v) else 'false'

        sn_changed = (
            'SERVER_NAME' in env_updates
            and env_updates['SERVER_NAME'] != (current_env.get('SERVER_NAME', '') or '')
        )
        https_changed = (
            'ENABLE_HTTPS' in env_updates
            and _norm_bool(env_updates['ENABLE_HTTPS']) != _norm_bool(current_env.get('ENABLE_HTTPS', 'false'))
        )
        certbot_active_changed = current_tls_mode == 'certbot' and (
            ('CERTBOT_DOMAIN' in env_updates and env_updates['CERTBOT_DOMAIN'] != current_env.get('CERTBOT_DOMAIN', ''))
            or ('CERTBOT_EXTRA_DOMAINS' in env_updates and env_updates['CERTBOT_EXTRA_DOMAINS'] != current_env.get('CERTBOT_EXTRA_DOMAINS', ''))
            or ('CERTBOT_STAGING' in env_updates and _norm_bool(env_updates['CERTBOT_STAGING']) != _norm_bool(current_env.get('CERTBOT_STAGING', 'false')))
        )
        needs_nginx_sync = sn_changed or https_changed or certbot_active_changed

        snapshot = self.env_manager.snapshot_state()
        ok, msg = self.env_manager.update_env_vars(env_updates)
        if not ok:
            return {'success': False, 'message': msg, 'status_code': 400}

        nginx_reloaded = False
        if needs_nginx_sync:
            regen_ok, regen_msg = self.env_manager.regenerate_nginx_config()
            if not regen_ok:
                self.env_manager.rollback_state(snapshot)
                return {
                    'success': False,
                    'message': f"Failed to regenerate Nginx config (rolled back .env): {regen_msg}",
                    'nginx_reloaded': False,
                    'status_code': 500,
                }
            reload_ok, reload_msg = self.env_manager.reload_nginx()
            if not reload_ok:
                self.env_manager.rollback_state(snapshot)
                return {
                    'success': False,
                    'message': f"Nginx reload failed (rolled back .env): {reload_msg}",
                    'nginx_reloaded': False,
                    'status_code': 500,
                }
            nginx_reloaded = True

        return {
            'success': True,
            'message': 'Certbot configuration saved successfully',
            'nginx_reloaded': nginx_reloaded,
            'status_code': 200,
        }

    def issue(self, dry_run: bool = False, staging: Optional[bool] = None) -> Dict[str, Any]:
        """Run preflight checks and issue a Let's Encrypt certificate via certbot certonly."""
        try:
            with self._acquire_lock():
                env_vars = self.env_manager.read_env_file()

                ok, domain = self._validate_domain(env_vars.get('CERTBOT_DOMAIN', ''))
                if not ok:
                    return {'success': False, 'message': domain, 'status_code': 400}

                ok, msg, extra_list = self._parse_extra_domains(env_vars.get('CERTBOT_EXTRA_DOMAINS', ''))
                if not ok:
                    return {'success': False, 'message': msg, 'status_code': 400}
                extra_list = [d for d in extra_list if d != domain]
                all_domains = [domain] + extra_list
                if len(all_domains) > 100:
                    return {'success': False, 'message': 'Total domains exceed Let\'s Encrypt limit of 100', 'status_code': 400}

                ok, email = self._validate_email(env_vars.get('CERTBOT_EMAIL', ''))
                if not ok:
                    return {'success': False, 'message': email, 'status_code': 400}

                challenge_type = (env_vars.get('CERTBOT_CHALLENGE_TYPE', 'http-01') or 'http-01').strip().lower()
                if challenge_type == 'dns-01':
                    return {
                        'success': False,
                        'message': "DNS-01 challenge is not configured (requires DNS provider plugin and credentials under /etc/letsencrypt/secrets/). Select http-01.",
                        'status_code': 400,
                    }
                if challenge_type != 'http-01':
                    return {'success': False, 'message': f"Unsupported challenge type: {challenge_type}", 'status_code': 400}

                # Check pt-certbot container availability
                if not self._custom_runner:
                    cstatus = self._get_container_status()
                    if not cstatus.get('running'):
                        return {
                            'success': False,
                            'message': f"Certbot container '{self.certbot_container}' is not running (status: {cstatus.get('status')})",
                            'status_code': 503,
                        }

                # Ensure webroot ACME directory is writable
                acme_dir = os.path.join(self.webroot_dir, '.well-known', 'acme-challenge')
                try:
                    os.makedirs(acme_dir, exist_ok=True)
                    if not os.access(acme_dir, os.W_OK):
                        return {'success': False, 'message': f"ACME webroot is not writable: {acme_dir}", 'status_code': 400}
                except OSError as e:
                    return {'success': False, 'message': f"ACME webroot error ({acme_dir}): {e}", 'status_code': 400}

                effective_staging = (
                    self._parse_bool(staging)
                    if staging is not None
                    else self._parse_bool(env_vars.get('CERTBOT_STAGING', 'false'))
                )
                raw_webroot = env_vars.get('CERTBOT_WEBROOT', '/var/www/certbot') or '/var/www/certbot'
                ok, container_webroot = self._validate_webroot(raw_webroot)
                if not ok:
                    return {'success': False, 'message': container_webroot, 'status_code': 400}

                cmd = [
                    'docker', 'exec', self.certbot_container,
                    'flock', '-n', '/etc/letsencrypt/.pt_certbot_op.lock',
                    'certbot', 'certonly',
                    '--webroot', '-w', container_webroot,
                    '--non-interactive', '--agree-tos',
                    '--email', email,
                    '--cert-name', domain,
                    '--expand',
                    '--keep-until-expiring',
                ]
                for d in all_domains:
                    cmd.extend(['-d', d])

                if effective_staging:
                    cmd.append('--staging')
                if dry_run:
                    cmd.append('--dry-run')

                # When transitioning from staging to production, force replacement of untrusted staging cert
                live_cert = os.path.join(self.letsencrypt_dir, 'live', domain, 'fullchain.pem')
                live_key = os.path.join(self.letsencrypt_dir, 'live', domain, 'privkey.pem')
                if not dry_run and not effective_staging and os.path.isfile(live_cert):
                    existing_meta = self.inspect_certificate(live_cert)
                    if existing_meta.get('is_staging'):
                        cmd.append('--force-renewal')

                try:
                    rc, stdout, stderr = self.runner(cmd, CERTBOT_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    self._last_run_status = 'issue-timeout'
                    return {
                        'success': False,
                        'timed_out': True,
                        'message': f"Certbot operation timed out after {CERTBOT_TIMEOUT_SECONDS}s",
                        'stdout': '',
                        'stderr': '',
                        'output': f"Timed out after {CERTBOT_TIMEOUT_SECONDS}s",
                        'status_code': 504,
                    }

                stdout = stdout or ''
                stderr = stderr or ''
                combined_output = "\n".join(part for part in (stdout.strip(), stderr.strip()) if part)

                if rc == -1 and 'timed out' in stderr.lower():
                    self._last_run_status = 'issue-timeout'
                    return {
                        'success': False,
                        'timed_out': True,
                        'message': f"Certbot operation timed out after {CERTBOT_TIMEOUT_SECONDS}s",
                        'stdout': stdout,
                        'stderr': stderr,
                        'output': combined_output,
                        'status_code': 504,
                    }

                if rc != 0:
                    if self._is_lock_contention(rc, combined_output):
                        return {
                            'success': False,
                            'message': "Another certificate operation is currently in progress in pt-certbot",
                            'stdout': stdout,
                            'stderr': stderr,
                            'output': combined_output,
                            'status_code': 409,
                        }
                    self._last_run_status = 'issue-failed'
                    return {
                        'success': False,
                        'message': f"Certbot issuance failed (exit code {rc})",
                        'exit_code': rc,
                        'stdout': stdout,
                        'stderr': stderr,
                        'output': combined_output,
                        'status_code': 500,
                    }

                if dry_run:
                    self._last_run_status = 'dry-run-success'
                    return {
                        'success': True,
                        'dry_run': True,
                        'staging': effective_staging,
                        'message': 'Certbot dry-run succeeded (.env and Nginx unchanged)',
                        'stdout': stdout,
                        'stderr': stderr,
                        'output': combined_output,
                        'status_code': 200,
                    }

                # Real issuance succeeded: verify cert/key pair on disk before switching Nginx
                if not (os.path.isfile(live_cert) and os.path.isfile(live_key)):
                    self._last_run_status = 'issue-missing-files'
                    return {
                        'success': False,
                        'message': f"Certbot exited 0, but issued files not found under {os.path.dirname(live_cert)}",
                        'stdout': stdout,
                        'stderr': stderr,
                        'output': combined_output,
                        'status_code': 500,
                    }

                matched, match_msg = self.verify_cert_key_pair(live_cert, live_key)
                if not matched:
                    self._last_run_status = 'issue-pair-mismatch'
                    return {
                        'success': False,
                        'message': f"Issued certificate/key verification failed: {match_msg}",
                        'stdout': stdout,
                        'stderr': stderr,
                        'output': combined_output,
                        'status_code': 500,
                    }

                env_updates: Dict[str, Any] = {
                    'TLS_MODE': 'certbot',
                    'CERTBOT_ENABLED': True,
                    'ENABLE_HTTPS': True,
                    'SERVER_NAME': ' '.join(all_domains),
                    'SSL_CERT_PATH': f'/etc/letsencrypt/live/{domain}/fullchain.pem',
                    'SSL_KEY_PATH': f'/etc/letsencrypt/live/{domain}/privkey.pem',
                }
                if staging is not None:
                    env_updates['CERTBOT_STAGING'] = effective_staging

                snapshot = self.env_manager.snapshot_state()
                ok, env_msg = self.env_manager.update_env_vars(env_updates)
                if not ok:
                    return {
                        'success': False,
                        'message': f"Certificate issued, but failed to update .env: {env_msg}",
                        'stdout': stdout,
                        'stderr': stderr,
                        'output': combined_output,
                        'status_code': 500,
                    }

                regen_ok, regen_msg = self.env_manager.regenerate_nginx_config()
                if not regen_ok:
                    self.env_manager.rollback_state(snapshot)
                    self._last_run_status = 'issue-nginx-regen-failed'
                    return {
                        'success': False,
                        'message': f"Certificate issued, but Nginx config regeneration failed (rolled back .env): {regen_msg}",
                        'reloaded': False,
                        'stdout': stdout,
                        'stderr': stderr,
                        'output': combined_output,
                        'status_code': 500,
                    }

                reload_ok, reload_msg = self.env_manager.reload_nginx()
                if not reload_ok:
                    self.env_manager.rollback_state(snapshot)
                    self._last_run_status = 'issue-nginx-reload-failed'
                    return {
                        'success': False,
                        'message': f"Certificate issued, but Nginx validation/reload failed (rolled back .env): {reload_msg}",
                        'reloaded': False,
                        'stdout': stdout,
                        'stderr': stderr,
                        'output': combined_output,
                        'status_code': 500,
                    }
                self._last_run_status = 'issue-success'
                return {
                    'success': True,
                    'dry_run': False,
                    'staging': effective_staging,
                    'reloaded': True,
                    'tls_mode': 'certbot',
                    'message': "Certificate issued and activated in Nginx",
                    'stdout': stdout,
                    'stderr': stderr,
                    'output': combined_output,
                    'status_code': 200,
                }
        except CertbotLockBusyError as e:
            return {'success': False, 'message': str(e), 'status_code': 409}

    def renew(self, dry_run: bool = False, force_renewal: bool = False) -> Dict[str, Any]:
        """Execute certbot renew with flock serialization and timeout <= 100s."""
        try:
            with self._acquire_lock():
                env_vars = self.env_manager.read_env_file()
                raw_webroot = env_vars.get('CERTBOT_WEBROOT', '/var/www/certbot') or '/var/www/certbot'
                ok, container_webroot = self._validate_webroot(raw_webroot)
                if not ok:
                    return {'success': False, 'message': container_webroot, 'status_code': 400}

                if not self._custom_runner:
                    cstatus = self._get_container_status()
                    if not cstatus.get('running'):
                        return {
                            'success': False,
                            'message': f"Certbot container '{self.certbot_container}' is not running (status: {cstatus.get('status')})",
                            'status_code': 503,
                        }

                cmd = [
                    'docker', 'exec', self.certbot_container,
                    'flock', '-n', '/etc/letsencrypt/.pt_certbot_op.lock',
                    'certbot', 'renew',
                    '--webroot', '-w', container_webroot,
                    '--non-interactive',
                ]
                if dry_run:
                    cmd.append('--dry-run')
                if force_renewal:
                    cmd.append('--force-renewal')

                try:
                    rc, stdout, stderr = self.runner(cmd, CERTBOT_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    self._last_run_status = 'renew-timeout'
                    return {
                        'success': False,
                        'timed_out': True,
                        'message': f"Certbot renewal timed out after {CERTBOT_TIMEOUT_SECONDS}s",
                        'stdout': '',
                        'stderr': '',
                        'output': f"Timed out after {CERTBOT_TIMEOUT_SECONDS}s",
                        'status_code': 504,
                    }

                stdout = stdout or ''
                stderr = stderr or ''
                combined_output = "\n".join(part for part in (stdout.strip(), stderr.strip()) if part)

                if rc == -1 and 'timed out' in stderr.lower():
                    self._last_run_status = 'renew-timeout'
                    return {
                        'success': False,
                        'timed_out': True,
                        'message': f"Certbot renewal timed out after {CERTBOT_TIMEOUT_SECONDS}s",
                        'stdout': stdout,
                        'stderr': stderr,
                        'output': combined_output,
                        'status_code': 504,
                    }

                if rc != 0:
                    if self._is_lock_contention(rc, combined_output):
                        return {
                            'success': False,
                            'message': "Another certificate operation is currently in progress in pt-certbot",
                            'stdout': stdout,
                            'stderr': stderr,
                            'output': combined_output,
                            'status_code': 409,
                        }
                    self._last_run_status = 'renew-failed'
                    return {
                        'success': False,
                        'message': f"Certbot renewal failed (exit code {rc})",
                        'exit_code': rc,
                        'stdout': stdout,
                        'stderr': stderr,
                        'output': combined_output,
                        'status_code': 500,
                    }

                if dry_run:
                    self._last_run_status = 'renew-dry-run-success'
                    return {
                        'success': True,
                        'dry_run': True,
                        'force_renewal': force_renewal,
                        'reloaded': False,
                        'message': 'Certbot renewal dry-run succeeded',
                        'stdout': stdout,
                        'stderr': stderr,
                        'output': combined_output,
                        'status_code': 200,
                    }

                reload_ok, reload_msg = self.env_manager.reload_nginx()
                self._last_run_status = 'renew-success' if reload_ok else 'renew-reload-warning'
                return {
                    'success': True,
                    'dry_run': False,
                    'force_renewal': force_renewal,
                    'reloaded': reload_ok,
                    'message': (
                        "Certbot renewal completed and Nginx reloaded"
                        if reload_ok
                        else f"Certbot renewal completed (Nginx reload warning: {reload_msg})"
                    ),
                    'stdout': stdout,
                    'stderr': stderr,
                    'output': combined_output,
                    'status_code': 200,
                }
        except CertbotLockBusyError as e:
            return {'success': False, 'message': str(e), 'status_code': 409}

    def switch_mode(self, tls_mode: str) -> Dict[str, Any]:
        """Switch TLS_MODE between self-signed, manual, and certbot after verifying cert/key pair."""
        if not tls_mode or tls_mode not in ALLOWED_TLS_MODES:
            return {
                'success': False,
                'message': f"Invalid tls_mode '{tls_mode}'. Allowed: {', '.join(ALLOWED_TLS_MODES)}",
                'status_code': 400,
            }

        try:
            with self._acquire_lock():
                env_vars = self.env_manager.read_env_file()

                if tls_mode == 'certbot':
                    ok, domain = self._validate_domain(env_vars.get('CERTBOT_DOMAIN', ''))
                    if not ok:
                        return {
                            'success': False,
                            'message': "Cannot switch to certbot mode: CERTBOT_DOMAIN is not configured",
                            'status_code': 400,
                        }
                    local_cert = os.path.join(self.letsencrypt_dir, 'live', domain, 'fullchain.pem')
                    local_key = os.path.join(self.letsencrypt_dir, 'live', domain, 'privkey.pem')
                    nginx_cert = f'/etc/letsencrypt/live/{domain}/fullchain.pem'
                    nginx_key = f'/etc/letsencrypt/live/{domain}/privkey.pem'
                    env_updates: Dict[str, Any] = {
                        'TLS_MODE': 'certbot',
                        'CERTBOT_ENABLED': True,
                        'SSL_CERT_PATH': nginx_cert,
                        'SSL_KEY_PATH': nginx_key,
                    }
                else:
                    local_cert = os.path.join(self.ssl_dir, 'server.crt')
                    local_key = os.path.join(self.ssl_dir, 'server.key')
                    nginx_cert = '/etc/ssl/ptweb/server.crt'
                    nginx_key = '/etc/ssl/ptweb/server.key'
                    env_updates = {
                        'TLS_MODE': tls_mode,
                        'SSL_CERT_PATH': nginx_cert,
                        'SSL_KEY_PATH': nginx_key,
                    }

                if not (os.path.isfile(local_cert) and os.path.isfile(local_key)):
                    return {
                        'success': False,
                        'message': f"Target certificate or key not found for mode '{tls_mode}' ({local_cert}, {local_key})",
                        'status_code': 400,
                    }

                matched, match_msg = self.verify_cert_key_pair(local_cert, local_key)
                if not matched:
                    return {
                        'success': False,
                        'message': f"Target certificate/key validation failed for mode '{tls_mode}': {match_msg}",
                        'status_code': 400,
                    }

                snapshot = self.env_manager.snapshot_state()
                ok, env_msg = self.env_manager.update_env_vars(env_updates)
                if not ok:
                    return {'success': False, 'message': f"Failed to update .env: {env_msg}", 'status_code': 500}

                regen_ok, regen_msg = self.env_manager.regenerate_nginx_config()
                if not regen_ok:
                    self.env_manager.rollback_state(snapshot)
                    return {
                        'success': False,
                        'message': f"Nginx config regeneration failed (rolled back .env): {regen_msg}",
                        'status_code': 500,
                    }

                reload_ok, reload_msg = self.env_manager.reload_nginx()
                if not reload_ok:
                    self.env_manager.rollback_state(snapshot)
                    return {
                        'success': False,
                        'message': f"Nginx reload failed (rolled back .env): {reload_msg}",
                        'status_code': 500,
                    }

                return {
                    'success': True,
                    'tls_mode': tls_mode,
                    'ssl_cert_path': nginx_cert,
                    'ssl_key_path': nginx_key,
                    'reloaded': True,
                    'message': f"Switched TLS mode to '{tls_mode}' and reloaded Nginx",
                    'status_code': 200,
                }
        except CertbotLockBusyError as e:
            return {'success': False, 'message': str(e), 'status_code': 409}
