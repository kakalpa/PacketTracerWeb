"""
Tier 5: White-Box Adversarial Coverage Hardening & Bug Regression Tests.

Combines:
- Part A (`pt-management/**`): 18 tests covering timeouts, flock contention, container
  failures, domain normalization, dns-01/strict bools, ECDSA/Ed25519/sequential backup
  restore, X.509 edge cases, 403 non-admin auth, UI XSS/DOM safety, and BUG-1..BUG-7
  regression gates.
- Part B (M2 Stack & Harness): 26 tests (18 functions + 8 parametrized env cases) covering
  conditional HSTS, .env parsing/glob safety/inode preservation, GeoIP numeric `=1`,
  anchored/validated PUBLIC_IP, certbot fallback with empty domain, watcher debounce/
  signals/symlinks, pt-certbot BusyBox env/signals/flock, deploy/remove/compose parity,
  lazy `$pt_mgmt_upstream` resolution without `pt-management`, empty GeoIP token
  handling, and BUG-M2-01..BUG-M2-06, BUG-M2-R2-01..02 + BUG-HARNESS-01 regression gates.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import time
import uuid
from pathlib import Path
from typing import List

import pytest
import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.x509.oid import NameOID

from tests.certbot.helpers import (
    EphemeralNginxRunner,
    MgmtAppBridge,
    assert_healthcheck_location_root_invariants,
    free_tcp_port,
    generate_self_signed_cert,
    generate_test_ca,
    read_env_file,
    repo_root,
    seed_certbot_live_cert,
    temp_stack_ws,
    write_env_file,
    x509_metadata,
)

pytestmark = pytest.mark.tier5


def _run_in_mgmt_container(ws: Path, python_code: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    """Execute inline white-box Python snippet inside `pt-management:latest` against `ws`."""
    ptmgmt_dir = repo_root() / "pt-management"
    user_args = ["--user", f"{os.getuid()}:{os.getgid()}"] if hasattr(os, "getuid") else []
    cmd = [
        "docker", "run", "--rm",
        *user_args,
        "--network", "none",
        "--entrypoint", "python3",
        "-v", f"{ptmgmt_dir}:/work_app:ro",
        "-v", f"{ws}:/test_ws:rw",
        "-w", "/work_app",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", "PYTHONPATH=/work_app",
        "-e", "ENV_PATH=/test_ws/.env",
        "-e", "PROJECT_ROOT=/test_ws",
        "-e", "SSL_DIR=/test_ws/ssl",
        "-e", "SSL_KEY_DIR=/test_ws/ssl",
        "-e", "CERTBOT_CONF_DIR=/test_ws/certbot/conf",
        "-e", "CERTBOT_WEBROOT=/test_ws/certbot/www",
        "-e", "SECRET_KEY=test-secret",
        "pt-management:latest",
        "-c", python_code,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


# ============================================================================
# PART A: pt-management/** Adversarial Coverage & BUG-1..BUG-7 Regression Tests
# ============================================================================


@pytest.mark.mgmt
@pytest.mark.docker
def test_t5_certbot_issue_and_renew_504_timeout(tmp_path: Path) -> None:
    """CertbotManager.issue() and renew() return status_code 504 on TimeoutExpired or rc=-1 timeout without mutating .env."""
    ws = temp_stack_ws(
        tmp_path,
        env_overrides={
            "CERTBOT_DOMAIN": "timeout.example.edu",
            "CERTBOT_EMAIL": "admin@example.edu",
            "TLS_MODE": "self-signed",
        },
    )
    env_before = (ws / ".env").read_text(encoding="utf-8")

    code = r"""
import json, subprocess
from ptmanagement.api.certbot_manager import CertbotManager
from ptmanagement.api.env_config import EnvConfigManager

env_m = EnvConfigManager('/test_ws/.env')
def raise_timeout(cmd, t):
    raise subprocess.TimeoutExpired(cmd, t)
def rc_timeout(cmd, t):
    return -1, '', f'Command timed out after {t}s'

cm1 = CertbotManager(env_manager=env_m, project_root='/test_ws', runner=raise_timeout, lock_path='/test_ws/cb1.lock')
cm2 = CertbotManager(env_manager=env_m, project_root='/test_ws', runner=rc_timeout, lock_path='/test_ws/cb2.lock')
print(json.dumps({
    'iss_exc': cm1.issue(dry_run=False),
    'ren_exc': cm1.renew(dry_run=False),
    'iss_rc': cm2.issue(dry_run=False),
    'ren_rc': cm2.renew(dry_run=False),
}))
"""
    proc = _run_in_mgmt_container(ws, code)
    assert proc.returncode == 0, f"Container probe failed: {proc.stderr}"
    res = json.loads(proc.stdout.strip().splitlines()[-1])

    for key in ("iss_exc", "ren_exc", "iss_rc", "ren_rc"):
        r = res[key]
        assert r["success"] is False
        assert r["timed_out"] is True
        assert r["status_code"] == 504

    assert (ws / ".env").read_text(encoding="utf-8") == env_before


@pytest.mark.mgmt
@pytest.mark.docker
def test_t5_certbot_409_flock_contention_container_and_worker(tmp_path: Path) -> None:
    """Container flock contention (MOCK_FLOCK_BUSY, silent rc=1, rc=75) and Python worker flock return 409."""
    ws = temp_stack_ws(
        tmp_path,
        env_overrides={
            "CERTBOT_DOMAIN": "flock.example.edu",
            "CERTBOT_EMAIL": "admin@example.edu",
            "TLS_MODE": "self-signed",
        },
    )
    bridge = MgmtAppBridge(ws)

    # 1. Container flock contention via HTTP API
    (ws / "MOCK_FLOCK_BUSY").write_text("1", encoding="utf-8")
    try:
        r_iss = bridge.request("POST", "/api/certbot/issue", json_body={"dry_run": True})
        r_ren = bridge.request("POST", "/api/certbot/renew", json_body={"dry_run": True})
    finally:
        (ws / "MOCK_FLOCK_BUSY").unlink(missing_ok=True)

    assert r_iss["status_code"] == 409, r_iss
    assert r_ren["status_code"] == 409, r_ren

    # 2. Silent rc=1 empty output, rc=75, and Python worker flock CertbotLockBusyError
    code = r"""
import fcntl, json
from ptmanagement.api.certbot_manager import CertbotManager
from ptmanagement.api.env_config import EnvConfigManager

env_m = EnvConfigManager('/test_ws/.env')
cm_silent = CertbotManager(env_manager=env_m, project_root='/test_ws', runner=lambda c, t: (1, '', ''), lock_path='/test_ws/l1.lock')
cm_75 = CertbotManager(env_manager=env_m, project_root='/test_ws', runner=lambda c, t: (75, '', 'tempfail'), lock_path='/test_ws/l2.lock')

lock_p = '/test_ws/worker.lock'
cm_busy = CertbotManager(env_manager=env_m, project_root='/test_ws', runner=lambda c, t: (0, '', ''), lock_path=lock_p)
with open(lock_p, 'a+') as lf:
    fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    worker_res = {
        'issue': cm_busy.issue(dry_run=True),
        'renew': cm_busy.renew(dry_run=True),
        'switch': cm_busy.switch_mode('self-signed'),
    }

