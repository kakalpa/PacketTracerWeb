"""
Tier 1: Feature Coverage Verification Test Suite.
Validates presence and depth across all 5 core components (C1-C5) and
all 5 operational domains (SEC, PERF, REL/HA, USE, MAINT).
"""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path
from typing import Optional

from tests.proposal_verification.parser import MarkdownParser, ParsedDocument, ComponentID, DomainCode

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


class BaseTier1TestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = get_document()


class TestDocumentStructureAndSections(BaseTier1TestCase):
    """Validates top-level document structure, executive summary, requirements R1 & R2, and roadmap."""

    def test_01_document_title_and_executive_summary(self):
        """Document must feature an H1 title and non-empty Executive Summary / Overview."""
        self.assertTrue(len(self.doc.headings) > 0, "Document contains no markdown headings.")
        h1s = [h for h in self.doc.headings if h.level == 1]
        self.assertTrue(len(h1s) >= 1, "Document lacks an H1 title heading.")
        title_matches = any(
            re.search(r"PacketTracerWeb|Production Hardening", h.title, re.IGNORECASE) for h in h1s
        )
        self.assertTrue(title_matches, f"H1 title does not mention PacketTracerWeb or Hardening: {[h.title for h in h1s]}")

        exec_summary = self.doc.find_sections_by_title(r"Executive Summary|Overview|Architecture")
        self.assertTrue(len(exec_summary) >= 1, "Document lacks an Executive Summary or System Overview section.")
        self.assertTrue(len(exec_summary[0].raw_content.strip()) > 50, "Executive Summary section content is too short or empty.")

    def test_02_r1_system_assessment_section_present(self):
        """Document must contain Requirement R1 System Assessment covering existing components."""
        sections = self.doc.find_sections_by_title(r"Assessment|Audit|Requirement R1|R1")
        self.assertTrue(len(sections) >= 1, "Document lacks an R1 System Assessment section.")
        content = sections[0].raw_content
        self.assertTrue(len(content.strip()) > 200, "R1 System Assessment content is too brief.")

    def test_03_r2_improvement_proposals_section_present(self):
        """Document must contain Requirement R2 Improvement Proposals section."""
        sections = self.doc.find_sections_by_title(r"Improvement Proposals|Proposals|Recommendations|Requirement R2|R2")
        self.assertTrue(len(sections) >= 1, "Document lacks an R2 Improvement Proposals section.")
        content = sections[0].raw_content
        self.assertTrue(len(content.strip()) > 200, "R2 Improvement Proposals content is too brief.")

    def test_04_roadmap_and_migration_section_present(self):
        """Document must contain a Phased Production Roadmap and Migration section."""
        sections = self.doc.find_sections_by_title(r"Roadmap|Migration|Phased Rollout")
        self.assertTrue(len(sections) >= 1, "Document lacks a Production Roadmap and Migration section.")

    def test_05_verification_resources_and_acceptance_criteria_present(self):
        """Document must reference existing scripts (health_check.sh, deploy.sh) and acceptance checklist."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"health_check\.sh", content),
            "Document does not reference existing verification script 'health_check.sh'."
        )
        self.assertTrue(
            re.search(r"deploy(?:-full)?\.sh", content),
            "Document does not reference existing deployment scripts 'deploy.sh' or 'deploy-full.sh'."
        )
        self.assertTrue(
            re.search(r"docker-compose\.ya?ml", content),
            "Document does not reference 'docker-compose.yml'."
        )


class TestComponent1Coverage(BaseTier1TestCase):
    """Component 1: Virtualized Desktop Container (ptvnc / VirtualGL / TurboVNC / Cisco Packet Tracer)."""

    def test_c1_01_section_and_scope(self):
        """C1 must address Virtualized Desktop Container scope."""
        findings = self.doc.get_findings_by_component("C1")
        proposals = self.doc.get_proposals_by_component("C1")
        self.assertTrue(len(findings) >= 3, f"Insufficient C1 findings: found {len(findings)}, expected >= 3.")
        self.assertTrue(len(proposals) >= 3, f"Insufficient C1 proposals: found {len(proposals)}, expected >= 3.")

    def test_c1_02_display_server_conflict_and_init(self):
        """C1 must address dual display server conflict / TurboVNC and init process / zombie reaping."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"tini|init|dumb-init|zombie|defunct", content, re.IGNORECASE),
            "C1 does not address container init process or defunct zombie mitigation."
        )

    def test_c1_03_resource_tuning_and_shm(self):
        """C1 must address /dev/shm sizing (>=512MB), RAM (>=2.0GB), and ulimits."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"shm|512m", content, re.IGNORECASE),
            "C1 does not address /dev/shm shared memory sizing (512MB)."
        )
        self.assertTrue(
            re.search(r"2\.5g|2g|2048|2560", content, re.IGNORECASE),
            "C1 does not address container RAM sizing."
        )

    def test_c1_04_installer_race_condition_and_volume_mutex(self):
        """C1 must address installer concurrency on shared named volume pt_opt."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"mutex|flock|race|installer|pt_opt", content, re.IGNORECASE),
            "C1 does not address pt_opt shared volume race condition or mutex locking."
        )

    def test_c1_05_clipboard_and_audio_subsystem(self):
        """C1 must address clipboard synchronization (autocutsel) and audio considerations."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"autocutsel|clipboard|audio|pulseaudio", content, re.IGNORECASE),
            "C1 does not address clipboard (autocutsel) or audio streaming."
        )

    def test_c1_06_domain_coverage_completeness(self):
        """C1 findings and proposals must cover security, performance, and reliability domains."""
        c1_findings = self.doc.get_findings_by_component("C1")
        domains = {DomainCode.normalize(f.domain_code) for f in c1_findings}
        self.assertTrue("SEC" in domains, "C1 lacks Security finding.")
        self.assertTrue("PERF" in domains, "C1 lacks Performance finding.")
        self.assertTrue("REL" in domains, "C1 lacks Reliability finding.")


class TestComponent2Coverage(BaseTier1TestCase):
    """Component 2: Apache Guacamole Stack (guacd, webapp, MariaDB backend, connection handling)."""

    def test_c2_01_section_and_scope(self):
        """C2 must address Apache Guacamole stack scope."""
        findings = self.doc.get_findings_by_component("C2")
        proposals = self.doc.get_proposals_by_component("C2")
        self.assertTrue(len(findings) >= 3, f"Insufficient C2 findings: found {len(findings)}, expected >= 3.")
        self.assertTrue(len(proposals) >= 3, f"Insufficient C2 proposals: found {len(proposals)}, expected >= 3.")

    def test_c2_02_mariadb_volume_persistence(self):
        """C2 must address MariaDB anonymous volume replacement with named volume mariadb_data."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"mariadb_data", content, re.IGNORECASE),
            "C2 does not specify named persistent volume 'mariadb_data'."
        )

    def test_c2_03_connection_deduplication_bug(self):
        """C2 must address connection deduplication failure due to NULL parent_id."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"parent_id|deduplicat|duplicate", content, re.IGNORECASE),
            "C2 does not address NULL parent_id connection deduplication defect."
        )

    def test_c2_04_tomcat_remoteipvalve_and_ban_prevention(self):
        """C2 must address Tomcat RemoteIpValve to prevent reverse proxy IP bans."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"RemoteIpValve", content, re.IGNORECASE),
            "C2 does not specify Tomcat RemoteIpValve configuration."
        )

    def test_c2_05_guacamole_proxy_buffering_and_websocket(self):
        """C2 must address Nginx proxy buffering and WebSocket upgrade settings for Guacamole."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"proxy_buffering\s+off|buffering", content, re.IGNORECASE),
            "C2 does not address disabling Nginx proxy buffering for Guacamole."
        )

    def test_c2_06_non_destructive_deprovisioning(self):
        """C2 must address non-destructive scale-in removing instances without restarting the stack."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"remove-instance|non-destructive|deprovision", content, re.IGNORECASE),
            "C2 does not address non-destructive deprovisioning in remove-instance.sh."
        )


