# PacketTracerWeb Proposal Verification Test Infrastructure

## Overview

The E2E Proposal Verification test harness provides an automated, requirement-driven, opaque-box validation framework for the `PRODUCTION_HARDENING_PROPOSAL.md` master deliverable. It validates that all architectural assessments, technical recommendations, configuration directives, and operational runbooks meet production-grade standards across all five core components and five operational domains.

The test infrastructure is implemented in pure Python standard library (`unittest`, `dataclasses`, `re`, `typing`, `pathlib`, `enum`, `json`, `argparse`, `sys`), ensuring zero external package dependencies, instant portability across all Python 3.8+ environments, and full compatibility with `pytest`.

```
                    [ PRODUCTION_HARDENING_PROPOSAL.md ]
                                      │
                                      ▼
                       [ Markdown Parser & AST Engine ]
                         (Code Fence Immunity, Regex)
                                      │
            ┌─────────────────────────┼─────────────────────────┐
            ▼                         ▼                         ▼
    [ Tier 1: Features ]     [ Tier 2: Boundaries ]    [ Tier 3: Cross-Feature ]
    - 5 Core Components      - 10 Critical Vulnerabilities - Component Interlocks
    - 5 Operational Domains  - Concrete Directives     - Pairwise Synergy
    - 5x5 Matrix (45 tests)  - Defect Fixes (56 tests) - Architectural Balance (20 tests)
            │                         │                         │
            └─────────────────────────┼─────────────────────────┘
                                      ▼
                           [ Tier 4: Real-World ]
                           - Phased Rollout Roadmap (Phases 1-3)
                           - Pre-Migration & Rollback Runbooks
                           - Incident & Scaling Scenarios (14 tests)
                                      │
                                      ▼
                          [ test_proposal.py Runner ]
                     Exit Code 0 (Pass) / 1 (Fail) / 2 (Config Error)
```

---

## Architecture & Components

The test infrastructure is located under `tests/proposal_verification/`:

| File | Role | Description |
|---|---|---|
| `parser.py` | AST Engine | Pure Python line-scanning Markdown parser with length-preserving code fence masking (`_mask_code_blocks`), synchronized fence delimiter tracking (`_extract_tables`), CRLF/CR newline normalization, finding (`[FINDING-C<comp>-<domain>-<num>]`) and proposal (`[PROP-C<comp>-<num>]`) extractors with bold-tolerant negative lookahead field boundary isolation, and 5x5 matrix retrieval. |
| `fixtures.py` | Mock Generator | Synthetic proposal generator supporting `valid`, `missing_tier3`, and `missing_tier4` modes for independent self-testing prior to deliverable completion. |
| `test_tier1_feature_coverage.py` | Tier 1 Suite | 45 tests across 8 classes verifying coverage of all 5 core components and 5 operational domains, non-empty node assertions, and mandatory finding-to-proposal mapping, validating 100% of Acceptance Criteria R1 & R2. |
| `test_tier2_boundary_corner.py` | Tier 2 Suite | 56 tests across 10 classes verifying the 10 critical boundary and vulnerability areas identified during empirical codebase inspection, including multiline YAML capability dropping and tightened API container bypass rules. |
| `test_tier3_cross_feature.py` | Tier 3 Suite | 20 tests across 4 classes verifying pairwise cross-component combinations, architectural balance, and inter-service synergy. |
| `test_tier4_real_world.py` | Tier 4 Suite | 14 tests across 4 classes verifying phased rollout roadmaps, disaster recovery runbooks, deterministic rollbacks, software compatibility, and incident response. |
| `test_proposal.py` | Unified CLI Runner | Standalone executable CLI supporting `--proposal PATH`, `--tier 1,2,3,4,all` (with strict set validation), `--verbose`, `--json [PATH]` (with automatic directory creation and error handling), `--self-test`, and strict exit codes (0, 1, 2). |
| `conftest.py` | Pytest Integration | Pytest configuration hooks (`pytest_addoption`, `pytest_configure`) and session fixtures enabling native `pytest tests/proposal_verification/` execution. |

---

## Multi-Tier Test Suite Specification

### Tier 1: Feature Coverage (45 Tests)
Validates core component presence, operational domain distribution, schema compliance, and requirement checklist alignment:

| Test Class | Test Count | Scope |
|---|---|---|
| `TestDocumentStructureAndSections` | 5 | H1 title, Executive Summary, R1 System Assessment, R2 Improvement Proposals, and Verification Resources references (`health_check.sh`, `deploy.sh`, `docker-compose.yml`). |
| `TestComponent1Coverage` | 6 | Virtualized Desktop Container (`ptvnc`): TurboVNC display server, init supervisor (`tini`), `/dev/shm` (512MB) and RAM (2.5GB) tuning, `pt_opt` installer mutex, and `autocutsel` clipboard sync. |
| `TestComponent2Coverage` | 6 | Apache Guacamole Stack: named volume persistence (`mariadb_data`), connection deduplication (`parent_id IS NULL`), Tomcat `RemoteIpValve`, proxy buffering, and non-destructive deprovisioning. |
| `TestComponent3Coverage` | 6 | Nginx Edge Gateway: modern GeoIP2 (`ngx_http_geoip2_module`), ISO country code fixes (`GB`, `LK`), TLS 1.2/1.3 ciphers, HSTS/CSP security headers, and port 5000 perimeter hardening. |
| `TestComponent4Coverage` | 6 | Flask Management Service: `docker-socket-proxy`, non-root execution (`USER ptmgmt`), anti-CSRF protection, dynamic `SECRET_KEY`, database connection pooling, and per-user isolated storage. |
| `TestComponent5Coverage` | 6 | Deployment & Orchestration: Docker `HEALTHCHECK`s, zero-sleep startup sequencing, network topology (`ptnet`), capability dropping (`cap_drop: [ALL]`), log rotation, and scoped cleanup. |
| `TestOperationalDomainCoverage` | 6 | Sizing across all 5 operational domains (SEC, PERF, REL, USE, MAINT) and validation of the full 5x5 Component × Domain matrix (zero unpopulated cells). |
| `TestFindingAndProposalSchemas` | 4 | Strict nomenclature compliance (`FINDING-C<comp>-<dom>-<num>`, `PROP-C<comp>-<num>`), non-empty node validation, mandatory finding-to-proposal mapping (`len(p.mapped_findings) > 0`), and mandatory attribute presence across findings and proposals. |

### Tier 2: Boundary & Corner Cases (56 Tests)
Validates concrete configuration directives, vulnerability remediation, and technical parameters across the 10 critical areas:

1. **Docker Socket Proxy & Rootless Execution** (6 tests): Intermediate `docker-socket-proxy`, endpoint whitelist (`CONTAINERS=1`, `POST=1`, `VOLUMES=0`, `SYSTEM=0`), non-root `USER ptmgmt` (UID 10001), `cap_drop: [ALL]` (inline and multiline YAML block sequence `cap_drop:\n  - ALL`), `no-new-privileges: true`, read-only rootfs with tmpfs mounts, and elimination of `-v "$ROOT_DIR:/project"`.
2. **GeoIP2 Migration & ISO Code Fixes** (6 tests): Deprecation of GeoIP1, migration to `ngx_http_geoip2_module` (`.mmdb`), ISO alpha-2 corrections (`UK` $\rightarrow$ `GB`, `SL` $\rightarrow$ `LK`), top-level `geo $trusted_ip` CIDR blocks, regex unanchored/unescaped remediation, and verified MaxMind provisioning.
3. **Tomcat RemoteIpValve & Ban Prevention** (6 tests): `org.apache.catalina.valves.RemoteIpValve` in `server.xml`, `internalProxies` matching Docker bridge CIDRs, `remoteIpHeader="x-forwarded-for"`, `BanningAuthenticationListener` DoS lockout isolation, and Nginx proxy header propagation.
4. **MariaDB Persistent Volumes & Connection Deduplication** (5 tests): Named volume `mariadb_data:/var/lib/mysql`, `NULL parent_id` unique key fix, idempotent SQL upsert in `generate-dynamic-connections.sh`, elimination of subquery multi-row `ERROR 1242`, and automated backup lifecycle.
5. **Docker HEALTHCHECKs & Zero-Sleep Startup Sequencing** (6 tests): Healthchecks on MariaDB (`mariadb-admin ping`), guacd (port 4822), Guacamole (`/guacamole/`), Management (`/health`), and VNC (port 5901); `depends_on: {condition: service_healthy}`; elimination of 115s hardcoded sleep delays via active readiness polling.
6. **Memory Sizing, /dev/shm, and ulimits** (5 tests): Container RAM allocation $\ge 2.0\text{ GB}$ (recommended 2.5GB), `/dev/shm \ge 512\text{MB}` mitigating WebEngine crash code 133 / SIGBUS, `nofile=65536:65536`, `nproc=4096:4096`, and cross-pathway resource limit synchronization.
7. **Init System & Zombie Process Mitigation** (5 tests): Container init process (`tini` on PID 1), `SIGCHLD` reaping of defunct `[AppRun]` zombies, signal forwarding (`tini -g`), elimination of unmonitored `while true; do sleep 3600; done` loop, and process supervision evaluation.
8. **Destructive Scale-In & Cleanup Script Remediation** (5 tests): Non-destructive scale-in removing only target `ptvncX` container and DB row, active session checking in `guacamole_connection_history`, elimination of legacy `--link` syntax, project-scoped host cleanup (`label=com.docker.compose.project=ptweb`), and `--purge-data` volume loss safeguards.
9. **TLS 1.2/1.3 Ciphers, HSTS, CSP, and Security Headers** (6 tests): Mozilla Intermediate cipher string, HSTS (`max-age=63072000`), CSP (`frame-ancestors 'self'`, WebSocket `connect-src`), `X-Frame-Options SAMEORIGIN`, `X-Content-Type-Options nosniff`, `server_tokens off`, TLS session caching, OCSP stapling, and port 5000 cookie flags.
10. **Unauthenticated API Bypass Removal & CSRF Protection** (6 tests): Elimination of unconditional `/api/containers` bypass (requiring `/api/containers` in conjunction with `bypass` or `unauthenticated`), removal of spoofable `172.` / `10.` internal IP checks, `Flask-WTF` CSRF protection across forms and AJAX, dynamic cryptographic `SECRET_KEY`, Bearer token auth for automation, and removal of unauthenticated `/downloads/` autoindex.

