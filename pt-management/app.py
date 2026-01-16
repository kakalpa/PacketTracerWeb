#!/usr/bin/env python3
"""
PT Management - Bulk User & Container Management Web Application
Manages Packet Tracer containers and Guacamole users directly via Docker and MariaDB
"""

import os
import logging
from flask import Flask, render_template, request, redirect, session, jsonify, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from datetime import timedelta

from ptmanagement.db.connection import get_db_connection
from ptmanagement.api.auth import verify_ptadmin_credentials

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_app():
    """Application factory"""
    app = Flask(__name__, template_folder='templates', static_folder='static')
    
    # Enable ProxyFix to handle X-Forwarded-* headers from nginx (if needed in future)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=0)
    
    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
    app.config['SESSION_COOKIE_SECURE'] = False  # HTTP on port 8080 (not exposed externally)
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
    
    # Test database connection on startup
    logger.info("Testing database connection...")
    try:
        db = get_db_connection()
        if db:
            cursor = db.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            cursor.close()
            db.close()
            logger.info("✓ Database connection successful")
        else:
            logger.warning("⚠ Database connection failed (returned None)")
    except Exception as e:
        logger.error(f"✗ Database connection failed: {e}")
    
    # ========================================================================
    # Authentication Routes
    # ========================================================================
    
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """Login page"""
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            
            if verify_ptadmin_credentials(username, password):
                session.permanent = True
                session['user'] = username
                logger.info(f"✓ User {username} logged in successfully")
                return redirect(url_for('dashboard'))
            
            logger.warning(f"✗ Failed login attempt for user {username}")
            return render_template('login.html', error='Invalid credentials'), 401
        
        return render_template('login.html')
    
    @app.route('/logout')
    def logout():
        """Logout"""
        user = session.pop('user', None)
        if user:
            logger.info(f"✓ User {user} logged out")
        return redirect(url_for('login'))
    
    # ========================================================================
    # Dashboard Routes
    # ========================================================================
    
    @app.before_request
    def check_authentication():
        """Check if user is authenticated for protected routes"""
        protected_routes = ['/dashboard', '/settings', '/files', '/api/']
        
        if any(request.path.startswith(route) for route in protected_routes):
            # Allow specific endpoints without auth (internal or batch operations)
            if request.path.startswith('/api/containers') and request.method == 'POST':
                return  # Skip auth
            if request.path.startswith('/api/env/defaults') and request.method == 'GET':
                return  # Skip auth for public defaults endpoint
            if request.path.startswith('/api/users') and request.method == 'POST':
                # Allow POST to /api/users for bulk create from internal network
                client_ip = request.remote_addr
                is_internal = (
                    client_ip in ['127.0.0.1', '::1', 'localhost'] or 
                    client_ip.startswith('172.') or 
                    client_ip.startswith('10.')
                )
                if is_internal:
                    return  # Allow internal requests
            if request.path.startswith('/api/users/bulk/delete') and request.method == 'POST':
                # Allow bulk delete from internal network
                client_ip = request.remote_addr
                is_internal = (
                    client_ip in ['127.0.0.1', '::1', 'localhost'] or 
                    client_ip.startswith('172.') or 
                    client_ip.startswith('10.')
                )
                if is_internal:
                    return  # Allow internal requests
            if request.path.startswith('/api/users/') and request.method == 'DELETE':
                # Allow DELETE /api/users/<username> from internal network
                client_ip = request.remote_addr
                is_internal = (
                    client_ip in ['127.0.0.1', '::1', 'localhost'] or 
                    client_ip.startswith('172.') or 
                    client_ip.startswith('10.')
                )
                if is_internal:
                    return  # Allow internal requests
                
            if 'user' not in session:
                return redirect(url_for('login'))
    
    @app.route('/')
    def index():
        """Home page - redirect to dashboard if logged in, login otherwise"""
        if 'user' in session:
            return redirect(url_for('dashboard'))
        return redirect(url_for('login'))
    
    @app.route('/dashboard')
    def dashboard():
        """Main dashboard"""
        return render_template('dashboard.html', username=session.get('user'))
    
    @app.route('/settings')
    def settings():
        """Nginx configuration settings page"""
        return render_template('env_settings.html', username=session.get('user'))
    
    @app.route('/files')
    def file_manager():
        """File manager page for managing /shared folder"""
        return render_template('file_manager.html', username=session.get('user'))
    
    # ========================================================================
    # API Routes
    # ========================================================================
    
    from ptmanagement.api.routes import create_api_blueprint
    api_bp = create_api_blueprint()
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # ========================================================================
    # Environment Configuration API
    # ========================================================================
    
    from ptmanagement.api.env_routes import create_env_config_blueprint
    env_api_bp = create_env_config_blueprint()
    app.register_blueprint(env_api_bp)  # Blueprint already has /api/env prefix
    
    # ========================================================================
    # File Upload API
    # ========================================================================
    
    from ptmanagement.api.upload_routes import create_file_upload_blueprint
    upload_api_bp = create_file_upload_blueprint()
    app.register_blueprint(upload_api_bp)  # Blueprint already has /api/upload prefix
    
    # ========================================================================
    # File Manager API
    # ========================================================================
    
    from ptmanagement.api.file_manager import create_file_manager_blueprint
    fm_api_bp = create_file_manager_blueprint()
    app.register_blueprint(fm_api_bp)  # Blueprint already has /api/files prefix
    
    # ========================================================================
    # Error Handlers
    # ========================================================================
    
    @app.errorhandler(404)
    def not_found(error):
        """404 error handler"""
        return render_template('error.html', code=404, message='Page not found'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        """500 error handler"""
        logger.error(f"✗ Internal server error: {error}")
        return render_template('error.html', code=500, message='Internal server error'), 500
    
    # ========================================================================
    # Health Check
    # ========================================================================
    
    @app.route('/health')
    def health():
        """Health check (no auth required)"""
        try:
            # Test database
            db = get_db_connection()
            db_ok = db is not None
            if db:
                db.close()
            
            # Test Docker socket API
            try:
                from ptmanagement.docker_mgmt.container import DockerManager
                docker_mgr = DockerManager()
                containers = docker_mgr.list_containers()
                docker_ok = isinstance(containers, list)
            except Exception as e:
                logger.warning(f"⚠ Docker check failed: {e}")
                docker_ok = False
            
            status = 200 if (db_ok and docker_ok) else 503
            return jsonify({
                'status': 'healthy' if status == 200 else 'degraded',
                'database': 'ok' if db_ok else 'error',
                'docker': 'ok' if docker_ok else 'error'
            }), status
        except Exception as e:
            logger.error(f"✗ Health check error: {e}")
            return jsonify({'status': 'unhealthy', 'error': str(e)}), 503
    
    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=False)