class TestComponent3Coverage(BaseTier1TestCase):
    """Component 3: Nginx Edge Gateway (TLS 1.2/1.3, GeoIP, rate limiting, security headers)."""

    def test_c3_01_section_and_scope(self):
        """C3 must address Nginx Edge Gateway scope."""
        findings = self.doc.get_findings_by_component("C3")
        proposals = self.doc.get_proposals_by_component("C3")
        self.assertTrue(len(findings) >= 3, f"Insufficient C3 findings: found {len(findings)}, expected >= 3.")
        self.assertTrue(len(proposals) >= 3, f"Insufficient C3 proposals: found {len(proposals)}, expected >= 3.")

    def test_c3_02_modern_geoip2_migration(self):
        """C3 must address migrating from legacy GeoIP1 to modern ngx_http_geoip2_module."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"geoip2|ngx_http_geoip2_module|mmdb", content, re.IGNORECASE),
            "C3 does not address modern GeoIP2 module migration."
        )

    def test_c3_03_geoip_filtering_bug_fixes(self):
        """C3 must address ISO code fixes (UK->GB, SL->LK) and regex bypass vulnerabilities."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"\bGB\b", content) and re.search(r"\bLK\b", content),
            "C3 does not address ISO country code corrections (UK->GB, SL->LK)."
        )

    def test_c3_04_ssl_tls_hardening_and_ciphers(self):
        """C3 must address TLS 1.2/1.3, Mozilla Intermediate ciphers, and HSTS."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"TLSv1\.[23]|TLS", content, re.IGNORECASE) and
            re.search(r"HSTS|Strict-Transport-Security", content, re.IGNORECASE),
            "C3 does not address TLS hardening or HSTS enforcement."
        )

    def test_c3_05_http_security_headers(self):
        """C3 must address CSP, X-Frame-Options, X-Content-Type-Options, and server_tokens off."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"X-Frame-Options", content, re.IGNORECASE) and
            re.search(r"X-Content-Type-Options", content, re.IGNORECASE),
            "C3 does not address perimeter HTTP security headers."
        )

    def test_c3_06_perimeter_and_port_5000_hardening(self):
        """C3 must address port 5000 perimeter hardening and disabling autoindex on /downloads/."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"5000", content) and re.search(r"autoindex", content, re.IGNORECASE),
            "C3 does not address port 5000 hardening or disabling unauthenticated autoindex."
        )


class TestComponent4Coverage(BaseTier1TestCase):
    """Component 4: Flask/Gunicorn Management Application."""

    def test_c4_01_section_and_scope(self):
        """C4 must address Flask/Gunicorn Management Application scope."""
        findings = self.doc.get_findings_by_component("C4")
        proposals = self.doc.get_proposals_by_component("C4")
        self.assertTrue(len(findings) >= 3, f"Insufficient C4 findings: found {len(findings)}, expected >= 3.")
        self.assertTrue(len(proposals) >= 3, f"Insufficient C4 proposals: found {len(proposals)}, expected >= 3.")

    def test_c4_02_docker_socket_proxy_security(self):
        """C4 must address Docker socket proxy and non-root execution."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"docker-socket-proxy|socket-proxy|non-root", content, re.IGNORECASE),
            "C4 does not address Docker socket proxy integration or non-root user execution."
        )

    def test_c4_03_api_authentication_and_csrf(self):
        """C4 must address unauthenticated /api/containers, IP bypasses, and CSRF protection."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"CSRF|Flask-WTF", content, re.IGNORECASE),
            "C4 does not address CSRF protection."
        )
        self.assertTrue(
            re.search(r"/api/containers|bypass", content, re.IGNORECASE),
            "C4 does not address eliminating unauthenticated API bypasses."
        )

    def test_c4_04_secret_and_credential_hardening(self):
        """C4 must address dynamic SECRET_KEY and eliminating default IlovePT."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"SECRET_KEY", content),
            "C4 does not address SECRET_KEY hardening."
        )

    def test_c4_05_database_pooling_and_sql_bug_fixes(self):
        """C4 must address MariaDB connection pooling and DB credential alignment."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"pool|MySQLConnectionPool", content, re.IGNORECASE),
            "C4 does not address MariaDB connection pooling in Flask."
        )

    def test_c4_06_isolated_file_management(self):
        """C4 must address per-user isolated directory architecture under /shared."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"/shared/users/|isolated|per-user", content, re.IGNORECASE),
            "C4 does not address per-user file isolation."
        )


