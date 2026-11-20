#!/usr/bin/env python3
"""
Certbot TLS API Routes
Handles REST endpoints for Let's Encrypt configuration, issuance, renewal, and TLS mode switching.
"""

import logging
from typing import Optional
from flask import Blueprint, jsonify, request
from ptmanagement.api.auth import require_admin
from ptmanagement.api.certbot_manager import CertbotManager

logger = logging.getLogger(__name__)


def _require_json_body():
    """Enforce application/json request body on mutating POST endpoints."""
    if not request.is_json:
        return None, (jsonify({'success': False, 'message': 'Content-Type must be application/json'}), 400)
    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        return None, (jsonify({'success': False, 'message': 'Invalid JSON payload'}), 400)
    return data, None


_TRUE_STRINGS = frozenset({'true', '1', 'yes', 'on'})
_FALSE_STRINGS = frozenset({'false', '0', 'no', 'off'})


def _parse_strict_bool(data: dict, key: str, default: Optional[bool] = False, allow_none: bool = False):
    """
    Strictly parse an optional boolean field from a JSON payload.
    Accepts JSON booleans (True/False) and recognized boolean strings ('true'/'false', etc.).
    Returns (parsed_value, error_response_tuple_or_None).
    """
    if key not in data:
        return default, None
    val = data[key]
    if val is None:
        if allow_none:
            return None, None
        return None, (jsonify({'success': False, 'message': f"Invalid boolean value for '{key}'"}), 400)
    if isinstance(val, bool):
        return val, None
    if isinstance(val, str):
        lowered = val.strip().lower()
        if lowered in _TRUE_STRINGS:
            return True, None
        if lowered in _FALSE_STRINGS:
            return False, None
    return None, (jsonify({'success': False, 'message': f"Invalid boolean value for '{key}'"}), 400)


def create_certbot_blueprint(certbot_manager: Optional[CertbotManager] = None) -> Blueprint:
    """Create and configure the Certbot TLS API blueprint."""
    certbot_api = Blueprint('certbot_api', __name__, url_prefix='/api/certbot')
    mgr = certbot_manager or CertbotManager()

    @certbot_api.route('/status', methods=['GET'])
    @require_admin
    def get_status():
        """Get current TLS mode, Certbot settings, active X.509 certificate metadata, and container status."""
        try:
            status = mgr.get_status()
            return jsonify(status), 200
        except Exception as e:
            logger.error(f"✗ Error getting Certbot status: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500

    @certbot_api.route('/config', methods=['POST'])
    @require_admin
    def save_config():
        """Validate and persist Certbot configuration in .env."""
        data, err_resp = _require_json_body()
        if err_resp is not None:
            return err_resp
        try:
            payload = dict(data)
            for bool_key in ('enabled', 'staging', 'auto_renew', 'enable_https'):
                if bool_key in payload:
                    parsed_val, bool_err = _parse_strict_bool(payload, bool_key, default=None, allow_none=False)
                    if bool_err is not None:
                        return bool_err
                    payload[bool_key] = parsed_val
            res = mgr.save_config(payload)
            status_code = res.pop('status_code', 200 if res.get('success') else 400)
            return jsonify(res), status_code
        except Exception as e:
            logger.error(f"✗ Error saving Certbot config: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500

    @certbot_api.route('/issue', methods=['POST'])
    @require_admin
    def issue_certificate():
        """Run preflight checks and issue a Let's Encrypt certificate via Certbot."""
        data, err_resp = _require_json_body()
        if err_resp is not None:
            return err_resp
        try:
            dry_run, bool_err = _parse_strict_bool(data, 'dry_run', default=False, allow_none=False)
            if bool_err is not None:
                return bool_err
            staging, bool_err = _parse_strict_bool(data, 'staging', default=None, allow_none=True)
            if bool_err is not None:
                return bool_err
            res = mgr.issue(dry_run=dry_run, staging=staging)
            status_code = res.pop('status_code', 200 if res.get('success') else 500)
            return jsonify(res), status_code
        except Exception as e:
            logger.error(f"✗ Error issuing certificate: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500

    @certbot_api.route('/renew', methods=['POST'])
    @require_admin
    def renew_certificate():
        """Execute certbot renew (supports dry_run and force_renewal)."""
        data, err_resp = _require_json_body()
        if err_resp is not None:
            return err_resp
        try:
            dry_run, bool_err = _parse_strict_bool(data, 'dry_run', default=False, allow_none=False)
            if bool_err is not None:
                return bool_err
            force_renewal, bool_err = _parse_strict_bool(data, 'force_renewal', default=False, allow_none=False)
            if bool_err is not None:
                return bool_err
            res = mgr.renew(dry_run=dry_run, force_renewal=force_renewal)
            status_code = res.pop('status_code', 200 if res.get('success') else 500)
            return jsonify(res), status_code
        except Exception as e:
            logger.error(f"✗ Error renewing certificate: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500

    @certbot_api.route('/switch-mode', methods=['POST'])
    @require_admin
    def switch_mode():
        """Switch TLS_MODE between self-signed, manual, and certbot."""
        data, err_resp = _require_json_body()
        if err_resp is not None:
            return err_resp
        try:
            tls_mode = data.get('tls_mode')
            if not tls_mode or not isinstance(tls_mode, str):
                return jsonify({'success': False, 'message': 'Missing tls_mode'}), 400
            res = mgr.switch_mode(tls_mode.strip())
            status_code = res.pop('status_code', 200 if res.get('success') else 400)
            return jsonify(res), status_code
        except Exception as e:
            logger.error(f"✗ Error switching TLS mode: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500

    return certbot_api
