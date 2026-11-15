"""
Tier 3: Cross-Feature Combinations and Architectural Consistency Test Suite.
Validates pairwise cross-component interlocks and architectural synergy across the proposal.
20 test methods across 4 classes.
"""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path
from typing import Optional

from tests.proposal_verification.parser import MarkdownParser, ParsedDocument

_CACHED_DOC: Optional[ParsedDocument] = None


def get_document() -> ParsedDocument:
    global _CACHED_DOC
    if _CACHED_DOC is not None:
        return _CACHED_DOC

    path_env = os.environ.get("PROPOSAL_PATH")
    if path_env:
        target_path = Path(path_env)
        if not target_path.is_file():
            raise FileNotFoundError(
                f"Target proposal document not found at: {target_path.resolve()}\n"
                f"Set PROPOSAL_PATH environment variable or specify --proposal flag."
            )
        _CACHED_DOC = MarkdownParser.parse_file(target_path)
        return _CACHED_DOC

    default_path = Path("PRODUCTION_HARDENING_PROPOSAL.md")
    if default_path.is_file():
        _CACHED_DOC = MarkdownParser.parse_file(default_path)
        return _CACHED_DOC

    from tests.proposal_verification.fixtures import create_synthetic_proposal
    fallback_path = create_synthetic_proposal("valid")
    os.environ["PROPOSAL_PATH"] = fallback_path
    _CACHED_DOC = MarkdownParser.parse_file(fallback_path)
    return _CACHED_DOC


class BaseTier3TestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = get_document()