### Tier 3: Cross-Feature Combinations (20 Tests)
Validates pairwise cross-component interlocks and architectural synergy across 4 classes:

- `TestGatewayAndTunnelSynergy` (5 tests): Nginx buffering off & connection upgrade map vs Guacamole tunnel latency; GeoIP2 rules & WebSocket rate limit exemption; Tomcat RemoteIpValve vs Guacamole brute-force ban lockout; Nginx frame security headers vs Guacamole portal iframe embedding; TLS ciphers vs WebSocket ALPN.
- `TestProvisioningAndReachabilitySynergy` (5 tests): Flask provisioning network attachment (`ptnet`) vs Guacamole container reachability without DNS races; Docker socket proxy permission scope vs non-root Flask capabilities; Shared volume mutex (`flock`) vs concurrent scale-out; Per-user file isolation vs Flask file manager API; Gunicorn async workers vs Docker API concurrency.
- `TestDatabaseAndStorageSynergy` (5 tests): MariaDB connection pooling & server `max_connections` sizing vs concurrent scale; MariaDB named volume persistence vs connection deduplication; TurboVNC dynamic authentication vs Guacamole connection parameters; Persistent `SECRET_KEY` vs session continuity; MariaDB backup vs `user_container_mapping` table synchronization.
- `TestRuntimeAndResourceSynergy` (5 tests): `tini` init supervisor vs Packet Tracer zombie reaping; `/dev/shm` 512MB & RAM sizing vs VirtualGL Qt6 rendering; Docker healthcheck readiness probes vs zero-sleep deployment; Non-destructive scale-in vs Guacamole session persistence; Capability dropping vs GPU device passthrough (`/dev/dri`).

### Tier 4: Real-World Scenarios (14 Tests)
Validates real-world operational execution and acceptance criteria across 4 classes:

- `TestPhasedRolloutRoadmap` (3 tests): Phase 1 (Zero-downtime hotfixes & security patches), Phase 2 (Architectural decoupling & structural container hardening), Phase 3 (Enterprise scaling, Prometheus observability, and log rotation).
- `TestMigrationAndDisasterRecoveryRunbooks` (4 tests): Pre-migration verification checklist (kernel settings, port availability, dry-run syntax checks `docker compose config` and `nginx -t`), MariaDB disaster recovery (`mysqldump --single-transaction`, RPO $\le 15$ min, RTO $\le 30$ min, retention policies), anonymous-to-named volume migration runbook, and deterministic rollback procedures across all phases with explicit trigger thresholds.
- `TestSoftwareCompatibilityVerification` (3 tests): Cisco Packet Tracer 8.x (Qt6 dependencies, OpenGL, non-interactive deb extraction, `.pkt`/`.pka` formats), TurboVNC 3.x & VirtualGL 3.x display pipeline, and Apache Guacamole 1.5.x stack image pinning and schema compatibility.
- `TestOperationalAndIncidentRunbooks` (4 tests): Guacamole IP ban lockout incident response (diagnosis, SQL unban, permanent valve verification), zombie process storm incident response (triage, killing zombies, `tini` fix), classroom peak scaling runbook (capacity formulas: RAM $(N \times 2.5) + 4$GB, CPU $(N \times 0.5) + 2$ cores, pre-warming), and file isolation multi-tenant security acceptance scenario.

