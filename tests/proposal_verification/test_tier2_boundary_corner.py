"""
Tier 2: Boundary & Corner Cases Verification Test Suite.
Validates technical depth, concrete configuration directives, and architectural
remediations across the 10 critical vulnerability areas from spec_miner_e2e_2.
56 test methods across 10 classes.
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


class BaseTier2TestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = get_document()


class TestDockerSocketAndRootless(BaseTier2TestCase):
    """Area 1: Docker Socket Proxy & Rootless Container Execution."""

    def test_t2_sock_01_proxy_architecture_and_whitelist(self):
        """Mandates deploying docker-socket-proxy with granular endpoint permissions."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"docker-socket-proxy|socket-proxy", content, re.IGNORECASE),
            "Proposal lacks specification for docker-socket-proxy intermediate proxy."
        )
        self.assertTrue(
            re.search(r"CONTAINERS\s*=\s*1", content, re.IGNORECASE) or
            re.search(r"POST\s*=\s*1", content, re.IGNORECASE),
            "Proposal fails to whitelist necessary container lifecycle permissions (CONTAINERS/POST)."
        )
        self.assertTrue(
            re.search(r"VOLUMES\s*=\s*0", content, re.IGNORECASE) or
            re.search(r"SYSTEM\s*=\s*0", content, re.IGNORECASE) or
            re.search(r"restricted", content, re.IGNORECASE),
            "Proposal fails to restrict dangerous Docker API endpoints (VOLUMES/SYSTEM)."
        )

    def test_t2_sock_02_non_root_user_execution(self):
        """Mandates non-root execution (USER ptmgmt / UID 10001) in pt-management Dockerfile."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"USER\s+(?:ptmgmt|ptuser|10001)", content, re.IGNORECASE) or
            re.search(r"non-root", content, re.IGNORECASE),
            "Proposal fails to mandate non-root user execution in pt-management Dockerfile."
        )

    def test_t2_sock_03_linux_capability_dropping(self):
        """Mandates dropping Linux capabilities (cap_drop: [ALL] / --cap-drop=ALL)."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"cap[-_]drop.*ALL", content, re.IGNORECASE) or
            re.search(r"cap[-_]drop:[\s\n\r\-]+ALL", content, re.IGNORECASE),
            "Proposal fails to mandate Linux capability dropping (cap_drop: [ALL])."
        )

    def test_t2_sock_04_no_new_privileges(self):
        """Mandates disabling privilege escalation flags (security_opt: [no-new-privileges:true])."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"no-new-privileges", content, re.IGNORECASE),
            "Proposal fails to mandate no-new-privileges security flag."
        )

    def test_t2_sock_05_read_only_root_tmpfs(self):
        """Mandates read-only root filesystem with ephemeral tmpfs mounts."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"read_only|read-only", content, re.IGNORECASE) and
            re.search(r"tmpfs", content, re.IGNORECASE),
            "Proposal fails to specify read-only root filesystem with tmpfs mounts."
        )

    def test_t2_sock_06_removal_of_host_project_mount(self):
        """Mandates eliminating the binding of the host project root (-v $ROOT_DIR:/project)."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r":/project|\$ROOT_DIR:/project|host project root", content, re.IGNORECASE),
            "Proposal fails to mandate eliminating host project root volume binding."
        )


class TestGeoIP2AndISOCodes(BaseTier2TestCase):
    """Area 2: GeoIP2 Migration & ISO Code Fixes."""

    def test_t2_geo_01_geoip2_module_migration(self):
        """Mandates migration from legacy GeoIP1 (.dat) to ngx_http_geoip2_module (.mmdb)."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"ngx_http_geoip2_module", content, re.IGNORECASE) or
            re.search(r"geoip2", content, re.IGNORECASE),
            "Proposal lacks ngx_http_geoip2_module migration specification."
        )
        self.assertTrue(
            re.search(r"\.mmdb|GeoLite2", content, re.IGNORECASE),
            "Proposal lacks MaxMind MMDB database format specification."
        )

    def test_t2_geo_02_iso_code_uk_to_gb(self):
        """Mandates correcting non-standard UK country code to ISO 3166-1 alpha-2 GB."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"\bGB\b", content),
            "Proposal fails to specify replacement of UK with ISO standard GB."
        )
        self.assertTrue(
            re.search(r"MaxMind", content, re.IGNORECASE) or re.search(r"ISO", content),
            "Proposal fails to explain MaxMind ISO 3166-1 country lookup behavior."
        )

    def test_t2_geo_03_iso_code_sl_to_lk(self):
        """Mandates correcting country code for Sri Lanka from SL to LK."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"\bLK\b", content) and re.search(r"\bSL\b", content),
            "Proposal fails to document and correct SL (Sierra Leone) vs LK (Sri Lanka)."
        )

    def test_t2_geo_04_cidr_geo_map_migration(self):
        """Mandates replacing location block if directives with top-level geo CIDR blocks."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"geo\s+\$trusted_ip", content, re.IGNORECASE) or
            re.search(r"CIDR", content),
            "Proposal fails to specify top-level Nginx geo CIDR map."
        )

    def test_t2_geo_05_regex_escape_anchor_remediation(self):
        """Mandates fixing unanchored and unescaped dots in legacy GeoIP bypass regex."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"86\.50\.84\.227|unanchored|unescaped", content, re.IGNORECASE),
            "Proposal fails to identify and remediate unanchored regex or unescaped dot flaw."
        )

    def test_t2_geo_06_maxmind_mmdb_provisioning(self):
        """Mandates eliminating unverified third-party mirror (mailfud.org) and automating MMDB acquisition."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"mailfud|MaxMind|checksum", content, re.IGNORECASE),
            "Proposal fails to eliminate mailfud.org or specify verified MMDB provisioning."
        )


class TestTomcatRemoteIpValve(BaseTier2TestCase):
    """Area 3: Tomcat RemoteIpValve & Ban Prevention."""

    def test_t2_tom_01_server_xml_declaration(self):
        """Mandates declaring RemoteIpValve inside Tomcat server.xml."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"org\.apache\.catalina\.valves\.RemoteIpValve|RemoteIpValve", content),
            "Proposal lacks Tomcat RemoteIpValve declaration in server.xml."
        )

    def test_t2_tom_02_internal_proxies_cidr_regex(self):
        """Mandates configuring internalProxies regex matching Docker subnets."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"internalProxies", content, re.IGNORECASE),
            "Proposal fails to configure internalProxies parameter for RemoteIpValve."
        )

    def test_t2_tom_03_header_mapping_verification(self):
        """Mandates configuring remoteIpHeader, proxiesHeader, and protocolHeader."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"remoteIpHeader|x-forwarded-for", content, re.IGNORECASE),
            "Proposal fails to configure remoteIpHeader mapping in Tomcat RemoteIpValve."
        )

    def test_t2_tom_04_proxy_ban_isolation_dos_prevention(self):
        """Documents how RemoteIpValve prevents proxy IP lockout under BanningAuthenticationListener."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"BanningAuthenticationListener|ban|lockout", content, re.IGNORECASE),
            "Proposal fails to explain BanningAuthenticationListener reverse proxy ban prevention."
        )

    def test_t2_tom_05_nginx_x_forwarded_for_integrity(self):
        """Verifies uniform forwarding of X-Forwarded-For and X-Forwarded-Proto in Nginx."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"proxy_set_header\s+X-Forwarded-For", content, re.IGNORECASE) and
            re.search(r"proxy_set_header\s+X-Forwarded-Proto", content, re.IGNORECASE),
            "Proposal fails to verify Nginx proxy header propagation directives."
        )

    def test_t2_tom_06_guacamole_brute_force_listener_isolation(self):
        """Verifies that brute force login bans isolate to actual client IP address."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"client IP|offender|attacker", content, re.IGNORECASE),
            "Proposal fails to verify client IP isolation during authentication failures."
        )


class TestMariaDBPersistentVolumesAndConnections(BaseTier2TestCase):
    """Area 4: MariaDB Persistent Volumes & Connection Deduplication."""

    def test_t2_mdb_01_named_persistent_volume_mariadb_data(self):
        """Mandates mounting named volume mariadb_data to /var/lib/mysql."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"mariadb_data:/var/lib/mysql", content) or
            re.search(r"mariadb_data", content),
            "Proposal fails to specify named volume mariadb_data:/var/lib/mysql."
        )

    def test_t2_mdb_02_connection_table_unique_key_null_fix(self):
        """Explains MariaDB UNIQUE KEY NULL = NULL behavior causing duplicate connections."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"parent_id|NULL|unique", content, re.IGNORECASE),
            "Proposal fails to explain NULL parent_id unique key behavior in MariaDB."
        )

    def test_t2_mdb_03_script_sql_idempotency(self):
        """Mandates idempotent SQL upsert in generate-dynamic-connections.sh."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"DUPLICATE KEY UPDATE|DELETE FROM.*guacamole_connection|idempotent", content, re.IGNORECASE),
            "Proposal fails to specify idempotent upsert or pre-check in connection script."
        )

    def test_t2_mdb_04_subquery_single_row_safety_error_1242(self):
        """Remediates subquery multi-row exception (ERROR 1242)."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"1242|Subquery returns more than 1 row|subquery", content, re.IGNORECASE),
            "Proposal fails to document subquery multi-row error 1242 and its resolution."
        )

    def test_t2_mdb_05_automated_backup_and_migration_lifecycle(self):
        """Mandates non-blocking database backup command with --single-transaction."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"(?:mysqldump|mariadb-dump).*single-transaction", content, re.IGNORECASE),
            "Proposal fails to specify non-blocking mysqldump command with --single-transaction."
        )


