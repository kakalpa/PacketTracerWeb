"""
Tier 1: Feature, Configuration, Syntax & API/UI Contract Tests.

Validates:
- M1 architecture & implementation plan presence and required sections
- `.env.example` and `.gitignore` contracts
- `ptweb-vnc/docker-compose.yml` syntax and service/mount/port contracts
- Shell syntax (`bash -n`) and absence of single-file SSL bind mounts in `deploy*.sh`
- `pt-certbot` service file contract
- `generate-nginx-conf.sh` profile matrix + ephemeral `pt-nginx:latest nginx -t`
- `generate-ssl-cert.sh` non-interactive execution & `0600` key permissions
- `EnvConfigManager` key append + inode preservation
- `pt-management` Certbot UI & `/api/certbot/*` + `/api/upload/*` auth & happy paths
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Dict, List

import pytest

from tests.certbot.helpers import (
    EphemeralNginxRunner,
    MgmtAppBridge,
    assert_healthcheck_location_root_invariants,
    generate_self_signed_cert,
    issue_ca_signed_cert,
    generate_test_ca,
    read_env_file,
    repo_root,
    seed_certbot_live_cert,
    temp_stack_ws,
    write_env_file,
    x509_metadata,
)


pytestmark = pytest.mark.tier1


def _discover_shell_scripts(base: Path) -> List[Path]:
    scripts: List[Path] = []
    if not base.exists():
        return scripts
    for p in sorted(base.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix == ".sh":
            scripts.append(p)
            continue
        try:
            first_line = p.read_text(encoding="utf-8", errors="ignore").splitlines()[0]
        except IndexError:
            continue
        if first_line.startswith("#!") and ("bash" in first_line or "/sh" in first_line):
            scripts.append(p)
    return scripts


def test_t1_m1_architecture_doc_present_and_complete() -> None:
    """M1 architecture & implementation plan exists under docs/proposals/ and covers all required areas."""
    proposals_dir = repo_root() / "docs" / "proposals"
    candidates = sorted(proposals_dir.glob("certbot*.md"))
    assert candidates, (
        f"Missing M1 architecture document matching docs/proposals/certbot*.md in {proposals_dir}"
    )

    doc_text = candidates[0].read_text(encoding="utf-8")
    assert len(doc_text) >= 2000, f"Architecture doc {candidates[0]} is unexpectedly short ({len(doc_text)} chars)"

    lower = doc_text.lower()
    required_concepts = [
        ("acme / http-01 flow", ("acme", "http-01", "well-known/acme-challenge")),
        ("issuance & renewal", ("certonly", "renew")),
        ("nginx reload integration", ("pt-nginx", "nginx -t", "reload")),
        ("pt-management admin portal", ("pt-management", "/api/certbot")),
        ("volumes & certbot container", ("pt-certbot", "/etc/letsencrypt", "/var/www/certbot")),
        ("coexistence with generate-ssl-cert.sh & manual upload", ("generate-ssl-cert.sh", "manual")),
        ("private key safety", ("0600", "600", "private key")),
    ]
    missing = [
        label for label, keywords in required_concepts if not any(kw in lower for kw in keywords)
    ]
    assert not missing, f"M1 doc {candidates[0].name} missing required coverage for: {missing}"


def test_t1_env_example_documents_certbot_vars() -> None:
    """`.env.example` documents TLS_MODE, SERVER_NAME, and all CERTBOT_* contract variables."""
    env_example = (repo_root() / ".env.example").read_text(encoding="utf-8")
    required_vars = [
        "TLS_MODE",
        "SERVER_NAME",
        "CERTBOT_ENABLED",
        "CERTBOT_DOMAIN",
        "CERTBOT_EXTRA_DOMAINS",
        "CERTBOT_EMAIL",
        "CERTBOT_CHALLENGE_TYPE",
        "CERTBOT_STAGING",
        "CERTBOT_AUTO_RENEW",
        "CERTBOT_WEBROOT",
    ]
    missing = [var for var in required_vars if not re.search(rf"^\s*{re.escape(var)}=", env_example, re.MULTILINE)]
    assert not missing, f".env.example missing required variable definitions: {missing}"


def test_t1_gitignore_ignores_certbot_and_ssl() -> None:
    """`.gitignore` excludes certbot runtime/cert directories, ssl artifacts, and .env files."""
    gitignore = (repo_root() / ".gitignore").read_text(encoding="utf-8")
    lines = [ln.strip() for ln in gitignore.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert any("certbot" in ln for ln in lines), ".gitignore must ignore certbot/ directory"
    assert any("ssl" in ln for ln in lines), ".gitignore must ignore ssl/ directory"
    assert any(".env" in ln for ln in lines), ".gitignore must ignore *.env"


@pytest.mark.docker
def test_t1_compose_syntax_valid() -> None:
    """`docker compose -f ptweb-vnc/docker-compose.yml config --quiet` succeeds."""
    compose_file = repo_root() / "ptweb-vnc" / "docker-compose.yml"
    compose_env = dict(os.environ)
    compose_env.setdefault("SHARED_HOST_PATH", str(repo_root() / "shared"))
    res = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "config", "--quiet"],
        env=compose_env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert res.returncode == 0, f"docker compose config --quiet failed:\n{res.stderr}"


@pytest.mark.docker
def test_t1_compose_yaml_and_certbot_contract() -> None:
    """Compose JSON defines pt-certbot, directory SSL/Certbot mounts, and ports 80/443/5000 on nginx."""
    compose_file = repo_root() / "ptweb-vnc" / "docker-compose.yml"
    compose_env = dict(os.environ)
    compose_env.setdefault("SHARED_HOST_PATH", str(repo_root() / "shared"))
    res = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "config", "--format", "json"],
        env=compose_env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert res.returncode == 0, f"docker compose config --format json failed:\n{res.stderr}"
    cfg = json.loads(res.stdout)
    services: Dict[str, dict] = cfg.get("services", {})

    for required_svc in ("mariadb", "guacd", "guacamole", "nginx", "pt-management"):
        assert required_svc in services, f"Missing service '{required_svc}' in docker-compose.yml"

    certbot_svc = services.get("pt-certbot") or services.get("certbot")
    assert certbot_svc is not None, "Missing pt-certbot/certbot service in ptweb-vnc/docker-compose.yml"
    assert certbot_svc.get("container_name") == "pt-certbot", (
        f"Expected container_name 'pt-certbot', got {certbot_svc.get('container_name')!r}"
    )

    nginx_svc = services["nginx"]
    assert nginx_svc.get("container_name") == "pt-nginx1"
    nginx_image = str(nginx_svc.get("image") or "")
    nginx_build = nginx_svc.get("build")
    assert nginx_image != "nginx:latest", (
        "nginx service must NOT use upstream nginx:latest (lacks GeoIP module & cert reload watcher)"
    )
    assert "pt-nginx" in nginx_image or (
        isinstance(nginx_build, dict) and "pt-nginx" in str(nginx_build.get("context", ""))
    ), f"nginx service must use custom pt-nginx image/build, got image={nginx_image!r}, build={nginx_build!r}"

    # Ports: nginx exposes 80, 443, 5000; pt-management exposes no host port 5000
    nginx_pub_ports = {int(p.get("published")) for p in nginx_svc.get("ports", []) if p.get("published")}
    assert {80, 443, 5000}.issubset(nginx_pub_ports), (
        f"nginx must publish ports 80, 443, 5000; got {sorted(nginx_pub_ports)}"
    )
    mgmt_pub_ports = {int(p.get("published")) for p in services["pt-management"].get("ports", []) if p.get("published")}
    assert 5000 not in mgmt_pub_ports, (
        f"pt-management must NOT publish host port 5000 directly (nginx proxies 5000); got {mgmt_pub_ports}"
    )

    # Volume mounts: no single-file server.crt/server.key bind mounts
    def _targets(svc_dict: dict) -> Dict[str, dict]:
        out: Dict[str, dict] = {}
        for vol in svc_dict.get("volumes", []):
            if isinstance(vol, dict) and "target" in vol:
                out[str(vol["target"])] = vol
        return out

    nginx_vols = _targets(nginx_svc)
    for forbidden in ("/etc/ssl/certs/server.crt", "/etc/ssl/private/server.key"):
        assert forbidden not in nginx_vols, f"nginx still has single-file bind mount {forbidden}"
    assert "/etc/ssl/ptweb" in nginx_vols, "nginx missing directory mount /etc/ssl/ptweb"
    assert "/etc/letsencrypt" in nginx_vols, "nginx missing directory mount /etc/letsencrypt"
    assert "/var/www/certbot" in nginx_vols, "nginx missing directory mount /var/www/certbot"

    cb_vols = _targets(certbot_svc)
    cb_vol_sources = {
        str(v.get("source", ""))
        for v in certbot_svc.get("volumes", [])
        if isinstance(v, dict)
    }
    assert "/var/run/docker.sock" not in cb_vols and not any("docker.sock" in t for t in cb_vols) and not any(
        "docker.sock" in s for s in cb_vol_sources
    ), f"pt-certbot must NOT mount /var/run/docker.sock (least privilege per M1): {certbot_svc.get('volumes')}"
    assert certbot_svc.get("privileged") is not True, "pt-certbot must NOT run in privileged mode"
    assert "/etc/letsencrypt" in cb_vols and not cb_vols["/etc/letsencrypt"].get("read_only", False), (
        "pt-certbot must mount /etc/letsencrypt read-write"
    )
    assert "/var/www/certbot" in cb_vols and not cb_vols["/var/www/certbot"].get("read_only", False), (
        "pt-certbot must mount /var/www/certbot read-write"
    )

    mgmt_vols = _targets(services["pt-management"])
    assert "/etc/letsencrypt" in mgmt_vols and not mgmt_vols["/etc/letsencrypt"].get("read_only", False), (
        "pt-management must mount /etc/letsencrypt read-write"
    )
    assert "/var/www/certbot" in mgmt_vols and not mgmt_vols["/var/www/certbot"].get("read_only", False), (
        "pt-management must mount /var/www/certbot read-write"
    )
    assert not any(t.endswith("/server.crt") or t.endswith("/server.key") for t in mgmt_vols), (
        f"pt-management must not use single-file ssl bind mounts: {list(mgmt_vols)}"
    )


def test_t1_shell_syntax_all_scripts() -> None:
    """`bash -n` passes for deploy*.sh, remove-instance.sh, generate-ssl-cert.sh, pt-nginx scripts, and pt-certbot scripts."""
    root = repo_root()
    scripts: List[Path] = [
        root / "deploy.sh",
        root / "deploy-full.sh",
        root / "generate-ssl-cert.sh",
    ]
    if (root / "remove-instance.sh").exists():
        scripts.append(root / "remove-instance.sh")
    scripts.extend(_discover_shell_scripts(root / "ptweb-vnc" / "pt-nginx"))
    scripts.extend(_discover_shell_scripts(root / "ptweb-vnc" / "pt-certbot"))

    failures: List[str] = []
    for script in scripts:
        assert script.exists(), f"Expected script missing: {script}"
        res = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True, timeout=10)
        if res.returncode != 0:
            failures.append(f"{script}: {res.stderr.strip()}")
    assert not failures, "bash -n failed:\n" + "\n".join(failures)


def test_t1_deploy_scripts_no_single_file_ssl_bind_mounts() -> None:
    """`deploy.sh`, `deploy-full.sh`, and `remove-instance.sh` use directory mounts for SSL & Certbot (no single-file ssl bind mounts)."""
    root = repo_root()
    targets = ["deploy.sh", "deploy-full.sh"]
    if (root / "remove-instance.sh").exists():
        targets.append("remove-instance.sh")
    for fname in targets:
        content = (root / fname).read_text(encoding="utf-8")
        assert not re.search(r"(--mount|-v)\s+[^\n]*server\.(crt|key)", content), (
            f"{fname} still contains a single-file bind mount for server.crt/server.key"
        )
    deploy_sh = (root / "deploy.sh").read_text(encoding="utf-8")
    assert "/etc/ssl/ptweb" in deploy_sh, "deploy.sh must mount ./ssl to /etc/ssl/ptweb"
    assert "/etc/letsencrypt" in deploy_sh, "deploy.sh must mount ./certbot/conf to /etc/letsencrypt"
    assert "/var/www/certbot" in deploy_sh, "deploy.sh must mount ./certbot/www to /var/www/certbot"


def test_t1_certbot_service_files_contract() -> None:
    """`ptweb-vnc/pt-certbot/` exists with Dockerfile, renewal loop (`--deploy-hook`), and reload hook."""
    cb_dir = repo_root() / "ptweb-vnc" / "pt-certbot"
    assert cb_dir.is_dir(), f"Missing directory {cb_dir}"
    dockerfile = cb_dir / "Dockerfile"
    assert dockerfile.is_file(), f"Missing {dockerfile}"
    df_text = dockerfile.read_text(encoding="utf-8").lower()
    assert "certbot" in df_text, "pt-certbot/Dockerfile must base on or install certbot"

    all_text = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in cb_dir.rglob("*")
        if p.is_file()
    )
    assert "certbot renew" in all_text, "pt-certbot service must execute `certbot renew`"
    assert "--deploy-hook" in all_text, "pt-certbot renewal loop must pass `--deploy-hook`"


@pytest.mark.docker
@pytest.mark.parametrize("profile", ["self_signed", "certbot_domain", "http_only", "geoip_ratelimit"])
def test_t1_generate_nginx_conf_matrix_and_nginx_test(
    tmp_path: Path, ephemeral_nginx: EphemeralNginxRunner, profile: str
) -> None:
    """generate-nginx-conf.sh produces valid Nginx configs passing `pt-nginx:latest nginx -t` across 4 profiles."""
    ws = temp_stack_ws(tmp_path)

    if profile == "self_signed":
        write_env_file(
            ws / ".env",
            {
                "PRODUCTION_MODE": "false",
                "ENABLE_HTTPS": "true",
                "TLS_MODE": "self-signed",
                "SERVER_NAME": "",
                "SSL_CERT_PATH": "/etc/ssl/ptweb/server.crt",
                "SSL_KEY_PATH": "/etc/ssl/ptweb/server.key",
                "NGINX_GEOIP_ALLOW": "false",
                "NGINX_GEOIP_BLOCK": "false",
                "NGINX_RATE_LIMIT_ENABLE": "false",
            },
        )
    elif profile == "certbot_domain":
        ca_crt, ca_key = generate_test_ca(tmp_path / "ca")
        seed_certbot_live_cert(
            ws / "certbot" / "conf",
            "pt.example.test",
            ca_crt,
            ca_key,
            sans=["pt.example.test", "alt.example.test"],
        )
        write_env_file(
            ws / ".env",
            {
                "PRODUCTION_MODE": "false",
                "ENABLE_HTTPS": "true",
                "TLS_MODE": "certbot",
                "SERVER_NAME": "pt.example.test alt.example.test",
                "CERTBOT_ENABLED": "true",
                "CERTBOT_DOMAIN": "pt.example.test",
                "CERTBOT_EXTRA_DOMAINS": "alt.example.test",
                "SSL_CERT_PATH": "/etc/letsencrypt/live/pt.example.test/fullchain.pem",
                "SSL_KEY_PATH": "/etc/letsencrypt/live/pt.example.test/privkey.pem",
                "NGINX_GEOIP_ALLOW": "false",
                "NGINX_GEOIP_BLOCK": "false",
                "NGINX_RATE_LIMIT_ENABLE": "false",
            },
        )
    elif profile == "http_only":
        write_env_file(
            ws / ".env",
            {
                "PRODUCTION_MODE": "false",
                "ENABLE_HTTPS": "false",
                "TLS_MODE": "self-signed",
                "SERVER_NAME": "localhost",
                "NGINX_GEOIP_ALLOW": "false",
                "NGINX_GEOIP_BLOCK": "false",
                "NGINX_RATE_LIMIT_ENABLE": "false",
            },
        )
    elif profile == "geoip_ratelimit":
        write_env_file(
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
                "NGINX_GEOIP_BLOCK": "true",
                "GEOIP_BLOCK_COUNTRIES": "RU,IR",
                "NGINX_RATE_LIMIT_ENABLE": "true",
                "NGINX_RATE_LIMIT_RATE": "100r/s",
                "NGINX_RATE_LIMIT_BURST": "200",
                "NGINX_RATE_LIMIT_ZONE_SIZE": "10m",
            },
        )

    gen = ephemeral_nginx.run_generate_nginx_conf(ws)
    assert gen.returncode == 0, f"generate-nginx-conf.sh failed for {profile}:\n{gen.stdout}\n{gen.stderr}"

    ptweb_conf = (ws / "ptweb-vnc" / "pt-nginx" / "conf" / "ptweb.conf").read_text(encoding="utf-8")

    # Every profile must carve out ACME challenge location on port 80
    assert "/.well-known/acme-challenge/" in ptweb_conf, f"[{profile}] Missing ACME challenge location in ptweb.conf"
    assert "/var/www/certbot" in ptweb_conf, f"[{profile}] Missing /var/www/certbot webroot in ptweb.conf"

    if profile == "self_signed":
        assert "server_name localhost" in ptweb_conf
        assert "return 301 https://$host$request_uri;" in ptweb_conf
        assert ptweb_conf.count("ssl_certificate ") >= 2
    elif profile == "certbot_domain":
        assert "pt.example.test" in ptweb_conf
        assert "alt.example.test" in ptweb_conf
        assert "/etc/letsencrypt/live/pt.example.test/fullchain.pem" in ptweb_conf
        assert "/etc/letsencrypt/live/pt.example.test/privkey.pem" in ptweb_conf
    elif profile == "http_only":
        assert "return 301 https://" not in ptweb_conf
        assert "proxy_pass http://pt-guacamole:8080/guacamole/" in ptweb_conf
    elif profile == "geoip_ratelimit":
        # Preserve health_check.sh:391,496,501,524 invariants on Guacamole `location /`
        assert_healthcheck_location_root_invariants(
            ptweb_conf,
            expect_allow=True,
            expect_block=True,
            expect_rate_limit=True,
        )

    test_res = ephemeral_nginx.nginx_test(ws, mount_legacy_ssl_files=False)
    assert test_res.returncode == 0, (
        f"ephemeral `nginx -t` failed for {profile}:\nSTDOUT:\n{test_res.stdout}\nSTDERR:\n{test_res.stderr}"
    )


def test_t1_generate_ssl_cert_noninteractive_and_permissions(tmp_path: Path) -> None:
    """`generate-ssl-cert.sh` runs non-interactively without stdin hang, sets 0600 key perms, and matches key/cert."""
    src = repo_root() / "generate-ssl-cert.sh"
    work = tmp_path / "ssl_script_ws"
    work.mkdir(parents=True, exist_ok=True)
    script = work / "generate-ssl-cert.sh"
    shutil.copy2(src, script)
    os.chmod(script, 0o755)

    # First run on fresh workspace (prefer --non-interactive if supported)
    script_text = script.read_text(encoding="utf-8")
    args = ["bash", str(script)]
    if "--non-interactive" in script_text:
        args.append("--non-interactive")

    r1 = subprocess.run(args, cwd=str(work), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15)
    assert r1.returncode == 0, f"Fresh generate-ssl-cert.sh failed:\n{r1.stdout}\n{r1.stderr}"

    crt = work / "ssl" / "server.crt"
    key = work / "ssl" / "server.key"
    assert crt.is_file() and key.is_file()

    key_mode = stat.S_IMODE(key.stat().st_mode)
    assert key_mode == 0o600, f"Expected ssl/server.key permissions 0600, got {oct(key_mode)}"

    # Verify X.509 cert & key modulus match
    crt_mod = subprocess.check_output(["openssl", "x509", "-in", str(crt), "-noout", "-modulus"], text=True).strip()
    key_mod = subprocess.check_output(["openssl", "rsa", "-in", str(key), "-noout", "-modulus"], text=True).strip()
    assert crt_mod == key_mod, "Generated server.crt and server.key moduli do not match"

    # Second run with existing files must not hang waiting for `read`
    r2 = subprocess.run(
        ["bash", str(script), "--non-interactive"] if "--non-interactive" in script_text else ["bash", str(script)],
        cwd=str(work),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert r2.returncode == 0, (
        f"Re-running generate-ssl-cert.sh with existing files failed (must support non-interactive mode):\n{r2.stdout}\n{r2.stderr}"
    )


@pytest.mark.docker
def test_t1_env_config_append_and_inode_preservation(tmp_path: Path) -> None:
    """EnvConfigManager appends missing Certbot keys in-place while preserving file inode and existing comments."""
    ws = temp_stack_ws(tmp_path)
    env_file = ws / ".env"
    env_file.write_text(
        "# Preserved header comment\n"
        "ENABLE_HTTPS=true\n"
        "PRODUCTION_MODE=false\n",
        encoding="utf-8",
    )
    orig_inode = env_file.stat().st_ino
    bridge = MgmtAppBridge(ws)

    updates = {
        "https": {
            "enabled": False,
            "tls_mode": "certbot",
            "server_name": "pt.example.edu",
        },
        "certbot": {
            "enabled": True,
            "domain": "pt.example.edu",
            "extra_domains": "www.pt.example.edu",
            "email": "admin@example.edu",
            "challenge_type": "http-01",
            "staging": True,
            "auto_renew": True,
        },
    }
    res = bridge.unit_call("env_config", "update_config", args=[updates])
    ok, msg = res["return"]
    assert ok is True, f"EnvConfigManager.update_config returned failure: {msg}"
    assert res["env_inode"] == orig_inode, "update_config replaced .env inode (breaks Docker bind mounts)"
    assert "# Preserved header comment" in res["env_raw"]

    parsed = res["env_parsed"]
    assert parsed.get("ENABLE_HTTPS") == "false"
    assert parsed.get("TLS_MODE") == "certbot"
    assert parsed.get("SERVER_NAME") == "pt.example.edu"
    for expected_key in (
        "TLS_MODE",
        "SERVER_NAME",
        "CERTBOT_ENABLED",
        "CERTBOT_DOMAIN",
        "CERTBOT_EXTRA_DOMAINS",
        "CERTBOT_EMAIL",
        "CERTBOT_CHALLENGE_TYPE",
        "CERTBOT_STAGING",
        "CERTBOT_AUTO_RENEW",
    ):
        assert expected_key in parsed, f"EnvConfigManager dropped missing key '{expected_key}' instead of appending"


@pytest.mark.docker
def test_t1_ui_certbot_controls_static_and_rendered(tmp_path: Path) -> None:
    """Admin settings UI exposes Certbot controls, status card, and JS API wiring."""
    root = repo_root()
    html_src = (root / "pt-management" / "templates" / "env_settings.html").read_text(encoding="utf-8")
    js_src = (root / "pt-management" / "static" / "js" / "env-config.js").read_text(encoding="utf-8")

    for api_path in (
        "/api/certbot/status",
        "/api/certbot/config",
        "/api/certbot/issue",
        "/api/certbot/renew",
        "/api/certbot/switch-mode",
    ):
        assert api_path in js_src, f"env-config.js missing Certbot API endpoint call {api_path}"

    assert "certbot" in html_src.lower(), "env_settings.html missing Certbot UI section"

    ws = temp_stack_ws(tmp_path)
    bridge = MgmtAppBridge(ws)

    unauth = bridge.request("GET", "/settings", login=False)
    assert unauth["status_code"] == 302 and "/login" in (unauth.get("location") or "")

    auth = bridge.request("GET", "/settings", login=True)
    assert auth["status_code"] == 200
    body_lower = auth["body"].lower()
    assert any(t in body_lower for t in ("tls_mode", "tls-mode", "tls mode")), (
        "Rendered /settings page missing expected Certbot UI TLS mode indicator ('tls_mode', 'tls-mode', or 'tls mode')"
    )
    for term in ("certbot", "domain", "email", "renew", "issue"):
        assert term in body_lower, f"Rendered /settings page missing expected Certbot UI element '{term}'"


@pytest.mark.docker
def test_t1_auth_enforcement_certbot_and_upload_endpoints(tmp_path: Path) -> None:
    """All /api/certbot/* and /api/upload/* routes reject unauthenticated requests with 401."""
    ws = temp_stack_ws(tmp_path)
    bridge = MgmtAppBridge(ws)

    out = bridge.http_sequence(
        [
            {"method": "GET", "path": "/api/certbot/status"},
            {"method": "POST", "path": "/api/certbot/config", "json": {"domain": "pt.example.edu"}},
            {"method": "POST", "path": "/api/certbot/issue", "json": {"dry_run": True}},
            {"method": "POST", "path": "/api/certbot/renew", "json": {"dry_run": True}},
            {"method": "POST", "path": "/api/certbot/switch-mode", "json": {"tls_mode": "self-signed"}},
            {"method": "GET", "path": "/api/upload/info/crt"},
            {"method": "GET", "path": "/api/upload/info/key"},
            {"method": "GET", "path": "/api/upload/backups"},
            {"method": "POST", "path": "/api/upload/certificate"},
            {"method": "POST", "path": "/api/upload/key"},
            {"method": "POST", "path": "/api/upload/restore", "json": {}},
            {"method": "POST", "path": "/api/upload/backup/delete", "json": {}},
            {"method": "GET", "path": "/api/env/defaults"},
        ],
        login=False,
    )
    resps = out["responses"]
    for idx, resp in enumerate(resps[:-1]):
        assert resp["status_code"] == 401, f"Endpoint index {idx} returned {resp['status_code']} instead of 401"
    assert resps[-1]["status_code"] == 200, "Public /api/env/defaults exemption broke"


@pytest.mark.docker
def test_t1_authenticated_certbot_and_upload_api_contracts(tmp_path: Path) -> None:
    """Authenticated admin can read Certbot status, save config, run dry-run issue/renew, and upload matching SSL."""
    ws = temp_stack_ws(tmp_path)
    bridge = MgmtAppBridge(ws)

    # Valid cert/key pair generated cleanly for upload test (using .pem key extension too)
    up_dir = tmp_path / "upload_pair"
    crt_path = up_dir / "custom.crt"
    key_path = up_dir / "custom.pem"
    generate_self_signed_cert(crt_path, key_path, cn="manual.example.edu")

    r_status = bridge.request("GET", "/api/certbot/status")
    assert r_status["status_code"] == 200, f"GET /api/certbot/status failed: {r_status['status_code']} {r_status['body']}"
    s_json = r_status["json"] or {}
    assert s_json.get("success") is True
    assert s_json.get("tls_mode") == "self-signed"

    r_cfg = bridge.request(
        "POST",
        "/api/certbot/config",
        json_body={
            "domain": "pt.example.edu",
            "extra_domains": "www.pt.example.edu",
            "email": "admin@example.edu",
            "challenge_type": "http-01",
            "staging": True,
            "auto_renew": True,
        },
    )
    assert r_cfg["status_code"] == 200, f"POST /api/certbot/config failed: {r_cfg['status_code']} {r_cfg['body']}"

    bridge.clear_logs()
    r_dry_issue = bridge.request("POST", "/api/certbot/issue", json_body={"dry_run": True})
    assert r_dry_issue["status_code"] == 200, f"Dry-run issue failed: {r_dry_issue['status_code']} {r_dry_issue['body']}"
    assert any("--dry-run" in c for c in bridge.certbot_calls() + bridge.docker_calls()), (
        "Dry-run issue did not invoke certbot with --dry-run"
    )
    assert "TLS_MODE=self-signed" in (ws / ".env").read_text(encoding="utf-8"), (
        "Dry-run issuance must NOT switch TLS_MODE away from self-signed"
    )

    r_dry_renew = bridge.request("POST", "/api/certbot/renew", json_body={"dry_run": True})
    assert r_dry_renew["status_code"] == 200, f"Dry-run renew failed: {r_dry_renew['status_code']} {r_dry_renew['body']}"
    assert any("renew" in c and "--dry-run" in c for c in bridge.certbot_calls() + bridge.docker_calls()), (
        "Dry-run renew did not invoke certbot renew --dry-run"
    )

    # Upload info + matching cert/key upload
    assert bridge.request("GET", "/api/upload/info/crt")["status_code"] == 200
    assert bridge.request("GET", "/api/upload/info/key")["status_code"] == 200
    assert bridge.request("GET", "/api/upload/backups")["status_code"] == 200

    # Upload matching pair sequentially (cert first, then .pem key) per M1 staged-pair contract
    bridge.clear_logs()
    r_up_crt = bridge.request(
        "POST",
        "/api/upload/certificate",
        files={"file": ("custom.crt", crt_path.read_bytes())},
    )
    assert r_up_crt["status_code"] == 200 and (r_up_crt.get("json") or {}).get("success") is True, (
        f"Cert upload failed: {r_up_crt['status_code']} {r_up_crt['body']}"
    )
    assert not any("nginx -s reload" in c for c in bridge.docker_calls()), (
        f"Unpaired half upload must not reload Nginx prematurely: {bridge.docker_calls()}"
    )

    r_up_key = bridge.request(
        "POST",
        "/api/upload/key",
        files={"file": ("custom.pem", key_path.read_bytes())},
    )
    assert r_up_key["status_code"] == 200 and (r_up_key.get("json") or {}).get("success") is True, (
        f"Matching .pem key upload failed: {r_up_key['status_code']} {r_up_key['body']}"
    )

    active_crt = ws / "ssl" / "server.crt"
    active_key = ws / "ssl" / "server.key"
    assert active_crt.is_file() and active_key.is_file(), "Active ssl/server.{crt,key} missing after matched upload"
    assert stat.S_IMODE(active_key.stat().st_mode) == 0o600, (
        f"Expected uploaded ssl/server.key mode 0600, got {oct(stat.S_IMODE(active_key.stat().st_mode))}"
    )
    assert x509_metadata(active_crt)["fingerprint"] == x509_metadata(crt_path)["fingerprint"], (
        "Active ssl/server.crt does not match uploaded custom.crt"
    )
    crt_pub = subprocess.check_output(["openssl", "x509", "-in", str(active_crt), "-pubkey", "-noout"], text=True).strip()
    key_pub = subprocess.check_output(["openssl", "pkey", "-in", str(active_key), "-pubout", "-passin", "pass:"], text=True).strip()
    assert crt_pub == key_pub, "Promoted ssl/server.crt and ssl/server.key public keys do not match"

    env_after_up = read_env_file(ws / ".env")
    assert env_after_up.get("TLS_MODE") == "manual", f"Expected TLS_MODE=manual after upload, got {env_after_up.get('TLS_MODE')!r}"

    up_calls = "\n".join(bridge.docker_calls())
    assert "nginx -t" in up_calls, f"Expected nginx -t after matched upload, got:\n{up_calls}"
    assert "nginx -s reload" in up_calls, f"Expected nginx -s reload after matched upload, got:\n{up_calls}"
