# Certbot TLS E2E Test Suite Ready (`tests/certbot/`)

The automated Certbot TLS End-to-End (E2E) verification suite (`tests/certbot/`) on branch `expirement` has completed multi-agent Gate verification (**Iteration 3 Gate PASS**: 2/2 Reviewers `APPROVE`, 2/2 Challengers `APPROVE`, Auditor `CLEAN`) and is ready for **M4 Final Milestone** execution.

Derived strictly from `ORIGINAL_REQUEST.md` (2026-11-18T12:56:50Z follow-up), `PROJECT.md` Interface Contracts, and `SCOPE.md`, the suite provides opaque-box validation across host configuration/syntax, isolated `pt-nginx:latest` ephemeral containers, `MgmtAppBridge` (`pt-management:latest` with `--network none` and mock `docker`/`certbot` shims producing real OpenSSL X.509 certificates), cross-feature reload flows, and stack non-regression.

See `tests/certbot/CERTBOT_TEST_INFRA.md` for full harness internals and isolation design.

---

## 1. Test Runner & CLI Options

### Standard Invocation Commands

- **Unified Bash Runner (Recommended)**:
  ```bash
  bash tests/certbot/run_certbot_e2e.sh
  ```
- **Direct Pytest Invocation**:
  ```bash
  /home/kalpa/.local/share/mise/installs/python/3.14.7/bin/pytest tests/certbot/
  ```
  > **Note**: Host default `python3` (`3.15.2`) has a broken `pytest` shim; `run_certbot_e2e.sh` automatically selects `/home/kalpa/.local/share/mise/installs/python/3.14.7/bin/python` (`pytest 9.1.1`) and verifies `"$PY_BIN" -c "import pytest"` before execution.

### Supported CLI Options (`tests/certbot/run_certbot_e2e.sh`)

| Flag | Default | Description |
|---|---|---|
| `--tier 1\|2\|3\|4\|5\|all` | `all` | Select a tier (`1`, `2`, `3`, `4`, `5`), `all`, or a comma-separated list (e.g. `--tier 1,2,3,4` or `--tier 1,2,3,4,5`). Also supports `--tier=<SPEC>`. Invalid values exit `2`. |
| `--collect-only` | off | Run `pytest --collect-only -q` and exit `0` when collection succeeds cleanly. |
| `--static-only` | off | Run host-only static, syntax, and git checks (`--certbot-static-only -m "not docker and not live"`). Cannot be combined with `--live` (exits `2`). |
| `--live` | off | Enable `@pytest.mark.live` live-stack checks (`CERTBOT_E2E_LIVE=1` and `--certbot-live`). Without `--live`, live checks are deselected (`-m "not live"`) so running containers on ports `80`/`443`/`5000` remain untouched. |
| `-v`, `--verbose` | off | Enable verbose pytest output (`-vv --tb=short`). |
| `--json <file>` | off | Write a structured JSON test summary report to `<file>` (also supports `--json=<file>`). Exits `2` if `<file>` is a directory or its parent is unwritable. |
| `-k <expr>` | off | Forward pytest `-k <expr>` keyword filter expression (also supports `-k=<expr>`). |
| `-h`, `--help` | — | Print usage information and exit `0`. |

### Exit Code Contract

| Exit Code | Meaning |
|:---:|---|
| `0` | All selected tests passed (or clean collection under `--collect-only`). |
| `1` | One or more test assertions failed. |
| `2` | Usage/CLI validation error, invalid `--tier`/`--json` argument, missing/unusable Python or `pytest`, or pytest collection/internal/no-tests-selected error (pytest codes `2`, `3`, `4`, `5` are mapped to `2`). |

### Expected Result on Clean M2+M3+M4 Code

- **Tiers 1–4 non-live run** (`bash tests/certbot/run_certbot_e2e.sh --tier 1,2,3,4`): **`50/50` tests pass** (`1` `@pytest.mark.live` test deselected) with **exit code `0`**.
- **Tier 5 adversarial run** (`bash tests/certbot/run_certbot_e2e.sh --tier 5`): **`44/44` tests pass** with **exit code `0`**.
- **Default full non-live run** (`bash tests/certbot/run_certbot_e2e.sh` or `--tier all`): **`94/94` tests pass** (`1` `@pytest.mark.live` test deselected) with **exit code `0`**.
- **Full run with live stack** (`bash tests/certbot/run_certbot_e2e.sh --live`): **`95/95` tests pass** with **exit code `0`**.

