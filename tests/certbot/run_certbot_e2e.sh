#!/usr/bin/env bash
set -euo pipefail

# Unified CLI runner for PacketTracerWeb Certbot TLS E2E Test Suite (Tiers 1-5)
# Usage: bash tests/certbot/run_certbot_e2e.sh [OPTIONS]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPT_PATH="$SCRIPT_DIR/run_certbot_e2e.sh"

TIER="all"
COLLECT_ONLY=0
STATIC_ONLY=0
LIVE_MODE=0
VERBOSE=0
JSON_PATH=""
KEYWORD_EXPR=""

usage() {
    cat <<'EOF'
PacketTracerWeb Certbot TLS E2E Test Runner

Usage:
  bash tests/certbot/run_certbot_e2e.sh [OPTIONS]

Options:
  --tier <SPEC>     Tier(s) to run: 1, 2, 3, 4, 5, all, or comma-separated (e.g. 1,2,3,4,5)
                    Default: all
  --collect-only    Collect tests only (`pytest --collect-only -q`), exit 0 if clean
  --static-only     Run host-only static/syntax/git checks (`-m "not docker and not live"`)
  --live            Enable live-stack checks (`CERTBOT_E2E_LIVE=1`); without this flag,
                    live tests are deselected so running containers on 80/443/5000 stay safe
  --verbose, -v     Verbose pytest output (`-vv --tb=short`)
  --json <PATH>     Write structured JSON test summary report to <PATH>
  -k <EXPR>         Forward pytest `-k <EXPR>` test name filter
  -h, --help        Show this help message and exit 0

Exit Codes:
  0  All selected tests passed (or clean collection under --collect-only)
  1  One or more test assertions failed
  2  Configuration, usage, Python/pytest environment, or collection error
EOF
}

# Parse CLI arguments
while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --tier)
            if [ $# -lt 2 ] || [ -z "${2:-}" ]; then
                echo "Error: --tier requires an argument (e.g. 1, 2, 3, 4, 5, all, or 1,2)." >&2
                exit 2
            fi
            TIER="$2"
            shift 2
            ;;
        --tier=*)
            TIER="${1#*=}"
            if [ -z "$TIER" ]; then
                echo "Error: --tier requires a non-empty argument." >&2
                exit 2
            fi
            shift
            ;;
        --collect-only)
            COLLECT_ONLY=1
            shift
            ;;
        --static-only)
            STATIC_ONLY=1
            shift
            ;;
        --live)
            LIVE_MODE=1
            shift
            ;;
        -v|--verbose)
            VERBOSE=1
            shift
            ;;
        --json)
            if [ $# -lt 2 ] || [ -z "${2:-}" ]; then
                echo "Error: --json requires a file path argument." >&2
                exit 2
            fi
            JSON_PATH="$2"
            shift 2
            ;;
        --json=*)
            JSON_PATH="${1#*=}"
            if [ -z "$JSON_PATH" ]; then
                echo "Error: --json requires a non-empty file path argument." >&2
                exit 2
            fi
            shift
            ;;
        -k)
            if [ $# -lt 2 ] || [ -z "${2:-}" ]; then
                echo "Error: -k requires a filter expression." >&2
                exit 2
            fi
            KEYWORD_EXPR="$2"
            shift 2
            ;;
        -k=*)
            KEYWORD_EXPR="${1#*=}"
            shift
            ;;
        *)
            echo "Error: Unknown option '$1'. Run with --help for usage." >&2
            exit 2
            ;;
    esac
done

if [ "$STATIC_ONLY" -eq 1 ] && [ "$LIVE_MODE" -eq 1 ]; then
    echo "Error: --static-only and --live cannot be combined." >&2
    exit 2
fi

