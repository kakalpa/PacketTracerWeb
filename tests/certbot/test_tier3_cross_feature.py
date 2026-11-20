"""
Tier 3: Cross-Feature Integration, Mode Switching & Renewal Reload Tests.

Validates:
- Combined Nginx config (TLS_MODE=certbot + HTTPS + GeoIP + RateLimit + PRODUCTION_MODE)
  preserving Guacamole WebSocket headers, `/api/student/files/`, and `health_check.sh` regexes
- Mode switching (`self-signed` <-> `certbot` <-> `manual`): missing target cert rejected (400),
  valid transitions update `.env`, regenerate `ptweb.conf`, validate `nginx -t`, and reload Nginx
- Port 443 and Port 5000 both serving identical active X.509 cert fingerprint, CN, and SANs
- Automated renewal deploy-hook / reload watcher updating both :443 and :5000 with RestartCount == 0
- `nginx -t` failure gate aborting reload without killing active Nginx workers
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from tests.certbot.helpers import (
    EphemeralNginxRunner,
    MgmtAppBridge,
    assert_healthcheck_location_root_invariants,
    generate_test_ca,
    read_env_file,
    repo_root,
    seed_certbot_live_cert,
    temp_stack_ws,
    write_env_file,
)


pytestmark = pytest.mark.tier3


@pytest.mark.docker
def test_t3_combined_nginx_config_preserves_guac_ws_student_api_and_healthcheck(
    tmp_path: Path, ephemeral_nginx: EphemeralNginxRunner
) -> None:
    """Combined Certbot + HTTPS + GeoIP + RateLimit + Production mode passes nginx -t and keeps Guac/student/healthcheck intact."""
    ws = temp_stack_ws(tmp_path)
    ca_crt, ca_key = generate_test_ca(tmp_path / "ca")
    seed_certbot_live_cert(
        ws / "certbot" / "conf",
        "prod.example.edu",
        ca_crt,
        ca_key,
        sans=["prod.example.edu", "portal.example.edu"],
    )

    write_env_file(
        ws / ".env",
        {
            "PRODUCTION_MODE": "true",
            "PUBLIC_IP": "203.0.113.10",
            "ENABLE_HTTPS": "true",
            "TLS_MODE": "certbot",
            "CERTBOT_ENABLED": "true",
            "CERTBOT_DOMAIN": "prod.example.edu",
            "CERTBOT_EXTRA_DOMAINS": "portal.example.edu",
            "SERVER_NAME": "prod.example.edu portal.example.edu",
            "SSL_CERT_PATH": "/etc/letsencrypt/live/prod.example.edu/fullchain.pem",
            "SSL_KEY_PATH": "/etc/letsencrypt/live/prod.example.edu/privkey.pem",
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

    nt = ephemeral_nginx.nginx_test(ws, mount_legacy_ssl_files=False)
    assert nt.returncode == 0, f"Combined config failed nginx -t:\n{nt.stderr}"

    ptweb = (ws / "ptweb-vnc" / "pt-nginx" / "conf" / "ptweb.conf").read_text(encoding="utf-8")
    assert "203\\.0\\.113\\.10" in ptweb or "203.0.113.10" in ptweb
    assert "location ^~ /api/student/files/" in ptweb
    assert "proxy_http_version 1.1;" in ptweb
    assert "proxy_buffering off;" in ptweb
    assert "Upgrade $http_upgrade;" in ptweb
    assert "Connection $connection_upgrade;" in ptweb
    assert "/etc/letsencrypt/live/prod.example.edu/fullchain.pem" in ptweb

    # Verify health_check.sh:391,496,501,524 invariants across all `location /` blocks
    assert_healthcheck_location_root_invariants(
        ptweb,
        expect_allow=True,
        expect_block=True,
        expect_rate_limit=True,
    )


@pytest.mark.docker
def test_t3_switch_mode_rejects_missing_target_certs(tmp_path: Path) -> None:
    """Switching TLS_MODE to a mode whose cert/key does not exist is rejected (400) without modifying .env."""
    ws = temp_stack_ws(tmp_path)
    bridge = MgmtAppBridge(ws)

    # 1. Switch to certbot with no issued cert under certbot/conf/live
    r_cb = bridge.request("POST", "/api/certbot/switch-mode", json_body={"tls_mode": "certbot"})
    assert r_cb["status_code"] == 400, f"Expected 400 when certbot cert missing, got {r_cb['status_code']}"
    assert read_env_file(ws / ".env").get("TLS_MODE") == "self-signed"

    # 2. Switch to manual when ssl/server.crt is missing
    (ws / "ssl" / "server.crt").unlink()
    r_man = bridge.request("POST", "/api/certbot/switch-mode", json_body={"tls_mode": "manual"})
    assert r_man["status_code"] == 400, f"Expected 400 when manual cert missing, got {r_man['status_code']}"
    assert read_env_file(ws / ".env").get("TLS_MODE") == "self-signed"

    # 3. Invalid mode name
    r_bad = bridge.request("POST", "/api/certbot/switch-mode", json_body={"tls_mode": "bogus"})
    assert r_bad["status_code"] == 400


@pytest.mark.docker
def test_t3_coexistence_mode_transitions_and_nginx_reload(tmp_path: Path) -> None:
    """Valid transitions self-signed -> certbot -> manual -> self-signed update .env, ptweb.conf, and trigger nginx -t + reload."""
    ws = temp_stack_ws(
        tmp_path,
        env_overrides={
            "TLS_MODE": "self-signed",
            "CERTBOT_DOMAIN": "pt.example.edu",
            "SERVER_NAME": "localhost",
        },
    )
    ca_crt, ca_key = generate_test_ca(tmp_path / "ca")
    seed_certbot_live_cert(ws / "certbot" / "conf", "pt.example.edu", ca_crt, ca_key)

    bridge = MgmtAppBridge(ws)
    bridge.clear_logs()

    # self-signed -> certbot
    r1 = bridge.request("POST", "/api/certbot/switch-mode", json_body={"tls_mode": "certbot"})
    assert r1["status_code"] == 200, f"Switch to certbot failed: {r1['body']}"
    env1 = read_env_file(ws / ".env")
    assert env1.get("TLS_MODE") == "certbot"
    assert "/etc/letsencrypt/live/pt.example.edu/fullchain.pem" in env1.get("SSL_CERT_PATH", "")
    ptweb1 = (ws / "ptweb-vnc" / "pt-nginx" / "conf" / "ptweb.conf").read_text(encoding="utf-8")
    assert "/etc/letsencrypt/live/pt.example.edu/fullchain.pem" in ptweb1
    assert "pt.example.edu" in ptweb1

    # certbot -> manual
    r2 = bridge.request("POST", "/api/certbot/switch-mode", json_body={"tls_mode": "manual"})
    assert r2["status_code"] == 200, f"Switch to manual failed: {r2['body']}"
    env2 = read_env_file(ws / ".env")
    assert env2.get("TLS_MODE") == "manual"
    assert env2.get("SSL_CERT_PATH") == "/etc/ssl/ptweb/server.crt"
    ptweb2 = (ws / "ptweb-vnc" / "pt-nginx" / "conf" / "ptweb.conf").read_text(encoding="utf-8")
    assert "/etc/ssl/ptweb/server.crt" in ptweb2

    # manual -> self-signed
    r3 = bridge.request("POST", "/api/certbot/switch-mode", json_body={"tls_mode": "self-signed"})
    assert r3["status_code"] == 200, f"Switch to self-signed failed: {r3['body']}"
    env3 = read_env_file(ws / ".env")
    assert env3.get("TLS_MODE") == "self-signed"

    calls = "\n".join(bridge.docker_calls())
    assert "nginx -t" in calls, f"Expected nginx -t calls in docker_calls.log, got:\n{calls}"
    assert "nginx -s reload" in calls, f"Expected nginx -s reload calls in docker_calls.log, got:\n{calls}"


@pytest.mark.docker
def test_t3_ports_443_and_5000_serve_identical_active_cert(
    tmp_path: Path, ephemeral_nginx: EphemeralNginxRunner
) -> None:
    """Ports 443 and 5000 serve identical active X.509 certificate fingerprint, CN, and SANs."""
    ws = temp_stack_ws(tmp_path)
    ca_crt, ca_key = generate_test_ca(tmp_path / "ca")
    meta = seed_certbot_live_cert(
        ws / "certbot" / "conf",
        "dual.example.test",
        ca_crt,
        ca_key,
        sans=["dual.example.test", "alt.example.test"],
        serial=5050,
    )
    write_env_file(
        ws / ".env",
        {
            "PRODUCTION_MODE": "false",
            "ENABLE_HTTPS": "true",
            "TLS_MODE": "certbot",
            "CERTBOT_ENABLED": "true",
            "CERTBOT_DOMAIN": "dual.example.test",
            "SERVER_NAME": "dual.example.test alt.example.test",
            "SSL_CERT_PATH": "/etc/letsencrypt/live/dual.example.test/fullchain.pem",
            "SSL_KEY_PATH": "/etc/letsencrypt/live/dual.example.test/privkey.pem",
            "NGINX_GEOIP_ALLOW": "false",
            "NGINX_GEOIP_BLOCK": "false",
            "NGINX_RATE_LIMIT_ENABLE": "false",
        },
    )
    gen = ephemeral_nginx.run_generate_nginx_conf(ws)
    assert gen.returncode == 0, gen.stderr

    srv = ephemeral_nginx.start_server(ws, mount_legacy_ssl_files=False, wait_ports=[80, 443, 5000])
    c443 = ephemeral_nginx.get_tls_cert_info("127.0.0.1", srv["p443"], "dual.example.test")
    c5000 = ephemeral_nginx.get_tls_cert_info("127.0.0.1", srv["p5000"], "dual.example.test")

    assert c443["fingerprint"] == meta["fingerprint"]
    assert c5000["fingerprint"] == meta["fingerprint"]
    assert c443["cn"] == "dual.example.test" and c5000["cn"] == "dual.example.test"
    assert set(c443["sans"]) == {"dual.example.test", "alt.example.test"}
    assert set(c5000["sans"]) == {"dual.example.test", "alt.example.test"}


@pytest.mark.docker
def test_t3_renewal_atomic_rotation_and_reload_updates_443_and_5000(
    tmp_path: Path, ephemeral_nginx: EphemeralNginxRunner
) -> None:
    """Atomic Certbot symlink rotation FP1 -> FP2 + reload updates both :443 and :5000 with zero container restarts."""
    ws = temp_stack_ws(tmp_path)
    ca_crt, ca_key = generate_test_ca(tmp_path / "ca")
    meta1 = seed_certbot_live_cert(
        ws / "certbot" / "conf",
        "renew.example.test",
        ca_crt,
        ca_key,
        version=1,
        days=30,
        serial=1111,
    )
    write_env_file(
        ws / ".env",
        {
            "PRODUCTION_MODE": "false",
            "ENABLE_HTTPS": "true",
            "TLS_MODE": "certbot",
            "CERTBOT_ENABLED": "true",
            "CERTBOT_DOMAIN": "renew.example.test",
            "SERVER_NAME": "renew.example.test",
            "SSL_CERT_PATH": "/etc/letsencrypt/live/renew.example.test/fullchain.pem",
            "SSL_KEY_PATH": "/etc/letsencrypt/live/renew.example.test/privkey.pem",
            "NGINX_GEOIP_ALLOW": "false",
            "NGINX_GEOIP_BLOCK": "false",
            "NGINX_RATE_LIMIT_ENABLE": "false",
        },
    )
    gen = ephemeral_nginx.run_generate_nginx_conf(ws)
    assert gen.returncode == 0, gen.stderr

    srv = ephemeral_nginx.start_server(
        ws,
        mount_legacy_ssl_files=False,
        env_vars={"NGINX_CERT_WATCH_INTERVAL": "1"},
        wait_ports=[80, 443, 5000],
    )
    cid = srv["container"]

    assert ephemeral_nginx.get_tls_cert_info("127.0.0.1", srv["p443"], "renew.example.test")["fingerprint"] == meta1["fingerprint"]
    assert ephemeral_nginx.get_tls_cert_info("127.0.0.1", srv["p5000"], "renew.example.test")["fingerprint"] == meta1["fingerprint"]

    # Rotate Certbot live symlinks to v2 (FP2); M2 watcher must autonomously detect
    # readlink -f hash change, debounce (2s), pass `nginx -t`, and reload without manual intervention.
    meta2 = seed_certbot_live_cert(
        ws / "certbot" / "conf",
        "renew.example.test",
        ca_crt,
        ca_key,
        version=2,
        days=90,
        serial=2222,
    )
    assert meta2["fingerprint"] != meta1["fingerprint"]

    deadline = time.monotonic() + 12.0
    seen_443 = seen_5000 = False
    while time.monotonic() < deadline:
        fp443 = ephemeral_nginx.get_tls_cert_info("127.0.0.1", srv["p443"], "renew.example.test")["fingerprint"]
        fp5000 = ephemeral_nginx.get_tls_cert_info("127.0.0.1", srv["p5000"], "renew.example.test")["fingerprint"]
        if fp443 == meta2["fingerprint"] and fp5000 == meta2["fingerprint"]:
            seen_443 = seen_5000 = True
            break
        time.sleep(0.4)

    assert seen_443 and seen_5000, (
        "M2 pt-nginx watcher did NOT autonomously reload ports 443/5000 from FP1 to FP2 "
        f"within 12s (NGINX_CERT_WATCH_INTERVAL=1): 443_ok={seen_443}, 5000_ok={seen_5000}"
    )
    info = ephemeral_nginx.inspect_container(cid)
    assert info["State"]["Running"] is True
    assert info["RestartCount"] == 0, f"Expected zero-downtime reload (RestartCount=0), got {info['RestartCount']}"


@pytest.mark.docker
def test_t3_certbot_deploy_hook_and_nginx_t_safety_gate(
    tmp_path: Path, ephemeral_nginx: EphemeralNginxRunner
) -> None:
    """M2 pt-certbot deploy-hook & pt-nginx watcher reload gate block invalid configs and recover autonomously."""
    root = repo_root()
    cb_dir = root / "ptweb-vnc" / "pt-certbot"
    assert cb_dir.is_dir(), f"Missing M2 pt-certbot directory at {cb_dir}"

    # Verify M2 pt-certbot deploy-hook & pt-nginx watcher files follow M1 contract
    cb_text = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore") for p in cb_dir.rglob("*") if p.is_file()
    )
    assert "--deploy-hook" in cb_text and ".nginx-reload-requested" in cb_text, (
        "pt-certbot must define --deploy-hook writing /etc/letsencrypt/.nginx-reload-requested"
    )
    nginx_ep = root / "ptweb-vnc" / "pt-nginx" / "docker-entrypoint.sh"
    assert nginx_ep.is_file(), f"Missing M2 pt-nginx watcher script: {nginx_ep}"
    nginx_ep_text = nginx_ep.read_text(encoding="utf-8")
    assert "NGINX_CERT_WATCH_INTERVAL" in nginx_ep_text and "nginx -t" in nginx_ep_text, (
        "pt-nginx/docker-entrypoint.sh must honor NGINX_CERT_WATCH_INTERVAL and gate reloads with `nginx -t`"
    )

    ws = temp_stack_ws(tmp_path)
    ca_crt, ca_key = generate_test_ca(tmp_path / "ca")
    meta1 = seed_certbot_live_cert(ws / "certbot" / "conf", "gate.example.test", ca_crt, ca_key, version=1, serial=3333)
    write_env_file(
        ws / ".env",
        {
            "PRODUCTION_MODE": "false",
            "ENABLE_HTTPS": "true",
            "TLS_MODE": "certbot",
            "CERTBOT_ENABLED": "true",
            "CERTBOT_DOMAIN": "gate.example.test",
            "SERVER_NAME": "gate.example.test",
            "SSL_CERT_PATH": "/etc/letsencrypt/live/gate.example.test/fullchain.pem",
            "SSL_KEY_PATH": "/etc/letsencrypt/live/gate.example.test/privkey.pem",
            "NGINX_GEOIP_ALLOW": "false",
            "NGINX_GEOIP_BLOCK": "false",
            "NGINX_RATE_LIMIT_ENABLE": "false",
        },
    )
    assert ephemeral_nginx.run_generate_nginx_conf(ws).returncode == 0
    srv = ephemeral_nginx.start_server(
        ws,
        mount_legacy_ssl_files=False,
        env_vars={"NGINX_CERT_WATCH_INTERVAL": "1"},
        wait_ports=[80, 443, 5000],
    )
    cid = srv["container"]

    # 1. Inject invalid Nginx config AND rotate cert + write deploy-hook trigger while broken
    broken = ws / "ptweb-vnc" / "pt-nginx" / "conf" / "99-broken-test.conf"
    broken.write_text("this_is_an_invalid_nginx_directive;\n", encoding="utf-8")
    meta2 = seed_certbot_live_cert(ws / "certbot" / "conf", "gate.example.test", ca_crt, ca_key, version=2, serial=4444)
    trigger_file = ws / "certbot" / "conf" / ".nginx-reload-requested"
    trigger_file.write_text(f"{int(time.time())}\n", encoding="utf-8")

    # Confirm `nginx -t` indeed fails while 99-broken-test.conf is present
    assert ephemeral_nginx.exec_in(cid, ["nginx", "-t"]).returncode != 0

    # Wait > watch interval (1s) + debounce (2s) for watcher to hit `nginx -t` safety gate
    time.sleep(4.0)
    info_broken = ephemeral_nginx.inspect_container(cid)
    assert info_broken["State"]["Running"] is True, "Nginx container died when watcher hit invalid config"
    assert info_broken["RestartCount"] == 0, f"Unexpected RestartCount={info_broken['RestartCount']}"
    assert ephemeral_nginx.get_tls_cert_info("127.0.0.1", srv["p443"], "gate.example.test")["fingerprint"] == meta1["fingerprint"], (
        "Port 443 rotated or disrupted despite invalid nginx -t state"
    )
    assert ephemeral_nginx.get_tls_cert_info("127.0.0.1", srv["p5000"], "gate.example.test")["fingerprint"] == meta1["fingerprint"], (
        "Port 5000 rotated or disrupted despite invalid nginx -t state"
    )

    # 2. Remove broken config and fire a fresh `.nginx-reload-requested` deploy-hook trigger;
    # watcher must autonomously recover and serve FP2 on both :443 and :5000 without manual `nginx -s reload`.
    broken.unlink()
    trigger_file.write_text(f"{int(time.time()) + 1}\n", encoding="utf-8")

    deadline = time.monotonic() + 12.0
    recovered = False
    while time.monotonic() < deadline:
        fp443 = ephemeral_nginx.get_tls_cert_info("127.0.0.1", srv["p443"], "gate.example.test")["fingerprint"]
        fp5000 = ephemeral_nginx.get_tls_cert_info("127.0.0.1", srv["p5000"], "gate.example.test")["fingerprint"]
        if fp443 == meta2["fingerprint"] and fp5000 == meta2["fingerprint"]:
            recovered = True
            break
        time.sleep(0.4)

    assert recovered, (
        "M2 watcher did NOT autonomously reload FP2 after removing broken config and touching .nginx-reload-requested"
    )
    assert ephemeral_nginx.inspect_container(cid)["RestartCount"] == 0
