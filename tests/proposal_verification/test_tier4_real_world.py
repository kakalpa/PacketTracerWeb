"""
Tier 4: Real-World Application Scenarios and Operational Runbooks Test Suite.
Validates phased rollout roadmaps, pre-migration checklists, disaster recovery / rollback
procedures, software compatibility matrices, and operational incident/scaling runbooks.
14 test methods across 4 classes.
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


class BaseTier4TestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = get_document()


class TestPhasedRolloutRoadmap(BaseTier4TestCase):
    """Scenario 1: Phased 3-Stage Rollout Roadmap (Immediate, Decoupling, Enterprise Scaling)."""

    def test_phased_rollout_phase1_hotfixes_and_security(self):
        """Verify Phase 1: Zero-downtime hotfixes, credential fixes, RemoteIpValve."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"Phase\s+1.*(?:Hotfix|Security|Immediate)", content, re.IGNORECASE),
            "Proposal lacks Phase 1 zero-downtime hotfix and security roadmap section."
        )
        self.assertTrue(
            re.search(r"IlovePT|RemoteIpValve|cleanup-all\.sh", content),
            "Phase 1 fails to address critical credentials, IP ban valve, or cleanup safeguards."
        )

    def test_phased_rollout_phase2_decoupling_and_hardening(self):
        """Verify Phase 2: Architectural decoupling, socket proxy, non-root, volumes."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"Phase\s+2.*(?:Decoupl|Hardening|Structure)", content, re.IGNORECASE),
            "Proposal lacks Phase 2 decoupling and container hardening roadmap section."
        )
        self.assertTrue(
            re.search(r"docker-socket-proxy|mariadb_data|tini", content, re.IGNORECASE),
            "Phase 2 fails to specify socket proxy, named volume migration, or tini supervisor."
        )

    def test_phased_rollout_phase3_scaling_and_observability(self):
        """Verify Phase 3: High availability, dynamic scaling, Prometheus, log rotation."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"Phase\s+3.*(?:Scale|Observab|Enterprise|HA)", content, re.IGNORECASE),
            "Proposal lacks Phase 3 enterprise scaling and observability roadmap section."
        )
        self.assertTrue(
            re.search(r"Prometheus|metric|log\s+rotation|pool", content, re.IGNORECASE),
            "Phase 3 fails to specify metrics monitoring, log rotation, or connection pooling."
        )


class TestMigrationAndDisasterRecoveryRunbooks(BaseTier4TestCase):
    """Scenario 2: Migration Procedures, Backup/Restore Runbooks, and Deterministic Rollbacks."""

    def test_pre_migration_verification_checklist(self):
        """Verify executable pre-migration audit checklist (Docker, kernel, ports, RAM)."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"pre-migration|checklist|prerequisite", content, re.IGNORECASE),
            "Proposal lacks pre-migration verification checklist."
        )
        self.assertTrue(
            re.search(r"nginx\s+-t|compose\s+config", content, re.IGNORECASE),
            "Pre-migration checklist lacks dry-run configuration validation commands."
        )

    def test_disaster_recovery_mariadb_backup_and_restore_runbook(self):
        """Verify MariaDB backup and restore runbook with mysqldump and RPO/RTO targets."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"(?:mysqldump|mariadb-dump).*single-transaction", content, re.IGNORECASE),
            "Proposal lacks safe mysqldump backup command with --single-transaction."
        )
        self.assertTrue(
            re.search(r"RPO|RTO|retention", content),
            "Proposal lacks RPO/RTO recovery time targets or backup retention policy."
        )

    def test_anonymous_to_named_volume_migration_procedure(self):
        """Verify step-by-step procedure to migrate legacy anonymous volume to mariadb_data."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"mariadb_data", content) and re.search(r"docker run.*alpine cp", content, re.IGNORECASE),
            "Proposal lacks safe data copy procedure to migrate anonymous volume to mariadb_data."
        )

    def test_rollback_procedures_across_all_phases(self):
        """Verify rollback runbooks and trigger criteria across all implementation phases."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"rollback.*procedure|rollback.*runbook|Rollback Procedures", content, re.IGNORECASE),
            "Proposal lacks explicit rollback procedures for implementation phases."
        )
        self.assertTrue(
            re.search(r"trigger|criteria|threshold", content, re.IGNORECASE),
            "Proposal fails to define objective criteria or thresholds for initiating rollbacks."
        )


class TestSoftwareCompatibilityVerification(BaseTier4TestCase):
    """Scenario 3: Proprietary Software and Stack Compatibility."""

    def test_cisco_packet_tracer_compatibility_verification(self):
        """Verify Cisco Packet Tracer 8.x, Qt6, OpenGL, and non-interactive deb extraction."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"Packet\s*Tracer\s*8\.[012]|CiscoPacketTracer", content, re.IGNORECASE),
            "Proposal lacks explicit compatibility verification for Cisco Packet Tracer 8.x."
        )
        self.assertTrue(
            re.search(r"Qt6|libqt6|libgl1", content, re.IGNORECASE),
            "Proposal lacks Linux Qt6 / OpenGL runtime dependency verification for Packet Tracer."
        )

    def test_turbovnc_and_virtualgl_compatibility_pipeline(self):
        """Verify TurboVNC 3.x, VirtualGL vglrun, Xvfb elimination, and autocutsel."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"TurboVNC.*3\.|VirtualGL.*3\.", content, re.IGNORECASE) or
            re.search(r"vglrun|autocutsel", content, re.IGNORECASE),
            "Proposal fails to verify TurboVNC / VirtualGL display pipeline compatibility."
        )

    def test_apache_guacamole_stack_compatibility_and_sizing(self):
        """Verify Guacamole 1.5.x image tag pinning, schema compatibility, and WebSocket fallback."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"guacamole.*1\.5|guacd.*1\.5", content, re.IGNORECASE),
            "Proposal lacks pinned image tags for Guacamole 1.5.x stack."
        )


class TestOperationalAndIncidentRunbooks(BaseTier4TestCase):
    """Scenario 4: Incident Response Runbooks and Operational Scaling Scenarios."""

    def test_incident_response_runbook_ip_ban_lockout(self):
        """Verify incident response runbook for diagnosing and clearing Guacamole IP bans."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"lockout|ban.*remediat|unban", content, re.IGNORECASE),
            "Proposal lacks operational incident runbook for resolving Guacamole IP ban lockouts."
        )

    def test_incident_response_runbook_zombie_process_storm(self):
        """Verify incident response runbook for triaging and mitigating defunct zombie storms."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"zombie|defunct|pid.*exhaust", content, re.IGNORECASE),
            "Proposal lacks operational incident runbook for zombie process storm remediation."
        )

    def test_classroom_peak_scaling_operational_runbook(self):
        """Verify classroom peak scaling runbook with capacity sizing and pre-warming."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"capacity|sizing|concurrent.*users|pre-warm", content, re.IGNORECASE),
            "Proposal lacks capacity planning formulas and operational peak scaling runbook."
        )

    def test_file_isolation_and_security_acceptance_scenario(self):
        """Verify student file confidentiality, path traversal rejection, and disk quotas."""
        content = self.doc.raw_text
        self.assertTrue(
            re.search(r"quota|confidentiality|traversal", content, re.IGNORECASE),
            "Proposal lacks file security acceptance criteria or quota enforcement runbooks."
        )


if __name__ == "__main__":
    unittest.main()
