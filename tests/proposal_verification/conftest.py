"""
Pytest integration configuration and fixtures for proposal verification.
Allows running the suite via `pytest tests/proposal_verification/` or standalone runner.
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from tests.proposal_verification.parser import MarkdownParser, ParsedDocument


def pytest_addoption(parser):
    """Adds the --proposal CLI option to pytest."""
    parser.addoption(
        "--proposal",
        action="store",
        default=os.environ.get("PROPOSAL_PATH", "PRODUCTION_HARDENING_PROPOSAL.md"),
        help="Path to proposal markdown document (default: PRODUCTION_HARDENING_PROPOSAL.md or env PROPOSAL_PATH)",
    )
    parser.addoption(
        "--tier",
        action="store",
        default="all",
        help="Tier(s) to execute: 1, 2, 3, 4, or comma-separated list like 1,2 (default: all)",
    )


def pytest_configure(config):
    """Sets the PROPOSAL_PATH environment variable before test collection."""
    prop_opt = config.getoption("--proposal", default=None)
    if prop_opt:
        os.environ["PROPOSAL_PATH"] = str(Path(prop_opt).resolve())


@pytest.fixture(scope="session")
def proposal_doc(request) -> ParsedDocument:
    """Session fixture returning the parsed document for custom pytest-style test functions."""
    path = request.config.getoption("--proposal")
    return MarkdownParser.parse_file(path)
