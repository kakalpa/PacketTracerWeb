#!/usr/bin/env python3
"""
Container-side / in-process test harness for `pt-management` Flask app and managers.

Reads a single JSON specification from stdin, executes either:
  - `http_sequence`: runs requests through `create_app().test_client()`
  - `unit_call`: invokes EnvConfigManager / FileUploadManager / CertbotManager

Redirects stdout to stderr during application execution so any incidental `print()`
statements inside `pt-management` never corrupt the JSON response emitted on stdout.
"""

from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Dict


def _build_files_payload(files_spec: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for field, spec in files_spec.items():
        filename = spec.get("filename", "upload.bin")
        if "content_b64" in spec:
            raw = base64.b64decode(spec["content_b64"])
        elif "path" in spec:
            raw = Path(spec["path"]).read_bytes()
        else:
            raw = spec.get("content", "").encode("utf-8")
        out[field] = (io.BytesIO(raw), filename)
    return out


def _run_http_sequence(spec: Dict[str, Any]) -> Dict[str, Any]:
    from app import create_app  # type: ignore

    app = create_app()
    app.config["TESTING"] = True

    result: Dict[str, Any] = {
        "login_status": None,
        "login_location": None,
        "responses": [],
    }

    with app.test_client() as client:
        login_cfg = spec.get("login")
        if login_cfg:
            login_resp = client.post(
                "/login",
                data={
                    "username": login_cfg.get("username", "ptadmin"),
                    "password": login_cfg.get("password", os.environ.get("PTADMIN_PASSWORD", "testpass")),
                },
                base_url=login_cfg.get("base_url", "https://localhost"),
                follow_redirects=False,
            )
            result["login_status"] = login_resp.status_code
            result["login_location"] = login_resp.headers.get("Location")

        for req in spec.get("requests", []):
            method = req.get("method", "GET").upper()
            path = req["path"]
            base_url = req.get("base_url", "https://localhost")
            headers = req.get("headers") or {}
            kwargs: Dict[str, Any] = {
                "base_url": base_url,
                "headers": headers,
                "follow_redirects": bool(req.get("follow_redirects", False)),
            }
            if "json" in req and req["json"] is not None:
                kwargs["json"] = req["json"]
            elif "files" in req and req["files"] is not None:
                data_payload = dict(req.get("data") or {})
                data_payload.update(_build_files_payload(req["files"]))
                kwargs["data"] = data_payload
                kwargs["content_type"] = "multipart/form-data"
            elif "data" in req and req["data"] is not None:
                kwargs["data"] = req["data"]

            resp = getattr(client, method.lower())(path, **kwargs)
            body_text = resp.get_data(as_text=True)
            parsed_json = None
            try:
                parsed_json = resp.get_json(silent=True)
            except Exception:
                parsed_json = None

            result["responses"].append(
                {
                    "status_code": resp.status_code,
                    "location": resp.headers.get("Location"),
                    "content_type": resp.content_type,
                    "body": body_text,
                    "json": parsed_json,
                }
            )

    return result


def _run_unit_call(spec: Dict[str, Any]) -> Dict[str, Any]:
    target = spec["target"]
    method = spec["method"]
    args = spec.get("args", [])
    kwargs = spec.get("kwargs", {})

    if target == "env_config":
        from ptmanagement.api.env_config import EnvConfigManager  # type: ignore

        env_path = spec.get("env_path") or os.environ.get("ENV_PATH")
        mgr = EnvConfigManager(env_path=env_path)
        fn = getattr(mgr, method)
        ret = fn(*args, **kwargs)
        env_file = Path(mgr.env_path)
        return {
            "return": list(ret) if isinstance(ret, tuple) else ret,
            "env_path": str(env_file),
            "env_inode": env_file.stat().st_ino if env_file.exists() else None,
            "env_raw": env_file.read_text(encoding="utf-8") if env_file.exists() else "",
            "env_parsed": mgr.read_env_file() if env_file.exists() else {},
        }

    if target == "file_upload":
        from werkzeug.datastructures import FileStorage  # type: ignore
        from ptmanagement.api.file_upload import FileUploadManager  # type: ignore

        mgr = FileUploadManager()
        if method == "upload_file":
            fspec = spec["file"]
            raw = base64.b64decode(fspec["content_b64"])
            fs = FileStorage(stream=io.BytesIO(raw), filename=fspec["filename"])
            ret = mgr.upload_file(fs, *args, **kwargs)
        elif method == "validate_file_content":
            raw = base64.b64decode(spec["content_b64"])
            ret = mgr.validate_file_content(raw, *args, **kwargs)
        else:
            ret = getattr(mgr, method)(*args, **kwargs)
        return {"return": list(ret) if isinstance(ret, tuple) else ret}

    if target == "certbot_manager":
        from ptmanagement.api.certbot_manager import CertbotManager  # type: ignore

        mgr = CertbotManager()
        ret = getattr(mgr, method)(*args, **kwargs)
        return {"return": list(ret) if isinstance(ret, tuple) else ret}

    raise ValueError(f"Unknown unit_call target: {target}")


def execute_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    action = spec.get("action")
    buf_err = io.StringIO()
    with contextlib.redirect_stdout(buf_err):
        try:
            if action == "http_sequence":
                payload = _run_http_sequence(spec)
            elif action == "unit_call":
                payload = _run_unit_call(spec)
            else:
                raise ValueError(f"Unsupported action: {action}")
            return {"ok": True, "result": payload, "captured_stdout": buf_err.getvalue()}
        except Exception as exc:
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
                "captured_stdout": buf_err.getvalue(),
            }


def main() -> int:
    raw = sys.stdin.read()
    spec = json.loads(raw)
    out = execute_spec(spec)
    sys.stdout.write(json.dumps(out))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