# Validate --json target path & parent directory if provided
if [ -n "$JSON_PATH" ]; then
    if [ -d "$JSON_PATH" ] || [[ "$JSON_PATH" == */ ]]; then
        echo "Error: --json path '$JSON_PATH' points to a directory; expected a file path." >&2
        exit 2
    fi
    JSON_DIR="$(dirname "$JSON_PATH")"
    if ! mkdir -p "$JSON_DIR" 2>/dev/null || [ ! -w "$JSON_DIR" ]; then
        echo "Error: Cannot write JSON report to '$JSON_PATH' (unwritable directory '$JSON_DIR')." >&2
        exit 2
    fi
fi

# Validate and resolve --tier into target test files
declare -a TEST_FILES=()
if [ "$TIER" = "all" ]; then
    TEST_FILES=("$SCRIPT_DIR")
else
    if [[ "$TIER" == ,* ]] || [[ "$TIER" == *, ]] || [[ "$TIER" == *,,* ]]; then
        echo "Error: Invalid --tier value '$TIER' (empty segment or trailing comma). Valid values: 1, 2, 3, 4, 5, all, or comma-separated (e.g. 1,2)." >&2
        exit 2
    fi
    IFS=',' read -ra TIER_PARTS <<< "$TIER"
    if [ ${#TIER_PARTS[@]} -eq 0 ]; then
        echo "Error: Invalid --tier value '$TIER'." >&2
        exit 2
    fi
    declare -A SEEN_TIERS=()
    for part in "${TIER_PARTS[@]}"; do
        case "$part" in
            1)
                if [ -z "${SEEN_TIERS[1]:-}" ]; then
                    TEST_FILES+=("$SCRIPT_DIR/test_tier1_feature_config.py")
                    SEEN_TIERS[1]=1
                fi
                ;;
            2)
                if [ -z "${SEEN_TIERS[2]:-}" ]; then
                    TEST_FILES+=("$SCRIPT_DIR/test_tier2_boundary_security.py")
                    SEEN_TIERS[2]=1
                fi
                ;;
            3)
                if [ -z "${SEEN_TIERS[3]:-}" ]; then
                    TEST_FILES+=("$SCRIPT_DIR/test_tier3_cross_feature.py")
                    SEEN_TIERS[3]=1
                fi
                ;;
            4)
                if [ -z "${SEEN_TIERS[4]:-}" ]; then
                    TEST_FILES+=("$SCRIPT_DIR/test_tier4_e2e_nonregression.py")
                    SEEN_TIERS[4]=1
                fi
                ;;
            5)
                if [ -z "${SEEN_TIERS[5]:-}" ]; then
                    TEST_FILES+=("$SCRIPT_DIR/test_tier5_adversarial.py")
                    SEEN_TIERS[5]=1
                fi
                ;;
            *)
                echo "Error: Invalid tier '$part' in --tier '$TIER'. Valid values: 1, 2, 3, 4, 5, all, or comma-separated (e.g. 1,2)." >&2
                exit 2
                ;;
        esac
    done
fi

# Self-validate runner bash syntax unless --collect-only
if [ "$COLLECT_ONLY" -eq 0 ]; then
    if ! bash -n "$SCRIPT_PATH" >/dev/null 2>&1; then
        echo "Error: bash -n syntax check failed for $SCRIPT_PATH" >&2
        bash -n "$SCRIPT_PATH" >&2 || true
        exit 2
    fi
fi

# Python / pytest auto-discovery (reject broken 3.15.2 shim cleanly)
PY_BIN=""
declare -a PYTEST_CMD=()

validate_python_with_pytest() {
    local candidate_py="$1"
    if [ -x "$candidate_py" ] || command -v "$candidate_py" >/dev/null 2>&1; then
        if "$candidate_py" -c "import pytest" >/dev/null 2>&1; then
            PY_BIN="$candidate_py"
            PYTEST_CMD=("$candidate_py" -m pytest)
            return 0
        fi
    fi
    return 1
}

