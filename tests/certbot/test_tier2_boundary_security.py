"""
Tier 2: Boundary, Input Validation, Injection Prevention & Security Tests.

Validates:
- Rejection of shell injection, newline injection, traversal & invalid domains/emails/challenges
- Private key protection: 0600 permissions, zero key leakage in API/HTML, zero keys in git
- Manual upload rejection of mismatched cert/key pairs, malformed PEM, binary garbage, encrypted keys
- ACME `/.well-known/acme-challenge/` GeoIP 444 & 301 redirect bypass in HTTPS & HTTP-only modes
- Missing Certbot certificate bootstrap fallback (no Nginx crash loop)
- Directory-mount vs single-file inode swap visibility inside `pt-nginx:latest`
"""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from pathlib import Path

import pytest
import requests

from tests.certbot.helpers import (
    PRIVATE_KEY_MARKERS,
    EphemeralNginxRunner,
    MgmtAppBridge,
    atomic_symlink,
    generate_encrypted_key_pem,
    generate_malformed_pem,
    generate_mismatched_pair,
    generate_self_signed_cert,
    generate_test_ca,
    read_env_file,
    repo_root,
    seed_certbot_live_cert,
    temp_stack_ws,
    write_env_file,
)


pytestmark = pytest.mark.tier2


@pytest.mark.docker
@pytest.mark.parametrize(
    "bad_payload",
    [
        {"domain": "foo; rm -rf /", "email": "admin@example.edu", "challenge_type": "http-01"},
        {"domain": "$(touch /test_ws/pwned)", "email": "admin@example.edu", "challenge_type": "http-01"},
        {"domain": "`id`", "email": "admin@example.edu", "challenge_type": "http-01"},
        {"domain": "pt.example.com\nEVIL=1", "email": "admin@example.edu", "challenge_type": "http-01"},
        {"domain": "*.bad..com", "email": "admin@example.edu", "challenge_type": "http-01"},
        {"domain": "bad domain.com", "email": "admin@example.edu", "challenge_type": "http-01"},
        {"domain": "-leadingdash.com", "email": "admin@example.edu", "challenge_type": "http-01"},
        {"domain": "../../etc/passwd", "email": "admin@example.edu", "challenge_type": "http-01"},
        {"domain": "", "enabled": True, "email": "admin@example.edu", "challenge_type": "http-01"},
        {"domain": "valid.example.edu", "extra_domains": "ok.example.edu, evil;cat /etc/passwd", "email": "admin@example.edu"},
        {"domain": "valid.example.edu", "email": "not-an-email", "challenge_type": "http-01"},
        {"domain": "valid.example.edu", "email": "admin@bad;rm -rf /", "challenge_type": "http-01"},
        {"domain": "valid.example.edu", "email": "admin@example.edu", "challenge_type": "tls-alpn-99"},
        {"domain": "valid.example.edu", "email": "admin@example.edu", "challenge_type": "http-01; id"},
    ],
)
def test_t2_certbot_input_injection_and_malformed_rejection(tmp_path: Path, bad_payload: dict) -> None:
    """Invalid/malicious domain, extra_domains, email, or challenge_type returns 400 without mutating .env or running certbot."""
    ws = temp_stack_ws(tmp_path)
    env_before = (ws / ".env").read_text(encoding="utf-8")
    bridge = MgmtAppBridge(ws)
    bridge.clear_logs()

    resp = bridge.request("POST", "/api/certbot/config", json_body=bad_payload)
    assert resp["status_code"] == 400, (
        f"Expected 400 for malicious/invalid payload {bad_payload}, got {resp['status_code']}: {resp['body']}"
    )
    assert not (ws / "pwned").exists(), "Command injection executed! /test_ws/pwned was created"
    assert (ws / ".env").read_text(encoding="utf-8") == env_before, ".env was modified after rejected payload"
    assert not bridge.certbot_calls(), f"certbot was invoked despite invalid config: {bridge.certbot_calls()}"