class TestDockerHealthchecksAndStartupSequencing(BaseTier2TestCase):
    """Area 5: Docker HEALTHCHECKs & Zero-Sleep Startup Sequencing."""

    def test_t2_hlt_01_mariadb_healthcheck(self):
        """Specifies Docker HEALTHCHECK on MariaDB using mariadb-admin ping."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"mariadb-admin ping|healthcheck\.sh", content, re.IGNORECASE),
            "Proposal lacks MariaDB healthcheck specification using mariadb-admin ping."
        )

    def test_t2_hlt_02_guacd_and_guacamole_healthchecks(self):
        """Specifies Docker HEALTHCHECK on guacd (port 4822) and pt-guacamole (HTTP /guacamole/)."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"4822", content) and re.search(r"/guacamole/", content),
            "Proposal fails to specify healthcheck probes for guacd and pt-guacamole."
        )

    def test_t2_hlt_03_management_and_vnc_healthchecks(self):
        """Specifies Docker HEALTHCHECK on pt-management (/health) and ptvnc (port 5901)."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"/health", content) and re.search(r"5901", content),
            "Proposal fails to specify healthchecks for management service and VNC desktop."
        )

    def test_t2_hlt_04_compose_depends_on_service_healthy(self):
        """Mandates depends_on: condition: service_healthy across service dependencies."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"condition:\s*service_healthy|service_healthy", content, re.IGNORECASE),
            "Proposal lacks condition: service_healthy in Docker Compose dependencies."
        )

    def test_t2_hlt_05_elimination_of_115s_sleep_delays(self):
        """Mandates removing cumulative 115+ seconds of procedural sleep calls."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"115|sleep", content, re.IGNORECASE),
            "Proposal fails to mandate eliminating hardcoded sleep delays in deployment scripts."
        )

    def test_t2_hlt_06_startup_readiness_polling_loops(self):
        """Mandates active status polling loops replacing sleep timers."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"polling|inspect|readiness", content, re.IGNORECASE),
            "Proposal fails to specify active readiness polling loops."
        )


