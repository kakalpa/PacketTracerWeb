"""System management API for Docker containers and logs"""

import os
import logging
import subprocess
from flask import Blueprint, jsonify, session, request
from functools import wraps

logger = logging.getLogger(__name__)


def require_auth(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function


def create_system_management_blueprint():
    """Create blueprint for system management endpoints"""
    sm = Blueprint('system_management', __name__)
    
    @sm.route('/health', methods=['GET'])
    @require_auth
    def health_check():
        """Health check for system services"""
        try:
            health_status = {
                'guacd': {'status': 'unknown', 'running': False},
                'guacamole': {'status': 'unknown', 'running': False},
                'mariadb': {'status': 'unknown', 'running': False},
                'nginx': {'status': 'unknown', 'running': False},
            }
            
            # Map service names to actual container names
            container_map = {
                'guacd': 'pt-guacd',
                'guacamole': 'pt-guacamole',
                'mariadb': 'guacamole-mariadb',
                'nginx': 'pt-nginx1',
            }
            
            # Check if containers are running
            for service, container in container_map.items():
                try:
                    result = subprocess.run(
                        ['sudo', 'docker', 'inspect', '-f', '{{.State.Running}}', container],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    is_running = 'true' in result.stdout.lower()
                    health_status[service]['running'] = is_running
                    health_status[service]['status'] = 'running' if is_running else 'stopped'
                    logger.debug(f"Container {container} status: {health_status[service]['status']}")
                except Exception as e:
                    logger.warning(f"Failed to check container {container}: {e}")
            
            return jsonify({
                'success': True,
                'services': health_status
            }), 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return jsonify({'error': str(e)}), 500
    
    @sm.route('/restart/guacd', methods=['POST'])
    @require_auth
    def restart_guacd():
        """Restart guacd container"""
        try:
            logger.info(f"Restarting guacd container (requested by {session.get('user')})")
            
            result = subprocess.run(
                ['sudo', 'docker', 'restart', 'pt-guacd'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                logger.info("✓ guacd restarted successfully")
                return jsonify({
                    'success': True,
                    'message': 'guacd restarted successfully'
                }), 200
            else:
                error_msg = result.stderr or "Unknown error"
                logger.error(f"Failed to restart guacd: {error_msg}")
                return jsonify({
                    'error': error_msg
                }), 500
        except subprocess.TimeoutExpired:
            logger.error("Timeout while restarting guacd")
            return jsonify({'error': 'Restart timeout'}), 500
        except Exception as e:
            logger.error(f"Failed to restart guacd: {e}")
            return jsonify({'error': str(e)}), 500
    
    @sm.route('/restart/guacamole', methods=['POST'])
    @require_auth
    def restart_guacamole():
        """Restart guacamole container"""
        try:
            logger.info(f"Restarting guacamole container (requested by {session.get('user')})")
            
            result = subprocess.run(
                ['sudo', 'docker', 'restart', 'pt-guacamole'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                logger.info("✓ guacamole restarted successfully")
                return jsonify({
                    'success': True,
                    'message': 'guacamole restarted successfully'
                }), 200
            else:
                error_msg = result.stderr or "Unknown error"
                logger.error(f"Failed to restart guacamole: {error_msg}")
                return jsonify({
                    'error': error_msg
                }), 500
        except subprocess.TimeoutExpired:
            logger.error("Timeout while restarting guacamole")
            return jsonify({'error': 'Restart timeout'}), 500
        except Exception as e:
            logger.error(f"Failed to restart guacamole: {e}")
            return jsonify({'error': str(e)}), 500
    
    @sm.route('/logs/guacd', methods=['GET'])
    @require_auth
    def get_guacd_logs():
        """Get guacd logs"""
        try:
            lines = request.args.get('lines', 100, type=int)
            if lines > 1000:
                lines = 1000  # Limit to 1000 lines
            
            result = subprocess.run(
                ['docker', 'logs', '--tail', str(lines), 'pt-guacd'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return jsonify({
                    'success': True,
                    'container': 'guacd',
                    'logs': result.stdout,
                    'lines': len(result.stdout.split('\n'))
                }), 200
            else:
                error_msg = result.stderr or "Failed to retrieve logs"
                logger.error(f"Failed to get guacd logs: {error_msg}")
                return jsonify({
                    'error': error_msg
                }), 500
        except subprocess.TimeoutExpired:
            logger.error("Timeout while retrieving guacd logs")
            return jsonify({'error': 'Log retrieval timeout'}), 500
        except Exception as e:
            logger.error(f"Failed to get guacd logs: {e}")
            return jsonify({'error': str(e)}), 500
    
    @sm.route('/logs/guacamole', methods=['GET'])
    @require_auth
    def get_guacamole_logs():
        """Get guacamole logs"""
        try:
            lines = request.args.get('lines', 100, type=int)
            if lines > 1000:
                lines = 1000  # Limit to 1000 lines
            
            result = subprocess.run(
                ['sudo', 'docker', 'logs', '--tail', str(lines), 'pt-guacamole'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return jsonify({
                    'success': True,
                    'container': 'guacamole',
                    'logs': result.stdout,
                    'lines': len(result.stdout.split('\n'))
                }), 200
            else:
                error_msg = result.stderr or "Failed to retrieve logs"
                logger.error(f"Failed to get guacamole logs: {error_msg}")
                return jsonify({
                    'error': error_msg
                }), 500
        except subprocess.TimeoutExpired:
            logger.error("Timeout while retrieving guacamole logs")
            return jsonify({'error': 'Log retrieval timeout'}), 500
        except Exception as e:
            logger.error(f"Failed to get guacamole logs: {e}")
            return jsonify({'error': str(e)}), 500
    
    return sm
