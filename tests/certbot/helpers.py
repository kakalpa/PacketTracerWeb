"""
Shared opaque-box helpers for the PacketTracerWeb Certbot TLS E2E test suite.

Provides:
- `repo_root()` and `temp_stack_ws(tmp_path)` workspace isolation
- OpenSSL / cryptography certificate & CA generators (self-signed, CA-signed,
  renewal rotation, mismatched cert/key, malformed PEM, encrypted key)
- `free_tcp_port()` dynamic port allocation on 127.0.0.1
- `EphemeralNginxRunner` for isolated `nginx -t` and ephemeral HTTP/HTTPS/GeoIP
  container execution without touching live ports 80/443/5000
- `MgmtAppBridge` with mock `docker`/`certbot` shims for opaque-box testing of
  `pt-management` endpoints and managers inside `pt-management:latest` (or
  in-process when `flask` is importable)
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import socket
import ssl
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

PRIVATE_KEY_MARKERS = (
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN EC PRIVATE KEY-----",
    "-----BEGIN ENCRYPTED PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
)


def repo_root() -> Path:
    """Return absolute path to the PacketTracerWeb repository root."""
    return Path(__file__).resolve().parents[2]


def write_env_file(env_path: Path, values: Dict[str, str], comments: Optional[List[str]] = None) -> None:
    """Write a bash-source-safe `.env` file."""
    lines: List[str] = []
    if comments:
        for c in comments:
            lines.append(c if c.startswith("#") else f"# {c}")
    for key, val in values.items():
        sval = str(val)
        if any(ch in sval for ch in (" ", "\t")) and not (
            (sval.startswith('"') and sval.endswith('"'))
            or (sval.startswith("'") and sval.endswith("'"))
        ):
            lines.append(f'{key}="{sval}"')
        else:
            lines.append(f"{key}={sval}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_env_file(env_path: Path) -> Dict[str, str]:
    """Parse `.env` key=value lines (stripping optional surrounding quotes)."""
    parsed: Dict[str, str] = {}
    if not env_path.exists():
        return parsed
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and ((v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'")):
            v = v[1:-1]
        parsed[k] = v
    return parsed


def update_env_values(env_path: Path, updates: Dict[str, str]) -> None:
    """Update existing keys or append missing keys in-place, preserving inode."""
    current = read_env_file(env_path)
    current.update({k: str(v) for k, v in updates.items()})
    lines = []
    for key, val in current.items():
        if any(ch in val for ch in (" ", "\t")):
            lines.append(f'{key}="{val}"')
        else:
            lines.append(f"{key}={val}")
    with open(env_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def extract_location_root_blocks(conf_text: str) -> List[Dict[str, Any]]:
    """
    Find every `location / { ... }` block in ptweb.conf using brace-depth tracking
    (never truncating at inner `if (...) { ... }` blocks) and capture the exact
    `health_check.sh` grep line windows (`lines[i:i+6]` and `lines[i:i+31]`).
    """
    lines = conf_text.splitlines()
    blocks: List[Dict[str, Any]] = []
    for idx, line in enumerate(lines):
        if re.match(r"^\s*location\s+/\s*\{", line):
            depth = 0
            block_lines: List[str] = []
            for j in range(idx, len(lines)):
                cur = lines[j]
                block_lines.append(cur)
                code_only = re.sub(r"(^|\s)#.*$", "", cur)
                depth += code_only.count("{") - code_only.count("}")
                if depth <= 0:
                    break
            blocks.append(
                {
                    "start_line": idx + 1,
                    "block_text": "\n".join(block_lines),
                    "win_5": "\n".join(lines[idx : idx + 6]),
                    "win_30": "\n".join(lines[idx : idx + 31]),
                }
            )
    return blocks


def assert_healthcheck_location_root_invariants(
    conf_text: str,
    *,
    expect_allow: bool = True,
    expect_block: bool = True,
    expect_rate_limit: bool = True,
) -> None:
    """
    Verify at least one `location / { ... }` block (specifically the Guacamole
    `proxy_pass` block) preserves `health_check.sh:391,496,501,524` invariants
    without truncating on inner `if` braces or matching port 80's redirect block.
    """
    blocks = extract_location_root_blocks(conf_text)
    assert blocks, "Missing `location / {` block in ptweb.conf"

    guac_blocks = [
        b for b in blocks if "proxy_pass http://pt-guacamole:8080/guacamole/;" in b["block_text"]
    ]
    assert len(guac_blocks) == 1, (
        f"Expected exactly 1 Guacamole `location /` block in ptweb.conf, found {len(guac_blocks)} "
        f"(all `location /` blocks at lines {[b['start_line'] for b in blocks]})"
    )
    gb = guac_blocks[0]

    def _strip_comments(text: str) -> str:
        return "\n".join(re.sub(r"(^|\s)#.*$", "", ln) for ln in text.splitlines())

    code_block = _strip_comments(gb["block_text"])
    code_win_5 = _strip_comments(gb["win_5"])
    code_win_30 = _strip_comments(gb["win_30"])

    if expect_allow:
        assert "$allowed_country" in code_win_5, (
            f"health_check.sh:496 requires $allowed_country within first 5 lines of `location /` "
            f"(line {gb['start_line']})"
        )
        assert "if ($allowed_country = 0) { return 444; }" in code_block, (
            f"Guacamole `location /` (line {gb['start_line']}) missing ALLOW enforcement `return 444`"
        )
    if expect_block:
        assert "$blocked_country" in code_win_5, (
            f"health_check.sh:501 requires $blocked_country within first 5 lines of `location /` "
            f"(line {gb['start_line']})"
        )
        assert "if ($blocked_country = 1) { return 444; }" in code_block, (
            f"Guacamole `location /` (line {gb['start_line']}) missing BLOCK enforcement `return 444`"
        )
    if expect_rate_limit:
        assert "limit_req zone=pt_req_zone" in code_win_30, (
            f"health_check.sh:391 requires `limit_req zone=pt_req_zone` within 30 lines of `location /` "
            f"(line {gb['start_line']})"
        )
        assert "limit_req zone=pt_req_zone" in code_block, (
            f"Guacamole `location /` (line {gb['start_line']}) missing `limit_req zone=pt_req_zone`"
        )


def cert_sha256_fingerprint(cert_input: bytes | str | Path) -> str:
    """Return colon-separated uppercase SHA-256 fingerprint matching `openssl x509 -fingerprint -sha256`."""
    if isinstance(cert_input, Path):
        raw = cert_input.read_bytes()
    elif isinstance(cert_input, str):
        raw = cert_input.encode("utf-8")
    else:
        raw = cert_input

    if b"-----BEGIN CERTIFICATE-----" in raw:
        cert = x509.load_pem_x509_certificate(raw)
    else:
        cert = x509.load_der_x509_certificate(raw)
    digest = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest().upper()
    return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2))


def x509_metadata(cert_input: bytes | str | Path) -> Dict[str, Any]:
    """Extract X.509 subject, CN, SANs, issuer, validity dates, serial, and SHA-256 fingerprint."""
    if isinstance(cert_input, Path):
        raw = cert_input.read_bytes()
    elif isinstance(cert_input, str):
        raw = cert_input.encode("utf-8")
    else:
        raw = cert_input

    if b"-----BEGIN CERTIFICATE-----" in raw:
        cert = x509.load_pem_x509_certificate(raw)
    else:
        cert = x509.load_der_x509_certificate(raw)

    cn_attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    cn = cn_attrs[0].value if cn_attrs else ""
    issuer_cn_attrs = cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)
    issuer_cn = issuer_cn_attrs[0].value if issuer_cn_attrs else ""
    sans: List[str] = []
    try:
        san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        sans.extend([str(d) for d in san_ext.get_values_for_type(x509.DNSName)])
        sans.extend([str(ip) for ip in san_ext.get_values_for_type(x509.IPAddress)])
    except x509.ExtensionNotFound:
        pass

    digest = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest().upper()
    fp = ":".join(digest[i : i + 2] for i in range(0, len(digest), 2))
    return {
        "cn": cn,
        "subject": cert.subject.rfc4514_string(),
        "issuer_cn": issuer_cn,
        "issuer": cert.issuer.rfc4514_string(),
        "sans": sans,
        "serial": cert.serial_number,
        "not_before": cert.not_valid_before_utc.isoformat(),
        "not_after": cert.not_valid_after_utc.isoformat(),
        "fingerprint": fp,
    }


def _gen_rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _san_extension(names: List[str]) -> x509.SubjectAlternativeName:
    import ipaddress

    entries: List[x509.GeneralName] = []
    for name in names:
        try:
            ip_obj = ipaddress.ip_address(name)
            entries.append(x509.IPAddress(ip_obj))
        except ValueError:
            entries.append(x509.DNSName(name))
    return x509.SubjectAlternativeName(entries)


def generate_self_signed_cert(
    cert_path: Path,
    key_path: Path,
    cn: str = "localhost",
    sans: Optional[List[str]] = None,
    days: int = 365,
    serial: Optional[int] = None,
) -> Dict[str, Any]:
    """Generate a self-signed RSA-2048 X.509 certificate and 0600 private key."""
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.parent.mkdir(parents=True, exist_ok=True)

    key = _gen_rsa_key()
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, cn),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PacketTracerWeb Test"),
        ]
    )
    now = dt.datetime.now(dt.timezone.utc)
    san_list = sans if sans is not None else ([cn, "127.0.0.1"] if cn == "localhost" else [cn])
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(serial if serial is not None else x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=days))
        .add_extension(_san_extension(san_list), critical=False)
    )
    cert = builder.sign(key, hashes.SHA256())

    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)

    key_path.write_bytes(key_pem)
    os.chmod(key_path, 0o600)
    cert_path.write_bytes(cert_pem)
    os.chmod(cert_path, 0o644)

    meta = x509_metadata(cert_pem)
    meta["cert_path"] = cert_path
    meta["key_path"] = key_path
    return meta


def generate_test_ca(ca_dir: Path, cn: str = "PacketTracerWeb Test Root CA") -> Tuple[Path, Path]:
    """Generate a test Root CA cert + private key (0600)."""
    ca_dir.mkdir(parents=True, exist_ok=True)
    ca_cert_path = ca_dir / "ca.crt"
    ca_key_path = ca_dir / "ca.key"

    key = _gen_rsa_key()
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, cn),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PacketTracerWeb Test CA"),
        ]
    )
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    ca_key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    os.chmod(ca_key_path, 0o600)
    ca_cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    os.chmod(ca_cert_path, 0o644)
    return ca_cert_path, ca_key_path


def issue_ca_signed_cert(
    ca_cert_path: Path,
    ca_key_path: Path,
    out_cert_path: Path,
    out_key_path: Path,
    cn: str,
    sans: Optional[List[str]] = None,
    days: int = 90,
    serial: Optional[int] = None,
    chain_out_path: Optional[Path] = None,
    fullchain_out_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Issue a leaf certificate signed by the provided Test CA."""
    out_cert_path.parent.mkdir(parents=True, exist_ok=True)
    out_key_path.parent.mkdir(parents=True, exist_ok=True)

    ca_cert = x509.load_pem_x509_certificate(ca_cert_path.read_bytes())
    ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)

    leaf_key = _gen_rsa_key()
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = dt.datetime.now(dt.timezone.utc)
    san_list = sans if sans is not None else [cn]
    leaf_cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(leaf_key.public_key())
        .serial_number(serial if serial is not None else x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(_san_extension(san_list), critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    leaf_key_pem = leaf_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    leaf_cert_pem = leaf_cert.public_bytes(serialization.Encoding.PEM)
    ca_cert_pem = ca_cert_path.read_bytes()

    out_key_path.write_bytes(leaf_key_pem)
    os.chmod(out_key_path, 0o600)
    out_cert_path.write_bytes(leaf_cert_pem)
    os.chmod(out_cert_path, 0o644)

    if chain_out_path is not None:
        chain_out_path.parent.mkdir(parents=True, exist_ok=True)
        chain_out_path.write_bytes(ca_cert_pem)
        os.chmod(chain_out_path, 0o644)
    if fullchain_out_path is not None:
        fullchain_out_path.parent.mkdir(parents=True, exist_ok=True)
        fullchain_out_path.write_bytes(leaf_cert_pem + ca_cert_pem)
        os.chmod(fullchain_out_path, 0o644)

    meta = x509_metadata(leaf_cert_pem)
    meta["cert_path"] = out_cert_path
    meta["key_path"] = out_key_path
    meta["fullchain_path"] = fullchain_out_path or out_cert_path
    return meta


def atomic_symlink(target: str, link_path: Path) -> None:
    """Atomically replace a symlink via tmp symlink + os.replace (mv -Tf semantics)."""
    tmp_link = link_path.parent / f".{link_path.name}.tmp.{uuid.uuid4().hex[:8]}"
    if tmp_link.exists() or tmp_link.is_symlink():
        tmp_link.unlink()
    os.symlink(target, tmp_link)
    os.replace(tmp_link, link_path)


def seed_certbot_live_cert(
    certbot_conf_dir: Path,
    domain: str,
    ca_cert_path: Path,
    ca_key_path: Path,
    sans: Optional[List[str]] = None,
    version: int = 1,
    days: int = 90,
    serial: Optional[int] = None,
) -> Dict[str, Any]:
    """Populate `/etc/letsencrypt/{archive,live,renewal}/<domain>/` with atomic symlinks."""
    archive_dir = certbot_conf_dir / "archive" / domain
    live_dir = certbot_conf_dir / "live" / domain
    renewal_dir = certbot_conf_dir / "renewal"
    archive_dir.mkdir(parents=True, exist_ok=True)
    live_dir.mkdir(parents=True, exist_ok=True)
    renewal_dir.mkdir(parents=True, exist_ok=True)

    cert_file = archive_dir / f"cert{version}.pem"
    chain_file = archive_dir / f"chain{version}.pem"
    fullchain_file = archive_dir / f"fullchain{version}.pem"
    privkey_file = archive_dir / f"privkey{version}.pem"

    meta = issue_ca_signed_cert(
        ca_cert_path=ca_cert_path,
        ca_key_path=ca_key_path,
        out_cert_path=cert_file,
        out_key_path=privkey_file,
        cn=domain,
        sans=sans or [domain],
        days=days,
        serial=serial,
        chain_out_path=chain_file,
        fullchain_out_path=fullchain_file,
    )

    for base_name in ("cert", "chain", "fullchain", "privkey"):
        atomic_symlink(f"../../archive/{domain}/{base_name}{version}.pem", live_dir / f"{base_name}.pem")

    renewal_conf = renewal_dir / f"{domain}.conf"
    renewal_conf.write_text(
        f"# renew_before_expiry = 30 days\n"
        f"archive_dir = /etc/letsencrypt/archive/{domain}\n"
        f"cert = /etc/letsencrypt/live/{domain}/cert.pem\n"
        f"privkey = /etc/letsencrypt/live/{domain}/privkey.pem\n"
        f"chain = /etc/letsencrypt/live/{domain}/chain.pem\n"
        f"fullchain = /etc/letsencrypt/live/{domain}/fullchain.pem\n",
        encoding="utf-8",
    )

    meta["live_fullchain"] = live_dir / "fullchain.pem"
    meta["live_privkey"] = live_dir / "privkey.pem"
    return meta


def generate_mismatched_pair(out_dir: Path) -> Tuple[Path, Path, Path, Path]:
    """Create two independent cert/key pairs (A and B) so (certA, keyB) is mismatched."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ca_cert_a = out_dir / "certA.crt"
    ca_key_a = out_dir / "keyA.key"
    ca_cert_b = out_dir / "certB.crt"
    ca_key_b = out_dir / "keyB.key"
    generate_self_signed_cert(ca_cert_a, ca_key_a, cn="pair-a.example.test", serial=1001)
    generate_self_signed_cert(ca_cert_b, ca_key_b, cn="pair-b.example.test", serial=1002)
    return ca_cert_a, ca_key_a, ca_cert_b, ca_key_b


def generate_encrypted_key_pem(passphrase: bytes = b"test-passphrase") -> bytes:
    """Return an encrypted PKCS#8 private key PEM."""
    key = _gen_rsa_key()
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(passphrase),
    )


def generate_malformed_pem() -> bytes:
    """Return PEM headers enclosing invalid base64 payload."""
    return b"-----BEGIN CERTIFICATE-----\nNOT_VALID_BASE64_PAYLOAD_!!!\n-----END CERTIFICATE-----\n"


def free_tcp_port() -> int:
    """Allocate an ephemeral unused TCP port on 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def temp_stack_ws(tmp_path: Path, env_overrides: Optional[Dict[str, str]] = None) -> Path:
    """
    Create an isolated temporary stack workspace mirroring repo config/scripts
    without touching the real repository or live container volumes.
    """
    root = repo_root()
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)

    (ws / "ssl").mkdir(parents=True, exist_ok=True)
    (ws / "certbot" / "conf").mkdir(parents=True, exist_ok=True)
    (ws / "certbot" / "www").mkdir(parents=True, exist_ok=True)
    (ws / "geoip").mkdir(parents=True, exist_ok=True)
    (ws / "shared" / "instances").mkdir(parents=True, exist_ok=True)
    (ws / "shared" / "common").mkdir(parents=True, exist_ok=True)

    # Copy pt-nginx directory excluding historical *.bak.* files
    src_nginx = root / "ptweb-vnc" / "pt-nginx"
    dst_nginx = ws / "ptweb-vnc" / "pt-nginx"
    shutil.copytree(
        src_nginx,
        dst_nginx,
        ignore=shutil.ignore_patterns("*.bak.*", "__pycache__"),
    )
    (dst_nginx / "conf").mkdir(parents=True, exist_ok=True)

    # Copy generate-ssl-cert.sh if present
    gen_ssl_src = root / "generate-ssl-cert.sh"
    if gen_ssl_src.exists():
        shutil.copy2(gen_ssl_src, ws / "generate-ssl-cert.sh")
        os.chmod(ws / "generate-ssl-cert.sh", 0o755)

    # Copy GeoIP.dat if present on host
    geoip_src = root / "geoip" / "GeoIP.dat"
    if geoip_src.exists():
        shutil.copy2(geoip_src, ws / "geoip" / "GeoIP.dat")

    # Seed baseline offline-deterministic .env
    env_vals: Dict[str, str] = {
        "PRODUCTION_MODE": "false",
        "PUBLIC_IP": "203.0.113.10",
        "ENABLE_HTTPS": "true",
        "TLS_MODE": "self-signed",
        "SERVER_NAME": "localhost",
        "SSL_CERT_PATH": "/etc/ssl/ptweb/server.crt",
        "SSL_KEY_PATH": "/etc/ssl/ptweb/server.key",
        "NGINX_GEOIP_ALLOW": "false",
        "GEOIP_ALLOW_COUNTRIES": "FI,US",
        "NGINX_GEOIP_BLOCK": "false",
        "GEOIP_BLOCK_COUNTRIES": "RU,IR",
        "NGINX_RATE_LIMIT_ENABLE": "false",
        "NGINX_RATE_LIMIT_RATE": "100r/s",
        "NGINX_RATE_LIMIT_BURST": "200",
        "NGINX_RATE_LIMIT_ZONE_SIZE": "10m",
        "CERTBOT_ENABLED": "false",
        "CERTBOT_DOMAIN": "",
        "CERTBOT_EXTRA_DOMAINS": "",
        "CERTBOT_EMAIL": "",
        "CERTBOT_CHALLENGE_TYPE": "http-01",
        "CERTBOT_STAGING": "false",
        "CERTBOT_AUTO_RENEW": "true",
        "CERTBOT_WEBROOT": "/var/www/certbot",
    }
    if env_overrides:
        env_vals.update({k: str(v) for k, v in env_overrides.items()})
    write_env_file(ws / ".env", env_vals, comments=["Isolated Certbot E2E test .env"])

    # Seed valid initial self-signed cert/key (0600 key)
    generate_self_signed_cert(ws / "ssl" / "server.crt", ws / "ssl" / "server.key", cn="localhost")
    return ws


class EphemeralNginxRunner:
    """Manages ephemeral `pt-nginx:latest` containers and isolated stub networks."""

    def __init__(self, image: str = "pt-nginx:latest") -> None:
        self.image = image
        self.containers: List[str] = []
        self.networks: List[str] = []

    def run_generate_nginx_conf(self, ws: Path, timeout: int = 20) -> subprocess.CompletedProcess[str]:
        script = ws / "ptweb-vnc" / "pt-nginx" / "generate-nginx-conf.sh"
        return subprocess.run(
            ["bash", str(script)],
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def nginx_test(
        self,
        ws: Path,
        mount_legacy_ssl_files: bool = True,
        extra_mounts: Optional[List[str]] = None,
        add_hosts: bool = True,
        timeout: int = 20,
    ) -> subprocess.CompletedProcess[str]:
        """Run `docker run --rm ... pt-nginx:latest nginx -t` against workspace configs."""
        cmd: List[str] = ["docker", "run", "--rm"]
        if add_hosts:
            cmd += ["--add-host", "pt-management:127.0.0.1", "--add-host", "pt-guacamole:127.0.0.1"]

        nginx_conf = ws / "ptweb-vnc" / "pt-nginx" / "nginx.conf"
        conf_dir = ws / "ptweb-vnc" / "pt-nginx" / "conf"
        cmd += [
            "-v",
            f"{nginx_conf}:/etc/nginx/nginx.conf:ro",
            "-v",
            f"{conf_dir}:/etc/nginx/conf.d:ro",
            "-v",
            f"{ws / 'ssl'}:/etc/ssl/ptweb:ro",
            "-v",
            f"{ws / 'certbot' / 'conf'}:/etc/letsencrypt:ro",
            "-v",
            f"{ws / 'certbot' / 'www'}:/var/www/certbot:ro",
        ]
        if mount_legacy_ssl_files and (ws / "ssl" / "server.crt").exists() and (ws / "ssl" / "server.key").exists():
            cmd += [
                "-v",
                f"{ws / 'ssl' / 'server.crt'}:/etc/ssl/certs/server.crt:ro",
                "-v",
                f"{ws / 'ssl' / 'server.key'}:/etc/ssl/private/server.key:ro",
            ]
        geoip = ws / "geoip" / "GeoIP.dat"
        if geoip.exists():
            cmd += ["-v", f"{geoip}:/usr/share/GeoIP/GeoIP.dat:ro"]
        if extra_mounts:
            for m in extra_mounts:
                cmd += ["-v", m]
        cmd += [self.image, "nginx", "-t"]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def create_isolated_bridge_with_stubs(self) -> Tuple[str, str, str]:
        """Create a private Docker bridge network with lightweight `pt-guacamole` and `pt-management` stubs."""
        net_name = f"pt-certbot-e2e-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        res = subprocess.run(["docker", "network", "create", net_name], capture_output=True, text=True, timeout=15)
        if res.returncode != 0:
            raise RuntimeError(f"Failed to create isolated Docker network {net_name}: {res.stderr}")
        self.networks.append(net_name)

        guac_name = f"{net_name}-guac"
        mgmt_name = f"{net_name}-mgmt"
        stub_script = (
            "import http.server, socketserver, sys\n"
            "port = int(sys.argv[1])\n"
            "body = sys.argv[2].encode()\n"
            "class H(http.server.BaseHTTPRequestHandler):\n"
            "  def do_GET(self):\n"
            "    self.send_response(200)\n"
            "    self.send_header('Content-Type', 'text/plain')\n"
            "    self.end_headers()\n"
            "    self.wfile.write(body)\n"
            "  def log_message(self, *a): pass\n"
            "socketserver.TCPServer.allow_reuse_address = True\n"
            "socketserver.TCPServer(('0.0.0.0', port), H).serve_forever()\n"
        )

        for cname, alias, port, marker in (
            (guac_name, "pt-guacamole", 8080, "GUAC_STUB_OK"),
            (mgmt_name, "pt-management", 5000, "MGMT_STUB_OK"),
        ):
            self.containers.append(cname)
            r = subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    cname,
                    "--network",
                    net_name,
                    "--network-alias",
                    alias,
                    "--entrypoint",
                    "python3",
                    "pt-management:latest",
                    "-c",
                    stub_script,
                    str(port),
                    marker,
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if r.returncode != 0:
                raise RuntimeError(f"Failed to start stub {alias}: {r.stderr}")

        return net_name, guac_name, mgmt_name

    def start_server(
        self,
        ws: Path,
        enable_realip_header: bool = False,
        with_stub_upstreams: bool = False,
        mount_legacy_ssl_files: bool = True,
        env_vars: Optional[Dict[str, str]] = None,
        extra_mounts: Optional[List[str]] = None,
        wait_ports: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Start an ephemeral `pt-nginx:latest` container bound to dynamic 127.0.0.1 ports."""
        net_name: Optional[str] = None
        if with_stub_upstreams:
            net_name, _, _ = self.create_isolated_bridge_with_stubs()

        nginx_conf = ws / "ptweb-vnc" / "pt-nginx" / "nginx.conf"
        conf_dir = ws / "ptweb-vnc" / "pt-nginx" / "conf"
        if enable_realip_header:
            realip_conf = conf_dir / "00-test-realip.conf"
            realip_conf.write_text(
                "set_real_ip_from 127.0.0.1;\n"
                "set_real_ip_from 172.16.0.0/12;\n"
                "set_real_ip_from 10.0.0.0/8;\n"
                "set_real_ip_from 192.168.0.0/16;\n"
                "real_ip_header X-Test-IP;\n",
                encoding="utf-8",
            )

        p80 = p443 = p5000 = 0
        cname = ""
        last_err = ""
        for attempt in range(3):
            p80 = free_tcp_port()
            p443 = free_tcp_port()
            p5000 = free_tcp_port()
            while p443 == p80:
                p443 = free_tcp_port()
            while p5000 in (p80, p443):
                p5000 = free_tcp_port()
            cname = f"pt-certbot-nginx-e2e-{os.getpid()}-{uuid.uuid4().hex[:6]}"

            cmd: List[str] = [
                "docker",
                "run",
                "-d",
                "--name",
                cname,
                "-p",
                f"127.0.0.1:{p80}:80",
                "-p",
                f"127.0.0.1:{p443}:443",
                "-p",
                f"127.0.0.1:{p5000}:5000",
            ]
            if net_name:
                cmd += ["--network", net_name]
            else:
                cmd += ["--add-host", "pt-management:127.0.0.1", "--add-host", "pt-guacamole:127.0.0.1"]

            cmd += [
                "-v",
                f"{nginx_conf}:/etc/nginx/nginx.conf:ro",
                "-v",
                f"{conf_dir}:/etc/nginx/conf.d:ro",
                "-v",
                f"{ws / 'ssl'}:/etc/ssl/ptweb:ro",
                "-v",
                f"{ws / 'certbot' / 'conf'}:/etc/letsencrypt:ro",
                "-v",
                f"{ws / 'certbot' / 'www'}:/var/www/certbot:ro",
            ]
            if mount_legacy_ssl_files and (ws / "ssl" / "server.crt").exists() and (ws / "ssl" / "server.key").exists():
                cmd += [
                    "-v",
                    f"{ws / 'ssl' / 'server.crt'}:/etc/ssl/certs/server.crt:ro",
                    "-v",
                    f"{ws / 'ssl' / 'server.key'}:/etc/ssl/private/server.key:ro",
                ]
            geoip = ws / "geoip" / "GeoIP.dat"
            if geoip.exists():
                cmd += ["-v", f"{geoip}:/usr/share/GeoIP/GeoIP.dat:ro"]

            if extra_mounts:
                for m in extra_mounts:
                    cmd += ["-v", m]

            if env_vars:
                for k, v in env_vars.items():
                    cmd += ["-e", f"{k}={v}"]

            cmd.append(self.image)

            res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if res.returncode == 0:
                self.containers.append(cname)
                break
            last_err = res.stderr
            subprocess.run(["docker", "rm", "-f", cname], capture_output=True, text=True, timeout=10)
            if attempt < 2 and (
                "port is already allocated" in last_err or "address already in use" in last_err
            ):
                time.sleep(0.1)
                continue
            raise RuntimeError(f"Failed to start ephemeral nginx container: {last_err}")

        port_map = {80: p80, 443: p443, 5000: p5000}
        raw_ports = wait_ports if wait_ports is not None else [80]
        target_ports = [port_map.get(tp, tp) for tp in raw_ports]
        container_listen_ports = [tp for tp in raw_ports if tp in port_map]
        deadline = time.monotonic() + 12.0
        ready = False
        while time.monotonic() < deadline:
            # Verify container hasn't exited
            st = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", cname],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if st.stdout.strip() != "true":
                logs = subprocess.run(["docker", "logs", cname], capture_output=True, text=True, timeout=5)
                raise RuntimeError(f"Ephemeral nginx exited prematurely.\nSTDOUT:\n{logs.stdout}\nSTDERR:\n{logs.stderr}")
            all_open = True
            if container_listen_ports:
                tcp_proc = subprocess.run(
                    ["docker", "exec", cname, "sh", "-c", "cat /proc/net/tcp /proc/net/tcp6 2>/dev/null"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if tcp_proc.returncode != 0:
                    all_open = False
                else:
                    listening_hex = set()
                    for line in tcp_proc.stdout.splitlines():
                        parts = line.split()
                        if len(parts) >= 4 and parts[3] == "0A" and ":" in parts[1]:
                            listening_hex.add(parts[1].rsplit(":", 1)[1].upper())
                    for cp in container_listen_ports:
                        if f"{cp:04X}" not in listening_hex:
                            all_open = False
                            break
            if all_open:
                for tp in target_ports:
                    try:
                        with socket.create_connection(("127.0.0.1", tp), timeout=0.4):
                            pass
                    except OSError:
                        all_open = False
                        break
            if all_open:
                ready = True
                break
            time.sleep(0.15)

        if not ready:
            logs = subprocess.run(["docker", "logs", cname], capture_output=True, text=True, timeout=5)
            raise RuntimeError(
                f"Timed out waiting for ephemeral nginx ports {target_ports}.\nLogs:\n{logs.stdout}\n{logs.stderr}"
            )

        return {
            "container": cname,
            "network": net_name,
            "p80": p80,
            "p443": p443,
            "p5000": p5000,
        }

    def exec_in(self, container: str, cmd: List[str], timeout: int = 15) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", "exec", container, *cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def inspect_container(self, container: str) -> Dict[str, Any]:
        res = subprocess.run(["docker", "inspect", container], capture_output=True, text=True, timeout=10)
        if res.returncode != 0:
            raise RuntimeError(f"docker inspect {container} failed: {res.stderr}")
        data = json.loads(res.stdout)
        return data[0]

    def get_tls_cert_info(self, host: str, port: int, servername: str = "localhost", timeout: float = 5.0) -> Dict[str, Any]:
        """Connect over TLS and extract active peer X.509 certificate metadata."""
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection((host, port), timeout=timeout) as raw_sock:
            with ctx.wrap_socket(raw_sock, server_hostname=servername) as tls_sock:
                der = tls_sock.getpeercert(binary_form=True)
        if not der:
            raise RuntimeError(f"No peer certificate received from {host}:{port} (SNI={servername})")
        return x509_metadata(der)

    def cleanup_all(self) -> None:
        for cname in reversed(self.containers):
            try:
                subprocess.run(["docker", "rm", "-f", cname], capture_output=True, text=True, timeout=15)
            except Exception:
                pass
        self.containers.clear()
        for net in reversed(self.networks):
            try:
                subprocess.run(["docker", "network", "rm", net], capture_output=True, text=True, timeout=15)
            except Exception:
                pass
        self.networks.clear()


_MOCK_DOCKER_SHIM = r'''#!/usr/bin/env bash
set -euo pipefail

WS_ROOT="${PROJECT_ROOT:-/test_ws}"
LOG_FILE="$WS_ROOT/docker_calls.log"
echo "docker $*" >> "$LOG_FILE"

if [ "${1:-}" = "exec" ]; then
    shift
    # Skip docker exec options (both boolean and value-taking flags)
    while [ $# -gt 0 ]; do
        case "$1" in
            --)
                shift
                break
                ;;
            -u|--user|-e|--env|--env-file|-w|--workdir|--detach-keys)
                shift
                if [ $# -gt 0 ]; then
                    shift
                fi
                ;;
            -u=*|--user=*|-e=*|--env=*|--env-file=*|-w=*|--workdir=*|--detach-keys=*)
                shift
                ;;
            -*)
                shift
                ;;
            *)
                break
                ;;
        esac
    done
    TARGET_CONTAINER="${1:-}"
    shift || true

    if [ "$TARGET_CONTAINER" = "pt-nginx1" ] || [[ "$TARGET_CONTAINER" == *nginx* ]]; then
        if [ "${1:-}" = "nginx" ] && [ "${2:-}" = "-t" ]; then
            if [ -f "$WS_ROOT/MOCK_NGINX_TEST_FAIL" ] || [ "${MOCK_NGINX_TEST_FAIL:-0}" = "1" ]; then
                echo "nginx: [emerg] simulated nginx -t failure" >&2
                exit 1
            fi
            echo "nginx: the configuration file /etc/nginx/nginx.conf syntax is ok"
            echo "nginx: configuration file /etc/nginx/nginx.conf test is successful"
            exit 0
        elif [ "${1:-}" = "nginx" ] && [ "${2:-}" = "-s" ] && [ "${3:-}" = "reload" ]; then
            if [ -f "$WS_ROOT/MOCK_NGINX_RELOAD_FAIL" ]; then
                echo "nginx: simulated reload failure" >&2
                exit 1
            fi
            echo "signal process started"
            exit 0
        fi
    fi

    # Unwrap optional `flock [opts] <lockfile>` wrapper (per M1 spec)
    if [ "${1:-}" = "flock" ] || [ "${1##*/}" = "flock" ]; then
        FLOCK_CONFLICT_EXIT=1
        shift
        while [ $# -gt 0 ]; do
            case "$1" in
                --)
                    shift
                    break
                    ;;
                -E|--conflict-exit-code)
                    FLOCK_CONFLICT_EXIT="${2:-1}"
                    shift
                    [ $# -gt 0 ] && shift
                    ;;
                -E=*|--conflict-exit-code=*)
                    FLOCK_CONFLICT_EXIT="${1#*=}"
                    shift
                    ;;
                -w|--wait|--timeout)
                    shift
                    [ $# -gt 0 ] && shift
                    ;;
                -w=*|--wait=*|--timeout=*)
                    shift
                    ;;
                -*)
                    shift
                    ;;
                *)
                    # Consume positional <lockfile> unless already at certbot
                    if [ "$1" != "certbot" ] && [ "${1##*/}" != "certbot" ]; then
                        shift
                    fi
                    break
                    ;;
            esac
        done
        if [ -f "$WS_ROOT/MOCK_FLOCK_BUSY" ] || [ "${MOCK_FLOCK_BUSY:-0}" = "1" ]; then
            echo "flock: simulated lock contention" >&2
            exit "$FLOCK_CONFLICT_EXIT"
        fi
    fi

    if [ "${1:-}" = "certbot" ] || [ "${1##*/}" = "certbot" ]; then
        shift
        exec "$WS_ROOT/bin/certbot" "$@"
    fi

    if [ "$TARGET_CONTAINER" = "pt-certbot" ] || [[ "$TARGET_CONTAINER" == *certbot* ]]; then
        case "${1:-}" in
            certonly|renew|certificates|-*)
                exec "$WS_ROOT/bin/certbot" "$@"
                ;;
            *)
                exit 0
                ;;
        esac
    fi
fi

if [ "${1:-}" = "restart" ]; then
    echo "${2:-pt-nginx1}"
    exit 0
fi

if [ "${1:-}" = "ps" ]; then
    echo "pt-certbot|Up 2 minutes|running"
    exit 0
fi

if [ "${1:-}" = "inspect" ]; then
    shift
    INSPECT_FMT=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --format|-f)
                if [ $# -ge 2 ]; then
                    INSPECT_FMT="$2"
                    shift 2
                else
                    shift
                fi
                ;;
            --format=*|-f=*)
                INSPECT_FMT="${1#*=}"
                shift
                ;;
            -f*)
                INSPECT_FMT="${1#-f}"
                shift
                ;;
            *)
                shift
                ;;
        esac
    done

    running="true"
    status="running"
    if [ "${MOCK_CERTBOT_STOPPED:-0}" = "1" ] || [ -f "$WS_ROOT/MOCK_CERTBOT_STOPPED" ]; then
        running="false"
        status="exited"
    fi

    if [[ "$INSPECT_FMT" == *"{{.State.Running}}"* ]] || [[ "$INSPECT_FMT" == *"{{.State.Status}}"* ]]; then
        out="$INSPECT_FMT"
        out="${out//\{\{.State.Running\}\}/${running}}"
        out="${out//\{\{.State.Status\}\}/${status}}"
        echo "$out"
    else
        echo "[{\"State\":{\"Running\":${running},\"Status\":\"${status}\",\"RestartCount\":0}}]"
    fi
    exit 0
fi

exit 0
'''

_MOCK_CERTBOT_SHIM = r'''#!/usr/bin/env bash
set -euo pipefail

WS_ROOT="${PROJECT_ROOT:-/test_ws}"
CONF_DIR="${CERTBOT_CONF_DIR:-$WS_ROOT/certbot/conf}"
LOG_FILE="$WS_ROOT/certbot_calls.log"
echo "certbot $*" >> "$LOG_FILE"

if [ -f "$WS_ROOT/MOCK_CERTBOT_FAIL" ] || [ "${MOCK_CERTBOT_FAIL:-0}" = "1" ]; then
    echo "Simulated ACME challenge failure (MOCK_CERTBOT_FAIL=1)" >&2
    exit 1
fi

SUBCMD=""
DRY_RUN=0
CERT_NAME=""
DEPLOY_HOOK=""
DOMAINS=()

append_domains() {
    local raw="$1"
    [ -z "$raw" ] && return 0
    local part
    local IFS=","
    read -ra _dom_parts <<< "$raw"
    for part in "${_dom_parts[@]}"; do
        [ -n "$part" ] && DOMAINS+=("$part")
    done
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        -d|--domain|--domains)
            if [ $# -ge 2 ] && [ -n "${2:-}" ]; then
                append_domains "$2"
            fi
            shift
            [ $# -gt 0 ] && shift
            ;;
        -d=*|--domain=*|--domains=*)
            append_domains "${1#*=}"
            shift
            ;;
        --cert-name)
            CERT_NAME="${2:-}"
            shift
            [ $# -gt 0 ] && shift
            ;;
        --cert-name=*)
            CERT_NAME="${1#*=}"
            shift
            ;;
        --deploy-hook)
            DEPLOY_HOOK="${2:-}"
            shift
            [ $# -gt 0 ] && shift
            ;;
        --deploy-hook=*)
            DEPLOY_HOOK="${1#*=}"
            shift
            ;;
        -w|--webroot-path|--config-dir|--work-dir|--logs-dir|--email|-m|--server|--preferred-challenges|--key-type|--rsa-key-size|--elliptic-curve|--pre-hook|--post-hook|--manual-auth-hook|--manual-cleanup-hook|-a|--authenticator|-i|--installer|--max-log-backups|--user-agent|--http-01-port|--http-01-address|--https-port)
            shift
            [ $# -gt 0 ] && shift
            ;;
        -w=*|--webroot-path=*|--config-dir=*|--work-dir=*|--logs-dir=*|--email=*|-m=*|--server=*|--preferred-challenges=*|--key-type=*|--rsa-key-size=*|--elliptic-curve=*|--pre-hook=*|--post-hook=*|--manual-auth-hook=*|--manual-cleanup-hook=*|-a=*|--authenticator=*|-i=*|--installer=*|--max-log-backups=*|--user-agent=*|--http-01-port=*|--http-01-address=*|--https-port=*)
            shift
            ;;
        certonly|renew|certificates)
            if [ -z "$SUBCMD" ]; then
                SUBCMD="$1"
            fi
            shift
            ;;
        *)
            shift
            ;;
    esac
done

if [ "$SUBCMD" = "certificates" ]; then
    found=0
    if [ -d "$CONF_DIR/live" ]; then
        for d in "$CONF_DIR/live"/*; do
            [ -d "$d" ] || continue
            dom="$(basename "$d")"
            if [ "$found" -eq 0 ]; then
                echo "Found the following certs:"
                found=1
            fi
            echo "  Certificate Name: $dom"
            echo "    Domains: $dom"
            echo "    Certificate Path: $d/fullchain.pem"
            echo "    Private Key Path: $d/privkey.pem"
        done
    fi
    if [ "$found" -eq 0 ]; then
        echo "No certificates found."
    fi
    exit 0
fi

if [ "$DRY_RUN" -eq 1 ]; then
    echo "Simulating certificate request or renewal (--dry-run)."
    echo "The dry run was successful."
    exit 0
fi

issue_cert_for_domain() {
    local dom="$1"
    shift
    local san_list=("$@")
    local arch_dir="$CONF_DIR/archive/$dom"
    local live_dir="$CONF_DIR/live/$dom"
    local ren_dir="$CONF_DIR/renewal"
    mkdir -p "$arch_dir" "$live_dir" "$ren_dir"

    local serial_file="$WS_ROOT/.mock_serial"
    local next_ver=1
    while [ -f "$arch_dir/cert${next_ver}.pem" ]; do
        next_ver=$((next_ver + 1))
    done
    local cur_serial=100
    if [ -f "$serial_file" ]; then
        cur_serial=$(( $(cat "$serial_file") + 1 ))
    fi
    echo "$cur_serial" > "$serial_file"

    local san_ext=""
    for d in "${san_list[@]}"; do
        if [ -n "$san_ext" ]; then
            san_ext="${san_ext},DNS:${d}"
        else
            san_ext="DNS:${d}"
        fi
    done
    if [ -z "$san_ext" ]; then
        san_ext="DNS:${dom}"
    fi

    openssl req -x509 -newkey rsa:2048 -nodes \
        -keyout "$arch_dir/privkey${next_ver}.pem" \
        -out "$arch_dir/cert${next_ver}.pem" \
        -days 90 \
        -set_serial "$cur_serial" \
        -subj "/CN=${dom}/O=Mock Lets Encrypt Test CA" \
        -addext "subjectAltName=${san_ext}" >/dev/null 2>&1
    chmod 600 "$arch_dir/privkey${next_ver}.pem"
    chmod 644 "$arch_dir/cert${next_ver}.pem"
    cp "$arch_dir/cert${next_ver}.pem" "$arch_dir/chain${next_ver}.pem"
    cp "$arch_dir/cert${next_ver}.pem" "$arch_dir/fullchain${next_ver}.pem"

    for f in cert chain fullchain privkey; do
        ln -sfn "../../archive/${dom}/${f}${next_ver}.pem" "$live_dir/${f}.pem.tmp"
        mv -Tf "$live_dir/${f}.pem.tmp" "$live_dir/${f}.pem"
    done

    cat > "$ren_dir/${dom}.conf" <<RENEW_EOF
archive_dir = /etc/letsencrypt/archive/${dom}
cert = /etc/letsencrypt/live/${dom}/cert.pem
privkey = /etc/letsencrypt/live/${dom}/privkey.pem
chain = /etc/letsencrypt/live/${dom}/chain.pem
fullchain = /etc/letsencrypt/live/${dom}/fullchain.pem
RENEW_EOF
}

run_deploy_hook() {
    local dom="$1"
    shift
    local domains_str="$*"
    [ -z "$DEPLOY_HOOK" ] && return 0
    local hook_cmd="$DEPLOY_HOOK"
    if [ "$CONF_DIR" != "/etc/letsencrypt" ]; then
        hook_cmd="${hook_cmd//\/etc\/letsencrypt/$CONF_DIR}"
    fi
    RENEWED_LINEAGE="$CONF_DIR/live/$dom" RENEWED_DOMAINS="$domains_str" sh -c "$hook_cmd"
}

if [ "$SUBCMD" = "certonly" ]; then
    if [ ${#DOMAINS[@]} -eq 0 ]; then
        echo "No domain (-d) provided to mock certbot certonly" >&2
        exit 1
    fi
    PRIMARY="${CERT_NAME:-${DOMAINS[0]}}"
    issue_cert_for_domain "$PRIMARY" "${DOMAINS[@]}"
    run_deploy_hook "$PRIMARY" "${DOMAINS[@]}"
    echo "Successfully received certificate."
    echo "Certificate is saved at: $CONF_DIR/live/$PRIMARY/fullchain.pem"
    exit 0
elif [ "$SUBCMD" = "renew" ]; then
    if [ -d "$CONF_DIR/live" ]; then
        for d in "$CONF_DIR/live"/*; do
            [ -d "$d" ] || continue
            dom="$(basename "$d")"
            issue_cert_for_domain "$dom" "$dom"
            run_deploy_hook "$dom" "$dom"
        done
    fi
    echo "Congratulations, all renewals succeeded."
    exit 0
fi

echo "Mock certbot executed: $SUBCMD"
exit 0
'''


class MgmtAppBridge:
    """
    Executes `pt-management` Flask `app.test_client()` requests and manager unit calls
    against an isolated workspace (`temp_stack_ws`), using in-process execution when
    Flask is importable or an ephemeral `pt-management:latest` container otherwise.
    """

    def __init__(self, ws: Path, image: str = "pt-management:latest") -> None:
        self.ws = ws
        self.image = image
        self.repo = repo_root()
        self.bin_dir = ws / "bin"
        self.bin_dir.mkdir(parents=True, exist_ok=True)
        self._install_shims()

    def _install_shims(self) -> None:
        docker_shim = self.bin_dir / "docker"
        docker_shim.write_text(_MOCK_DOCKER_SHIM, encoding="utf-8")
        os.chmod(docker_shim, 0o755)

        certbot_shim = self.bin_dir / "certbot"
        certbot_shim.write_text(_MOCK_CERTBOT_SHIM, encoding="utf-8")
        os.chmod(certbot_shim, 0o755)

    def docker_calls(self) -> List[str]:
        log = self.ws / "docker_calls.log"
        if not log.exists():
            return []
        return [line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]

    def certbot_calls(self) -> List[str]:
        log = self.ws / "certbot_calls.log"
        if not log.exists():
            return []
        return [line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]

    def clear_logs(self) -> None:
        for fname in ("docker_calls.log", "certbot_calls.log"):
            p = self.ws / fname
            if p.exists():
                p.unlink()

    def set_mock_certbot_fail(self, enabled: bool) -> None:
        flag = self.ws / "MOCK_CERTBOT_FAIL"
        if enabled:
            flag.write_text("1", encoding="utf-8")
        elif flag.exists():
            flag.unlink()

    def set_mock_nginx_test_fail(self, enabled: bool) -> None:
        flag = self.ws / "MOCK_NGINX_TEST_FAIL"
        if enabled:
            flag.write_text("1", encoding="utf-8")
        elif flag.exists():
            flag.unlink()

    def _has_inprocess_flask(self) -> bool:
        return (
            importlib.util.find_spec("flask") is not None
            and importlib.util.find_spec("dotenv") is not None
            and importlib.util.find_spec("mysql") is not None
            and importlib.util.find_spec("docker") is not None
        )

    def _run_spec(self, spec: Dict[str, Any], timeout: int = 45) -> Dict[str, Any]:
        payload_json = json.dumps(spec)

        # In-process only if all pt-management dependencies are installed AND we are not forced to Docker
        if self._has_inprocess_flask() and os.environ.get("CERTBOT_E2E_FORCE_DOCKER_MGMT", "") != "1":
            harness_path = self.repo / "tests" / "certbot" / "_mgmt_harness.py"
            old_env = os.environ.copy()
            try:
                os.environ.update(
                    {
                        "PYTHONPATH": str(self.repo / "pt-management"),
                        "DB_HOST": "127.0.0.1",
                        "ENV_PATH": str(self.ws / ".env"),
                        "PROJECT_ROOT": str(self.ws),
                        "SSL_DIR": str(self.ws / "ssl"),
                        "SSL_KEY_DIR": str(self.ws / "ssl"),
                        "CERTBOT_CONF_DIR": str(self.ws / "certbot" / "conf"),
                        "CERTBOT_WEBROOT": str(self.ws / "certbot" / "www"),
                        "SECRET_KEY": "test-secret",
                        "PTADMIN_PASSWORD": "testpass",
                        "PATH": f"{self.bin_dir}:{old_env.get('PATH', '')}",
                    }
                )
                if str(self.repo / "pt-management") not in sys.path:
                    sys.path.insert(0, str(self.repo / "pt-management"))
                spec_mod = importlib.util.spec_from_file_location("_mgmt_harness_local", harness_path)
                assert spec_mod and spec_mod.loader
                mod = importlib.util.module_from_spec(spec_mod)
                spec_mod.loader.exec_module(mod)
                out = mod.execute_spec(spec)
            finally:
                os.environ.clear()
                os.environ.update(old_env)
        else:
            harness_file = self.repo / "tests" / "certbot" / "_mgmt_harness.py"
            ptmgmt_dir = self.repo / "pt-management"
            user_args = ["--user", f"{os.getuid()}:{os.getgid()}"] if hasattr(os, "getuid") else []
            cmd = [
                "docker",
                "run",
                "--rm",
                "-i",
                *user_args,
                "--network",
                "none",
                "--entrypoint",
                "python3",
                "-v",
                f"{ptmgmt_dir}:/work_app:ro",
                "-v",
                f"{harness_file}:/_mgmt_harness.py:ro",
                "-v",
                f"{self.ws}:/test_ws:rw",
                "-w",
                "/work_app",
                "-e",
                "PYTHONDONTWRITEBYTECODE=1",
                "-e",
                "PYTHONPATH=/work_app",
                "-e",
                "DB_HOST=127.0.0.1",
                "-e",
                "DB_USER=none",
                "-e",
                "DB_PASSWORD=none",
                "-e",
                "ENV_PATH=/test_ws/.env",
                "-e",
                "PROJECT_ROOT=/test_ws",
                "-e",
                "SSL_DIR=/test_ws/ssl",
                "-e",
                "SSL_KEY_DIR=/test_ws/ssl",
                "-e",
                "CERTBOT_CONF_DIR=/test_ws/certbot/conf",
                "-e",
                "CERTBOT_WEBROOT=/test_ws/certbot/www",
                "-e",
                "SECRET_KEY=test-secret",
                "-e",
                "PTADMIN_PASSWORD=testpass",
                "-e",
                "PATH=/test_ws/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                self.image,
                "/_mgmt_harness.py",
            ]
            proc = subprocess.run(cmd, input=payload_json, capture_output=True, text=True, timeout=timeout)
            if proc.returncode != 0:
                raise RuntimeError(
                    f"_mgmt_harness container failed (rc={proc.returncode}):\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
                )
            try:
                out = json.loads(proc.stdout)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Invalid JSON from _mgmt_harness: {exc}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
                ) from exc

        if not out.get("ok"):
            raise RuntimeError(f"_mgmt_harness error: {out.get('error')}\n{out.get('traceback', '')}")
        return out["result"]

    def http_sequence(
        self,
        requests_list: List[Dict[str, Any]],
        login: bool = True,
        username: str = "ptadmin",
        password: str = "testpass",
        timeout: int = 45,
    ) -> Dict[str, Any]:
        """Execute a sequence of HTTP calls through `app.test_client()`."""
        spec: Dict[str, Any] = {
            "action": "http_sequence",
            "login": {"username": username, "password": password} if login else None,
            "requests": requests_list,
        }
        res = self._run_spec(spec, timeout=timeout)
        if login and res.get("login_status") != 302:
            raise AssertionError(
                f"Expected ptadmin login to return 302, got {res.get('login_status')} (location={res.get('login_location')})"
            )
        return res

    def request(
        self,
        method: str,
        path: str,
        *,
        login: bool = True,
        json_body: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Tuple[str, bytes]]] = None,
        headers: Optional[Dict[str, str]] = None,
        base_url: str = "https://localhost",
    ) -> Dict[str, Any]:
        """Convenience wrapper for a single HTTP call."""
        req: Dict[str, Any] = {"method": method, "path": path, "base_url": base_url}
        if headers:
            req["headers"] = headers
        if json_body is not None:
            req["json"] = json_body
        if data is not None:
            req["data"] = data
        if files is not None:
            encoded_files: Dict[str, Any] = {}
            for field, (fname, content) in files.items():
                encoded_files[field] = {
                    "filename": fname,
                    "content_b64": base64.b64encode(content).decode("ascii"),
                }
            req["files"] = encoded_files
        out = self.http_sequence([req], login=login)
        return out["responses"][0]

    def unit_call(
        self,
        target: str,
        method: str,
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Invoke a manager class method inside the isolated harness."""
        spec: Dict[str, Any] = {
            "action": "unit_call",
            "target": target,
            "method": method,
            "args": args or [],
            "kwargs": kwargs or {},
        }
        if extra:
            spec.update(extra)
        return self._run_spec(spec)