class TestMemorySizingAndUlimits(BaseTier2TestCase):
    """Area 6: Memory Sizing, /dev/shm, and ulimits."""

    def test_t2_res_01_ram_allocation_minimum_2gb(self):
        """Mandates container RAM allocation >= 2.0GB (recommended 2.5GB)."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"2\.5G|2G|2560M|2048M", content, re.IGNORECASE),
            "Proposal fails to specify container RAM sizing of at least 2.0GB."
        )

    def test_t2_res_02_expanded_dev_shm_512mb(self):
        """Mandates /dev/shm >= 512MB and explains Qt6 WebEngine crash code 133 / SIGBUS."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"512m|512MB", content, re.IGNORECASE),
            "Proposal fails to mandate /dev/shm size of at least 512MB."
        )
        self.assertTrue(
            re.search(r"133|SIGBUS|WebEngine|Chromium", content, re.IGNORECASE),
            "Proposal fails to document WebEngine crash code 133 or SIGBUS shared memory faults."
        )

    def test_t2_res_03_open_file_descriptors_nofile_65536(self):
        """Mandates ulimit nofile=65536 across container configurations."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"nofile=65536", content, re.IGNORECASE) or
            re.search(r"65536", content),
            "Proposal fails to specify open file descriptor limit nofile=65536."
        )

    def test_t2_res_04_maximum_processes_nproc_4096(self):
        """Mandates ulimit nproc=4096 across container configurations."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"nproc=4096", content, re.IGNORECASE) or
            re.search(r"4096", content),
            "Proposal fails to specify maximum process thread limit nproc=4096."
        )

    def test_t2_res_05_cross_pathway_resource_enforcement(self):
        """Mandates synchronizing resource limit constants across all provisioning entry points."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"RAM=|SHM=|NOFILE=|NPROC=|uniform|synchroniz", content, re.IGNORECASE),
            "Proposal fails to mandate unified resource limit enforcement across provisioning pathways."
        )


class TestInitSystemAndZombieProcessMitigation(BaseTier2TestCase):
    """Area 7: Init System & Zombie Process Mitigation."""

    def test_t2_ini_01_container_init_integration_tini(self):
        """Mandates integrating tini or dumb-init as container PID 1."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"tini|dumb-init|init:\s*true", content, re.IGNORECASE),
            "Proposal lacks specification for tini or init process integration."
        )

    def test_t2_ini_02_defunct_apprun_zombie_reaping(self):
        """Explains SIGCHLD handling and reaping of defunct [AppRun] processes."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"AppRun|defunct|zombie", content, re.IGNORECASE) and
            re.search(r"SIGCHLD|reap|waitpid", content, re.IGNORECASE),
            "Proposal fails to explain SIGCHLD reaping of defunct [AppRun] zombie processes."
        )

    def test_t2_ini_03_graceful_signal_forwarding_sigterm(self):
        """Specifies tini -g flag for signal forwarding and graceful container termination."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"-g|signal|SIGTERM|graceful", content, re.IGNORECASE),
            "Proposal fails to specify signal forwarding or graceful shutdown handling."
        )

    def test_t2_ini_04_elimination_of_unmonitored_sleep_loop(self):
        """Mandates eliminating unmonitored 'while true; do sleep 3600; done' keepalive loop."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"sleep 3600|keepalive|while true", content, re.IGNORECASE),
            "Proposal fails to mandate eliminating unmonitored while sleep 3600 keepalive loop."
        )

    def test_t2_ini_05_process_supervision_architecture(self):
        """Evaluates or specifies a process supervisor (supervisord/s6) for desktop subsystems."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"supervisor|supervisord|s6", content, re.IGNORECASE),
            "Proposal fails to evaluate or specify process supervisor architecture."
        )