---

## 2. Coverage Summary & Tier Breakdown

| Tier | File | Total Tests | Default Run | `--live` Run | Scope & Validation Focus |
|---|---|:---:|:---:|:---:|---|
| **Tier 1** | `tests/certbot/test_tier1_feature_config.py` | **17** | 17 | 17 | **Feature & Config Coverage**: M1 architecture doc, `.env.example`, `.gitignore`, `docker-compose.yml` YAML & `pt-certbot` contract, shell `bash -n`, `deploy*.sh`/`remove-instance.sh` directory mounts, `pt-certbot` files, `generate-nginx-conf.sh` 4-profile matrix (`self_signed`, `certbot_domain`, `http_only`, `geoip_ratelimit`) + `nginx -t`, `generate-ssl-cert.sh`, `EnvConfigManager` append/inode preservation, Certbot UI controls, and `/api/certbot/*` + `/api/upload/*` auth & contracts. |
| **Tier 2** | `tests/certbot/test_tier2_boundary_security.py` | **22** | 22 | 22 | **Boundary, Security & Corner Cases**: 14 parameterized injection/malformed payload rejections (`bad_payload0`–`bad_payload13`), upload path traversal rejection, git private-key tracking scan, `0600` key permissions & zero key leakage in API/HTML, mismatched/malformed/binary/encrypted upload rejection, ACME `/.well-known/acme-challenge/` GeoIP `444` & `301` bypass (HTTPS & HTTP-only), missing Certbot cert bootstrap fallback, and directory-mount atomic cert/symlink swap visibility. |
| **Tier 3** | `tests/certbot/test_tier3_cross_feature.py` | **6** | 6 | 6 | **Cross-Feature Interactions**: Combined Certbot + HTTPS + GeoIP + RateLimit + Production Nginx config preserving Guacamole WebSocket headers, `/api/student/files/`, and `health_check.sh` regexes; `switch-mode` missing-cert rejection (`400`); `self-signed` <-> `certbot` <-> `manual` transitions & reload; dual-port `:443` & `:5000` identical active X.509 cert parity; atomic renewal rotation `FP1 -> FP2` with `RestartCount == 0`; and `nginx -t` failure safety gate. |
| **Tier 4** | `tests/certbot/test_tier4_e2e_nonregression.py` | **6** | 5 | 6 | **End-to-End Scenarios & Non-Regression**: Full `pt-management` Certbot API lifecycle, full ephemeral Nginx TLS lifecycle (`self-signed` -> `certbot v1` -> `renew v2` -> `rollback`), git branch integrity (`HEAD == expirement`, `main == origin/main`), `test_tier0_local.sh` & `health_check.sh` invariants, existing `pt-management` endpoint non-regression, plus `1` `@pytest.mark.live` probe (`test_t4_live_nginx_and_acme_probe`, deselected unless `--live` is passed). |
| **Tier 5** | `tests/certbot/test_tier5_adversarial.py` | **44** | 44 | 44 | **White-Box Adversarial Hardening & Regressions**: 18 `pt-management` tests (504 timeouts, 409 flock contention, 503/500 container errors, domain normalization, dns-01/strict bools, ECDSA/Ed25519/sequential backup restore, X.509 edge cases, 403 non-admin auth, UI XSS/DOM safety, `BUG-1`..`BUG-7` regressions) + 26 M2 stack/harness tests (conditional HSTS, `.env` parsing/glob/inode safety, `=1` GeoIP/HTTPS flags, anchored/validated `PUBLIC_IP`, empty-domain certbot fallback, watcher debounce/signals, `pt-certbot` BusyBox env/signals/flock, deploy/compose parity, lazy `$pt_mgmt_upstream` resolution without `pt-management`, empty GeoIP token filtering, `BUG-M2-01`..`06`, `BUG-M2-R2-01`..`02` & `BUG-HARNESS-01` regressions). |
| **Total** | **`tests/certbot/`** | **95** | **94** | **95** | **94 default non-live tests (50 Tiers 1–4 + 44 Tier 5) + 1 `@pytest.mark.live` test**. |

---

## 3. Feature Checklist (F1–F12)