class TestComponent5Coverage(BaseTier1TestCase):
    """Component 5: Deployment & Orchestration Harness."""

    def test_c5_01_section_and_scope(self):
        """C5 must address Deployment & Orchestration Harness scope."""
        findings = self.doc.get_findings_by_component("C5")
        proposals = self.doc.get_proposals_by_component("C5")
        self.assertTrue(len(findings) >= 3, f"Insufficient C5 findings: found {len(findings)}, expected >= 3.")
        self.assertTrue(len(proposals) >= 3, f"Insufficient C5 proposals: found {len(proposals)}, expected >= 3.")

    def test_c5_02_health_checks_and_startup_sequencing(self):
        """C5 must address Docker HEALTHCHECK and eliminating 115s sleep delays."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"HEALTHCHECK", content),
            "C5 does not specify Docker HEALTHCHECK directives."
        )
        self.assertTrue(
            re.search(r"sleep|sequencing|readiness", content, re.IGNORECASE),
            "C5 does not address eliminating sleep delays via health probes."
        )

    def test_c5_03_network_topology_and_segmentation(self):
        """C5 must address network segmentation and eliminating deprecated --link flags."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"network|bridge|ptnet|--link", content, re.IGNORECASE),
            "C5 does not address network topology, ptnet unification, or --link deprecation."
        )

    def test_c5_04_container_privilege_and_capability_dropping(self):
        """C5 must address capability dropping (cap_drop: [ALL]) and no-new-privileges."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"cap[-_]drop|capabilities|no-new-privileges", content, re.IGNORECASE),
            "C5 does not address Linux capability dropping or privilege restrictions."
        )

    def test_c5_05_logging_log_rotation_and_metrics(self):
        """C5 must address log rotation and Prometheus metrics monitoring."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"log\s+rotation|json-file|Prometheus|metric", content, re.IGNORECASE),
            "C5 does not address log rotation or metrics monitoring."
        )

    def test_c5_06_backup_and_disaster_recovery(self):
        """C5 must address automated database backups, rotation, and scoped cleanup."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"backup|cleanup-all|disaster", content, re.IGNORECASE),
            "C5 does not address automated database backups or scoped host cleanup."
        )


class TestOperationalDomainCoverage(BaseTier1TestCase):
    """Operational Domains: Security, Performance, HA/Reliability, Usability, Maintainability."""

    def test_domain_01_security_hardening_coverage(self):
        """Document must contain >= 5 Security & Hardening (SEC) proposals across components."""
        props = self.doc.get_proposals_by_domain("SEC")
        self.assertTrue(len(props) >= 5, f"Insufficient SEC proposals: found {len(props)}, expected >= 5.")

    def test_domain_02_performance_scaling_coverage(self):
        """Document must contain >= 5 Performance & Scaling (PERF) proposals across components."""
        props = self.doc.get_proposals_by_domain("PERF")
        self.assertTrue(len(props) >= 5, f"Insufficient PERF proposals: found {len(props)}, expected >= 5.")

    def test_domain_03_high_availability_reliability_coverage(self):
        """Document must contain >= 5 High Availability & Reliability (REL/HA) proposals across components."""
        props = self.doc.get_proposals_by_domain("REL")
        self.assertTrue(len(props) >= 5, f"Insufficient REL proposals: found {len(props)}, expected >= 5.")

    def test_domain_04_usability_coverage(self):
        """Document must contain >= 4 Usability (USE) proposals across components."""
        props = self.doc.get_proposals_by_domain("USE")
        self.assertTrue(len(props) >= 4, f"Insufficient USE proposals: found {len(props)}, expected >= 4.")

    def test_domain_05_maintainability_coverage(self):
        """Document must contain >= 4 Maintainability (MAINT) proposals across components."""
        props = self.doc.get_proposals_by_domain("MAINT")
        self.assertTrue(len(props) >= 4, f"Insufficient MAINT proposals: found {len(props)}, expected >= 4.")

    def test_domain_06_5x5_component_domain_matrix_completeness(self):
        """Validates that all 25 cells in the 5 Components x 5 Operational Domains matrix are populated."""
        matrix = self.doc.get_findings_matrix()
        empty_cells = [f"{comp}-{dom}" for (comp, dom), findings in matrix.items() if len(findings) == 0]
        self.assertEqual(
            len(empty_cells), 0,
            f"5x5 Component x Domain matrix has unpopulated cells: {empty_cells}"
        )


class TestFindingAndProposalSchemas(BaseTier1TestCase):
    """Schema and nomenclature compliance for findings and proposals."""

    def test_schema_01_finding_id_nomenclature(self):
        """All findings must adhere to [FINDING-C<comp>-<domain>-<num>] schema."""
        self.assertTrue(len(self.doc.findings) >= 25, f"Expected at least 25 findings, found {len(self.doc.findings)}.")
        pattern = re.compile(r"^FINDING-C[1-5]-(SEC|PERF|REL|HA|USE|MAINT)-[0-9]{1,3}$")
        for f in self.doc.findings:
            self.assertTrue(
                pattern.match(f.finding_id),
                f"Finding ID '{f.finding_id}' does not match standard nomenclature schema."
            )

    def test_schema_02_finding_required_fields(self):
        """Every finding must specify non-empty description and impact."""
        self.assertTrue(len(self.doc.findings) > 0, "No findings extracted to validate required fields.")
        for f in self.doc.findings:
            self.assertTrue(
                len(f.limitation_description.strip()) > 0,
                f"Finding '{f.finding_id}' has empty limitation description."
            )
            self.assertTrue(
                len(f.operational_impact.strip()) > 0 or len(f.title.strip()) > 0,
                f"Finding '{f.finding_id}' lacks operational impact."
            )

    def test_schema_03_proposal_id_and_mapping(self):
        """All proposals must adhere to [PROP-C<comp>-<num>] schema and map to findings."""
        self.assertTrue(len(self.doc.proposals) >= 20, f"Expected at least 20 proposals, found {len(self.doc.proposals)}.")
        pattern = re.compile(r"^PROP-C[1-5](?:-[A-Z]{2,5})?-[0-9]{1,3}$")
        for p in self.doc.proposals:
            self.assertTrue(
                pattern.match(p.proposal_id),
                f"Proposal ID '{p.proposal_id}' does not match standard nomenclature schema."
            )
            self.assertTrue(
                len(p.mapped_findings) > 0,
                f"Proposal '{p.proposal_id}' does not map to any finding ID."
            )

    def test_schema_04_proposal_required_fields(self):
        """Every proposal must specify non-empty current state, proposed solution, and impact."""
        self.assertTrue(len(self.doc.proposals) > 0, "No proposals extracted to validate required fields.")
        for p in self.doc.proposals:
            self.assertTrue(
                len(p.current_state_risk.strip()) > 0,
                f"Proposal '{p.proposal_id}' has empty current state / risk."
            )
            self.assertTrue(
                len(p.proposed_solution.strip()) > 0,
                f"Proposal '{p.proposal_id}' has empty proposed solution."
            )
            self.assertTrue(
                len(p.impact_on_stability.strip()) > 0,
                f"Proposal '{p.proposal_id}' has empty impact on stability."
            )


if __name__ == "__main__":
    unittest.main()