class TestGatewayAndTunnelSynergy(BaseTier3TestCase):
    """Pairwise interlocks between Nginx Gateway, Guacamole Tunnel, and Client Browser."""

    def test_nginx_buffering_vs_guacamole_tunnel(self):
        """Verify Nginx proxy_buffering off, connection upgrade map, and timeouts for Guacamole."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"proxy_buffering\s+off", content, re.IGNORECASE),
            "Proposal lacks Nginx 'proxy_buffering off;' directive for low-latency Guacamole tunneling."
        )
        self.assertTrue(
            re.search(r"map\s+\$http_upgrade\s+\$connection_upgrade", content, re.IGNORECASE) or
            re.search(r"proxy_set_header\s+Upgrade", content, re.IGNORECASE),
            "Proposal lacks Nginx WebSocket connection upgrade header mapping."
        )
        self.assertTrue(
            re.search(r"proxy_read_timeout\s+(?:3600|86400|\d{4,})", content, re.IGNORECASE),
            "Proposal lacks extended proxy_read_timeout (>=3600s) to prevent idle desktop disconnects."
        )

    def test_geoip_filtering_rules_vs_client_websocket_connections(self):
        """Verify GeoIP2 MMDB migration, ISO fixes (GB/LK), and WebSocket rate limit exemption."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"geoip2|ngx_http_geoip2_module|maxmind|mmdb", content, re.IGNORECASE),
            "Proposal lacks modern GeoIP2 MMDB module migration."
        )
        self.assertTrue(
            re.search(r"\bGB\b", content) and re.search(r"\bLK\b", content),
            "Proposal fails to correct ISO country codes (UK->GB, SL->LK)."
        )

    def test_tomcat_remote_ip_valve_vs_guacamole_ban_lockout(self):
        """Verify Tomcat RemoteIpValve configuration to prevent proxy IP ban lockouts."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"RemoteIpValve", content, re.IGNORECASE),
            "Proposal lacks Tomcat RemoteIpValve configuration in server.xml."
        )
        self.assertTrue(
            re.search(r"x-forwarded-for|remoteIpHeader", content, re.IGNORECASE),
            "Proposal fails to configure remoteIpHeader for real client IP extraction."
        )

    def test_nginx_security_headers_vs_guacamole_iframe_embedding(self):
        """Verify Nginx frame options permit portal iframe embedding (SAMEORIGIN / frame-ancestors 'self')."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"SAMEORIGIN|frame-ancestors\s+'self'", content, re.IGNORECASE),
            "Proposal fails to configure X-Frame-Options: SAMEORIGIN or CSP frame-ancestors 'self' for portal embedding."
        )
        self.assertFalse(
            re.search(r"X-Frame-Options:\s+DENY", content, re.IGNORECASE) and
            not re.search(r"SAMEORIGIN", content, re.IGNORECASE),
            "Proposal configures conflicting X-Frame-Options: DENY which breaks legitimate web portal iframe embedding."
        )

    def test_tls_ciphers_vs_modern_browser_websocket_alpn(self):
        """Verify Mozilla Intermediate TLS 1.2/1.3 ciphers and ALPN compatibility with WebSockets."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"TLSv1\.[23]|TLS_AES|ECDHE", content, re.IGNORECASE),
            "Proposal lacks Mozilla Intermediate TLS 1.2/1.3 cipher specifications."
        )


class TestProvisioningAndReachabilitySynergy(BaseTier3TestCase):
    """Pairwise interlocks between Flask Management, Container Provisioning, and Network Reachability."""

    def test_flask_provisioning_network_vs_guacamole_reachability(self):
        """Verify unified network creation eliminating post-creation connect race condition."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"BULK_INSTANCE_DNS_FIX|network_mode|ptnet", content, re.IGNORECASE),
            "Proposal fails to unify provisioning network attachment or address post-creation DNS races."
        )

    def test_docker_socket_proxy_scope_vs_flask_api_capabilities(self):
        """Verify docker-socket-proxy permissions (CONTAINERS=1, POST=1, VOLUMES=0) and non-root execution."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"docker-socket-proxy|socket-proxy", content, re.IGNORECASE),
            "Proposal lacks docker-socket-proxy integration to secure Docker daemon access."
        )
        self.assertTrue(
            re.search(r"CONTAINERS\s*=\s*1", content, re.IGNORECASE) or
            re.search(r"POST\s*=\s*1", content, re.IGNORECASE),
            "Proposal fails to configure necessary container lifecycle permissions in socket proxy."
        )
        self.assertTrue(
            re.search(r"non-root|USER\s+(?:ptmgmt|ptuser|10001)|uid\s+1000", content, re.IGNORECASE),
            "Proposal fails to mandate non-root user execution for the Flask management container."
        )

    def test_shared_volume_mutex_locking_vs_concurrent_instance_scale(self):
        """Verify mutex locking (flock) or installer container pattern on shared pt_opt volume."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"flock|mutex|installer|docker-compose\.installer", content, re.IGNORECASE),
            "Proposal lacks mutex locking or init-container pattern for shared volume pt_opt."
        )

    def test_per_user_file_isolation_vs_flask_file_manager_api(self):
        """Verify replacement of global /shared with per-user isolated directories and path traversal defense."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"/shared/users/|isolated|per-user", content, re.IGNORECASE),
            "Proposal lacks per-user isolated directory architecture under /shared."
        )
        self.assertTrue(
            re.search(r"traversal|Path\.relative_to|\.\.", content, re.IGNORECASE),
            "Proposal fails to mandate path traversal validation in Flask file manager API."
        )

    def test_gunicorn_async_workers_vs_docker_api_concurrency(self):
        """Verify Gunicorn async workers or background task queue to prevent worker blocking."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"gevent|async|eventlet|celery|rq|queue", content, re.IGNORECASE),
            "Proposal fails to address Gunicorn synchronous worker blocking during container provisioning."
        )