@pytest.mark.docker
def test_t2_upload_path_traversal_rejection(tmp_path: Path) -> None:
    """Upload restore/delete endpoints reject path traversal payloads cleanly."""
    ws = temp_stack_ws(tmp_path)
    bridge = MgmtAppBridge(ws)

    for ep in ("/api/upload/restore", "/api/upload/backup/delete"):
        resp = bridge.request(
            "POST",
            ep,
            json_body={"backup_path": "../../../../etc/passwd", "file_type": "server.crt"},
        )
        assert resp["status_code"] in (400, 403, 404), (
            f"{ep} did not reject path traversal: {resp['status_code']} {resp['body']}"
        )


def test_t2_no_private_keys_tracked_in_git() -> None:
    """Zero Certbot/new private key files or PEM private key blocks are tracked in git."""
    root = repo_root()
    res = subprocess.run(["git", "ls-files"], cwd=str(root), capture_output=True, text=True, timeout=10)
    assert res.returncode == 0
    tracked = [ln.strip() for ln in res.stdout.splitlines() if ln.strip()]

    # 1. No files under certbot/ or privkey*.pem anywhere in git
    certbot_tracked = [f for f in tracked if f.startswith("certbot/") or "privkey" in Path(f).name]
    assert not certbot_tracked, f"Certbot/private-key files tracked in git: {certbot_tracked}"

    # 2. No private keys added/modified on branch expirement relative to main
    diff_res = subprocess.run(
        ["git", "diff", "--name-only", "main...HEAD"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=10,
    )
    changed_files = [ln.strip() for ln in diff_res.stdout.splitlines() if ln.strip()] if diff_res.returncode == 0 else []
    untracked_res = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=10,
    )
    candidate_files = sorted(set(changed_files + [ln.strip() for ln in untracked_res.stdout.splitlines() if ln.strip()]))

    new_key_files = [
        f
        for f in candidate_files
        if not f.startswith("tests/") and (f.endswith(".key") or "privkey" in Path(f).name)
    ]
    assert not new_key_files, f"New private key filenames tracked/unignored on expirement: {new_key_files}"

    leaked_content = []
    for rel in candidate_files:
        if rel.startswith("tests/"):
            continue
        p = root / rel
        if not p.is_file() or p.suffix not in (".pem", ".crt", ".cert", ".key", ".conf", ".env", ".txt", ".md"):
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        if any(marker in txt for marker in PRIVATE_KEY_MARKERS):
            leaked_content.append(rel)
    assert not leaked_content, f"Files on expirement contain private key PEM markers: {leaked_content}"


@pytest.mark.docker
def test_t2_private_key_permissions_and_no_api_leakage(tmp_path: Path) -> None:
    """Private keys remain 0600 on disk and zero private key PEM material appears in any API/HTML response."""
    ws = temp_stack_ws(tmp_path)
    bridge = MgmtAppBridge(ws)

    # Configure and issue mocked cert
    r_cfg = bridge.request(
        "POST",
        "/api/certbot/config",
        json_body={
            "domain": "sec.example.edu",
            "email": "sec@example.edu",
            "challenge_type": "http-01",
            "staging": True,
            "auto_renew": True,
        },
    )
    assert r_cfg["status_code"] == 200, f"Config failed: {r_cfg['body']}"

    r_issue = bridge.request("POST", "/api/certbot/issue", json_body={"dry_run": False})
    assert r_issue["status_code"] == 200, f"Issue failed: {r_issue['body']}"

    # Inspect key file permissions
    ssl_key = ws / "ssl" / "server.key"
    assert stat.S_IMODE(ssl_key.stat().st_mode) == 0o600
    priv_keys = list((ws / "certbot" / "conf").rglob("privkey*.pem"))
    assert priv_keys, "No privkey*.pem created under certbot/conf"
    for pk in priv_keys:
        if not pk.is_symlink():
            assert stat.S_IMODE(pk.stat().st_mode) == 0o600, f"{pk} has insecure mode {oct(pk.stat().st_mode)}"

    # Inspect API responses for any PEM private key leakage
    responses = [
        bridge.request("GET", "/api/certbot/status"),
        bridge.request("GET", "/api/upload/info/key"),
        bridge.request("GET", "/api/upload/info/crt"),
        bridge.request("GET", "/settings"),
        r_cfg,
        r_issue,
    ]
    for idx, r in enumerate(responses):
        body = r["body"]
        for marker in PRIVATE_KEY_MARKERS:
            assert marker not in body, f"Private key material ({marker}) leaked in response #{idx}"


