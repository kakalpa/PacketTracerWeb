#!/usr/bin/env python3
"""
PacketTracerWeb Production Hardening Proposal Verification Suite Runner.

Unified CLI executable supporting:
  --proposal PATH      (path to proposal markdown file)
  --tier 1,2,3,4,all   (selective tier execution)
  --verbose            (detailed test output)
  --json [PATH]        (machine-readable JSON report output)
  --self-test          (validate test suite against built-in synthetic proposals)

Exit codes:
  0 = ALL TESTS PASSED
  1 = TEST ASSERTIONS FAILED
  2 = CONFIGURATION OR USAGE ERROR
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from typing import Dict, List, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def setup_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PacketTracerWeb Production Hardening Proposal Verification Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--proposal", "-p",
        dest="proposal_path",
        default=os.environ.get("PROPOSAL_PATH", "PRODUCTION_HARDENING_PROPOSAL.md"),
        help="Path to proposal markdown document (default: PRODUCTION_HARDENING_PROPOSAL.md or env PROPOSAL_PATH)",
    )
    parser.add_argument(
        "--tier", "-t",
        dest="tiers",
        default="all",
        help="Tier(s) to execute: 1, 2, 3, 4, or comma-separated list like 1,2 (default: all)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable detailed per-test logging and error tracebacks",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        nargs="?",
        const="test_report.json",
        default=None,
        help="Output machine-readable JSON report (default filename: test_report.json if flag passed without value)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Execute self-test suite against mock proposals to validate the test harness",
    )
    return parser


def load_test_suite_for_tiers(tiers: List[int], proposal_path: str) -> unittest.TestSuite:
    """Dynamically load test cases based on selected tiers."""
    abs_path = str(Path(proposal_path).resolve())
    os.environ["PROPOSAL_PATH"] = abs_path

    # Reset caches in test modules
    for mod_name in [
        "tests.proposal_verification.test_tier1_feature_coverage",
        "tests.proposal_verification.test_tier2_boundary_corner",
        "tests.proposal_verification.test_tier3_cross_feature",
        "tests.proposal_verification.test_tier4_real_world",
    ]:
        if mod_name in sys.modules:
            setattr(sys.modules[mod_name], "_CACHED_DOC", None)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    tier_modules = {
        1: "tests.proposal_verification.test_tier1_feature_coverage",
        2: "tests.proposal_verification.test_tier2_boundary_corner",
        3: "tests.proposal_verification.test_tier3_cross_feature",
        4: "tests.proposal_verification.test_tier4_real_world",
    }

    for tier_num in tiers:
        module_name = tier_modules.get(tier_num)
        if not module_name:
            continue
        try:
            mod = __import__(module_name, fromlist=["*"])
            # Reset cache if already loaded
            if hasattr(mod, "_CACHED_DOC"):
                mod._CACHED_DOC = None
            sub_suite = loader.loadTestsFromModule(mod)
            suite.addTests(sub_suite)
        except ImportError as e:
            print(f"Warning: Could not import {module_name}: {e}", file=sys.stderr)

    return suite


class CustomTestResult(unittest.TextTestResult):
    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.test_records = []

    def startTest(self, test):
        super().startTest(test)
        self._start_time = time.time()

    def addSuccess(self, test):
        super().addSuccess(test)
        elapsed = time.time() - self._start_time
        self.test_records.append({
            "test": test.id(),
            "status": "PASS",
            "duration": elapsed,
            "message": "",
        })

    def addFailure(self, test, err):
        super().addFailure(test, err)
        elapsed = time.time() - self._start_time
        self.test_records.append({
            "test": test.id(),
            "status": "FAIL",
            "duration": elapsed,
            "message": str(err[1]),
        })

    def addError(self, test, err):
        super().addError(test, err)
        elapsed = time.time() - self._start_time
        self.test_records.append({
            "test": test.id(),
            "status": "ERROR",
            "duration": elapsed,
            "message": str(err[1]),
        })


def run_self_test() -> int:
    """Execute self-test validation using synthetic mock proposals."""
    print("=" * 70)
    print("RUNNING PROPOSAL VERIFICATION HARNESS SELF-TEST")
    print("=" * 70)
    from tests.proposal_verification.fixtures import (
        create_synthetic_proposal,
        cleanup_synthetic_proposals,
    )

    script_path = str(Path(__file__).resolve())
    sub_env = os.environ.copy()
    sub_env["PYTHONPATH"] = str(PROJECT_ROOT)

    # Step 1: Verify missing proposal path returns exit code 2
    print("\n[Self-Test 1/4] Verifying missing proposal error handling...")
    proc = subprocess.run(
        [sys.executable, script_path, "--proposal", "/nonexistent/path/proposal.md"],
        capture_output=True,
        text=True,
        env=sub_env,
    )
    if proc.returncode != 2:
        print(f"FAILED: Expected exit code 2, got {proc.returncode}")
        print("STDERR:", proc.stderr)
        return 1
    print("✓ Missing file correctly returned exit code 2.")

    # Step 2: Verify valid synthetic proposal passes 100%
    print("\n[Self-Test 2/4] Verifying fully compliant synthetic proposal...")
    valid_path = create_synthetic_proposal("valid")
    proc = subprocess.run(
        [sys.executable, script_path, "--proposal", valid_path],
        capture_output=True,
        text=True,
        env=sub_env,
    )
    if proc.returncode != 0:
        print(f"FAILED: Valid synthetic proposal expected exit code 0, got {proc.returncode}")
        print("STDOUT:\n", proc.stdout)
        print("STDERR:\n", proc.stderr)
        cleanup_synthetic_proposals()
        return 1
    print("✓ Valid synthetic proposal passed 100% (exit code 0).")

    # Step 3: Verify missing Tier 3 requirements are caught
    print("\n[Self-Test 3/4] Verifying Tier 3 cross-feature fault detection...")
    faulty_tier3 = create_synthetic_proposal("missing_tier3")
    proc = subprocess.run(
        [sys.executable, script_path, "--proposal", faulty_tier3, "--tier", "3"],
        capture_output=True,
        text=True,
        env=sub_env,
    )
    if proc.returncode != 1:
        print(f"FAILED: Faulty Tier 3 proposal expected exit code 1, got {proc.returncode}")
        print("STDOUT:\n", proc.stdout)
        cleanup_synthetic_proposals()
        return 1
    print("✓ Faulty Tier 3 proposal correctly caught assertions (exit code 1).")

    # Step 4: Verify missing Tier 4 requirements are caught
    print("\n[Self-Test 4/4] Verifying Tier 4 real-world scenario fault detection...")
    faulty_tier4 = create_synthetic_proposal("missing_tier4")
    proc = subprocess.run(
        [sys.executable, script_path, "--proposal", faulty_tier4, "--tier", "4"],
        capture_output=True,
        text=True,
        env=sub_env,
    )
    if proc.returncode != 1:
        print(f"FAILED: Faulty Tier 4 proposal expected exit code 1, got {proc.returncode}")
        print("STDOUT:\n", proc.stdout)
        cleanup_synthetic_proposals()
        return 1
    print("✓ Faulty Tier 4 proposal correctly caught assertions (exit code 1).")

    cleanup_synthetic_proposals()
    print("\n" + "=" * 70)
    print("ALL 4 SELF-TEST STEPS PASSED: Test harness and assertions verified!")
    print("=" * 70)
    return 0


def main() -> int:
    parser = setup_argument_parser()
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    # Validate proposal path
    proposal_path = Path(args.proposal_path)
    if not proposal_path.exists():
        print(f"Error: Proposal file not found at: {proposal_path}", file=sys.stderr)
        print("Use --proposal <PATH> or set PROPOSAL_PATH environment variable.", file=sys.stderr)
        return 2

    # Parse tiers
    if args.tiers.lower() == "all":
        tiers = [1, 2, 3, 4]
    else:
        try:
            tiers = [int(t.strip()) for t in args.tiers.split(",") if t.strip()]
        except ValueError:
            print(f"Error: Invalid tier specification '{args.tiers}'. Use 1,2,3,4 or 'all'.", file=sys.stderr)
            return 2

        if not tiers or any(t not in (1, 2, 3, 4) for t in tiers):
            invalid_tiers = [t for t in tiers if t not in (1, 2, 3, 4)]
            print(f"Error: Invalid tier specification '{args.tiers}'. Valid tiers are 1, 2, 3, 4, or 'all'. Invalid: {invalid_tiers}", file=sys.stderr)
            return 2

        tiers = sorted(list(set(tiers)))

    print("=" * 70)
    print("PACKETTRACERWEB PROPOSAL VERIFICATION SUITE")
    print("=" * 70)
    print(f"Target Proposal: {proposal_path.resolve()}")
    print(f"Active Tiers:    {tiers}")
    print(f"Verbosity:       {'High' if args.verbose else 'Standard'}")
    print("=" * 70 + "\n")

    suite = load_test_suite_for_tiers(tiers, str(proposal_path))
    if suite.countTestCases() == 0:
        print("Warning: No test cases found for specified tiers.", file=sys.stderr)
        return 2

    stream = sys.stdout
    verbosity = 2 if args.verbose else 1
    runner = unittest.TextTestRunner(stream=stream, resultclass=CustomTestResult, verbosity=verbosity)

    start_time = time.time()
    result = runner.run(suite)
    elapsed = time.time() - start_time

    # Generate JSON summary if requested
    if args.json_output:
        summary_data = {
            "proposal_path": str(proposal_path.resolve()),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration": elapsed,
            "total_tests": result.testsRun,
            "passes": result.testsRun - len(result.failures) - len(result.errors),
            "failures": len(result.failures),
            "errors": len(result.errors),
            "records": getattr(result, "test_records", []),
        }
        json_path = Path(args.json_output)
        try:
            json_path.parent.mkdir(parents=True, exist_ok=True)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(summary_data, f, indent=2)
            print(f"\nJSON report written to: {args.json_output}")
        except OSError as e:
            print(f"Error writing JSON report to '{args.json_output}': {e}", file=sys.stderr)
            return 2

    if result.wasSuccessful():
        print(f"\n✓ ALL {result.testsRun} PROPOSAL VERIFICATION TESTS PASSED in {elapsed:.2f}s")
        return 0
    else:
        failed_count = len(result.failures) + len(result.errors)
        print(f"\n✗ VERIFICATION FAILED: {failed_count} of {result.testsRun} tests failed in {elapsed:.2f}s", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