Mapping of all 12 surveyed requirements/features (`SCOPE.md` & `PROJECT.md`) to verified Tier 1–4 test functions:

| ID | Feature / Requirement | Covered Tiers | Verified Test Coverage (`tests/certbot/`) |
|---|---|---|---|
| **F1** | Written Architecture & Implementation Plan on `expirement` | Tier 1, Tier 4 | `test_t1_m1_architecture_doc_present_and_complete`, `test_t4_git_branch_integrity` |
| **F2** | ACME HTTP-01 challenge routing (`/.well-known/acme-challenge/`) & `SERVER_NAME` in `generate-nginx-conf.sh` + `nginx -t` | Tier 1, Tier 2 | `test_t1_generate_nginx_conf_matrix_and_nginx_test` (4 profiles), `test_t2_acme_bypass_vs_geoip_and_redirect_https_mode`, `test_t2_acme_bypass_vs_geoip_http_only_mode` |
| **F3** | Directory-level cert & Certbot mounts (`./ssl`, `./certbot/conf`, `./certbot/www`) in `deploy*.sh` & `docker-compose.yml` | Tier 1, Tier 2, Tier 3 | `test_t1_compose_yaml_and_certbot_contract`, `test_t1_deploy_scripts_no_single_file_ssl_bind_mounts`, `test_t2_directory_mount_sees_atomic_cert_and_symlink_swap`, `test_t3_renewal_atomic_rotation_and_reload_updates_443_and_5000` |
| **F4** | `pt-certbot` service & 12h renewal loop + `--deploy-hook` | Tier 1, Tier 3, Tier 4 | `test_t1_compose_yaml_and_certbot_contract`, `test_t1_certbot_service_files_contract`, `test_t3_certbot_deploy_hook_and_nginx_t_safety_gate`, `test_t4_full_mgmt_api_certbot_lifecycle` |
| **F5** | Zero-downtime `pt-nginx1` reload watcher & missing-cert bootstrap fallback | Tier 2, Tier 3 | `test_t2_missing_certbot_cert_fallback`, `test_t3_renewal_atomic_rotation_and_reload_updates_443_and_5000`, `test_t3_certbot_deploy_hook_and_nginx_t_safety_gate` |
| **F6** | Compose & Deploy alignment + TLS coverage on ports `443` and `5000` | Tier 1, Tier 3 | `test_t1_compose_syntax_valid`, `test_t1_compose_yaml_and_certbot_contract`, `test_t3_ports_443_and_5000_serve_identical_active_cert`, `test_t3_renewal_atomic_rotation_and_reload_updates_443_and_5000` |
| **F7** | `generate-ssl-cert.sh` non-interactive/fallback + `0600` key perms + `.env.example` / `.gitignore` | Tier 1, Tier 2 | `test_t1_env_example_documents_certbot_vars`, `test_t1_gitignore_ignores_certbot_and_ssl`, `test_t1_generate_ssl_cert_noninteractive_and_permissions`, `test_t2_no_private_keys_tracked_in_git`, `test_t2_private_key_permissions_and_no_api_leakage` |
| **F8** | `EnvConfigManager` key append fix (preserving bind-mount inode) | Tier 1, Tier 3 | `test_t1_env_config_append_and_inode_preservation`, `test_t3_coexistence_mode_transitions_and_nginx_reload` |
| **F9** | `pt-management` Certbot backend manager & `/api/certbot/*` endpoints (auth, validation, status, config, issue, renew, switch-mode) | Tier 1, Tier 2, Tier 3, Tier 4 | `test_t1_auth_enforcement_certbot_and_upload_endpoints`, `test_t1_authenticated_certbot_and_upload_api_contracts`, `test_t2_certbot_input_injection_and_malformed_rejection[0..13]`, `test_t2_private_key_permissions_and_no_api_leakage`, `test_t3_switch_mode_rejects_missing_target_certs`, `test_t3_coexistence_mode_transitions_and_nginx_reload`, `test_t4_full_mgmt_api_certbot_lifecycle` |
| **F10** | Manual SSL upload (`FileUploadManager` / `/api/upload/*`) X.509 cert/key match validation, `0600` key perms, RW write + reload | Tier 1, Tier 2, Tier 3 | `test_t1_auth_enforcement_certbot_and_upload_endpoints`, `test_t1_authenticated_certbot_and_upload_api_contracts`, `test_t2_upload_path_traversal_rejection`, `test_t2_manual_upload_mismatch_malformed_binary_encrypted_rejected`, `test_t3_coexistence_mode_transitions_and_nginx_reload` |
| **F11** | `pt-management` Admin Portal UI (`env_settings.html`, `env-config.js`) Certbot panel & X.509 status card | Tier 1 | `test_t1_ui_certbot_controls_static_and_rendered` |
| **F12** | Non-regression (`tests/test_tier0_local.sh`, `health_check.sh` compatibility) & git branch integrity (`expirement` only, `main` untouched) | Tier 1, Tier 3, Tier 4 | `test_t1_shell_syntax_all_scripts`, `test_t3_combined_nginx_config_preserves_guac_ws_student_api_and_healthcheck`, `test_t4_git_branch_integrity`, `test_t4_nonregression_static_and_healthcheck_invariants`, `test_t4_nonregression_mgmt_existing_endpoints`, `test_t4_full_ephemeral_nginx_tls_lifecycle`, `test_t4_live_nginx_and_acme_probe` (`--live`) |