print(json.dumps({
    'silent_iss': cm_silent.issue(dry_run=True),
    'silent_ren': cm_silent.renew(dry_run=True),
    'rc75_iss': cm_75.issue(dry_run=True),
    'worker': worker_res,
}))
"""
    proc = _run_in_mgmt_container(ws, code)
    assert proc.returncode == 0, proc.stderr
    res = json.loads(proc.stdout.strip().splitlines()[-1])
    assert res["silent_iss"]["status_code"] == 409
    assert res["silent_ren"]["status_code"] == 409
    assert res["rc75_iss"]["status_code"] == 409
    assert res["worker"]["issue"]["status_code"] == 409
    assert res["worker"]["renew"]["status_code"] == 409
    assert res["worker"]["switch"]["status_code"] == 409


@pytest.mark.mgmt
@pytest.mark.docker
def test_t5_certbot_503_when_container_stopped_and_500_on_fail(tmp_path: Path) -> None:
    """Stopped pt-certbot yields 503; certbot failure yields 500 without mutating .env or reloading Nginx."""
    ws = temp_stack_ws(
        tmp_path,
        env_overrides={
            "CERTBOT_DOMAIN": "err.example.edu",
            "CERTBOT_EMAIL": "admin@example.edu",
            "TLS_MODE": "self-signed",
        },
    )
    env_before = (ws / ".env").read_text(encoding="utf-8")
    bridge = MgmtAppBridge(ws)

    (ws / "MOCK_CERTBOT_STOPPED").write_text("1", encoding="utf-8")
    try:
        r_iss_503 = bridge.request("POST", "/api/certbot/issue", json_body={"dry_run": False})
        r_ren_503 = bridge.request("POST", "/api/certbot/renew", json_body={"dry_run": False})
    finally:
        (ws / "MOCK_CERTBOT_STOPPED").unlink(missing_ok=True)
    assert r_iss_503["status_code"] == 503
    assert r_ren_503["status_code"] == 503

    bridge.clear_logs()
    bridge.set_mock_certbot_fail(True)
    try:
        r_iss_500 = bridge.request("POST", "/api/certbot/issue", json_body={"dry_run": False})
        r_ren_500 = bridge.request("POST", "/api/certbot/renew", json_body={"dry_run": False})
    finally:
        bridge.set_mock_certbot_fail(False)
    assert r_iss_500["status_code"] == 500
    assert r_ren_500["status_code"] == 500
    assert (ws / ".env").read_text(encoding="utf-8") == env_before
    assert not any("nginx -s reload" in c for c in bridge.docker_calls())


@pytest.mark.mgmt
@pytest.mark.docker
def test_t5_certbot_staging_then_prod_force_renewal_and_extra_domains_normalization(tmp_path: Path) -> None:
    """extra_domains strips whitespace/duplicates/primary domain, enforces 100-domain limit, and staging->prod adds --force-renewal."""
    ws = temp_stack_ws(tmp_path)
    bridge = MgmtAppBridge(ws)

    # 1. > 100 domains rejected with 400
    too_many = ",".join(f"d{i}.example.edu" for i in range(1, 101))
    r_101 = bridge.request(
        "POST",
        "/api/certbot/config",
        json_body={"domain": "d0.example.edu", "extra_domains": too_many, "email": "admin@example.edu"},
    )
    assert r_101["status_code"] == 400

    # 2. Whitespace, uppercase, duplicates, and duplicate of primary domain normalized cleanly
    r_cfg = bridge.request(
        "POST",
        "/api/certbot/config",
        json_body={
            "domain": "  APP.EXAMPLE.EDU ",
            "extra_domains": " app.example.edu , WWW.APP.EXAMPLE.EDU , api.example.edu , API.EXAMPLE.EDU ",
            "email": "admin@example.edu",
            "staging": True,
        },
    )
    assert r_cfg["status_code"] == 200, r_cfg
    env_cfg = read_env_file(ws / ".env")
    assert env_cfg["CERTBOT_DOMAIN"] == "app.example.edu"
    assert env_cfg["CERTBOT_EXTRA_DOMAINS"] == "www.app.example.edu,api.example.edu"

    # 3. Staging issue sets TLS_MODE=certbot, CERTBOT_STAGING=true, SERVER_NAME with all domains, --staging, --cert-name, --expand
    bridge.clear_logs()
    r_stg = bridge.request("POST", "/api/certbot/issue", json_body={"dry_run": False, "staging": True})
    assert r_stg["status_code"] == 200, r_stg
    cb_calls_1 = "\n".join(bridge.certbot_calls())
    assert "--cert-name app.example.edu" in cb_calls_1
    assert "--expand" in cb_calls_1
    assert "--staging" in cb_calls_1
    assert "-d app.example.edu -d www.app.example.edu -d api.example.edu" in cb_calls_1
    env_stg = read_env_file(ws / ".env")
    assert env_stg["TLS_MODE"] == "certbot"
    assert env_stg["CERTBOT_STAGING"] == "true"
    assert env_stg["SERVER_NAME"] == "app.example.edu www.app.example.edu api.example.edu"

    # 4. Replace live cert with real Staging issuer CN so staging->prod detects is_staging and adds --force-renewal
    ca_crt, ca_key = generate_test_ca(tmp_path / "ca_stg", cn="(STAGING) Artificial Apricot R3")
    seed_certbot_live_cert(ws / "certbot" / "conf", "app.example.edu", ca_crt, ca_key)

    bridge.clear_logs()
    r_prod = bridge.request("POST", "/api/certbot/issue", json_body={"dry_run": False, "staging": False})
    assert r_prod["status_code"] == 200, r_prod
    cb_calls_2 = "\n".join(bridge.certbot_calls())
    assert "--force-renewal" in cb_calls_2
    assert "--staging" not in cb_calls_2
    assert read_env_file(ws / ".env")["CERTBOT_STAGING"] == "false"


@pytest.mark.mgmt
@pytest.mark.docker
def test_t5_certbot_dns01_preflight_and_non_dict_json_and_strict_bools(tmp_path: Path) -> None:
    """dns-01 preflight rejects issue with 400; mutating endpoints reject non-dict JSON, non-JSON Content-Type, and invalid booleans."""
    ws = temp_stack_ws(
        tmp_path,
        env_overrides={
            "CERTBOT_DOMAIN": "dns.example.edu",
            "CERTBOT_EMAIL": "admin@example.edu",
            "CERTBOT_CHALLENGE_TYPE": "dns-01",
        },
    )
    bridge = MgmtAppBridge(ws)

    r_dns = bridge.request("POST", "/api/certbot/issue", json_body={"dry_run": True})
    assert r_dns["status_code"] == 400
    assert "dns-01" in (r_dns.get("json") or {}).get("message", "").lower()

    for ep in ("/api/certbot/config", "/api/certbot/issue", "/api/certbot/renew", "/api/certbot/switch-mode"):
        r_list = bridge.request("POST", ep, json_body=["not-a-dict"])  # type: ignore[arg-type]
        r_txt = bridge.request("POST", ep, data="foo=bar", headers={"Content-Type": "text/plain"})
        assert r_list["status_code"] == 400, f"{ep} accepted list JSON: {r_list}"
        assert r_txt["status_code"] == 400, f"{ep} accepted text/plain: {r_txt}"

    for bad_bool in ("maybe", 1, None):
        r_b = bridge.request("POST", "/api/certbot/issue", json_body={"dry_run": bad_bool})
        assert r_b["status_code"] == 400, f"Accepted invalid dry_run={bad_bool!r}: {r_b}"


@pytest.mark.mgmt
@pytest.mark.docker
def test_t5_upload_key_without_cert_ecdsa_ed25519_and_sequential_backup_restore(tmp_path: Path) -> None:
    """Covers key-without-cert staging, ECDSA P-256 & Ed25519 upload promotion, sequential backup restore, and backup delete."""
    ws = temp_stack_ws(tmp_path)
    (ws / "ssl" / "server.crt").unlink()
    (ws / "ssl" / "server.key").unlink()
    bridge = MgmtAppBridge(ws)
    now = dt.datetime.now(dt.timezone.utc)

    # 1. Upload key when active cert is missing -> staged in .pending/, pair_matched=False
    rsa_crt = tmp_path / "rsa.crt"
    rsa_key = tmp_path / "rsa.key"
    generate_self_signed_cert(rsa_crt, rsa_key, cn="rsa.example.edu")
    r_k_only = bridge.request("POST", "/api/upload/key", files={"file": ("rsa.key", rsa_key.read_bytes())})
    assert r_k_only["status_code"] == 200
    assert (r_k_only["json"] or {}).get("staged") is True
    assert (r_k_only["json"] or {}).get("pair_matched") is False
    assert not (ws / "ssl" / "server.key").exists()

    # Complete RSA pair so a backup is created when ECDSA replaces it
    r_c_rsa = bridge.request("POST", "/api/upload/certificate", files={"file": ("rsa.crt", rsa_crt.read_bytes())})
    assert r_c_rsa["status_code"] == 200 and (r_c_rsa["json"] or {}).get("pair_matched") is True

    # 2. ECDSA P-256 pair
    ec_key = ec.generate_private_key(ec.SECP256R1())
    ec_cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ecdsa.example.edu")]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ecdsa.example.edu")]))
        .public_key(ec_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=90))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("ecdsa.example.edu")]), critical=False)
        .sign(ec_key, hashes.SHA256())
    )
    assert bridge.request(
        "POST", "/api/upload/certificate",
        files={"file": ("ec.crt", ec_cert.public_bytes(serialization.Encoding.PEM))},
    )["status_code"] == 200
    r_ec = bridge.request(
        "POST", "/api/upload/key",
        files={"file": ("ec.key", ec_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))},
    )
    assert r_ec["status_code"] == 200 and (r_ec["json"] or {}).get("pair_matched") is True
    assert stat.S_IMODE((ws / "ssl" / "server.key").stat().st_mode) == 0o600

    # 3. Ed25519 pair
    ed_key = ed25519.Ed25519PrivateKey.generate()
    ed_cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ed25519.example.edu")]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ed25519.example.edu")]))
        .public_key(ed_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=90))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("ed25519.example.edu")]), critical=False)
        .sign(ed_key, None)
    )
    assert bridge.request(
        "POST", "/api/upload/certificate",
        files={"file": ("ed.crt", ed_cert.public_bytes(serialization.Encoding.PEM))},
    )["status_code"] == 200
    r_ed = bridge.request(
        "POST", "/api/upload/key",
        files={"file": ("ed.key", ed_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))},
    )
    assert r_ed["status_code"] == 200 and (r_ed["json"] or {}).get("pair_matched") is True

    # 4. Sequential restore of backed-up RSA pair from .backups/ -> activates & reloads
    r_baks = bridge.request("GET", "/api/upload/backups")
    assert r_baks["status_code"] == 200
    backups = (r_baks["json"] or {}).get("backups", [])
    rsa_crt_baks = [b for b in backups if b["type"] == "server.crt"]
    rsa_key_baks = [b for b in backups if b["type"] == "server.key"]
    assert rsa_crt_baks and rsa_key_baks

    oldest_crt = rsa_crt_baks[-1]["path"]
    oldest_key = rsa_key_baks[-1]["path"]
    bridge.clear_logs()
    r_res1 = bridge.request("POST", "/api/upload/restore", json_body={"backup_path": oldest_crt, "file_type": "server.crt"})
    assert r_res1["status_code"] == 200 and (r_res1["json"] or {}).get("staged") is True
    r_res2 = bridge.request("POST", "/api/upload/restore", json_body={"backup_path": oldest_key, "file_type": "server.key"})
    assert r_res2["status_code"] == 200 and (r_res2["json"] or {}).get("pair_matched") is True
    assert any("nginx -s reload" in c for c in bridge.docker_calls())

    # 5. Delete a backup
    r_del = bridge.request("POST", "/api/upload/backup/delete", json_body={"backup_path": oldest_crt})
    assert r_del["status_code"] == 200


@pytest.mark.mgmt
@pytest.mark.docker
def test_t5_upload_corrupt_symlink_directory_backup_and_non_dict_json(tmp_path: Path) -> None:
    """Upload restore/delete rejects corrupt PEM backups, symlink escapes, directory paths, and non-dict JSON bodies."""
    ws = temp_stack_ws(tmp_path)
    bridge = MgmtAppBridge(ws)
    bdir = ws / "ssl" / ".backups"
    bdir.mkdir(parents=True, exist_ok=True)

    corrupt = bdir / "server.crt.backup.corrupt"
    corrupt.write_text("-----BEGIN CERTIFICATE-----\nCORRUPT\n-----END CERTIFICATE-----\n", encoding="utf-8")
    sym = bdir / "server.crt.backup.symlink"
    os.symlink("/etc/passwd", sym)

    r_cor = bridge.request(
        "POST", "/api/upload/restore",
        json_body={"backup_path": "/test_ws/ssl/.backups/server.crt.backup.corrupt", "file_type": "server.crt"},
    )
    r_sym = bridge.request(
        "POST", "/api/upload/restore",
        json_body={"backup_path": "/test_ws/ssl/.backups/server.crt.backup.symlink", "file_type": "server.crt"},
    )
    r_dir = bridge.request(
        "POST", "/api/upload/restore",
        json_body={"backup_path": "/test_ws/ssl/.backups", "file_type": "server.crt"},
    )
    r_del_dir = bridge.request(
        "POST", "/api/upload/backup/delete",
        json_body={"backup_path": "/test_ws/ssl/.backups"},
    )
    assert r_cor["status_code"] == 400
    assert r_sym["status_code"] == 400
    assert r_dir["status_code"] == 400
    assert r_del_dir["status_code"] == 400

    for ep in ("/api/upload/restore", "/api/upload/backup/delete"):
        assert bridge.request("POST", ep, json_body=["list"])["status_code"] == 400  # type: ignore[arg-type]


@pytest.mark.mgmt
@pytest.mark.docker
def test_t5_x509_inspect_no_san_expired_staging_and_symlink(tmp_path: Path) -> None:
    """inspect_certificate handles certs without SANs, expired certs (days_remaining < 0), staging issuers, and symlinks."""
    ws = temp_stack_ws(tmp_path)
    now = dt.datetime.now(dt.timezone.utc)
    key = rsa.generate_private_key(65537, 2048)
    (ws / "ssl" / "probe.key").write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )

    c_nosan = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "nosan.example.edu")]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "nosan.example.edu")]))
        .public_key(key.public_key())
        .serial_number(11)
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    (ws / "ssl" / "nosan.crt").write_bytes(c_nosan.public_bytes(serialization.Encoding.PEM))

    c_exp = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "expired.example.edu")]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "expired.example.edu")]))
        .public_key(key.public_key())
        .serial_number(12)
        .not_valid_before(now - dt.timedelta(days=100))
        .not_valid_after(now - dt.timedelta(days=5))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("expired.example.edu")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    (ws / "ssl" / "exp.crt").write_bytes(c_exp.public_bytes(serialization.Encoding.PEM))

    ca_crt, ca_key = generate_test_ca(tmp_path / "ca", cn="(STAGING) Artificial Apricot R3")
    seed_certbot_live_cert(ws / "certbot" / "conf", "stg.example.edu", ca_crt, ca_key, sans=["stg.example.edu", "alt.example.edu"])

    bridge = MgmtAppBridge(ws)
    r_nosan = bridge.unit_call("certbot_manager", "inspect_certificate", args=["/test_ws/ssl/nosan.crt", "/test_ws/ssl/probe.key", "self-signed"])["return"]
    r_exp = bridge.unit_call("certbot_manager", "inspect_certificate", args=["/test_ws/ssl/exp.crt", "/test_ws/ssl/probe.key", "self-signed"])["return"]
    r_stg = bridge.unit_call(
        "certbot_manager",
        "inspect_certificate",
        args=["/test_ws/certbot/conf/live/stg.example.edu/fullchain.pem", "/test_ws/certbot/conf/live/stg.example.edu/privkey.pem", "certbot"],
    )["return"]

    assert r_nosan["exists"] is True and r_nosan["sans"] == [] and r_nosan["pair_matched"] is True
    assert r_exp["exists"] is True and r_exp["days_remaining"] < 0
    assert r_stg["exists"] is True and r_stg["is_staging"] is True and r_stg["source"] == "letsencrypt-staging"
    assert set(r_stg["sans"]) == {"stg.example.edu", "alt.example.edu"}


@pytest.mark.mgmt
@pytest.mark.docker
def test_t5_auth_403_non_admin_user_across_admin_apis(tmp_path: Path) -> None:
    """Authenticated non-admin user receives 403 Forbidden across /api/certbot/*, /api/env/*, and /api/upload/*."""
    ws = temp_stack_ws(tmp_path)
    code = r"""
import json
from app import create_app

app = create_app()
out = {}
with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['user'] = 'student1'
    for method, ep in [
        ('GET', '/api/certbot/status'),
        ('POST', '/api/certbot/config'),
        ('POST', '/api/certbot/issue'),
        ('POST', '/api/certbot/renew'),
        ('POST', '/api/certbot/switch-mode'),
        ('GET', '/api/env/config'),
        ('POST', '/api/env/config'),
        ('GET', '/api/upload/backups'),
        ('POST', '/api/upload/restore'),
    ]:
        r = c.open(ep, method=method, json={})
        out[f'{method} {ep}'] = r.status_code
print(json.dumps(out))
"""
    proc = _run_in_mgmt_container(ws, code)
    assert proc.returncode == 0, proc.stderr
    statuses = json.loads(proc.stdout.strip().splitlines()[-1])
    for endpoint, code_val in statuses.items():
        assert code_val == 403, f"{endpoint} returned {code_val} instead of 403 for non-admin user"


@pytest.mark.mgmt
@pytest.mark.docker
def test_t5_env_config_bool_as_int_disabled_ratelimit_and_user_id_validation(tmp_path: Path) -> None:
    """EnvConfigManager rejects bool-as-int, non-dict sections, invalid disabled rate_limit, and bad user_id payloads."""
    ws = temp_stack_ws(tmp_path)
    bridge = MgmtAppBridge(ws)

    for bad_cfg in (
        {"rate_limit": {"enabled": True, "rate": "10r/s", "burst": True}},
        {"rate_limit": {"enabled": False, "rate": "bad-rate"}},
        {"rate_limit": {"enabled": False, "burst": False}},
        {"https": {"enabled": 1}},
        {"https": ["not-a-dict"]},
    ):
        r = bridge.request("POST", "/api/env/validate", json_body=bad_cfg)
        assert r["status_code"] == 200 and (r["json"] or {}).get("valid") is False, f"Accepted invalid cfg {bad_cfg}: {r}"

    for bad_uid_payload in (
        {"user_id": True},
        {"user_id": 1.5},
        {"user_id": 0},
        {"user_id": -3},
        {"user_id": "²"},
        {"user_ids": "1,2"},
        {"user_ids": []},
    ):
        for ep in ("/api/env/users/unlock", "/api/env/users/reset-attempts"):
            r = bridge.request("POST", ep, json_body=bad_uid_payload)
            assert r["status_code"] == 400, f"{ep} accepted {bad_uid_payload}: {r}"


@pytest.mark.mgmt
def test_t5_ui_js_html_xss_and_dom_handler_safety() -> None:
    """UI env-config.js and env_settings.html escape XSS in X.509/locked-user/GeoIP DOM and use zero inline onclick in dynamic rows."""
    node = shutil.which("node")
    assert node, "node binary required for UI JS verification"
    root = repo_root()
    js_path = root / "pt-management" / "static" / "js" / "env-config.js"
    html_path = root / "pt-management" / "templates" / "env_settings.html"

    chk = subprocess.run([node, "--check", str(js_path)], capture_output=True, text=True, timeout=10)
    assert chk.returncode == 0, f"node --check failed: {chk.stderr}"

    script = f"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const html = fs.readFileSync({json.dumps(str(html_path))}, 'utf8');
const js = fs.readFileSync({json.dumps(str(js_path))}, 'utf8');

const ids = [...new Set([...js.matchAll(/document\\.getElementById\\(['"]([^'"]+)['"]\\)/g)].map(m => m[1]))];
const missing = ids.filter(id => id !== 'loading-spinner' && !html.includes('id="' + id + '"') && !html.includes("id='" + id + "'"));
assert.deepStrictEqual(missing, [], 'Missing DOM IDs: ' + missing.join(','));

function makeEl(id) {{
  return {{
    id, value: '', checked: false, disabled: false, className: '',
    style: {{ cssText: '', display: '' }}, children: [],
    _innerHTML: '', _textContent: '',
    classList: {{ add() {{}}, remove() {{}} }},
    set innerHTML(v) {{ this._innerHTML = String(v); }},
    get innerHTML() {{ return this._innerHTML; }},
    set textContent(v) {{ this._textContent = String(v); }},
    get textContent() {{ return this._textContent; }},
    appendChild(c) {{ this.children.push(c); }},
    addEventListener() {{}},
    querySelector() {{ return {{ addEventListener() {{}} }}; }},
    scrollTop: 0, scrollHeight: 0,
  }};
}}
const els = {{}};
const sb = {{
  console, FormData: class {{}}, confirm: () => true, alert: () => {{}},
  setTimeout: () => 0, setInterval: () => 0, clearInterval: () => {{}},
  fetch: async () => ({{ ok: true, json: async () => ({{ success: true }}) }}),
  document: {{
    getElementById: (id) => els[id] || (els[id] = makeEl(id)),
    createElement: (t) => makeEl(t),
    querySelectorAll: () => [],
    addEventListener: () => {{}},
  }},
  window: {{}},
}};
sb.window = sb;
vm.createContext(sb);
vm.runInContext(js, sb);

const xss = '<img src=x onerror=alert(1)>';
sb.renderCertbotStatus({{
  tls_mode: 'certbot', ssl_cert_path: xss,
  container: {{ name: xss, running: true, status: xss }},
  certificate: {{ exists: true, source: xss, subject: xss, issuer: xss, sans: [xss], not_before: xss, not_after: xss, days_remaining: -2, pair_matched: false }},
  renewal: {{ next_check_note: xss, renewal_configs_present: false, last_run_status: xss }},
  certbot: {{ enabled: true, domain: xss, extra_domains: xss, email: xss, challenge_type: 'http-01', staging: false, auto_renew: true }},
}});
for (const id of ['cert-status-subject', 'cert-status-issuer', 'cert-status-sans', 'cert-status-validity', 'cert-status-path', 'cert-status-renewal']) {{
  assert(!els[id].innerHTML.includes('<img'), 'Unescaped XSS in ' + id);
  assert(els[id].innerHTML.includes('&lt;img'), 'Expected escaped HTML in ' + id);
}}
sb.document.getElementById('locked-users-tbody').children = [];
sb.displayLockedUsers([{{ user_id: 1, username: xss, failed_attempts: 3, last_failed_login: null, locked_until: null, locked: 1 }}]);
const rowHtml = els['locked-users-tbody'].children[0].innerHTML;
assert(!rowHtml.includes('<img') && rowHtml.includes('&lt;img'));
assert(!rowHtml.includes('onclick='));

sb.document.getElementById('geoip-allow-countries').value = 'FI,' + xss;
sb.document.getElementById('geoip-allow-tags').children = [];
sb.updateCountryTags('geoip-allow-countries', 'geoip-allow-tags');
assert.strictEqual(els['geoip-allow-tags'].children.length, 1);

// Verify showSpinner escapes HTML in message
sb.showSpinner(xss);
const spinChildren = els['alerts-container'].children;
assert(!spinChildren[spinChildren.length - 1].innerHTML.includes('<img'));
"""
    res = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=10)
    assert res.returncode == 0, f"Node UI verification failed:\n{res.stderr}"


@pytest.mark.mgmt
@pytest.mark.docker
def test_t5_bug_upload_rejects_combined_cert_and_private_key_pem(tmp_path: Path) -> None:
    """BUG-1: POST /api/upload/certificate must reject combined PEM containing a PRIVATE KEY block (prevents 0644 key leak)."""
    ws = temp_stack_ws(tmp_path)
    crt_p = tmp_path / "c.crt"
    key_p = tmp_path / "k.key"
    generate_self_signed_cert(crt_p, key_p, cn="combined.example.edu")
    combined = crt_p.read_bytes() + b"\n" + key_p.read_bytes()

    bridge = MgmtAppBridge(ws)
    resp = bridge.request("POST", "/api/upload/certificate", files={"file": ("combined.pem", combined)})
    assert resp["status_code"] == 400, f"Combined cert+key PEM accepted as server.crt (0644 private key leak!): {resp}"


@pytest.mark.mgmt
@pytest.mark.docker
def test_t5_bug_certbot_webroot_rejects_dot_and_double_slash(tmp_path: Path) -> None:
    """BUG-2: validate_certbot_webroot and POST /api/certbot/config must reject '/.' and '//' (normalize to '/')."""
    ws = temp_stack_ws(tmp_path)
    bridge = MgmtAppBridge(ws)
    for bad_wr in ("/.", "//", "/var/www/./", "/var//www", "/var/."):
        resp = bridge.request("POST", "/api/certbot/config", json_body={"domain": "wr.example.edu", "webroot": bad_wr})
        assert resp["status_code"] == 400, f"Accepted unsafe webroot {bad_wr!r}: {resp}"


@pytest.mark.mgmt
@pytest.mark.docker
def test_t5_bug_validate_env_value_burst_unicode_digits(tmp_path: Path) -> None:
    """BUG-3: validate_env_value('NGINX_RATE_LIMIT_BURST', ...) must return (False, ...) on '²' and reject non-ASCII digits '٠١٢'."""
    ws = temp_stack_ws(tmp_path)
    code = r"""
import json
from ptmanagement.api.env_config import validate_env_value
out = {}
for v in ('²', '٠١٢'):
    ok, msg, fmt = validate_env_value('NGINX_RATE_LIMIT_BURST', v)
    out[v] = [ok, msg, fmt]
print(json.dumps(out))
"""
    proc = _run_in_mgmt_container(ws, code)
    assert proc.returncode == 0, f"validate_env_value crashed on Unicode digit: {proc.stderr}"
    res = json.loads(proc.stdout.strip().splitlines()[-1])
    assert res["²"][0] is False
    assert res["٠١٢"][0] is False, f"Accepted non-ASCII digits '٠١٢': {res['٠١٢']}"


@pytest.mark.mgmt
@pytest.mark.docker
def test_t5_bug_validate_config_geoip_rejects_non_list_and_whitespace_countries(tmp_path: Path) -> None:
    """BUG-4: /api/env/validate & /api/env/config must reject bool/int/whitespace-only geoip country lists."""
    ws = temp_stack_ws(tmp_path)
    bridge = MgmtAppBridge(ws)
    for bad_countries in (True, 123, ["   "], [123]):
        r = bridge.request(
            "POST",
            "/api/env/validate",
            json_body={"geoip": {"allow_enabled": True, "allow_countries": bad_countries}},
        )
        assert r["status_code"] == 200 and (r["json"] or {}).get("valid") is False, (
            f"validate_config accepted invalid allow_countries={bad_countries!r}: {r}"
        )
        r_cfg = bridge.request(
            "POST",
            "/api/env/config",
            json_body={"geoip": {"allow_enabled": True, "allow_countries": bad_countries}},
        )
        assert r_cfg["status_code"] == 400, f"/api/env/config accepted invalid allow_countries={bad_countries!r}: {r_cfg}"

    r_ok = bridge.request(
        "POST",
        "/api/env/validate",
        json_body={"geoip": {"allow_enabled": True, "allow_countries": ["FI", "US"]}},
    )
    assert r_ok["status_code"] == 200 and (r_ok["json"] or {}).get("valid") is True


@pytest.mark.mgmt
@pytest.mark.docker
def test_t5_bug_validate_config_rejects_whitespace_cert_and_key_paths(tmp_path: Path) -> None:
    """BUG-5: validate_config must reject whitespace-only https.cert_path/key_path when https.enabled=True."""
    ws = temp_stack_ws(tmp_path)
    bridge = MgmtAppBridge(ws)
    r = bridge.request(
        "POST",
        "/api/env/validate",
        json_body={"https": {"enabled": True, "cert_path": "   ", "key_path": "   "}},
    )
    assert r["status_code"] == 200 and (r["json"] or {}).get("valid") is False, (
        f"validate_config accepted whitespace cert_path/key_path: {r}"
    )


@pytest.mark.mgmt
@pytest.mark.docker
def test_t5_bug_switch_mode_rolls_back_env_on_nginx_test_failure(tmp_path: Path) -> None:
    """BUG-6: switch-mode, save_config, issue, and apply_config_changes must roll back .env (preserving inode) and ptweb.conf if nginx -t fails."""
    ws = temp_stack_ws(
        tmp_path,
        env_overrides={
            "TLS_MODE": "self-signed",
            "CERTBOT_DOMAIN": "rb.example.edu",
            "CERTBOT_EMAIL": "admin@example.edu",
            "SERVER_NAME": "localhost",
        },
    )
    ca_crt, ca_key = generate_test_ca(tmp_path / "ca")
    seed_certbot_live_cert(ws / "certbot" / "conf", "rb.example.edu", ca_crt, ca_key)

    env_path = ws / ".env"
    ptweb_path = ws / "ptweb-vnc" / "pt-nginx" / "conf" / "ptweb.conf"
    # Seed initial ptweb.conf so rollback restoration of ptweb.conf is also exercised
    subprocess.run(["bash", str(ws / "ptweb-vnc" / "pt-nginx" / "generate-nginx-conf.sh")], cwd=str(ws), check=True, capture_output=True)
    orig_env_ino = env_path.stat().st_ino
    orig_ptweb_text = ptweb_path.read_text(encoding="utf-8")

    bridge = MgmtAppBridge(ws)
    bridge.set_mock_nginx_test_fail(True)
    try:
        # 1. switch-mode rollback
        r_sw = bridge.request("POST", "/api/certbot/switch-mode", json_body={"tls_mode": "certbot"})
        assert r_sw["status_code"] == 500
        assert read_env_file(env_path).get("TLS_MODE") == "self-signed"
        assert env_path.stat().st_ino == orig_env_ino
        assert ptweb_path.read_text(encoding="utf-8") == orig_ptweb_text

        # 2. save_config rollback (needs_nginx_sync=True via server_name change)
        r_cfg = bridge.request("POST", "/api/certbot/config", json_body={"server_name": "changed.example.edu"})
        assert r_cfg["status_code"] == 500
        assert read_env_file(env_path).get("SERVER_NAME") == "localhost"
        assert env_path.stat().st_ino == orig_env_ino
        assert ptweb_path.read_text(encoding="utf-8") == orig_ptweb_text

        # 3. issue rollback (post-issue .env/Nginx config update fails nginx -t)
        r_iss = bridge.request("POST", "/api/certbot/issue", json_body={"dry_run": False})
        assert r_iss["status_code"] == 500
        assert read_env_file(env_path).get("TLS_MODE") == "self-signed"
        assert env_path.stat().st_ino == orig_env_ino
        assert ptweb_path.read_text(encoding="utf-8") == orig_ptweb_text

        # 4. apply_config_changes (/api/env/config) rollback
        r_env = bridge.request(
            "POST",
            "/api/env/config",
            json_body={"https": {"enabled": True, "cert_path": "/etc/ssl/ptweb/server.crt", "key_path": "/etc/ssl/ptweb/server.key", "server_name": "other.example.edu"}},
        )
        assert r_env["status_code"] == 500
        assert read_env_file(env_path).get("SERVER_NAME") == "localhost"
        assert env_path.stat().st_ino == orig_env_ino
        assert ptweb_path.read_text(encoding="utf-8") == orig_ptweb_text
    finally:
        bridge.set_mock_nginx_test_fail(False)


@pytest.mark.mgmt
def test_t5_bug_ui_cancelled_preview_does_not_leak_stale_preview_data() -> None:
    """BUG-7: Cancelling preview modal (closePreviewModal) must clear previewData so subsequent applyConfiguration uses fresh form values."""
    node = shutil.which("node")
    assert node
    js_path = repo_root() / "pt-management" / "static" / "js" / "env-config.js"
    html_path = repo_root() / "pt-management" / "templates" / "env_settings.html"

    script = f"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const html = fs.readFileSync({json.dumps(str(html_path))}, 'utf8');
const js = fs.readFileSync({json.dumps(str(js_path))}, 'utf8');

function makeEl(id) {{
  return {{
    id, value: '', checked: false, disabled: false, className: '',
    style: {{ cssText: '', display: '' }}, children: [],
    _innerHTML: '', _textContent: '',
    classList: {{ add() {{}}, remove() {{}} }},
    set innerHTML(v) {{ this._innerHTML = String(v); }},
    get innerHTML() {{ return this._innerHTML; }},
    set textContent(v) {{ this._textContent = String(v); }},
    get textContent() {{ return this._textContent; }},
    appendChild() {{}}, remove() {{}}, addEventListener() {{}},
    querySelector() {{ return {{ addEventListener() {{}} }}; }},
    scrollTop: 0, scrollHeight: 0,
  }};
}}
const els = {{}};
const posted = [];
const sb = {{
  console, confirm: () => true, alert: () => {{}},
  setTimeout: () => 0, setInterval: () => 0, clearInterval: () => {{}},
  fetch: async (url, opts) => {{
    if (opts && opts.body) posted.push({{ url, body: JSON.parse(opts.body) }});
    return {{
      ok: true,
      headers: {{ get: () => 'application/json' }},
      json: async () => ({{
        success: true,
        preview: {{ changes: {{}}, total_changes: 0 }},
        config: {{
          https: {{ enabled: false, cert_path: '', key_path: '', server_name: 'first.example.edu' }},
          geoip: {{ allow_enabled: false, allow_countries: [], block_enabled: false, block_countries: [] }},
          rate_limit: {{ enabled: false, rate: '100r/s', burst: 200, zone_size: '10m' }},
          production: {{ mode: false, public_ip: '' }},
        }},
      }}),
    }};
  }},
  document: {{
    getElementById: (id) => els[id] || (els[id] = makeEl(id)),
    createElement: (t) => makeEl(t),
    querySelectorAll: () => [],
    addEventListener: () => {{}},
  }},
  window: {{}},
}};
sb.window = sb;
vm.createContext(sb);
vm.runInContext(js, sb);

(async () => {{
  sb.document.getElementById('https-server-name').value = 'first.example.edu';
  await sb.previewChanges();
  sb.closePreviewModal();
  sb.document.getElementById('https-server-name').value = 'second.example.edu';
  await sb.applyConfiguration();
  const applyReq = posted.find(p => p.url === '/api/env/config');
  assert.strictEqual(applyReq.body.https.server_name, 'second.example.edu');
}})().catch(err => {{ console.error(err); process.exit(1); }});
"""
    res = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=10)
    assert res.returncode == 0, f"Stale previewData leaked on Apply after Cancel:\n{res.stderr}"


# ============================================================================
# PART B: M2 Stack & Harness Adversarial Coverage + BUG-M2-* Regression Tests
# ============================================================================


@pytest.mark.docker
def test_t5_conditional_hsts_only_when_certbot_cert_active(
    tmp_path: Path, ephemeral_nginx: EphemeralNginxRunner
) -> None:
    """
    [GAP-01] Strict-Transport-Security is emitted on :443 and :5000 ONLY when
    TLS_MODE=certbot and an active Let's Encrypt cert exists; absent otherwise.
    """
    ca_crt, ca_key = generate_test_ca(tmp_path / "ca")

    # Case A: TLS_MODE=certbot with active LE cert -> HSTS MUST be present
    ws_cb = temp_stack_ws(
        tmp_path / "cb_active",
        env_overrides={
            "ENABLE_HTTPS": "true",
            "TLS_MODE": "certbot",
            "CERTBOT_DOMAIN": "hsts.example.test",
            "SERVER_NAME": "hsts.example.test",
            "NGINX_GEOIP_ALLOW": "false",
            "NGINX_GEOIP_BLOCK": "false",
            "NGINX_RATE_LIMIT_ENABLE": "false",
        },
    )
    seed_certbot_live_cert(ws_cb / "certbot" / "conf", "hsts.example.test", ca_crt, ca_key)
    assert ephemeral_nginx.run_generate_nginx_conf(ws_cb).returncode == 0
    srv_cb = ephemeral_nginx.start_server(
        ws_cb, with_stub_upstreams=True, mount_legacy_ssl_files=False, wait_ports=[80, 443, 5000]
    )
    r443 = requests.get(f"https://127.0.0.1:{srv_cb['p443']}/", verify=False, timeout=4)
    r5000 = requests.get(f"https://127.0.0.1:{srv_cb['p5000']}/", verify=False, timeout=4)
    assert "max-age=" in (r443.headers.get("Strict-Transport-Security") or "")
    assert "max-age=" in (r5000.headers.get("Strict-Transport-Security") or "")

    # Case B: TLS_MODE=certbot missing LE cert (bootstrap fallback) -> HSTS MUST be absent
    ws_fb = temp_stack_ws(
        tmp_path / "cb_fallback",
        env_overrides={
            "ENABLE_HTTPS": "true",
            "TLS_MODE": "certbot",
            "CERTBOT_DOMAIN": "missing.example.test",
            "SERVER_NAME": "missing.example.test",
            "NGINX_GEOIP_ALLOW": "false",
            "NGINX_GEOIP_BLOCK": "false",
            "NGINX_RATE_LIMIT_ENABLE": "false",
        },
    )
    assert ephemeral_nginx.run_generate_nginx_conf(ws_fb).returncode == 0
    srv_fb = ephemeral_nginx.start_server(
        ws_fb, with_stub_upstreams=True, mount_legacy_ssl_files=False, wait_ports=[80, 443, 5000]
    )
    r443_fb = requests.get(f"https://127.0.0.1:{srv_fb['p443']}/", verify=False, timeout=4)
    r5000_fb = requests.get(f"https://127.0.0.1:{srv_fb['p5000']}/", verify=False, timeout=4)
    assert r443_fb.headers.get("Strict-Transport-Security") is None
    assert r5000_fb.headers.get("Strict-Transport-Security") is None

    # Case C: TLS_MODE=self-signed & TLS_MODE=manual -> HSTS MUST be absent in ptweb.conf
    for mode in ("self-signed", "manual"):
        ws_m = temp_stack_ws(
            tmp_path / f"mode_{mode}",
            env_overrides={"ENABLE_HTTPS": "true", "TLS_MODE": mode},
        )
        assert ephemeral_nginx.run_generate_nginx_conf(ws_m).returncode == 0
        ptweb = (ws_m / "ptweb-vnc" / "pt-nginx" / "conf" / "ptweb.conf").read_text(encoding="utf-8")
        assert "Strict-Transport-Security" not in ptweb, f"Unexpected HSTS under TLS_MODE={mode}"


def test_t5_generate_nginx_conf_env_parsing_wildcard_legacy_and_inode(
    tmp_path: Path, ephemeral_nginx: EphemeralNginxRunner
) -> None:
    """
    [GAP-03] Verify safe .env parsing (comments, CRLF, export+tabs, quotes),
    wildcard SERVER_NAME globbing safety (`set -f`), legacy cert path normalization,
    command-substitution non-execution, invalid CERTBOT_DOMAIN rejection, and
    nginx.conf/ptweb.conf inode preservation.
    """
    ws = temp_stack_ws(tmp_path)
    (ws / "trap.example.com").write_text("glob-trap", encoding="utf-8")

    nginx_conf = ws / "ptweb-vnc" / "pt-nginx" / "nginx.conf"
    ptweb_conf = ws / "ptweb-vnc" / "pt-nginx" / "conf" / "ptweb.conf"
    assert ephemeral_nginx.run_generate_nginx_conf(ws).returncode == 0
    orig_nginx_ino = nginx_conf.stat().st_ino
    orig_ptweb_ino = ptweb_conf.stat().st_ino

    (ws / ".env").write_text(
        "# Comment line\r\n"
        "  \texport \t ENABLE_HTTPS='true'\r\n"
        'TLS_MODE="self-signed"\r\n'
        'SERVER_NAME="*.example.com localhost"\r\n'
        "SSL_CERT_PATH=/etc/ssl/certs/server.crt\r\n"
        "SSL_KEY_PATH=/etc/ssl/private/server.key\r\n"
        "NGINX_GEOIP_ALLOW=false\r\n"
        "NGINX_GEOIP_BLOCK=false\r\n"
        "NGINX_RATE_LIMIT_ENABLE=false\r\n",
        encoding="utf-8",
    )
    res = ephemeral_nginx.run_generate_nginx_conf(ws)
    assert res.returncode == 0, res.stderr
    assert nginx_conf.stat().st_ino == orig_nginx_ino, "nginx.conf inode changed (breaks :ro single-file bind mount)"
    assert ptweb_conf.stat().st_ino == orig_ptweb_ino, "ptweb.conf inode changed"

    ptweb_txt = ptweb_conf.read_text(encoding="utf-8")
    assert "server_name *.example.com localhost;" in ptweb_txt
    assert "trap.example.com" not in ptweb_txt, "Wildcard SERVER_NAME globbed CWD files!"
    assert "ssl_certificate /etc/ssl/ptweb/server.crt;" in ptweb_txt
    assert "ssl_certificate_key /etc/ssl/ptweb/server.key;" in ptweb_txt

    pwned = tmp_path / "env_pwned"
    for bad_env in (
        f'SERVER_NAME="$(touch {pwned})"\n',
        f'SERVER_NAME="`touch {pwned}`"\n',
        "TLS_MODE=certbot\nCERTBOT_DOMAIN=invalid_single_label\nSERVER_NAME=localhost\n",
    ):
        (ws / ".env").write_text(bad_env, encoding="utf-8")
        bad_res = ephemeral_nginx.run_generate_nginx_conf(ws)
        assert bad_res.returncode != 0, f"Expected failure for {bad_env!r}"
    assert not pwned.exists(), "Shell injection executed during generate-nginx-conf.sh!"


@pytest.mark.docker
def test_t5_geoip_numeric_flag_1_enforces_blocking(
    tmp_path: Path, ephemeral_nginx: EphemeralNginxRunner
) -> None:
    """
    [REGRESSION BUG-M2-01] Setting NGINX_GEOIP_ALLOW=1 must emit GeoIP maps in
    nginx.conf just like NGINX_GEOIP_ALLOW=true, not silently allow all IPs.
    """
    ws = temp_stack_ws(
        tmp_path,
        env_overrides={
            "ENABLE_HTTPS": "false",
            "NGINX_GEOIP_ALLOW": "1",
            "GEOIP_ALLOW_COUNTRIES": "FI,US",
            "NGINX_GEOIP_BLOCK": "false",
        },
    )
    assert ephemeral_nginx.run_generate_nginx_conf(ws).returncode == 0
    nginx_txt = (ws / "ptweb-vnc" / "pt-nginx" / "nginx.conf").read_text(encoding="utf-8")
    assert "map $geoip_country_code $allowed_country" in nginx_txt, (
        "NGINX_GEOIP_ALLOW=1 failed to emit $allowed_country map in nginx.conf"
    )
    assert "FI 1;" in nginx_txt

    srv = ephemeral_nginx.start_server(
        ws, enable_realip_header=True, with_stub_upstreams=True, wait_ports=[80]
    )
    with pytest.raises(requests.exceptions.ConnectionError):
        requests.get(
            f"http://127.0.0.1:{srv['p80']}/",
            headers={"X-Test-IP": "1.1.1.1"},
            timeout=4,
        )


@pytest.mark.docker
def test_t5_public_ip_regex_is_anchored_and_validated(
    tmp_path: Path, ephemeral_nginx: EphemeralNginxRunner
) -> None:
    """
    [REGRESSION BUG-M2-02] PUBLIC_IP in TRUSTED_IPS_REGEX must be anchored (^...$)
    so an attacker IP like 77.88.55.80 cannot bypass GeoIP when PUBLIC_IP=7.88.55.8,
    and malformed PUBLIC_IP values must be rejected/ignored before writing ptweb.conf.
    """
    ws = temp_stack_ws(
        tmp_path / "anchor",
        env_overrides={
            "PRODUCTION_MODE": "true",
            "PUBLIC_IP": "7.88.55.8",
            "ENABLE_HTTPS": "false",
            "NGINX_GEOIP_ALLOW": "true",
            "GEOIP_ALLOW_COUNTRIES": "FI,US",
            "NGINX_GEOIP_BLOCK": "true",
            "GEOIP_BLOCK_COUNTRIES": "RU,IR",
        },
    )
    assert ephemeral_nginx.run_generate_nginx_conf(ws).returncode == 0
    srv = ephemeral_nginx.start_server(
        ws, enable_realip_header=True, with_stub_upstreams=True, wait_ports=[80]
    )
    with pytest.raises(requests.exceptions.ConnectionError):
        requests.get(
            f"http://127.0.0.1:{srv['p80']}/",
            headers={"X-Test-IP": "77.88.55.80"},
            timeout=4,
        )

    # Malformed PUBLIC_IP (e.g. HTML error page from ifconfig.co) must not break nginx -t
    ws_bad = temp_stack_ws(
        tmp_path / "bad_ip",
        env_overrides={
            "PRODUCTION_MODE": "true",
            "PUBLIC_IP": "<html>503; } bad",
        },
    )
    ephemeral_nginx.run_generate_nginx_conf(ws_bad)
    nt = ephemeral_nginx.nginx_test(ws_bad, mount_legacy_ssl_files=False)
    assert nt.returncode == 0, f"Malformed PUBLIC_IP broke nginx -t:\n{nt.stderr}"


@pytest.mark.docker
def test_t5_certbot_mode_empty_domain_stale_ssl_path_falls_back(
    tmp_path: Path, ephemeral_nginx: EphemeralNginxRunner
) -> None:
    """
    [REGRESSION BUG-M2-04] When TLS_MODE=certbot and CERTBOT_DOMAIN='', stale
    SSL_CERT_PATH pointing to a missing LE path must fall back to /etc/ssl/ptweb/server.{crt,key}.
    """
    ws = temp_stack_ws(
        tmp_path,
        env_overrides={
            "ENABLE_HTTPS": "true",
            "TLS_MODE": "certbot",
            "CERTBOT_DOMAIN": "",
            "SSL_CERT_PATH": "/etc/letsencrypt/live/stale.example.test/fullchain.pem",
            "SSL_KEY_PATH": "/etc/letsencrypt/live/stale.example.test/privkey.pem",
        },
    )
    assert ephemeral_nginx.run_generate_nginx_conf(ws).returncode == 0
    nt = ephemeral_nginx.nginx_test(ws, mount_legacy_ssl_files=False)
    assert nt.returncode == 0, f"Stale SSL_CERT_PATH with empty CERTBOT_DOMAIN failed nginx -t:\n{nt.stderr}"


@pytest.mark.docker
def test_t5_nginx_entrypoint_trigger_only_debounce_symlinks_and_signals(
    tmp_path: Path, ephemeral_nginx: EphemeralNginxRunner
) -> None:
    """
    [GAP-02] Verify docker-entrypoint.sh:
    1) Creates /etc/ssl/{certs,private}/server.{crt,key} -> /etc/ssl/ptweb/* symlinks on :ro mounts
    2) Reloads on `.nginx-reload-requested` changes even when cert content is unchanged
    3) Debounces rapid cert+key replacement (0.8s apart) without false nginx -t failures
    4) Exits 0 in <5s on SIGTERM and SIGINT
    """
    ws = temp_stack_ws(
        tmp_path,
        env_overrides={"ENABLE_HTTPS": "true", "TLS_MODE": "self-signed"},
    )
    assert ephemeral_nginx.run_generate_nginx_conf(ws).returncode == 0
    srv = ephemeral_nginx.start_server(
        ws,
        mount_legacy_ssl_files=False,
        env_vars={"NGINX_CERT_WATCH_INTERVAL": "1"},
        wait_ports=[80, 443, 5000],
    )
    cid = srv["container"]

    sym = ephemeral_nginx.exec_in(
        cid, ["sh", "-c", "readlink /etc/ssl/certs/server.crt && readlink /etc/ssl/private/server.key"]
    )
    assert sym.returncode == 0
    assert sym.stdout.strip().splitlines() == [
        "/etc/ssl/ptweb/server.crt",
        "/etc/ssl/ptweb/server.key",
    ]

    # 1. Trigger-only reload
    trig = ws / "certbot" / "conf" / ".nginx-reload-requested"
    trig.write_text(f"{int(time.time())}\n", encoding="utf-8")
    deadline = time.monotonic() + 8.0
    reloaded = False
    while time.monotonic() < deadline:
        logs = subprocess.run(["docker", "logs", cid], capture_output=True, text=True).stderr
        if "reloading nginx..." in logs:
            reloaded = True
            break
        time.sleep(0.3)
    assert reloaded, "Watcher did not reload when only .nginx-reload-requested changed"

    # 2. Debounced cert + key update (0.8s apart)
    new_crt = tmp_path / "deb.crt"
    new_key = tmp_path / "deb.key"
    meta_new = generate_self_signed_cert(new_crt, new_key, cn="debounced.example.test", serial=9191)
    os.replace(new_crt, ws / "ssl" / "server.crt")
    time.sleep(0.8)
    os.replace(new_key, ws / "ssl" / "server.key")

    deadline = time.monotonic() + 10.0
    rotated = False
    while time.monotonic() < deadline:
        fp = ephemeral_nginx.get_tls_cert_info("127.0.0.1", srv["p443"], "localhost")["fingerprint"]
        if fp == meta_new["fingerprint"]:
            rotated = True
            break
        time.sleep(0.3)
    assert rotated, "Watcher failed to serve new cert after debounced cert+key swap"
    logs_after = subprocess.run(["docker", "logs", cid], capture_output=True, text=True).stderr
    assert "nginx -t failed" not in logs_after, f"Debounce failed to coalesce cert+key swap:\n{logs_after}"

    # 3. SIGTERM fast exit (<5s)
    t0 = time.monotonic()
    st = subprocess.run(["docker", "stop", "-t", "10", cid], capture_output=True, text=True, timeout=15)
    dt_term = time.monotonic() - t0
    assert st.returncode == 0
    assert dt_term < 5.0, f"SIGTERM shutdown took {dt_term:.2f}s (>=5s)"
    assert ephemeral_nginx.inspect_container(cid)["State"]["ExitCode"] == 0

    # 4. SIGINT fast exit (<5s)
    srv2 = ephemeral_nginx.start_server(
        ws, mount_legacy_ssl_files=False, env_vars={"NGINX_CERT_WATCH_INTERVAL": "1"}, wait_ports=[80]
    )
    cid2 = srv2["container"]
    t0 = time.monotonic()
    subprocess.run(["docker", "kill", "-s", "SIGINT", cid2], check=True, capture_output=True)
    subprocess.run(["docker", "wait", cid2], check=True, capture_output=True, timeout=10)
    dt_int = time.monotonic() - t0
    assert dt_int < 5.0, f"SIGINT shutdown took {dt_int:.2f}s (>=5s)"
    assert ephemeral_nginx.inspect_container(cid2)["State"]["ExitCode"] == 0


@pytest.mark.docker
def test_t5_nginx_entrypoint_boots_with_legacy_ro_mounts_and_fails_fast_on_bad_config(
    tmp_path: Path, ephemeral_nginx: EphemeralNginxRunner
) -> None:
    """
    [GAP-02] Verify docker-entrypoint.sh skips symlink overwrite without EROFS when
    legacy single-file `:ro` mounts exist, and fails fast if static config is invalid.
    """
    ws = temp_stack_ws(tmp_path)
    assert ephemeral_nginx.run_generate_nginx_conf(ws).returncode == 0

    srv = ephemeral_nginx.start_server(ws, mount_legacy_ssl_files=True, wait_ports=[80, 443])
    assert ephemeral_nginx.inspect_container(srv["container"])["State"]["Running"] is True

    (ws / "ptweb-vnc" / "pt-nginx" / "conf" / "99-bad.conf").write_text("bad_directive;\n", encoding="utf-8")
    res = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{ws / 'ptweb-vnc' / 'pt-nginx' / 'nginx.conf'}:/etc/nginx/nginx.conf:ro",
            "-v",
            f"{ws / 'ptweb-vnc' / 'pt-nginx' / 'conf'}:/etc/nginx/conf.d:ro",
            "-v",
            f"{ws / 'ssl'}:/etc/ssl/ptweb:ro",
            "pt-nginx:latest",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert res.returncode != 0, "pt-nginx entrypoint must fail fast on invalid static config"


@pytest.mark.docker
def test_t5_certbot_entrypoint_signals_flock_and_missing_renewal_skip(tmp_path: Path) -> None:
    """
    [GAP-04] Verify real `pt-certbot:latest` container:
    1) Skips `certbot renew` when `/etc/letsencrypt/renewal/*.conf` is absent
    2) Enforces `flock -n /etc/letsencrypt/.pt_certbot_op.lock` contention (`rc=1`)
    3) Exits 0 in <2s on SIGTERM
    """
    cb_conf = tmp_path / "cb_conf"
    cb_www = tmp_path / "cb_www"
    cb_conf.mkdir()
    cb_www.mkdir()
    cb_env = tmp_path / ".env"
    cb_env.write_text("CERTBOT_AUTO_RENEW=true\n", encoding="utf-8")
    cname = f"pt-certbot-e2e-t5-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                cname,
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "-v",
                f"{cb_conf}:/etc/letsencrypt:rw",
                "-v",
                f"{cb_www}:/var/www/certbot:rw",
                "-v",
                f"{cb_env}:/app/.env:ro",
                "-e",
                "CERTBOT_RENEW_INTERVAL=60",
                "pt-certbot:latest",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        time.sleep(1.0)
        logs = subprocess.run(["docker", "logs", cname], capture_output=True, text=True).stdout
        assert "Checking certificates for renewal" not in logs

        holder = subprocess.Popen(
            ["docker", "exec", cname, "flock", "/etc/letsencrypt/.pt_certbot_op.lock", "sleep", "3"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            time.sleep(0.5)
            contender = subprocess.run(
                ["docker", "exec", cname, "flock", "-n", "/etc/letsencrypt/.pt_certbot_op.lock", "echo", "busy"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            assert contender.returncode == 1, f"Expected flock -n rc=1 under contention, got {contender.returncode}"
        finally:
            holder.wait(timeout=10)

        t0 = time.monotonic()
        st = subprocess.run(["docker", "stop", "-t", "10", cname], capture_output=True, text=True, timeout=15)
        dt = time.monotonic() - t0
        assert st.returncode == 0
        assert dt < 2.0, f"pt-certbot SIGTERM shutdown took {dt:.3f}s (>=2s)"
        ec = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.ExitCode}}", cname],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert ec == "0"
    finally:
        subprocess.run(["docker", "rm", "-f", cname], capture_output=True)


@pytest.mark.docker
@pytest.mark.parametrize(
    "env_text,env_var_override,expected",
    [
        (None, {"CERTBOT_AUTO_RENEW": "false"}, "false"),
        ("CERTBOT_AUTO_RENEW=false\n", {}, "false"),
        ('CERTBOT_AUTO_RENEW="false"\n', {}, "false"),
        ("CERTBOT_AUTO_RENEW='false'\n", {}, "false"),
        ('  \texport \t CERTBOT_AUTO_RENEW="false"\r\n', {}, "false"),
        ("# CERTBOT_AUTO_RENEW=false\nCERTBOT_AUTO_RENEW=true\n", {}, "true"),
        ("CERTBOT_AUTO_RENEW=$(touch /tmp/t5_cb_pwned)\n", {}, "$(touch /tmp/t5_cb_pwned)"),
        # [REGRESSION BUG-M2-06] Trailing whitespace after closing quote must still strip quotes:
        ('CERTBOT_AUTO_RENEW="true"  \n', {}, "true"),
    ],
)
def test_t5_certbot_get_auto_renew_parsing(
    tmp_path: Path, env_text: str | None, env_var_override: dict[str, str], expected: str
) -> None:
    """
    [GAP-04 / REGRESSION BUG-M2-06] Validate BusyBox POSIX `get_auto_renew()` inside `pt-certbot:latest`.
    """
    mounts: List[str] = []
    if env_text is not None:
        ef = tmp_path / "test.env"
        ef.write_text(env_text, encoding="utf-8")
        mounts = ["-v", f"{ef}:/app/.env:ro"]
    envs: List[str] = []
    for k, v in env_var_override.items():
        envs += ["-e", f"{k}={v}"]

    cmd = [
        "docker",
        "run",
        "--rm",
        "--entrypoint",
        "/bin/sh",
        *mounts,
        *envs,
        "pt-certbot:latest",
        "-c",
        "sed -n '/^get_auto_renew()/,/^}/p' /entrypoint.sh > /tmp/gar.sh && . /tmp/gar.sh && get_auto_renew",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == expected


def test_t5_remove_instance_pt_nginx1_parity_and_cleanup_regex() -> None:
    """
    [GAP-05] Verify `remove-instance.sh` maintains full `pt-nginx1` parity with `deploy.sh`,
    and `Scripts/cleanup-all.sh` includes `pt-certbot` while ignoring non-project names.
    """
    root = repo_root()
    rem = (root / "remove-instance.sh").read_text(encoding="utf-8")
    for required in (
        "--network ptnet",
        "-p 80:80",
        "-p 443:443",
        "-p 5000:5000",
        "nginx.conf,target=/etc/nginx/nginx.conf,readonly",
        "/etc/ssl/ptweb,readonly",
        "/etc/letsencrypt,readonly",
        "/var/www/certbot,readonly",
        "GEOIP_ARGS",
        "docker network connect pt-stack",
        'generate-ssl-cert.sh" --if-missing',
    ):
        assert required in rem, f"remove-instance.sh missing deploy.sh parity fragment: {required}"

    cleanup = (root / "Scripts" / "cleanup-all.sh").read_text(encoding="utf-8")
    assert "pt-certbot" in cleanup, "Scripts/cleanup-all.sh missing pt-certbot cleanup"


def test_t5_posix_and_auxiliary_shell_syntax() -> None:
    """
    [GAP-05] POSIX `sh -n` passes on `#!/bin/sh` entrypoints and `bash -n` passes
    on auxiliary scripts (`Scripts/cleanup-all.sh`, `add-instance.sh`).
    """
    root = repo_root()
    for rel in ("ptweb-vnc/pt-nginx/docker-entrypoint.sh", "ptweb-vnc/pt-certbot/entrypoint.sh"):
        res = subprocess.run(["sh", "-n", str(root / rel)], capture_output=True, text=True, timeout=10)
        assert res.returncode == 0, f"sh -n failed for {rel}: {res.stderr}"
    for rel in ("Scripts/cleanup-all.sh", "add-instance.sh"):
        res = subprocess.run(["bash", "-n", str(root / rel)], capture_output=True, text=True, timeout=10)
        assert res.returncode == 0, f"bash -n failed for {rel}: {res.stderr}"


def test_t5_generate_ssl_cert_if_missing_preserves_and_recovers_half_missing(tmp_path: Path) -> None:
    """
    [GAP-05] `generate-ssl-cert.sh --if-missing` hardens 0644->0600 without overwriting
    an existing valid pair, and regenerates cleanly when server.key is missing.
    """
    work = tmp_path / "ssl_ws"
    work.mkdir()
    script = work / "generate-ssl-cert.sh"
    shutil.copy2(repo_root() / "generate-ssl-cert.sh", script)
    os.chmod(script, 0o755)

    r1 = subprocess.run(
        ["bash", str(script), "--if-missing"], cwd=str(work), stdin=subprocess.DEVNULL, capture_output=True, text=True
    )
    assert r1.returncode == 0, r1.stderr
    crt = work / "ssl" / "server.crt"
    key = work / "ssl" / "server.key"
    fp1 = x509_metadata(crt)["fingerprint"]

    os.chmod(key, 0o644)
    r2 = subprocess.run(
        ["bash", str(script), "--if-missing"], cwd=str(work), stdin=subprocess.DEVNULL, capture_output=True, text=True
    )
    assert r2.returncode == 0, r2.stderr
    assert x509_metadata(crt)["fingerprint"] == fp1, "--if-missing overwrote existing valid cert"
    assert stat.S_IMODE(key.stat().st_mode) == 0o600, "--if-missing failed to harden key permissions to 0600"

    key.unlink()
    r3 = subprocess.run(
        ["bash", str(script), "--if-missing"], cwd=str(work), stdin=subprocess.DEVNULL, capture_output=True, text=True
    )
    assert r3.returncode == 0, r3.stderr
    assert key.is_file() and stat.S_IMODE(key.stat().st_mode) == 0o600
    assert x509_metadata(crt)["fingerprint"] != fp1


@pytest.mark.docker
def test_t5_compose_requires_shared_host_path_and_mounts_certbot_env() -> None:
    """
    [GAP-05] `docker compose config` fails fast when SHARED_HOST_PATH is unset, and
    `pt-certbot` mounts `../.env:/app/.env:ro`.
    """
    compose_file = repo_root() / "ptweb-vnc" / "docker-compose.yml"
    clean_env = {k: v for k, v in os.environ.items() if k != "SHARED_HOST_PATH"}
    res_fail = subprocess.run(
        ["docker", "compose", "--env-file", "/dev/null", "-f", str(compose_file), "config", "--quiet"],
        env=clean_env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert res_fail.returncode != 0, "docker compose config must fail when SHARED_HOST_PATH is unset"


def test_t5_deploy_and_remove_https_numeric_1_parity() -> None:
    """
    [REGRESSION BUG-M2-05] deploy.sh and remove-instance.sh must treat ENABLE_HTTPS=1
    consistently with generate-nginx-conf.sh when bootstrapping SSL certs.
    """
    root = repo_root()
    for fname in ("deploy.sh", "remove-instance.sh"):
        txt = (root / fname).read_text(encoding="utf-8")
        assert re.search(r'ENABLE_HTTPS.*=\s*"1"', txt), (
            f"{fname} only checks ENABLE_HTTPS=true, missing ENABLE_HTTPS=1 parity with generate-nginx-conf.sh"
        )


@pytest.mark.docker
def test_t5_harness_mock_flock_busy_returns_409(tmp_path: Path) -> None:
    """
    [GAP-05] Verify `MOCK_FLOCK_BUSY=1` in `_MOCK_DOCKER_SHIM` maps to HTTP 409 in CertbotManager.
    """
    ws = temp_stack_ws(tmp_path)
    bridge = MgmtAppBridge(ws)
    assert (
        bridge.request(
            "POST",
            "/api/certbot/config",
            json_body={"domain": "flock.example.edu", "email": "admin@example.edu"},
        )["status_code"]
        == 200
    )
    flag = ws / "MOCK_FLOCK_BUSY"
    flag.write_text("1", encoding="utf-8")
    try:
        resp = bridge.request("POST", "/api/certbot/issue", json_body={"dry_run": False})
    finally:
        flag.unlink(missing_ok=True)
    assert resp["status_code"] == 409, f"Expected HTTP 409 on MOCK_FLOCK_BUSY, got {resp['status_code']}"


def test_t5_harness_healthcheck_invariants_reject_commented_directives() -> None:
    """
    [REGRESSION BUG-HARNESS-01] `assert_healthcheck_location_root_invariants()` must
    strip `#` comments before matching GeoIP and limit_req enforcement directives.
    """
    commented_conf = (
        "server {\n"
        "  listen 443 ssl;\n"
        "  location / {\n"
        "    # $allowed_country $blocked_country\n"
        "    # if ($allowed_country = 0) { return 444; }\n"
        "    # if ($blocked_country = 1) { return 444; }\n"
        "    # limit_req zone=pt_req_zone burst=200 nodelay;\n"
        "    proxy_pass http://pt-guacamole:8080/guacamole/;\n"
        "  }\n"
        "}\n"
    )
    with pytest.raises(AssertionError):
        assert_healthcheck_location_root_invariants(
            commented_conf, expect_allow=True, expect_block=True, expect_rate_limit=True
        )


def test_t5_certbot_test_ready_reflects_resolved_bad_payload8() -> None:
    """
    [REGRESSION BUG-M2-03] `CERTBOT_TEST_READY.md` must not claim `bad_payload8` is
    an active failing test (`49/50`) now that `CertbotManager.save_config()` rejects it.
    """
    ready_md = (repo_root() / "CERTBOT_TEST_READY.md").read_text(encoding="utf-8")
    assert "49/50" not in ready_md and "Sole Failing Test" not in ready_md, (
        "CERTBOT_TEST_READY.md still reports outdated 49/50 bad_payload8 failure note"
    )


@pytest.mark.docker
def test_t5_nginx_boots_and_passes_nginx_t_without_pt_management(
    tmp_path: Path, ephemeral_nginx: EphemeralNginxRunner
) -> None:
    """
    [REGRESSION BUG-M2-R2-01] `pt-nginx:latest` must pass `nginx -t`, boot (`Running=true`),
    and serve `/.well-known/acme-challenge/` + Guacamole `/` when ONLY `pt-guacamole` exists
    on the network (no `pt-management` container and no `--add-host pt-management`).
    Once `pt-management` attaches, `/api/student/files/list`, `/my-files`, and
    `/downloads/sample.pkt` must proxy with exact request paths preserved.
    """
    ws = temp_stack_ws(tmp_path)
    gen = ephemeral_nginx.run_generate_nginx_conf(ws)
    assert gen.returncode == 0, gen.stderr

    acme_dir = ws / "certbot" / "www" / ".well-known" / "acme-challenge"
    acme_dir.mkdir(parents=True, exist_ok=True)
    (acme_dir / "t5-no-mgmt-token").write_text("acme-no-mgmt-ok", encoding="utf-8")

    net_name = f"pt-certbot-e2e-t5-nomgmt-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    net_res = subprocess.run(["docker", "network", "create", net_name], capture_output=True, text=True, timeout=15)
    assert net_res.returncode == 0, net_res.stderr
    ephemeral_nginx.networks.append(net_name)

    guac_stub_script = (
        "import http.server, socketserver\n"
        "class H(http.server.BaseHTTPRequestHandler):\n"
        "  def do_GET(self):\n"
        "    self.send_response(200)\n"
        "    self.send_header('Content-Type', 'text/plain')\n"
        "    self.end_headers()\n"
        "    self.wfile.write(b'GUAC_STUB_OK')\n"
        "  def log_message(self, *a): pass\n"
        "socketserver.TCPServer.allow_reuse_address = True\n"
        "socketserver.TCPServer(('0.0.0.0', 8080), H).serve_forever()\n"
    )
    guac_name = f"{net_name}-guac"
    ephemeral_nginx.containers.append(guac_name)
    guac_res = subprocess.run(
        [
            "docker", "run", "-d", "--name", guac_name,
            "--network", net_name, "--network-alias", "pt-guacamole",
            "--entrypoint", "python3", "pt-management:latest", "-c", guac_stub_script,
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert guac_res.returncode == 0, guac_res.stderr

    nginx_conf = ws / "ptweb-vnc" / "pt-nginx" / "nginx.conf"
    conf_dir = ws / "ptweb-vnc" / "pt-nginx" / "conf"
    base_mounts = [
        "-v", f"{nginx_conf}:/etc/nginx/nginx.conf:ro",
        "-v", f"{conf_dir}:/etc/nginx/conf.d:ro",
        "-v", f"{ws / 'ssl'}:/etc/ssl/ptweb:ro",
        "-v", f"{ws / 'certbot' / 'conf'}:/etc/letsencrypt:ro",
        "-v", f"{ws / 'certbot' / 'www'}:/var/www/certbot:ro",
    ]
    geoip = ws / "geoip" / "GeoIP.dat"
    if geoip.exists():
        base_mounts += ["-v", f"{geoip}:/usr/share/GeoIP/GeoIP.dat:ro"]

    # 1. `nginx -t` must pass with ONLY `pt-guacamole` on the network (no `pt-management`).
    nt = subprocess.run(
        ["docker", "run", "--rm", "--network", net_name, *base_mounts, "pt-nginx:latest", "nginx", "-t"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert nt.returncode == 0, f"nginx -t failed without pt-management:\n{nt.stdout}\n{nt.stderr}"

    # 2. Boot `pt-nginx:latest` on the same network (again without `pt-management`).
    p80 = p443 = p5000 = 0
    nginx_cname = ""
    for attempt in range(3):
        p80 = free_tcp_port()
        p443 = free_tcp_port()
        p5000 = free_tcp_port()
        while p443 == p80:
            p443 = free_tcp_port()
        while p5000 in (p80, p443):
            p5000 = free_tcp_port()
        nginx_cname = f"pt-certbot-e2e-t5-nx-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        run_res = subprocess.run(
            [
                "docker", "run", "-d", "--name", nginx_cname,
                "--network", net_name,
                "-p", f"127.0.0.1:{p80}:80",
                "-p", f"127.0.0.1:{p443}:443",
                "-p", f"127.0.0.1:{p5000}:5000",
                *base_mounts,
                "pt-nginx:latest",
            ],
            capture_output=True,
            text=True,
            timeout=25,
        )
        if run_res.returncode == 0:
            ephemeral_nginx.containers.append(nginx_cname)
            break
        subprocess.run(["docker", "rm", "-f", nginx_cname], capture_output=True, text=True, timeout=10)
        if attempt < 2 and ("port is already allocated" in run_res.stderr or "address already in use" in run_res.stderr):
            time.sleep(0.1)
            continue
        raise AssertionError(f"Failed to start pt-nginx without pt-management: {run_res.stderr}")

    deadline = time.monotonic() + 12.0
    ready = False
    while time.monotonic() < deadline:
        info = ephemeral_nginx.inspect_container(nginx_cname)
        assert info["State"]["Running"] is True, "pt-nginx crashed without pt-management"
        tcp_proc = ephemeral_nginx.exec_in(
            nginx_cname, ["sh", "-c", "cat /proc/net/tcp /proc/net/tcp6 2>/dev/null"]
        )
        all_open = False
        if tcp_proc.returncode == 0:
            listening_hex = set()
            for line in tcp_proc.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 4 and parts[3] == "0A" and ":" in parts[1]:
                    listening_hex.add(parts[1].rsplit(":", 1)[1].upper())
            all_open = all(f"{cp:04X}" in listening_hex for cp in (80, 443, 5000))
        if all_open:
            try:
                for tp in (p80, p443, p5000):
                    with socket.create_connection(("127.0.0.1", tp), timeout=0.4):
                        pass
                ready = True
                break
            except OSError:
                pass
        time.sleep(0.15)
    assert ready, "Timed out waiting for pt-nginx ports without pt-management"

    r_acme = requests.get(f"http://127.0.0.1:{p80}/.well-known/acme-challenge/t5-no-mgmt-token", timeout=5)
    assert r_acme.status_code == 200
    assert r_acme.text == "acme-no-mgmt-ok"

    r_guac = requests.get(f"https://127.0.0.1:{p443}/", verify=False, timeout=5)
    assert r_guac.status_code == 200
    assert r_guac.text == "GUAC_STUB_OK"

    # 3. Attach stub `pt-management` and verify exact URI path preservation across all 3 routes + :5000.
    mgmt_stub_script = (
        "import http.server, socketserver\n"
        "class H(http.server.BaseHTTPRequestHandler):\n"
        "  def do_GET(self):\n"
        "    self.send_response(200)\n"
        "    self.send_header('Content-Type', 'text/plain')\n"
        "    self.end_headers()\n"
        "    self.wfile.write(f'MGMT_PATH={self.path}'.encode())\n"
        "  def log_message(self, *a): pass\n"
        "socketserver.TCPServer.allow_reuse_address = True\n"
        "socketserver.TCPServer(('0.0.0.0', 5000), H).serve_forever()\n"
    )
    mgmt_name = f"{net_name}-mgmt"
    ephemeral_nginx.containers.append(mgmt_name)
    mgmt_res = subprocess.run(
        [
            "docker", "run", "-d", "--name", mgmt_name,
            "--network", net_name, "--network-alias", "pt-management",
            "--entrypoint", "python3", "pt-management:latest", "-c", mgmt_stub_script,
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert mgmt_res.returncode == 0, mgmt_res.stderr

    probe_deadline = time.monotonic() + 15.0
    last_status = None
    while time.monotonic() < probe_deadline:
        try:
            r = requests.get(f"https://127.0.0.1:{p443}/api/student/files/list", verify=False, timeout=3)
            last_status = r.status_code
            if r.status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(0.3)
    assert last_status == 200, f"Stub pt-management did not become reachable via nginx (last_status={last_status})"

    for path in (
        "/api/student/files/list",
        "/api/student/files/token?container=ptvnc1&file=lab.pkt",
        "/my-files",
        "/downloads/sample.pkt",
    ):
        resp = requests.get(f"https://127.0.0.1:{p443}{path}", verify=False, timeout=5)
        assert resp.status_code == 200, f"{path} returned {resp.status_code}: {resp.text}"
        assert resp.text == f"MGMT_PATH={path}", f"Path mismatch for {path}: got {resp.text!r}"

    resp_5000 = requests.get(f"https://127.0.0.1:{p5000}/health", verify=False, timeout=5)
    assert resp_5000.status_code == 200
    assert resp_5000.text == "MGMT_PATH=/health"

    final_info = ephemeral_nginx.inspect_container(nginx_cname)
    assert final_info["State"]["Running"] is True
    assert final_info["RestartCount"] == 0


@pytest.mark.docker
def test_t5_generate_nginx_conf_handles_empty_geoip_country_tokens(
    tmp_path: Path, ephemeral_nginx: EphemeralNginxRunner
) -> None:
    """
    [REGRESSION BUG-M2-R2-02] `generate-nginx-conf.sh` must trim whitespace and skip
    empty tokens in GEOIP_ALLOW_COUNTRIES / GEOIP_BLOCK_COUNTRIES so values like
    `FI,,US`, `FI, , US`, or `"   "` never emit bare `1;` map entries that break `nginx -t`.
    """
    cases = [
        ("FI,,US", "RU,,IR"),
        ("FI, , US", "RU, , IR"),
        ("   ", "   "),
    ]
    for idx, (allow_countries, block_countries) in enumerate(cases):
        case_dir = tmp_path / f"geo_case_{idx}"
        case_dir.mkdir(parents=True, exist_ok=True)
        ws = temp_stack_ws(
            case_dir,
            env_overrides={
                "NGINX_GEOIP_ALLOW": "1",
                "GEOIP_ALLOW_COUNTRIES": allow_countries,
                "NGINX_GEOIP_BLOCK": "1",
                "GEOIP_BLOCK_COUNTRIES": block_countries,
            },
        )
        # Write raw .env to preserve exact empty/whitespace-only country tokens
        write_env_file(
            ws / ".env",
            {
                "PRODUCTION_MODE": "false",
                "ENABLE_HTTPS": "true",
                "TLS_MODE": "self-signed",
                "SERVER_NAME": "localhost",
                "SSL_CERT_PATH": "/etc/ssl/ptweb/server.crt",
                "SSL_KEY_PATH": "/etc/ssl/ptweb/server.key",
                "NGINX_GEOIP_ALLOW": "1",
                "GEOIP_ALLOW_COUNTRIES": allow_countries,
                "NGINX_GEOIP_BLOCK": "1",
                "GEOIP_BLOCK_COUNTRIES": block_countries,
                "NGINX_RATE_LIMIT_ENABLE": "false",
            },
        )
        gen = ephemeral_nginx.run_generate_nginx_conf(ws)
        assert gen.returncode == 0, f"Case {idx} ({allow_countries!r}, {block_countries!r}) gen failed:\n{gen.stderr}"

        nginx_conf = (ws / "ptweb-vnc" / "pt-nginx" / "nginx.conf").read_text(encoding="utf-8")
        assert re.search(r"^\s+1;\s*$", nginx_conf, re.MULTILINE) is None, (
            f"Case {idx} emitted invalid bare `1;` map entry:\n{nginx_conf}"
        )
        if allow_countries.strip():
            assert "FI 1;" in nginx_conf and "US 1;" in nginx_conf
        if block_countries.strip():
            assert "RU 1;" in nginx_conf and "IR 1;" in nginx_conf

        nt = ephemeral_nginx.nginx_test(ws, mount_legacy_ssl_files=False)
        assert nt.returncode == 0, (
            f"Case {idx} ({allow_countries!r}, {block_countries!r}) failed nginx -t:\n{nt.stdout}\n{nt.stderr}"
        )