if [ -n "${PYTEST_BIN:-}" ]; then
    # Verify explicitly supplied PYTEST_BIN works and its interpreter can import pytest
    resolved_pytest=""
    if [ -x "$PYTEST_BIN" ]; then
        resolved_pytest="$PYTEST_BIN"
    elif command -v "$PYTEST_BIN" >/dev/null 2>&1; then
        resolved_pytest="$(command -v "$PYTEST_BIN")"
    else
        echo "Error: PYTEST_BIN='$PYTEST_BIN' is not executable or found on PATH." >&2
        exit 2
    fi
    shebang_py="$(head -n1 "$resolved_pytest" 2>/dev/null | sed -n 's/^#![[:space:]]*\([^[:space:]]*\).*/\1/p' || true)"
    if [ -n "$shebang_py" ] && [[ "$shebang_py" == *python* ]]; then
        if ! "$shebang_py" -c "import pytest" >/dev/null 2>&1; then
            echo "Error: PYTEST_BIN='$PYTEST_BIN' points to Python '$shebang_py' which cannot import pytest." >&2
            exit 2
        fi
        PY_BIN="$shebang_py"
    elif command -v python3.14 >/dev/null 2>&1 && python3.14 -c "import pytest" >/dev/null 2>&1; then
        PY_BIN="$(command -v python3.14)"
    fi
    if ! "$resolved_pytest" --version >/dev/null 2>&1; then
        echo "Error: PYTEST_BIN='$PYTEST_BIN' failed '--version' check." >&2
        exit 2
    fi
    PYTEST_CMD=("$resolved_pytest")
else
    if validate_python_with_pytest "/home/kalpa/.local/share/mise/installs/python/3.14.7/bin/python"; then
        :
    elif validate_python_with_pytest "python3.14"; then
        :
    elif validate_python_with_pytest "python3"; then
        :
    elif command -v pytest >/dev/null 2>&1; then
        path_pytest="$(command -v pytest)"
        shebang_py="$(head -n1 "$path_pytest" 2>/dev/null | sed -n 's/^#![[:space:]]*\([^[:space:]]*\).*/\1/p' || true)"
        if [ -n "$shebang_py" ] && [[ "$shebang_py" == *python* ]] && "$shebang_py" -c "import pytest" >/dev/null 2>&1 && "$path_pytest" --version >/dev/null 2>&1; then
            PY_BIN="$shebang_py"
            PYTEST_CMD=("$path_pytest")
        fi
    fi
fi