**Total Test Count**: $45 + 56 + 20 + 14 = 135$ test methods.

---

## Test Execution & CLI Runner Usage

The primary entry point is the standalone executable `tests/proposal_verification/test_proposal.py`.

### Command-Line Arguments

```
usage: test_proposal.py [-h] [--proposal PROPOSAL_PATH] [--tier TIER]
                        [--verbose] [--json [JSON_PATH]] [--self-test]

options:
  -h, --help            Show this help message and exit
  --proposal PROPOSAL_PATH, -p PROPOSAL_PATH
                        Path to markdown proposal file (default:
                        PRODUCTION_HARDENING_PROPOSAL.md, or env PROPOSAL_PATH)
  --tier TIER, -t TIER  Tier(s) to execute: 1, 2, 3, 4, or comma-separated list
                        like 1,2 (default: all)
  --verbose, -v         Enable detailed per-test logging and error tracebacks
  --json [JSON_PATH]    Output machine-readable JSON report (default: test_report.json)
  --self-test           Execute self-test suite against mock proposals
```

### Exit Code Contract

| Exit Code | Meaning | Condition |
|---|---|---|
| `0` | **SUCCESS** | All executed tests passed without assertions or errors. |
| `1` | **FAILURE** | One or more test assertions failed or raised unexpected exceptions (proposal missing requirements). |
| `2` | **CONFIGURATION ERROR** | Specified proposal file not found, invalid tier arguments (e.g. `--tier 1,9`), parent directory unwritable for `--json`, or AST parse error. |

### Execution Examples

1. **Full Verification Suite Execution**:
   ```bash
   python3 tests/proposal_verification/test_proposal.py --proposal PRODUCTION_HARDENING_PROPOSAL.md
   ```

2. **Selective Tier Execution (e.g. Tiers 1 and 2)**:
   ```bash
   python3 tests/proposal_verification/test_proposal.py --proposal PRODUCTION_HARDENING_PROPOSAL.md --tier 1,2
   ```

3. **Detailed Verbose Output with JSON Summary Report**:
   ```bash
   python3 tests/proposal_verification/test_proposal.py --proposal PRODUCTION_HARDENING_PROPOSAL.md --verbose --json report.json
   ```

4. **Harness Self-Test (Validation against Synthetic Mock Proposals)**:
   ```bash
   python3 tests/proposal_verification/test_proposal.py --self-test
   ```

5. **Pytest Native Invocation**:
   ```bash
   pytest tests/proposal_verification/ --proposal PRODUCTION_HARDENING_PROPOSAL.md
   ```

6. **Python Unittest Discovery**:
   ```bash
   python3 -m unittest discover tests/proposal_verification
   ```

---

## Self-Test Attestation

The test suite includes a built-in verification mechanism (`--self-test`) that validates test discovery, assertion sensitivity, and exit codes using synthetic mock proposals generated on-the-fly:

- **Self-Test Step 1**: Missing proposal path (`/nonexistent/path/proposal.md`) $\rightarrow$ Exit code `2` (CONFIG ERROR).
- **Self-Test Step 2**: Fully compliant synthetic proposal $\rightarrow$ All 135 tests pass $\rightarrow$ Exit code `0` (PASS).
- **Self-Test Step 3**: Faulty proposal omitting Nginx proxy buffering $\rightarrow$ Tier 3 assertion fails $\rightarrow$ Exit code `1` (FAIL).
- **Self-Test Step 4**: Faulty proposal omitting Phase 3 enterprise scaling $\rightarrow$ Tier 4 assertion fails $\rightarrow$ Exit code `1` (FAIL).

Result: **100% Self-Test Pass Rate**. The test harness is verified and ready for opaque-box evaluation of `PRODUCTION_HARDENING_PROPOSAL.md`.