@pytest.mark.docker
def test_t2_manual_upload_mismatch_malformed_binary_encrypted_rejected(tmp_path: Path) -> None:
    """Manual SSL upload never activates mismatched cert/key, rejects malformed/binary/encrypted with 400, and switch-mode rejects mismatched pair."""
    ws = temp_stack_ws(tmp_path)
    cert_a, key_a, cert_b, key_b = generate_mismatched_pair(tmp_path / "pairs")
    cert_c = tmp_path / "pairs" / "certC.crt"
    key_c = tmp_path / "pairs" / "keyC.key"
    generate_self_signed_cert(cert_c, key_c, cn="pair-c.example.test", serial=1003)

    # Seed active valid pair (A, A)
    active_crt = ws / "ssl" / "server.crt"
    active_key = ws / "ssl" / "server.key"
    active_crt.write_bytes(cert_a.read_bytes())
    active_key.write_bytes(key_a.read_bytes())
    os.chmod(active_key, 0o600)

    orig_crt_sha = hashlib.sha256(active_crt.read_bytes()).hexdigest()
    orig_key_sha = hashlib.sha256(active_key.read_bytes()).hexdigest()

    bridge = MgmtAppBridge(ws)
    bridge.clear_logs()

    def _assert_mismatch_not_activated(resp: dict, label: str) -> None:
        if resp["status_code"] == 400:
            return
        assert resp["status_code"] == 200, (
            f"{label}: expected 400 rejection or 200 staged non-activation, got {resp['status_code']} {resp['body']}"
        )
        payload = resp.get("json") or {}
        assert payload.get("pair_matched") is False, (
            f"{label}: staged 200 response must report pair_matched=False, got {payload}"
        )
        assert payload.get("reloaded") is False, (
            f"{label}: staged 200 response must report reloaded=False, got {payload}"
        )

    # 1. Mismatched key B against active cert A
    r_mis_key = bridge.request("POST", "/api/upload/key", files={"file": ("server.key", key_b.read_bytes())})
    _assert_mismatch_not_activated(r_mis_key, "mismatched key B")

    # 2. Mismatched cert C (distinct from both active key A and staged key B)
    r_mis_crt = bridge.request("POST", "/api/upload/certificate", files={"file": ("server.crt", cert_c.read_bytes())})
    _assert_mismatch_not_activated(r_mis_crt, "mismatched cert C")

    # 3. Malformed PEM certificate
    r_bad_pem = bridge.request("POST", "/api/upload/certificate", files={"file": ("bad.crt", generate_malformed_pem())})
    assert r_bad_pem["status_code"] == 400, f"Malformed PEM cert was NOT rejected: {r_bad_pem['status_code']} {r_bad_pem['body']}"

    # 4. Binary garbage disguised as .crt
    r_bin = bridge.request(
        "POST",
        "/api/upload/certificate",
        files={"file": ("fake.crt", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\xff\xd8\xff")},
    )
    assert r_bin["status_code"] == 400

    # 5. Encrypted private key
    r_enc = bridge.request(
        "POST",
        "/api/upload/key",
        files={"file": ("enc.key", generate_encrypted_key_pem())},
    )
    assert r_enc["status_code"] == 400, f"Encrypted private key was NOT rejected: {r_enc['status_code']} {r_enc['body']}"

    # Active valid pair must remain completely untouched and Nginx must not have reloaded
    assert hashlib.sha256(active_crt.read_bytes()).hexdigest() == orig_crt_sha, "Active server.crt was corrupted"
    assert hashlib.sha256(active_key.read_bytes()).hexdigest() == orig_key_sha, "Active server.key was corrupted"
    assert not any("nginx -s reload" in c for c in bridge.docker_calls()), (
        f"nginx -s reload was called during mismatched/invalid uploads: {bridge.docker_calls()}"
    )

    # 6. switch-mode to manual must refuse to activate a mismatched pair on disk (400) and never reload Nginx
    active_key.write_bytes(key_b.read_bytes())
    os.chmod(active_key, 0o600)
    r_sw = bridge.request("POST", "/api/certbot/switch-mode", json_body={"tls_mode": "manual"})
    assert r_sw["status_code"] == 400, (
        f"switch-mode to manual must reject mismatched pair on disk with 400, got {r_sw['status_code']} {r_sw['body']}"
    )
    assert read_env_file(ws / ".env").get("TLS_MODE") == "self-signed"
    assert not any("nginx -s reload" in c for c in bridge.docker_calls()), (
        f"nginx -s reload was called when switch-mode rejected mismatched pair: {bridge.docker_calls()}"
    )


def _probe_expect_geoip_444(url: str, headers: dict) -> None:
    try:
        r = requests.get(url, headers=headers, verify=False, allow_redirects=False, timeout=4)
    except requests.exceptions.ConnectionError as exc:
        # Nginx `return 444` closes the TCP/TLS connection without an HTTP response;
        # guard against connection-refused so a crashed server cannot false-pass.
        msg = str(exc)
        assert "Connection refused" not in msg and "Failed to establish a new connection" not in msg, (
            f"Target unreachable (not GeoIP 444 drop) for {url} with {headers}: {exc}"
        )
        return
    assert r.status_code == 444, (
        f"Expected GeoIP 444 connection close (or HTTP 444) for {url} with {headers}, got HTTP {r.status_code}"
    )


@pytest.mark.docker
def test_t2_acme_bypass_vs_geoip_and_redirect_https_mode(
    tmp_path: Path, ephemeral_nginx: EphemeralNginxRunner
) -> None:
    """ACME HTTP-01 bypasses 301 redirect and GeoIP 444 while non-ACME paths stay GeoIP/301 protected (HTTPS mode)."""
    ws = temp_stack_ws(
        tmp_path,
        env_overrides={
            "PRODUCTION_MODE": "false",
            "ENABLE_HTTPS": "true",
            "TLS_MODE": "self-signed",
            "SERVER_NAME": "localhost",
            "SSL_CERT_PATH": "/etc/ssl/ptweb/server.crt",
            "SSL_KEY_PATH": "/etc/ssl/ptweb/server.key",
            "NGINX_GEOIP_ALLOW": "true",
            "GEOIP_ALLOW_COUNTRIES": "FI,US",
            "NGINX_GEOIP_BLOCK": "true",
            "GEOIP_BLOCK_COUNTRIES": "RU,IR",
            "NGINX_RATE_LIMIT_ENABLE": "true",
            "NGINX_RATE_LIMIT_RATE": "100r/s",
            "NGINX_RATE_LIMIT_BURST": "200",
            "NGINX_RATE_LIMIT_ZONE_SIZE": "10m",
        },
    )
    gen = ephemeral_nginx.run_generate_nginx_conf(ws)
    assert gen.returncode == 0, gen.stderr

    acme_dir = ws / "certbot" / "www" / ".well-known" / "acme-challenge"
    acme_dir.mkdir(parents=True, exist_ok=True)
    (acme_dir / "tok1").write_text("acme-ok-123", encoding="utf-8")

    srv = ephemeral_nginx.start_server(
        ws,
        enable_realip_header=True,
        with_stub_upstreams=True,
        mount_legacy_ssl_files=True,
        wait_ports=[80, 443, 5000],
    )
    p80, p443 = srv["p80"], srv["p443"]

    # 1. Disallowed AU (1.1.1.1) and blocked RU (77.88.55.80) MUST reach ACME token with HTTP 200
    for ip in ("1.1.1.1", "77.88.55.80", "193.166.4.1"):
        r = requests.get(
            f"http://127.0.0.1:{p80}/.well-known/acme-challenge/tok1",
            headers={"X-Test-IP": ip},
            allow_redirects=False,
            timeout=4,
        )
        assert r.status_code == 200 and r.text == "acme-ok-123", (
            f"ACME HTTP-01 failed for IP {ip}: status={r.status_code} body={r.text!r}"
        )

    # 2. Non-ACME paths on port 80 must redirect (301) or drop (444), never 200
    for path in ("/", "/guacamole/", "/admin", "/.well-known/other"):
        for ip in ("193.166.4.1", "1.1.1.1"):
            try:
                r = requests.get(
                    f"http://127.0.0.1:{p80}{path}",
                    headers={"X-Test-IP": ip},
                    allow_redirects=False,
                    timeout=4,
                )
                assert r.status_code == 301, f"Port 80 {path} for {ip} expected 301, got {r.status_code}"
            except requests.exceptions.ConnectionError:
                pass

    # 3. Non-ACME paths on port 443 MUST drop (444) for disallowed/blocked IPs
    for path in ("/", "/guacamole/", "/admin", "/.well-known/other"):
        for bad_ip in ("1.1.1.1", "77.88.55.80"):
            _probe_expect_geoip_444(f"https://127.0.0.1:{p443}{path}", {"X-Test-IP": bad_ip})

    # 4. Allowed FI IP (193.166.4.1) reaches stub upstream on HTTPS /
    r_ok = requests.get(
        f"https://127.0.0.1:{p443}/",
        headers={"X-Test-IP": "193.166.4.1"},
        verify=False,
        allow_redirects=False,
        timeout=4,
    )
    assert r_ok.status_code == 200 and "GUAC_STUB_OK" in r_ok.text


@pytest.mark.docker
def test_t2_acme_bypass_vs_geoip_http_only_mode(
    tmp_path: Path, ephemeral_nginx: EphemeralNginxRunner
) -> None:
    """ACME HTTP-01 returns 200 for all IPs while non-ACME paths enforce GeoIP 444 in HTTP-only mode."""
    ws = temp_stack_ws(
        tmp_path,
        env_overrides={
            "PRODUCTION_MODE": "false",
            "ENABLE_HTTPS": "false",
            "TLS_MODE": "self-signed",
            "SERVER_NAME": "localhost",
            "NGINX_GEOIP_ALLOW": "true",
            "GEOIP_ALLOW_COUNTRIES": "FI,US",
            "NGINX_GEOIP_BLOCK": "true",
            "GEOIP_BLOCK_COUNTRIES": "RU,IR",
            "NGINX_RATE_LIMIT_ENABLE": "false",
        },
    )
    gen = ephemeral_nginx.run_generate_nginx_conf(ws)
    assert gen.returncode == 0, gen.stderr

    acme_dir = ws / "certbot" / "www" / ".well-known" / "acme-challenge"
    acme_dir.mkdir(parents=True, exist_ok=True)
    (acme_dir / "tok_http").write_text("http-only-ok", encoding="utf-8")

    srv = ephemeral_nginx.start_server(
        ws,
        enable_realip_header=True,
        with_stub_upstreams=True,
        mount_legacy_ssl_files=True,
        wait_ports=[80],
    )
    p80 = srv["p80"]

    r_acme = requests.get(
        f"http://127.0.0.1:{p80}/.well-known/acme-challenge/tok_http",
        headers={"X-Test-IP": "1.1.1.1"},
        allow_redirects=False,
        timeout=4,
    )
    assert r_acme.status_code == 200 and r_acme.text == "http-only-ok"

    for path in ("/", "/guacamole/", "/admin", "/.well-known/other"):
        _probe_expect_geoip_444(f"http://127.0.0.1:{p80}{path}", {"X-Test-IP": "1.1.1.1"})

    r_fi = requests.get(
        f"http://127.0.0.1:{p80}/",
        headers={"X-Test-IP": "193.166.4.1"},
        allow_redirects=False,
        timeout=4,
    )
    assert r_fi.status_code == 200 and "GUAC_STUB_OK" in r_fi.text


@pytest.mark.docker
def test_t2_missing_certbot_cert_fallback(
    tmp_path: Path, ephemeral_nginx: EphemeralNginxRunner
) -> None:
    """When TLS_MODE=certbot but /etc/letsencrypt has no cert yet, Nginx falls back safely without crash-looping."""
    ws = temp_stack_ws(
        tmp_path,
        env_overrides={
            "PRODUCTION_MODE": "false",
            "ENABLE_HTTPS": "true",
            "TLS_MODE": "certbot",
            "CERTBOT_ENABLED": "true",
            "CERTBOT_DOMAIN": "notissued.example.test",
            "SERVER_NAME": "notissued.example.test",
            "NGINX_GEOIP_ALLOW": "false",
            "NGINX_GEOIP_BLOCK": "false",
            "NGINX_RATE_LIMIT_ENABLE": "false",
        },
    )
    # Intentionally leave ws/certbot/conf empty while ws/ssl has fallback self-signed cert
    gen = ephemeral_nginx.run_generate_nginx_conf(ws)
    assert gen.returncode == 0, gen.stderr

    nt = ephemeral_nginx.nginx_test(ws, mount_legacy_ssl_files=False)
    assert nt.returncode == 0, f"nginx -t failed with missing certbot cert fallback:\n{nt.stderr}"

    acme_dir = ws / "certbot" / "www" / ".well-known" / "acme-challenge"
    acme_dir.mkdir(parents=True, exist_ok=True)
    (acme_dir / "bootstrap").write_text("bootstrap-acme", encoding="utf-8")

    srv = ephemeral_nginx.start_server(
        ws,
        with_stub_upstreams=True,
        mount_legacy_ssl_files=False,
        wait_ports=[80, 443, 5000],
    )
    info = ephemeral_nginx.inspect_container(srv["container"])
    assert info["State"]["Running"] is True
    assert info["RestartCount"] == 0

    r_acme = requests.get(
        f"http://127.0.0.1:{srv['p80']}/.well-known/acme-challenge/bootstrap",
        allow_redirects=False,
        timeout=4,
    )
    assert r_acme.status_code == 200 and r_acme.text == "bootstrap-acme"

    c443 = ephemeral_nginx.get_tls_cert_info("127.0.0.1", srv["p443"], "notissued.example.test")
    c5000 = ephemeral_nginx.get_tls_cert_info("127.0.0.1", srv["p5000"], "notissued.example.test")
    assert c443["fingerprint"] == c5000["fingerprint"]


@pytest.mark.docker
def test_t2_directory_mount_sees_atomic_cert_and_symlink_swap(
    tmp_path: Path, ephemeral_nginx: EphemeralNginxRunner
) -> None:
    """Directory mounts allow running pt-nginx container to see atomic file replacements & symlink rotations immediately."""
    ws = temp_stack_ws(tmp_path)
    ca_crt, ca_key = generate_test_ca(tmp_path / "ca")
    seed_certbot_live_cert(ws / "certbot" / "conf", "rot.example.test", ca_crt, ca_key, version=1, serial=11)

    gen = ephemeral_nginx.run_generate_nginx_conf(ws)
    assert gen.returncode == 0, gen.stderr

    srv = ephemeral_nginx.start_server(
        ws,
        with_stub_upstreams=False,
        mount_legacy_ssl_files=False,
        wait_ports=[80, 443, 5000],
    )
    cid = srv["container"]

    def _container_sha(path_in_container: str) -> str:
        res = ephemeral_nginx.exec_in(cid, ["sha256sum", path_in_container])
        assert res.returncode == 0, f"sha256sum {path_in_container} failed: {res.stderr}"
        return res.stdout.split()[0]

    old_ssl_sha = _container_sha("/etc/ssl/ptweb/server.crt")
    old_cb_sha = _container_sha("/etc/letsencrypt/live/rot.example.test/fullchain.pem")

    # Atomically replace host ssl/server.crt (new inode)
    tmp_crt = ws / "ssl" / "server.crt.new"
    tmp_key = ws / "ssl" / "server.key.new"
    generate_self_signed_cert(tmp_crt, tmp_key, cn="replaced.example.test", serial=999)
    os.replace(tmp_crt, ws / "ssl" / "server.crt")
    os.replace(tmp_key, ws / "ssl" / "server.key")

    # Atomically rotate Certbot live symlink v1 -> v2
    seed_certbot_live_cert(ws / "certbot" / "conf", "rot.example.test", ca_crt, ca_key, version=2, serial=22)

    new_ssl_sha = _container_sha("/etc/ssl/ptweb/server.crt")
    new_cb_sha = _container_sha("/etc/letsencrypt/live/rot.example.test/fullchain.pem")

    assert new_ssl_sha != old_ssl_sha, "Container did not observe atomic server.crt replacement"
    assert new_cb_sha != old_cb_sha, "Container did not observe Certbot live symlink rotation"