if [ ${#PYTEST_CMD[@]} -eq 0 ]; then
    echo "Error: No working Python+pytest installation found (tried \$PYTEST_BIN, mise python 3.14.7, python3.14, python3, pytest)." >&2
    echo "Hint: Ensure /home/kalpa/.local/share/mise/installs/python/3.14.7/bin/pytest is installed (default python 3.15.2 shim lacks pytest)." >&2
    exit 2
fi

if [ -z "$PY_BIN" ]; then
    PY_BIN="/home/kalpa/.local/share/mise/installs/python/3.14.7/bin/python"
    if [ ! -x "$PY_BIN" ]; then
        PY_BIN="$(command -v python3 || true)"
    fi
fi

# Build pytest arguments
declare -a PYTEST_ARGS=("${TEST_FILES[@]}")

if [ "$COLLECT_ONLY" -eq 1 ]; then
    PYTEST_ARGS+=(--collect-only -q)
fi

if [ "$STATIC_ONLY" -eq 1 ]; then
    export CERTBOT_E2E_STATIC_ONLY=1
    unset CERTBOT_E2E_LIVE || true
    PYTEST_ARGS+=(--certbot-static-only -m "not docker and not live")
elif [ "$LIVE_MODE" -eq 1 ]; then
    export CERTBOT_E2E_LIVE=1
    unset CERTBOT_E2E_STATIC_ONLY || true
    PYTEST_ARGS+=(--certbot-live)
else
    unset CERTBOT_E2E_LIVE || true
    unset CERTBOT_E2E_STATIC_ONLY || true
    PYTEST_ARGS+=(-m "not live")
fi

if [ "$VERBOSE" -eq 1 ] && [ "$COLLECT_ONLY" -eq 0 ]; then
    PYTEST_ARGS+=(-vv --tb=short)
fi

if [ -n "$KEYWORD_EXPR" ]; then
    PYTEST_ARGS+=(-k "$KEYWORD_EXPR")
fi

JUNIT_TMP=""
cleanup_tmp() {
    if [ -n "$JUNIT_TMP" ] && [ -f "$JUNIT_TMP" ]; then
        rm -f "$JUNIT_TMP"
    fi
}
trap cleanup_tmp EXIT

if [ -n "$JSON_PATH" ] && [ "$COLLECT_ONLY" -eq 0 ]; then
    JUNIT_TMP="$(mktemp /tmp/certbot_e2e_junit_XXXXXX.xml)"
    PYTEST_ARGS+=(--junitxml="$JUNIT_TMP")
fi

cd "$REPO_ROOT"

START_TS="$(date +%s)"
set +e
"${PYTEST_CMD[@]}" "${PYTEST_ARGS[@]}"
PYTEST_RC=$?
set -e
END_TS="$(date +%s)"
DURATION="$((END_TS - START_TS))"

# Map pytest exit codes to runner contract: 0->0, 1->1, 2/3/4/5->2
MAPPED_RC=2
case "$PYTEST_RC" in
    0) MAPPED_RC=0 ;;
    1) MAPPED_RC=1 ;;
    2|3|4|5) MAPPED_RC=2 ;;
    *) MAPPED_RC=2 ;;
esac

if [ -n "$JSON_PATH" ]; then
    "$PY_BIN" - "$JUNIT_TMP" "$JSON_PATH" "$TIER" "$MAPPED_RC" "$PYTEST_RC" "$DURATION" "$STATIC_ONLY" "$LIVE_MODE" "$COLLECT_ONLY" <<'PYEOF'
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

junit_path, json_path, tier, mapped_rc, pytest_rc, duration, static_only, live_mode, collect_only = sys.argv[1:10]
summary = {
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "tier": tier,
    "static_only": bool(int(static_only)),
    "live": bool(int(live_mode)),
    "collect_only": bool(int(collect_only)),
    "exit_code": int(mapped_rc),
    "pytest_exit_code": int(pytest_rc),
    "duration_seconds": int(duration),
    "counts": {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0},
    "tests": [],
}

if junit_path and os.path.exists(junit_path) and os.path.getsize(junit_path) > 0:
    try:
        tree = ET.parse(junit_path)
        root = tree.getroot()
        suites = [root] if root.tag == "testsuite" else root.findall(".//testsuite")
        for suite in suites:
            for tc in suite.findall("testcase"):
                name = tc.attrib.get("name", "")
                classname = tc.attrib.get("classname", "")
                status = "passed"
                message = ""
                failure = tc.find("failure")
                error = tc.find("error")
                skipped = tc.find("skipped")
                if failure is not None:
                    status = "failed"
                    message = failure.attrib.get("message", "")
                    summary["counts"]["failed"] += 1
                elif error is not None:
                    status = "error"
                    message = error.attrib.get("message", "")
                    summary["counts"]["errors"] += 1
                elif skipped is not None:
                    status = "skipped"
                    message = skipped.attrib.get("message", "")
                    summary["counts"]["skipped"] += 1
                else:
                    summary["counts"]["passed"] += 1
                summary["counts"]["total"] += 1
                summary["tests"].append({
                    "classname": classname,
                    "name": name,
                    "status": status,
                    "time": float(tc.attrib.get("time", "0") or 0),
                    "message": message,
                })
    except Exception as exc:
        summary["junit_parse_error"] = str(exc)

with open(json_path, "w", encoding="utf-8") as fh:
    json.dump(summary, fh, indent=2)
PYEOF
fi

exit "$MAPPED_RC"
