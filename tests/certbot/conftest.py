"""
Pytest configuration and shared fixtures for PacketTracerWeb Certbot TLS E2E tests.

Uses --certbot-live and --certbot-static-only (never --tier or --proposal) so
running `pytest tests/` across the entire repository has zero option collisions
with `tests/proposal_verification/conftest.py`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterator

import pytest

_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tests.certbot.helpers import (
    EphemeralNginxRunner,
    MgmtAppBridge,
    repo_root,
    temp_stack_ws,
)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register Certbot-specific options without colliding with proposal_verification."""
    parser.addoption(
        "--certbot-live",
        action="store_true",
        default=False,
        help="Include @pytest.mark.live checks against the running stack on ports 80/443/5000.",
    )
    parser.addoption(
        "--certbot-static-only",
        action="store_true",
        default=False,
        help="Deselect @pytest.mark.docker and @pytest.mark.live tests (host-only static checks).",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers for Certbot E2E test tiers and runtime scopes."""
    config.addinivalue_line("markers", "tier1: Tier 1 feature, syntax, and configuration contract checks")
    config.addinivalue_line("markers", "tier2: Tier 2 boundary, input validation, and security checks")
    config.addinivalue_line("markers", "tier3: Tier 3 cross-feature integration and reload checks")
    config.addinivalue_line("markers", "tier4: Tier 4 end-to-end lifecycle and non-regression checks")
    config.addinivalue_line("markers", "tier5: Tier 5 white-box adversarial hardening and bug regression checks")
    config.addinivalue_line("markers", "mgmt: Tests targeting pt-management Flask/API/UI components")
    config.addinivalue_line("markers", "docker: Requires Docker daemon and local pt-nginx / pt-management images")
    config.addinivalue_line("markers", "live: Probes running live containers on ports 80/443/5000 (deselected by default)")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """
    Deselect live tests by default (unless --certbot-live or CERTBOT_E2E_LIVE=1)
    and deselect docker+live tests under --certbot-static-only / CERTBOT_E2E_STATIC_ONLY=1.
    Uses deselection (not pytest.skip or xfail) so non-selected suites never produce false passes.
    """
    live_enabled = bool(
        config.getoption("--certbot-live", default=False)
        or os.environ.get("CERTBOT_E2E_LIVE", "") == "1"
    )
    static_only = bool(
        config.getoption("--certbot-static-only", default=False)
        or os.environ.get("CERTBOT_E2E_STATIC_ONLY", "") == "1"
    )

    kept: list[pytest.Item] = []
    deselected: list[pytest.Item] = []

    for item in items:
        is_live = item.get_closest_marker("live") is not None
        is_docker = item.get_closest_marker("docker") is not None

        if static_only and (is_docker or is_live):
            deselected.append(item)
        elif not live_enabled and is_live:
            deselected.append(item)
        else:
            kept.append(item)

    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = kept


@pytest.fixture(scope="session")
def repo_dir() -> Path:
    """Return the repository root path."""
    return repo_root()


@pytest.fixture
def stack_ws(tmp_path: Path) -> Path:
    """Provision an isolated temporary stack workspace for a single test."""
    return temp_stack_ws(tmp_path)


@pytest.fixture
def ephemeral_nginx() -> Iterator[EphemeralNginxRunner]:
    """Yield an EphemeralNginxRunner and guarantee cleanup of all containers/networks."""
    runner = EphemeralNginxRunner()
    try:
        yield runner
    finally:
        runner.cleanup_all()


@pytest.fixture
def mgmt_bridge(stack_ws: Path) -> MgmtAppBridge:
    """Provide an isolated MgmtAppBridge targeting the test's temporary workspace."""
    return MgmtAppBridge(stack_ws)
