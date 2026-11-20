"""
Tier 4: End-to-End Lifecycle, Branch Integrity & Non-Regression Tests.

Validates:
- Full `pt-management` Certbot API lifecycle (self-signed -> config -> dry-run -> issue -> status -> renew -> rollback)
- Full ephemeral Nginx + mock-upstream lifecycle on an isolated Docker bridge network
- Git branch integrity (`HEAD == expirement`, `main == origin/main`, zero Certbot changes on `main`)
- Safe non-regression checks (`test_tier0_local.sh` invariants, `health_check.sh` compatibility,
  existing `/api/env/*`, `/api/upload/*`, `/dashboard`, `/settings`, `/files` endpoints)
- `@pytest.mark.live` checks against the running stack (ONLY executed when `--live` / `--certbot-live` is passed)
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest
import requests

from tests.certbot.helpers import (
    EphemeralNginxRunner,
    MgmtAppBridge,
    generate_test_ca,
    read_env_file,
    repo_root,
    seed_certbot_live_cert,
    temp_stack_ws,
    update_env_values,
    x509_metadata,
)


pytestmark = pytest.mark.tier4


def _snapshot_live_containers() -> dict[str, tuple[str, str]]:
    snap: dict[str, tuple[str, str]] = {}
    for name in ("pt-nginx1", "pt-management", "pt-guacamole"):
        res = subprocess.run(
            ["docker", "inspect", "-f", "{{.Id}} {{.State.StartedAt}}", name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode == 0 and res.stdout.strip():
            parts = res.stdout.strip().split(" ", 1)
            snap[name] = (parts[0], parts[1] if len(parts) > 1 else "")
    return snap


@pytest.mark.docker
def test_t4_full_mgmt_api_certbot_lifecycle(tmp_path: Path) -> None:
    """End-to-end pt-management API lifecycle via MgmtAppBridge + mock docker/certbot + real openssl certs."""
    ws = temp_stack_ws(tmp_path)
    bridge = MgmtAppBridge(ws)

    # 1. Baseline self-signed status
    s0 = bridge.request("GET", "/api/certbot/status")
    assert s0["status_code"] == 200, f"Initial status failed: {s0['body']}"
    assert (s0["json"] or {}).get("tls_mode") == "self-signed"

    # 2. Configure Certbot domain & SANs
    cfg = bridge.request(
        "POST",
        "/api/certbot/config",
        json_body={
            "domain": "lab.example.edu",
            "extra_domains": "portal.example.edu",
            "email": "netadmin@example.edu",
            "challenge_type": "http-01",
            "staging": True,
            "auto_renew": True,
        },
    )
    assert cfg["status_code"] == 200, f"Config failed: {cfg['body']}"
    env_cfg = read_env_file(ws / ".env")
    assert env_cfg.get("CERTBOT_DOMAIN") == "lab.example.edu"
    assert env_cfg.get("CERTBOT_EXTRA_DOMAINS") == "portal.example.edu"

    # 3. Dry-run issue leaves TLS_MODE untouched
    dry = bridge.request("POST", "/api/certbot/issue", json_body={"dry_run": True})
    assert dry["status_code"] == 200, f"Dry-run issue failed: {dry['body']}"
    assert read_env_file(ws / ".env").get("TLS_MODE") == "self-signed"

    # 4. Real mocked issue produces cert serial #1, switches TLS_MODE=certbot, regenerates & reloads
    bridge.clear_logs()
    iss = bridge.request("POST", "/api/certbot/issue", json_body={"dry_run": False})
    assert iss["status_code"] == 200, f"Real mocked issue failed: {iss['body']}"
    env_issued = read_env_file(ws / ".env")
    assert env_issued.get("TLS_MODE") == "certbot"
    assert "/etc/letsencrypt/live/lab.example.edu/fullchain.pem" in env_issued.get("SSL_CERT_PATH", "")
    assert "lab.example.edu" in env_issued.get("SERVER_NAME", "")
    ptweb_cfg_issued = (ws / "ptweb-vnc" / "pt-nginx" / "conf" / "ptweb.conf").read_text(encoding="utf-8")
    assert "lab.example.edu" in ptweb_cfg_issued
    assert "portal.example.edu" in ptweb_cfg_issued

    live_crt = ws / "certbot" / "conf" / "live" / "lab.example.edu" / "fullchain.pem"
    assert live_crt.exists(), "Mock certbot did not issue fullchain.pem"
    meta1 = x509_metadata(live_crt)
    assert meta1["cn"] == "lab.example.edu"
    assert "portal.example.edu" in meta1["sans"]

    # 5. Status reflects new Certbot certificate without leaking private key
    s1 = bridge.request("GET", "/api/certbot/status")
    assert s1["status_code"] == 200
    assert (s1["json"] or {}).get("tls_mode") == "certbot"
    assert "lab.example.edu" in s1["body"]
    assert "PRIVATE KEY" not in s1["body"]

    # 6. Renew rotates cert to serial #2 and reloads Nginx
    bridge.clear_logs()
    ren = bridge.request("POST", "/api/certbot/renew", json_body={"force_renewal": True})
    assert ren["status_code"] == 200, f"Renew failed: {ren['body']}"
    meta2 = x509_metadata(live_crt)
    assert meta2["serial"] != meta1["serial"] or meta2["fingerprint"] != meta1["fingerprint"], (
        "Renew did not rotate certificate serial/fingerprint"
    )
    assert any("nginx -s reload" in c for c in bridge.docker_calls())

    # 7. Switch back to self-signed
    sw = bridge.request("POST", "/api/certbot/switch-mode", json_body={"tls_mode": "self-signed"})
    assert sw["status_code"] == 200, f"Switch-mode rollback failed: {sw['body']}"
    assert read_env_file(ws / ".env").get("TLS_MODE") == "self-signed"
    ptweb_back = (ws / "ptweb-vnc" / "pt-nginx" / "conf" / "ptweb.conf").read_text(encoding="utf-8")
    assert "/etc/ssl/ptweb/server.crt" in ptweb_back


@pytest.mark.docker
def test_t4_full_ephemeral_nginx_tls_lifecycle(
    tmp_path: Path, ephemeral_nginx: EphemeralNginxRunner
) -> None:
    """End-to-end ephemeral Nginx + mock-upstream lifecycle: bootstrap -> certbot v1 -> renew v2 -> rollback."""
    live_before = _snapshot_live_containers()
    ws = temp_stack_ws(tmp_path)

    # Phase A: Bootstrap self-signed via generate-ssl-cert.sh
    gen_ssl = ws / "generate-ssl-cert.sh"
    assert gen_ssl.exists(), "generate-ssl-cert.sh missing from workspace"
    (ws / "ssl" / "server.crt").unlink(missing_ok=True)
    (ws / "ssl" / "server.key").unlink(missing_ok=True)
    args = ["bash", str(gen_ssl)]
    if "--non-interactive" in gen_ssl.read_text(encoding="utf-8"):
        args.append("--non-interactive")
    r_ssl = subprocess.run(args, cwd=str(ws), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15)
    assert r_ssl.returncode == 0, r_ssl.stderr
    fp_self = x509_metadata(ws / "ssl" / "server.crt")["fingerprint"]

    update_env_values(
        ws / ".env",
        {
            "PRODUCTION_MODE": "false",
            "ENABLE_HTTPS": "true",
            "TLS_MODE": "self-signed",
            "SERVER_NAME": "localhost",
            "SSL_CERT_PATH": "/etc/ssl/ptweb/server.crt",
            "SSL_KEY_PATH": "/etc/ssl/ptweb/server.key",
            "NGINX_GEOIP_ALLOW": "true",
            "GEOIP_ALLOW_COUNTRIES": "FI,US",
            "NGINX_GEOIP_BLOCK": "false",
            "NGINX_RATE_LIMIT_ENABLE": "false",
        },
    )
    assert ephemeral_nginx.run_generate_nginx_conf(ws).returncode == 0

    acme_dir = ws / "certbot" / "www" / ".well-known" / "acme-challenge"
    acme_dir.mkdir(parents=True, exist_ok=True)
    (acme_dir / "e2e-token").write_text("e2e-acme-challenge-ok", encoding="utf-8")

    srv = ephemeral_nginx.start_server(
        ws,
        enable_realip_header=True,
        with_stub_upstreams=True,
        mount_legacy_ssl_files=False,
        wait_ports=[80, 443, 5000],
    )
    cid = srv["container"]

    r_acme_e2e = requests.get(
        f"http://127.0.0.1:{srv['p80']}/.well-known/acme-challenge/e2e-token",
        headers={"X-Test-IP": "1.1.1.1"},
        allow_redirects=False,
        timeout=4,
    )
    assert r_acme_e2e.status_code == 200 and r_acme_e2e.text == "e2e-acme-challenge-ok"
    assert requests.get(
        f"http://127.0.0.1:{srv['p80']}/",
        headers={"X-Test-IP": "193.166.4.1"},
        allow_redirects=False,
        timeout=4,
    ).status_code == 301
    assert ephemeral_nginx.get_tls_cert_info("127.0.0.1", srv["p443"], "localhost")["fingerprint"] == fp_self
    assert ephemeral_nginx.get_tls_cert_info("127.0.0.1", srv["p5000"], "localhost")["fingerprint"] == fp_self

    r_guac = requests.get(
        f"https://127.0.0.1:{srv['p443']}/",
        headers={"X-Test-IP": "193.166.4.1"},
        verify=False,
        allow_redirects=False,
        timeout=4,
    )
    assert r_guac.status_code == 200 and "GUAC_STUB_OK" in r_guac.text
    with pytest.raises(requests.exceptions.ConnectionError):
        requests.get(
            f"https://127.0.0.1:{srv['p443']}/",
            headers={"X-Test-IP": "1.1.1.1"},
            verify=False,
            allow_redirects=False,
            timeout=4,
        )

    def _wait_cert_fp(servername: str, expected_fp: str, timeout_s: float = 5.0) -> None:
        deadline = time.monotonic() + timeout_s
        last_443 = last_5000 = ""
        while time.monotonic() < deadline:
            last_443 = ephemeral_nginx.get_tls_cert_info("127.0.0.1", srv["p443"], servername)["fingerprint"]
            last_5000 = ephemeral_nginx.get_tls_cert_info("127.0.0.1", srv["p5000"], servername)["fingerprint"]
            if last_443 == expected_fp and last_5000 == expected_fp:
                return
            time.sleep(0.25)
        raise AssertionError(
            f"Timed out waiting {timeout_s}s for :443/:5000 cert {expected_fp} (SNI={servername}); "
            f"last_443={last_443}, last_5000={last_5000}"
        )

    # Phase B: Initial issuance transition (self-signed -> certbot v1)
    ca_crt, ca_key = generate_test_ca(tmp_path / "ca")
    cb_v1 = seed_certbot_live_cert(
        ws / "certbot" / "conf",
        "pt.example.test",
        ca_crt,
        ca_key,
        version=1,
        days=60,
        serial=7001,
    )
    update_env_values(
        ws / ".env",
        {
            "TLS_MODE": "certbot",
            "CERTBOT_ENABLED": "true",
            "CERTBOT_DOMAIN": "pt.example.test",
            "SERVER_NAME": "pt.example.test",
            "SSL_CERT_PATH": "/etc/letsencrypt/live/pt.example.test/fullchain.pem",
            "SSL_KEY_PATH": "/etc/letsencrypt/live/pt.example.test/privkey.pem",
        },
    )
    assert ephemeral_nginx.run_generate_nginx_conf(ws).returncode == 0
    r_rel1 = ephemeral_nginx.exec_in(cid, ["sh", "-c", "nginx -t && nginx -s reload"])
    assert r_rel1.returncode == 0, r_rel1.stderr

    _wait_cert_fp("pt.example.test", cb_v1["fingerprint"])
    assert ephemeral_nginx.inspect_container(cid)["RestartCount"] == 0

    # Phase C: Automated renewal swap (FP_CB1 -> FP_CB2)
    cb_v2 = seed_certbot_live_cert(
        ws / "certbot" / "conf",
        "pt.example.test",
        ca_crt,
        ca_key,
        version=2,
        days=90,
        serial=7002,
    )
    r_rel2 = ephemeral_nginx.exec_in(cid, ["sh", "-c", "nginx -t && nginx -s reload"])
    assert r_rel2.returncode == 0, r_rel2.stderr
    _wait_cert_fp("pt.example.test", cb_v2["fingerprint"])
    assert ephemeral_nginx.inspect_container(cid)["RestartCount"] == 0

    # Phase D: Rollback to self-signed
    update_env_values(
        ws / ".env",
        {
            "TLS_MODE": "self-signed",
            "SERVER_NAME": "localhost",
            "SSL_CERT_PATH": "/etc/ssl/ptweb/server.crt",
            "SSL_KEY_PATH": "/etc/ssl/ptweb/server.key",
        },
    )
    assert ephemeral_nginx.run_generate_nginx_conf(ws).returncode == 0
    r_rel3 = ephemeral_nginx.exec_in(cid, ["sh", "-c", "nginx -t && nginx -s reload"])
    assert r_rel3.returncode == 0, r_rel3.stderr
    _wait_cert_fp("localhost", fp_self)

    # Phase E: Live stack containers remained completely untouched
    live_after = _snapshot_live_containers()
    assert live_after == live_before, f"Live stack containers changed! before={live_before} after={live_after}"


def test_t4_git_branch_integrity() -> None:
    """Repository HEAD is strictly on `expirement`, `main` matches `origin/main`, and zero Certbot artifacts exist on `main`."""
    root = repo_root()

    head = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(root), text=True).strip()
    assert head == "expirement", f"Expected active branch 'expirement', got '{head}'"

    main_sha = subprocess.check_output(["git", "rev-parse", "main"], cwd=str(root), text=True).strip()
    orig_main_res = subprocess.run(
        ["git", "rev-parse", "origin/main"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=10,
    )
    if orig_main_res.returncode == 0:
        assert main_sha == orig_main_res.stdout.strip(), "Local 'main' branch diverged from 'origin/main'"

    main_files = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", "main"],
        cwd=str(root),
        text=True,
    ).splitlines()
    certbot_on_main = [
        f
        for f in main_files
        if "pt-certbot" in f or "certbot_routes" in f or "certbot_manager" in f or "certbot_tls_architecture" in f
    ]
    assert not certbot_on_main, f"Certbot files must NOT exist on branch 'main': {certbot_on_main}"


def test_t4_nonregression_static_and_healthcheck_invariants() -> None:
    """Preserve test_tier0_local.sh Group 1 invariants and health_check.sh ptweb.conf & .env sourcing invariants."""
    root = repo_root()

    # No hardcoded /run/media/kalpa paths in deployment/management scripts
    for check_dir in (root / "ptweb-vnc", root / "pt-management"):
        for f in check_dir.rglob("*"):
            if f.is_file() and f.suffix in (".sh", ".py", ".yml"):
                txt = f.read_text(encoding="utf-8", errors="ignore")
                assert "/run/media/kalpa" not in txt, f"Hardcoded local path /run/media/kalpa found in {f}"

    # Existing ptweb.conf preserves GeoIP + rate limit + proxy_pass for health_check.sh
    ptweb_conf = (root / "ptweb-vnc" / "pt-nginx" / "conf" / "ptweb.conf").read_text(encoding="utf-8")
    assert "proxy_pass http://pt-guacamole:8080/guacamole/" in ptweb_conf
    assert "location /" in ptweb_conf

    # `.env` on disk (if present) must be safely parseable by `bash -n` (health_check.sh sources `.env`)
    repo_env = root / ".env"
    if repo_env.exists():
        res = subprocess.run(["bash", "-n", str(repo_env)], capture_output=True, text=True, timeout=10)
        assert res.returncode == 0, f"Repo .env is not bash-source-safe (breaks health_check.sh):\n{res.stderr}"


@pytest.mark.docker
def test_t4_nonregression_mgmt_existing_endpoints(tmp_path: Path) -> None:
    """Existing pt-management endpoints (/api/env/defaults, /api/env/config, /api/upload/certificate, /dashboard, /settings, /files) work."""
    ws = temp_stack_ws(tmp_path)
    bridge = MgmtAppBridge(ws)

    unauth = bridge.http_sequence(
        [
            {"method": "GET", "path": "/api/env/defaults"},
            {"method": "GET", "path": "/api/env/config"},
            {"method": "POST", "path": "/api/upload/certificate"},
            {"method": "GET", "path": "/dashboard"},
            {"method": "GET", "path": "/settings"},
            {"method": "GET", "path": "/files"},
        ],
        login=False,
    )["responses"]
    assert unauth[0]["status_code"] == 200
    assert unauth[1]["status_code"] == 401
    assert unauth[2]["status_code"] == 401
    assert unauth[3]["status_code"] == 302
    assert unauth[4]["status_code"] == 302
    assert unauth[5]["status_code"] == 302

    auth = bridge.http_sequence(
        [
            {"method": "GET", "path": "/api/env/config"},
            {"method": "GET", "path": "/dashboard"},
            {"method": "GET", "path": "/settings"},
        ],
        login=True,
    )["responses"]
    assert auth[0]["status_code"] == 200
    assert auth[1]["status_code"] == 200
    assert auth[2]["status_code"] == 200


@pytest.mark.live
@pytest.mark.docker
def test_t4_live_nginx_and_acme_probe() -> None:
    """LIVE-ONLY: Validate running pt-nginx1 `nginx -t`, live ACME probe, and live port 5000 health/auth."""
    res = subprocess.run(["docker", "exec", "pt-nginx1", "nginx", "-t"], capture_output=True, text=True, timeout=15)
    assert res.returncode == 0, f"Live pt-nginx1 nginx -t failed:\n{res.stderr}"

    r_health = requests.get("https://localhost:5000/health", verify=False, timeout=5)
    assert r_health.status_code == 200

    r_cb_unauth = requests.get("https://localhost:5000/api/certbot/status", verify=False, timeout=5)
    assert r_cb_unauth.status_code == 401, f"Live /api/certbot/status unauth expected 401, got {r_cb_unauth.status_code}"

    # Non-destructive ACME webroot probe cleaned up in finally
    probe_dir = repo_root() / "certbot" / "www" / ".well-known" / "acme-challenge"
    probe_dir.mkdir(parents=True, exist_ok=True)
    probe_file = probe_dir / f"live-probe-{os.getpid()}"
    try:
        probe_file.write_text("live-acme-ok", encoding="utf-8")
        r_acme = requests.get(f"http://127.0.0.1/.well-known/acme-challenge/{probe_file.name}", timeout=5)
        assert r_acme.status_code == 200 and r_acme.text == "live-acme-ok"
    finally:
        if probe_file.exists():
            probe_file.unlink()