---

## 4. M4 Execution Instructions & Remediation Status

### Preconditions Before Running Tiers 1–5

1. **Docker Image Currency**: Ensure `pt-nginx:latest`, `pt-certbot:latest`, and `pt-management:latest` are built from the latest M2/M3/M4 `expirement` sources:
   ```bash
   docker build -t pt-nginx:latest ptweb-vnc/pt-nginx
   docker build -t pt-certbot:latest ptweb-vnc/pt-certbot
   docker build -t pt-management:latest pt-management
   ```
2. **Branch & Non-Regression Prerequisites**:
   - Confirm active branch is `expirement` (`git branch --show-current` == `expirement`) and `main` is untouched (`main == origin/main`, zero Certbot changes on `main`).
   - Run existing baseline non-regression checks alongside the Certbot suite:
     ```bash
     bash tests/test_tier0_local.sh
     bash health_check.sh
     ```

### Recommended M4 Sequential Execution Commands

1. **Collection Sanity Check**:
   ```bash
   bash tests/certbot/run_certbot_e2e.sh --collect-only
   ```
   Expected: `94/95 tests collected (1 deselected)` with exit code `0`.

2. **Sequential Tier Execution**:
   ```bash
   bash tests/certbot/run_certbot_e2e.sh --tier 1 -v
   bash tests/certbot/run_certbot_e2e.sh --tier 2 -v
   bash tests/certbot/run_certbot_e2e.sh --tier 3 -v
   bash tests/certbot/run_certbot_e2e.sh --tier 4 -v
   bash tests/certbot/run_certbot_e2e.sh --tier 5 -v
   ```

3. **Tiers 1–4 & Full Non-Live Suite (Combined Gate Checks)**:
   ```bash
   bash tests/certbot/run_certbot_e2e.sh --tier 1,2,3,4 -v
   bash tests/certbot/run_certbot_e2e.sh --tier all -v
   ```
   Expected: **`50/50`** for `--tier 1,2,3,4` and **`94/94`** for `--tier all`, exit code `0`.

4. **Live-Stack Verification** *(after live stack containers on ports `80`/`443`/`5000` are verified healthy)*:
   ```bash
   bash tests/certbot/run_certbot_e2e.sh --live -v
   ```
   Expected: **`95/95` passed**, exit code `0`.

---

### Resolved M3 & M4 Phase 2 Gaps

- **`bad_payload8` (Tier 2)**: Resolved in `CertbotManager.save_config()` (`pt-management/ptmanagement/api/certbot_manager.py`), which rejects `enabled=True` with empty `CERTBOT_DOMAIN` (`HTTP 400`); Tier 2 passes **`22/22`**.
- **M4 Phase 2 Adversarial Remediations**: Resolved `BUG-1`..`BUG-7` (`pt-management/**`), `BUG-M2-01`..`BUG-M2-06` and `BUG-M2-R2-01`..`BUG-M2-R2-02` (`generate-nginx-conf.sh`, `deploy.sh`, `remove-instance.sh`, `pt-certbot/entrypoint.sh`, `CERTBOT_TEST_READY.md`), and `BUG-HARNESS-01` (`tests/certbot/helpers.py`), verified by all `44/44` Tier 5 tests.
