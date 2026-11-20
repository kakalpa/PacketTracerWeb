# PacketTracerWeb Certbot TLS E2E Test Infrastructure

## Overview

The Certbot TLS E2E verification suite (`tests/certbot/`) provides an automated, opaque-box, requirement-driven validation framework for automated Let's Encrypt (Certbot) TLS issuance, renewal, zero-downtime Nginx certificate reload, `pt-management` Admin Portal configuration, and stack non-regression on branch `expirement`.

```
                  [ bash tests/certbot/run_certbot_e2e.sh ]
                    (Python 3.14.7 / pytest 9.1.1 discovery)
                                       │
          ┌────────────────────────────┼────────────────────────────┐
          ▼                            ▼                            ▼
  [ Host Static / Git ]    [ Ephemeral pt-nginx:latest ]   [ MgmtAppBridge ]
  - YAML/Compose/Shell     - Dynamic 127.0.0.1:<free>      - pt-management:latest
  - M1 Doc & .env.example  - --add-host stub upstreams       (--network none)
  - cryptography X.509/CA  - 00-test-realip.conf GeoIP     - app.test_client()
  - Git branch integrity   - Atomic symlink / reload       - Mock docker+certbot
          │                            │                            │
          └────────────────────────────┴────────────────────────────┘
                                       │
       ┌──────────────┬────────────────┼────────────────┬──────────────┐
       ▼              ▼                ▼                ▼              ▼
  [ Tier 1 ]     [ Tier 2 ]       [ Tier 3 ]       [ Tier 4 ]     [ Tier 5 ]     [ --live ]
  Feature &      Boundary &       Cross-Feature    E2E Lifecycle  Adversarial    Live Stack
  Config         Security         & Reload         & Regression   Hardening      Probes
  (17 items)     (22 items)       (6 items)        (5 items)      (44 items)     (1 item)
```

---

## File Inventory (`tests/certbot/`)

| File | Role | Description |
|---|---|---|
| `__init__.py` | Package Marker | Marks `tests/certbot` as a Python test package. |
| `run_certbot_e2e.sh` | Unified CLI Runner | Executable Bash entry point (`chmod +x`). Auto-discovers Python 3.14.7 + `pytest`, validates `bash -n`, parses `--tier`, `--collect-only`, `--static-only`, `--live`, `--verbose`, `--json`, `-k`, and enforces exit codes `0`/`1`/`2`. |
| `conftest.py` | Pytest Configuration | Registers markers (`tier1`–`tier5`, `mgmt`, `docker`, `live`), adds `--certbot-live` and `--certbot-static-only` (avoiding `--tier`/`--proposal` collision with `tests/proposal_verification/conftest.py`), deselects `live` by default, and provides `repo_dir`, `stack_ws`, `ephemeral_nginx`, and `mgmt_bridge` fixtures. |
| `helpers.py` | Test Harness & Generators | Implements `temp_stack_ws()`, OpenSSL/`cryptography` self-signed & Test-CA cert generators, `free_tcp_port()`, `EphemeralNginxRunner`, and `MgmtAppBridge` (with mock `docker` & `certbot` shims generating real X.509 certs). |
| `_mgmt_harness.py` | Container-Side Runner | Executed inside `pt-management:latest` (or in-process if `flask` is importable) to drive `create_app().test_client()` and `EnvConfigManager` / `FileUploadManager` / `CertbotManager` via JSON stdin/stdout. |
| `test_tier1_feature_config.py` | Tier 1 Suite | Validates M1 doc, `.env.example`, `.gitignore`, `docker-compose.yml`, shell `bash -n`, `pt-certbot` service, `generate-nginx-conf.sh` matrix, `generate-ssl-cert.sh`, `EnvConfigManager` append/inode, UI, and `/api/certbot/*` + `/api/upload/*` auth & contracts. |
| `test_tier2_boundary_security.py` | Tier 2 Suite | Validates input injection rejection (14 malformed/injection payloads), path traversal rejection, `0600` key perms, zero key leakage, mismatched/malformed/binary/encrypted upload rejection, ACME GeoIP/301 bypass, missing-cert fallback, and directory-mount atomic swaps. |
| `test_tier3_cross_feature.py` | Tier 3 Suite | Validates combined Nginx config (`certbot` + HTTPS + GeoIP + RateLimit + Production), mode switching (`self-signed` <-> `certbot` <-> `manual`), identical TLS certs on `:443` & `:5000`, atomic symlink renewal reload with `RestartCount == 0`, and `nginx -t` failure gating. |
| `test_tier4_e2e_nonregression.py` | Tier 4 Suite | Validates full `pt-management` API lifecycle, full ephemeral Nginx lifecycle on an isolated bridge network, git branch integrity (`expirement` vs `main`), `test_tier0_local.sh` & `health_check.sh` invariants, existing `pt-management` endpoints, and optional `--live` probes. |
| `test_tier5_adversarial.py` | Tier 5 Suite | White-box adversarial hardening & bug-regression suite (44 tests: 18 `pt-management` tests + 26 M2 stack/harness tests). |
| `CERTBOT_TEST_INFRA.md` | Documentation | This architecture and specification document. |