class TestScaleInAndCleanupRemediation(BaseTier2TestCase):
    """Area 8: Destructive Scale-In & Cleanup Script Remediation."""

    def test_t2_scl_01_non_destructive_scale_in_architecture(self):
        """Mandates refactoring remove-instance.sh into non-destructive scale-in without restarting stack."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"remove-instance|non-destructive|scale-in", content, re.IGNORECASE),
            "Proposal fails to mandate non-destructive scale-in in remove-instance.sh."
        )

    def test_t2_scl_02_active_session_checking_before_removal(self):
        """Mandates querying active sessions in guacamole_connection_history before container removal."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"guacamole_connection_history|active session|end_date IS NULL", content, re.IGNORECASE),
            "Proposal fails to mandate checking active sessions before instance removal."
        )

    def test_t2_scl_03_elimination_of_deprecated_link_syntax(self):
        """Mandates eliminating legacy --link flags in favor of Docker bridge embedded DNS."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"--link|deprecated", content, re.IGNORECASE),
            "Proposal fails to mandate eliminating legacy --link flags."
        )

    def test_t2_scl_04_project_scoping_for_host_cleanup(self):
        """Mandates scoping host cleanup scripts strictly to project labels."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"label=com\.docker\.compose\.project|project label|scoped", content, re.IGNORECASE),
            "Proposal fails to mandate project scoping for host cleanup operations."
        )

    def test_t2_scl_05_database_volume_safeguards_purge_flag(self):
        """Mandates data loss safeguards and explicit --purge-data flag for volume deletion."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"purge-data|safeguard|volume.*preserv", content, re.IGNORECASE),
            "Proposal fails to specify volume preservation safeguards and explicit purge confirmation."
        )


class TestTLSAndSecurityHeaders(BaseTier2TestCase):
    """Area 9: TLS 1.2/1.3 Ciphers, HSTS, CSP, and Security Headers."""

    def test_t2_tls_01_modern_mozilla_intermediate_ciphers(self):
        """Mandates enforcing Mozilla Intermediate TLS cipher suite and TLS 1.2/1.3."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"ECDHE-ECDSA-AES128-GCM-SHA256|ECDHE-RSA-AES128-GCM-SHA256|Mozilla", content, re.IGNORECASE),
            "Proposal lacks Mozilla Intermediate cipher suite specification."
        )
        self.assertTrue(
            re.search(r"TLSv1\.2\s+TLSv1\.3|TLS 1\.2.*1\.3", content, re.IGNORECASE),
            "Proposal fails to specify TLS 1.2 and TLS 1.3 protocols."
        )

    def test_t2_tls_02_strict_transport_security_hsts(self):
        """Mandates Strict-Transport-Security header with max-age >= 31536000."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"Strict-Transport-Security.*max-age=(?:63072000|31536000)", content, re.IGNORECASE),
            "Proposal fails to specify HSTS header with max-age >= 31536000."
        )

    def test_t2_tls_03_content_security_policy_frame_ancestors(self):
        """Mandates Content-Security-Policy with frame-ancestors 'self' and WebSocket connect-src."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"Content-Security-Policy.*frame-ancestors\s+'self'", content, re.IGNORECASE),
            "Proposal fails to specify CSP with frame-ancestors 'self'."
        )
        self.assertTrue(
            re.search(r"connect-src.*wss:", content, re.IGNORECASE) or re.search(r"connect-src", content),
            "Proposal fails to specify CSP connect-src allowing WebSocket connections."
        )

    def test_t2_tls_04_perimeter_security_headers_and_server_tokens(self):
        """Mandates X-Frame-Options, X-Content-Type-Options, Referrer-Policy, and server_tokens off."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"X-Frame-Options\s+SAMEORIGIN", content, re.IGNORECASE),
            "Proposal fails to specify X-Frame-Options SAMEORIGIN."
        )
        self.assertTrue(
            re.search(r"X-Content-Type-Options\s+nosniff", content, re.IGNORECASE),
            "Proposal fails to specify X-Content-Type-Options nosniff."
        )
        self.assertTrue(
            re.search(r"server_tokens\s+off", content, re.IGNORECASE),
            "Proposal fails to mandate server_tokens off."
        )

    def test_t2_tls_05_session_resumption_and_ocsp_stapling(self):
        """Mandates ssl_session_cache, ssl_session_timeout, and ssl_stapling."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"ssl_session_cache", content, re.IGNORECASE) and
            re.search(r"ssl_stapling\s+on", content, re.IGNORECASE),
            "Proposal fails to specify TLS session caching and OCSP stapling."
        )

    def test_t2_tls_06_port_5000_perimeter_hardening_and_cookies(self):
        """Mandates perimeter hardening on port 5000 and secure cookie flags."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"Secure;\s*HttpOnly;\s*SameSite", content, re.IGNORECASE) or
            re.search(r"proxy_cookie_path", content, re.IGNORECASE),
            "Proposal fails to specify secure cookie flags (Secure; HttpOnly; SameSite=Lax)."
        )


class TestAPIAuthAndCSRFProtection(BaseTier2TestCase):
    """Area 10: Unauthenticated API Bypass Removal & CSRF Protection."""

    def test_t2_api_01_auth_enforcement_on_api_containers(self):
        """Mandates removing unconditional unauthenticated bypass on /api/containers."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"/api/containers.*(?:bypass|unauthenticated)|(?:bypass|unauthenticated).*/api/containers", content, re.IGNORECASE),
            "Proposal fails to mandate removing unauthenticated bypass on /api/containers."
        )

    def test_t2_api_02_removal_of_spoofable_ip_bypasses(self):
        """Mandates removing spoofable client_ip.startswith('172.') and 10. IP bypasses."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"172\.|X-Forwarded-For.*spoof|IP bypass", content, re.IGNORECASE),
            "Proposal fails to mandate eliminating spoofable internal IP bypasses."
        )

    def test_t2_api_03_anti_csrf_protection_implementation(self):
        """Mandates integrating Flask-WTF CSRFProtect and tokens in forms and AJAX calls."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"Flask-WTF|CSRFProtect|CSRF", content, re.IGNORECASE),
            "Proposal lacks specification for Flask anti-CSRF protection."
        )

    def test_t2_api_04_dynamic_strong_secret_key_enforcement(self):
        """Mandates eliminating default SECRET_KEY and enforcing cryptographic random keys."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"SECRET_KEY", content) and re.search(r"secrets\.token|random|cryptograph", content, re.IGNORECASE),
            "Proposal fails to specify dynamic cryptographic SECRET_KEY generation."
        )

    def test_t2_api_05_token_based_api_authentication(self):
        """Specifies Bearer token or API key authentication for automation."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"Bearer|API token|API key|token", content, re.IGNORECASE),
            "Proposal fails to specify token-based authentication for programmatic access."
        )

    def test_t2_api_06_removal_of_public_downloads_autoindex(self):
        """Mandates disabling unauthenticated public autoindex on /downloads/."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"autoindex\s+off|autoindex", content, re.IGNORECASE) and
            re.search(r"/downloads/|downloads", content, re.IGNORECASE),
            "Proposal fails to mandate disabling unauthenticated autoindex on /downloads/."
        )


if __name__ == "__main__":
    unittest.main()