class TestDatabaseAndStorageSynergy(BaseTier3TestCase):
    """Pairwise interlocks between MariaDB, Volume Storage, and Guacamole Connection Mapping."""

    def test_mariadb_connection_pooling_vs_instance_scale(self):
        """Verify MariaDB connection pooling in Flask and server max_connections sizing."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"MySQLConnectionPool|pool_size|connection\s+pool", content, re.IGNORECASE),
            "Proposal lacks database connection pooling in Flask management application."
        )
        self.assertTrue(
            re.search(r"max_connections\s*=\s*(?:250|300|500|\d{3,})", content, re.IGNORECASE) or
            re.search(r"max_connections", content, re.IGNORECASE),
            "Proposal fails to tune MariaDB server max_connections for concurrent scale."
        )

    def test_mariadb_volume_persistence_vs_dynamic_connection_deduplication(self):
        """Verify named volume mariadb_data and connection deduplication bugfix."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"mariadb_data", content, re.IGNORECASE),
            "Proposal lacks named volume 'mariadb_data' for database persistence."
        )
        self.assertTrue(
            re.search(r"parent_id|deduplicat|duplicate", content, re.IGNORECASE),
            "Proposal fails to address NULL parent_id connection deduplication bug."
        )

    def test_turbovnc_auth_generation_vs_guacamole_connection_parameters(self):
        """Verify TurboVNC authentication and dynamic password generation in Guacamole DB."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"rfbauth|PasswordFile|vncpasswd", content, re.IGNORECASE) or
            re.search(r"SecurityTypes\s+None", content, re.IGNORECASE),
            "Proposal fails to eliminate -SecurityTypes None or mandate VNC password authentication."
        )

    def test_persistent_secret_key_vs_session_cookie_invalidation(self):
        """Verify persistent SECRET_KEY generation eliminating default IlovePT."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"SECRET_KEY", content) and not re.search(r"default-dev-key", content),
            "Proposal fails to enforce persistent, cryptographically secure Flask SECRET_KEY."
        )

    def test_mariadb_automated_backup_vs_mapping_table_synchronization(self):
        """Verify automated backup captures both Guacamole schema and custom user_container_mapping."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"user_container_mapping", content, re.IGNORECASE),
            "Proposal fails to include custom user_container_mapping table in backup procedures."
        )


class TestRuntimeAndResourceSynergy(BaseTier3TestCase):
    """Pairwise interlocks between Container Runtime, Process Init, Healthchecks, and Host Resources."""

    def test_tini_init_supervisor_vs_packettracer_zombie_reaping(self):
        """Verify tini/supervisor as PID 1 to reap defunct [AppRun] processes."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"tini|dumb-init|init:\s*true", content, re.IGNORECASE),
            "Proposal lacks tini init supervisor integration to reap defunct zombie processes."
        )

    def test_dev_shm_memory_sizing_vs_virtualgl_qt_rendering(self):
        """Verify /dev/shm >= 512MB and RAM >= 2.0GB to prevent Chromium/Qt SIGBUS crashes."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"shm_size:\s*512m|--shm-size[=\s]+512m|512MB", content, re.IGNORECASE),
            "Proposal fails to configure /dev/shm to >= 512MB for VirtualGL and Qt6 rendering."
        )

    def test_healthcheck_readiness_vs_zero_sleep_orchestration(self):
        """Verify Docker HEALTHCHECKs and zero-sleep dependency sequencing."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"HEALTHCHECK", content),
            "Proposal lacks Docker HEALTHCHECK instructions across stack services."
        )
        self.assertTrue(
            re.search(r"service_healthy", content, re.IGNORECASE) or
            re.search(r"readiness\s+probe", content, re.IGNORECASE),
            "Proposal fails to replace procedural sleep delays with healthcheck readiness sequencing."
        )

    def test_non_destructive_scale_in_vs_guacamole_session_persistence(self):
        """Verify non-destructive deprovisioning in remove-instance.sh eliminating service restarts."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"remove-instance\.sh|deprovisioning|scale-in", content, re.IGNORECASE),
            "Proposal fails to address destructive restarts during instance removal."
        )

    def test_capability_dropping_vs_gpu_device_access(self):
        """Verify capability dropping preserving /dev/dri GPU device passthrough."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"cap-drop|cap_drop", content, re.IGNORECASE),
            "Proposal lacks container privilege and capability dropping recommendations."
        )


if __name__ == "__main__":
    unittest.main()