---

## Host vs. Container Execution Strategy

1. **Python & Pytest Selection**:
   - Host default `python3` (`3.15.2`) has a broken `pytest` shim; `mise python@3.14.7` (`/home/kalpa/.local/share/mise/installs/python/3.14.7/bin/pytest`) has `pytest 9.1.1`, `cryptography`, `PyYAML`, `requests`, and `python-dotenv`, while `pt-management:latest` (Python `3.11.18`) contains `Flask 3.0.0`, `Werkzeug`, `mysql-connector-python`, `docker`, and `openssl` CLI.
   - `run_certbot_e2e.sh` validates `"$PY_BIN" -c "import pytest"` before invoking `pytest`, rejecting unusable interpreters with exit code `2`.
   - Test modules **never** import `flask` or `ptmanagement` at module top level, guaranteeing clean `pytest --collect-only` on host Python `3.14.7`.
2. **`MgmtAppBridge` Isolation**:
   - Auto-selects in-process execution only if `flask`, `dotenv`, `mysql`, and `docker` are all importable; otherwise runs `docker run --rm --network none --entrypoint python3 -v <repo>/pt-management:/work_app:ro -v <tmp_ws>:/test_ws:rw ... pt-management:latest /_mgmt_harness.py`.
   - Overrides `ENV_PATH`, `PROJECT_ROOT`, `SSL_DIR`, `SSL_KEY_DIR`, `CERTBOT_CONF_DIR`, `CERTBOT_WEBROOT`, `SECRET_KEY`, `PTADMIN_PASSWORD`, and prepends `<tmp_ws>/bin` (containing mock `docker` and `certbot` executables) to `PATH`.
   - Mock `certbot` uses real `/usr/bin/openssl` inside the container to generate genuine X.509 certificates with `0600` private keys and distinct serial numbers.
3. **`EphemeralNginxRunner` Isolation**:
   - Ephemeral `nginx -t` passes `--add-host pt-management:127.0.0.1 --add-host pt-guacamole:127.0.0.1` so Nginx config parsing succeeds outside the live `ptnet` network.
   - Ephemeral serving containers bind strictly to `127.0.0.1:<free_port>` for ports `80`, `443`, `5000` on isolated Docker bridge networks (`pt-certbot-e2e-<pid>-<rand>`) with lightweight HTTP stub upstreams (`pt-guacamole`, `pt-management`), and are cleaned up unconditionally in `finally`.
   - GeoIP tests inject a test-only `00-test-realip.conf` (`real_ip_header X-Test-IP;`) in the ephemeral container to test real `GeoIP.dat` lookups (`1.1.1.1` / `77.88.55.80` -> strict `444` TCP close vs `193.166.4.1` -> `200`) without altering production configs.
   - Tier 3 autonomous watcher tests (`test_t3_renewal_atomic_rotation_and_reload_updates_443_and_5000` and `test_t3_certbot_deploy_hook_and_nginx_t_safety_gate`) start `pt-nginx:latest` with `NGINX_CERT_WATCH_INTERVAL=1` and verify autonomous reload (without manual `nginx -s reload` fallback) and `nginx -t` failure gating. **Precondition**: `pt-nginx:latest` must be rebuilt from M2's updated `ptweb-vnc/pt-nginx/` (`docker build -t pt-nginx:latest ptweb-vnc/pt-nginx`) before running Tier 3.
4. **Option Collision Avoidance**:
   - `tests/proposal_verification/conftest.py` registers `--proposal` and `--tier` on pytest's global option parser. `tests/certbot/conftest.py` uses `--certbot-live` and `--certbot-static-only` instead, allowing `pytest tests/` to collect the entire repository cleanly.

---

## Multi-Tier Coverage Matrix

| Tier | File | Scope | Marker |
|---|---|---|---|
| Tier 1 | `test_tier1_feature_config.py` | M1 doc, `.env.example`, `.gitignore`, Compose YAML/JSON (incl. custom `pt-nginx` & `pt-certbot` least-privilege), `bash -n`, `deploy*.sh`/`remove-instance.sh` mounts, `pt-certbot` files, `generate-nginx-conf.sh` 4-profile matrix + `nginx -t`, `generate-ssl-cert.sh`, `EnvConfigManager` append/inode, UI & `/api/certbot/*` + `/api/upload/*` auth & staged matched-pair upload contracts | `@pytest.mark.tier1` |
| Tier 2 | `test_tier2_boundary_security.py` | Domain/email/challenge shell & newline injection rejection (14 cases), upload path traversal rejection, git key tracking scan, `0600` perms & zero key leakage, mismatched/malformed/binary/encrypted upload rejection, ACME `/.well-known/acme-challenge/` GeoIP `444` & `301` bypass (HTTPS & HTTP-only), missing-cert fallback, directory-mount atomic swap visibility | `@pytest.mark.tier2` |
| Tier 3 | `test_tier3_cross_feature.py` | Combined Certbot + HTTPS + GeoIP + RateLimit + Production Nginx config, `self-signed` <-> `certbot` <-> `manual` transitions & missing-cert rejection, dual-port `:443` & `:5000` cert parity, atomic renewal symlink rotation `FP1 -> FP2` with `RestartCount == 0`, `nginx -t` failure gate | `@pytest.mark.tier3` |
| Tier 4 | `test_tier4_e2e_nonregression.py` | Full `pt-management` API lifecycle, full ephemeral Nginx + stub-upstream lifecycle (`self-signed` -> `certbot v1` -> `renew v2` -> `rollback`), git branch integrity (`HEAD == expirement`, `main == origin/main`), `test_tier0_local.sh` & `health_check.sh` invariants, existing `pt-management` endpoint regression, optional `--live` probes | `@pytest.mark.tier4` |
| Tier 5 | `test_tier5_adversarial.py` | White-box adversarial hardening & bug regressions across `pt-management/**` (timeouts, flock, domain normalization, ECDSA/Ed25519, 403 auth, XSS, `BUG-1`..`BUG-7`) and M2 stack/harness (conditional HSTS, `.env` parsing/glob/inode, `=1` parity, anchored/validated `PUBLIC_IP`, watcher debounce/signals, `pt-certbot` BusyBox env/flock, lazy `$pt_mgmt_upstream` resolution without `pt-management`, empty GeoIP token filtering, `BUG-M2-01`..`06`, `BUG-M2-R2-01`..`02`, `BUG-HARNESS-01`) | `@pytest.mark.tier5` |

---

## CLI Runner (`run_certbot_e2e.sh`) Reference

### Options

| Flag | Description |
|---|---|
| `--tier <1\|2\|3\|4\|5\|all\|1,2,...>` | Select one or more tiers (default: `all`). Invalid values exit `2`. |
| `--collect-only` | Run `pytest --collect-only -q` and exit `0` when collection succeeds. |
| `--static-only` | Run host-only tests (`-m "not docker and not live"`). Cannot combine with `--live`. |
| `--live` | Enable `@pytest.mark.live` checks (`CERTBOT_E2E_LIVE=1`). Deselected by default. |
| `--verbose`, `-v` | Enable verbose output (`-vv --tb=short`). |
| `--json <PATH>` | Write structured JSON summary report to `<PATH>`. |
| `-k <EXPR>` | Forward pytest `-k <EXPR>` filter expression. |
| `-h`, `--help` | Print usage and exit `0`. |

### Exit Code Contract

| Exit Code | Meaning |
|---|---|
| `0` | All selected tests passed (or clean collection with `--collect-only`). |
| `1` | One or more test assertions failed. |
| `2` | Usage error, invalid `--tier`/`--json` argument, missing/broken Python/`pytest`, or pytest collection/internal error (pytest codes `2`, `3`, `4`, `5` mapped to `2`). |

---

## Non-Regression & Live-Stack Safety Rules

1. **Live Stack Protection**: Live containers (`pt-nginx1`, `pt-management`, `pt-guacamole`, `pt-guacd`, `guacamole-mariadb`, `ptvnc*`) bind host ports `80`, `443`, `5000`. All `@pytest.mark.live` checks are **deselected by default** via `conftest.py` (`pytest_collection_modifyitems`) and `run_certbot_e2e.sh` (`-m "not live"`) unless `--live` / `--certbot-live` is explicitly passed.
2. **No Silent Skips**: Optional runtime scopes are filtered cleanly by pytest marker deselection; individual test functions never call `pytest.skip` or `pytest.xfail` to mask unimplemented contracts.
3. **`health_check.sh` Compatibility**:
   - `health_check.sh` runs `source "$WORKDIR/.env"` and inspects `ptweb.conf` with `grep -A 5 'location /'` for `$allowed_country`/`$blocked_country` and `grep -A 30 'location /'` for `limit_req zone=pt_req_zone`. Tiers 1, 3, and 4 explicitly verify these invariants.
4. **`Scripts/test-ssl-setup.sh` Caveat**:
   - `Scripts/test-ssl-setup.sh` assumes `CN=localhost` and `SUBJECT=ISSUER` (self-signed only) and resolves paths relative to `Scripts/`. It is therefore excluded from CA-signed `TLS_MODE=certbot` assertions; instead, Tier 1 and Tier 4 validate `generate-ssl-cert.sh` in an isolated workspace and verify active TLS certificates across all modes via `cryptography.x509`.
5. **Branch Integrity**:
   - Tier 4 unconditionally asserts `HEAD == expirement`, `main == origin/main`, and zero Certbot changes on `main`.
