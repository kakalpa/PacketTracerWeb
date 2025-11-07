"""API routes for bulk user and container management"""

import logging
import os
import subprocess
from functools import wraps
from flask import Blueprint, request, jsonify, session
from ptmanagement.db.guacamole import (
    get_all_users, create_user, delete_user, user_exists, get_user_connections,
    assign_connection_to_user, assign_container_to_user, get_user_container, 
    get_users_by_container, create_vnc_connection, reset_user_password, execute_query, get_user_entity_id,
    delete_connection, grant_admin_permission, revoke_admin_permission
)
from ptmanagement.docker_mgmt.container import DockerManager

logger = logging.getLogger(__name__)

docker_mgr = DockerManager()


def require_auth(f):
    """Decorator to require authentication for API endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function


def require_auth_or_internal(f):
    """Decorator to require authentication OR internal network access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Allow internal network (127.0.0.1, ::1, localhost, docker internal IPs starting with 172. or 10.)
        client_ip = request.remote_addr
        is_internal = (
            client_ip in ['127.0.0.1', '::1', 'localhost'] or 
            client_ip.startswith('172.') or 
            client_ip.startswith('10.')
        )
        
        if is_internal:
            logger.debug(f"✓ Allowing internal request from {client_ip}")
            return f(*args, **kwargs)
        
        # Otherwise require session auth
        if 'user' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function


def create_api_blueprint():
    """Create and configure the API blueprint"""
    api = Blueprint('api', __name__)
    
    # ========================================================================
    # User Management Endpoints
    # ========================================================================
    
    @api.route('/users', methods=['GET'])
    @require_auth
    def list_users():
        """Get all Guacamole users"""
        try:
            users = get_all_users()
            return jsonify({
                'success': True,
                'users': users,
                'count': len(users)
            }), 200
        except Exception as e:
            logger.error(f"✗ Failed to list users: {e}")
            return jsonify({'error': str(e)}), 500
    
    @api.route('/users/<username>', methods=['GET'])
    @require_auth
    def get_user(username):
        """Get user details and their connections"""
        try:
            if not user_exists(username):
                return jsonify({'error': 'User not found'}), 404
            
            connections = get_user_connections(username)
            return jsonify({
                'success': True,
                'username': username,
                'connections': connections
            }), 200
        except Exception as e:
            logger.error(f"✗ Failed to get user {username}: {e}")
            return jsonify({'error': str(e)}), 500
    
    @api.route('/users', methods=['POST'])
    @require_auth_or_internal
    def create_users():
        """
        Create multiple users from CSV data.
        
        Expected JSON:
        {
            "users": [
                {"username": "user1", "password": "pass1", "create_container": true, "is_admin": true},
                {"username": "user2", "password": "pass2", "container": "ptvnc1", "is_admin": false}
            ]
        }
        
        Options:
        - is_admin (bool): Grant ADMINISTER permission to user (default: false)
        - create_container (bool): Create a new container for this user (default: false)
        - container (string): Assign existing container to user (default: none)
        """
        try:
            data = request.get_json()
            if not data or 'users' not in data:
                return jsonify({'error': 'Missing users data'}), 400
            
            users = data['users']
            created = []
            failed = []
            
            for user_data in users:
                username = user_data.get('username', '').strip()
                password = user_data.get('password', '').strip()
                create_container = user_data.get('create_container', False)
                existing_container = user_data.get('container', '').strip()
                is_admin = user_data.get('is_admin', False)
                
                logger.info(f"DEBUG: Processing user {username}, create_container={create_container}, is_admin={is_admin}")
                
                if not username or not password:
                    failed.append({'username': username, 'error': 'Missing username or password'})
                    continue
                
                if user_exists(username):
                    failed.append({'username': username, 'error': 'User already exists'})
                    continue
                
                # Create user with plain-text password; create_user will hash it internally
                user_id, success = create_user(username, password)
                if success:
                    container_assigned = None
                    
                    # Grant admin permission if requested
                    if is_admin:
                        if grant_admin_permission(username):
                            logger.info(f"✓ Granted admin permission to {username}")
                        else:
                            logger.warning(f"⚠ Failed to grant admin permission to {username}")
                    
                    if create_container:
                        # Spin up a new container - auto-increment ptvnc naming
                        try:
                            # Get all existing ptvnc containers to find the next number
                            from ptmanagement.docker_mgmt.container import DockerManager
                            docker_mgr = DockerManager()
                            existing_containers = docker_mgr.list_containers()
                            
                            # Extract numbers from container names like ptvnc1, ptvnc10, etc.
                            next_number = 1
                            numbers = []
                            for container in existing_containers:
                                name = container.get('name', '')
                                if name.startswith('ptvnc') and len(name) > 5:
                                    suffix = name[5:]  # Everything after 'ptvnc'
                                    if suffix.isdigit():
                                        numbers.append(int(suffix))
                            
                            if numbers:
                                next_number = max(numbers) + 1
                            
                            container_name = f'ptvnc{next_number}'
                            logger.info(f"Creating container {container_name} for user {username}...")
                            
                            # Get the actual host path for /shared (needed for docker daemon to understand)
                            shared_path = os.getenv('SHARED_HOST_PATH', os.path.join(os.getenv('PROJECT_ROOT', '/project'), 'shared'))
                            
                            # Create the container using docker CLI with /shared mount
                            cmd = [
                                'docker', 'run', '-d',
                                '--name', container_name,
                                '--restart', 'unless-stopped',
                                '--cpus', '0.5',
                                '-m', '512m',
                                '-v', 'pt_opt:/opt/pt',  # Named volume for Packet Tracer binary
                                f'--mount=type=bind,source={shared_path},target=/shared,bind-propagation=rprivate',
                                'ptvnc'
                            ]
                            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                            
                            if result.returncode == 0:
                                logger.info(f"✓ Created container {container_name}")

                                # Connect container to pt-stack network for Guacamole connectivity
                                try:
                                    net_cmd = ['docker', 'network', 'connect', 'pt-stack', container_name]
                                    net_result = subprocess.run(net_cmd, capture_output=True, text=True, timeout=10)
                                    if net_result.returncode == 0:
                                        logger.info(f"✓ Connected {container_name} to pt-stack network")
                                    else:
                                        logger.warning(f"⚠ Failed to connect {container_name} to pt-stack: {net_result.stderr}")
                                except Exception as e:
                                    logger.warning(f"⚠ Error connecting to network: {e}")
                                
                                # Create Desktop symlink to /shared for easy file access
                                try:
                                    symlink_cmd = [
                                        'docker', 'exec', container_name,
                                        'bash', '-c',
                                        'mkdir -p /home/ptuser/Desktop && ln -sf /shared /home/ptuser/Desktop/shared'
                                    ]
                                    symlink_result = subprocess.run(symlink_cmd, capture_output=True, text=True, timeout=10)
                                    if symlink_result.returncode == 0:
                                        logger.info(f"✓ Created Desktop symlink in {container_name}")
                                    else:
                                        logger.warning(f"⚠ Failed to create Desktop symlink in {container_name}: {symlink_result.stderr}")
                                except Exception as e:
                                    logger.warning(f"⚠ Error creating Desktop symlink: {e}")
                                
                                # Assign container to user
                                if assign_container_to_user(username, container_name):
                                    logger.info(f"✓ Assigned container {container_name} to {username}")
                                    container_assigned = container_name
                                    
                                    # Create VNC connection in Guacamole for this container
                                    connection_name = f"vnc-{container_name}"
                                    try:
                                        connection_id = create_vnc_connection(connection_name, container_name, vnc_port=5900)
                                        if connection_id:
                                            # Assign connection to user (use connection_id, not connection_name!)
                                            if assign_connection_to_user(username, connection_id):
                                                logger.info(f"✓ Created and assigned VNC connection {connection_name} to {username}")
                                            else:
                                                logger.warning(f"⚠ Failed to assign connection {connection_name} to {username}")
                                        else:
                                            logger.warning(f"⚠ Failed to create VNC connection {connection_name}")
                                    except Exception as conn_err:
                                        logger.warning(f"⚠ Error creating VNC connection: {conn_err}")
                                    
                                    # Get list of admin users and assign them the same container
                                    # For now, we'll assign to the logged-in admin user
                                    current_user = session.get('user')
                                    if current_user:
                                        assign_container_to_user(current_user, container_name)
                                        logger.info(f"✓ Assigned container {container_name} to admin {current_user}")
                                        # Also assign the connection to admin
                                        try:
                                            assign_connection_to_user(current_user, connection_id)
                                            logger.info(f"✓ Assigned connection {connection_name} to admin {current_user}")
                                        except Exception as conn_err:
                                            logger.warning(f"⚠ Error assigning connection to admin: {conn_err}")
                                else:
                                    logger.warning(f"⚠ Failed to assign container {container_name} to {username}")
                            else:
                                logger.error(f"✗ Failed to create container {container_name}: {result.stderr}")
                                failed.append({'username': username, 'error': f'Container creation failed: {result.stderr}'})
                                continue
                                
                        except Exception as e:
                            logger.error(f"✗ Error creating container: {e}")
                            failed.append({'username': username, 'error': f'Container creation error: {str(e)}'})
                            continue
                    
                    elif existing_container:
                        # Assign existing container if provided
                        if assign_container_to_user(username, existing_container):
                            logger.info(f"✓ Assigned container {existing_container} to {username}")
                            container_assigned = existing_container
                        else:
                            logger.warning(f"⚠ Failed to assign container {existing_container} to {username}")
                    
                    created.append({'username': username, 'container': container_assigned or 'none'})
                else:
                    failed.append({'username': username, 'error': 'Database error'})
            
            return jsonify({
                'success': True,
                'created': created,
                'failed': failed,
                'count_created': len(created),
                'count_failed': len(failed)
            }), 201
        except Exception as e:
            logger.error(f"✗ Failed to create users: {e}")
            return jsonify({'error': str(e)}), 500
    
    @api.route('/users/<username>', methods=['DELETE'])
    @require_auth
    def delete_user_endpoint(username):
        """Delete a user with optional container deletion
        
        Query parameters:
        - delete_container: 'true' or 'false' (default: 'false')
        """
        try:
            if not user_exists(username):
                return jsonify({'error': 'User not found'}), 404
            
            delete_container = request.args.get('delete_container', 'false').lower() == 'true'
            containers_deleted = []
            
            # If delete_container flag is set, get and delete assigned containers
            if delete_container:
                from ptmanagement.db.guacamole import get_containers_by_user
                user_containers = get_containers_by_user(username)
                
                for container_name in user_containers:
                    try:
                        docker_mgr.delete_container(container_name, force=True)
                        containers_deleted.append(container_name)
                        logger.info(f"✓ Deleted container {container_name} for user {username}")
                    except Exception as e:
                        logger.warning(f"⚠ Failed to delete container {container_name}: {e}")
            
            if delete_user(username):
                response = {
                    'success': True,
                    'message': f'User {username} deleted',
                    'containers_deleted': containers_deleted
                }
                return jsonify(response), 200
            else:
                return jsonify({'error': 'Failed to delete user'}), 500
        except Exception as e:
            logger.error(f"✗ Failed to delete user {username}: {e}")
            return jsonify({'error': str(e)}), 500
    
    @api.route('/users/bulk/delete', methods=['POST'])
    @require_auth_or_internal
    def bulk_delete_users():
        """
        Delete multiple users with optional container deletion.
        
        Expected JSON:
        {
            "users": [
                {"username": "user1"},
                {"username": "user2"}
            ],
            "delete_containers": true  # Optional: delete assigned containers (default: false)
        }
        """
        try:
            data = request.get_json()
            if not data or 'users' not in data:
                return jsonify({'error': 'Missing users data'}), 400
            
            users = data['users']
            delete_containers = data.get('delete_containers', False)
            deleted = []
            failed = []
            not_found = []
            containers_deleted = []
            
            from ptmanagement.db.guacamole import get_containers_by_user
            
            for user_data in users:
                username = user_data.get('username', '').strip()
                
                if not username:
                    failed.append({'username': username, 'error': 'Missing username'})
                    continue
                
                if not user_exists(username):
                    not_found.append(username)
                    continue
                
                # Delete containers if requested
                if delete_containers:
                    try:
                        user_containers = get_containers_by_user(username)
                        for container_name in user_containers:
                            try:
                                docker_mgr.delete_container(container_name, force=True)
                                containers_deleted.append(container_name)
                                logger.info(f"✓ Deleted container {container_name} for user {username}")
                            except Exception as e:
                                logger.warning(f"⚠ Failed to delete container {container_name}: {e}")
                    except Exception as e:
                        logger.warning(f"⚠ Failed to get containers for user {username}: {e}")
                
                if delete_user(username):
                    deleted.append(username)
                else:
                    failed.append({'username': username, 'error': 'Database error'})
            
            return jsonify({
                'success': True,
                'deleted': deleted,
                'not_found': not_found,
                'failed': failed,
                'containers_deleted': containers_deleted,
                'count_deleted': len(deleted),
                'count_not_found': len(not_found),
                'count_failed': len(failed),
                'count_containers_deleted': len(containers_deleted)
            }), 200
        except Exception as e:
            logger.error(f"✗ Failed to bulk delete users: {e}")
            return jsonify({'error': str(e)}), 500
    
    # ========================================================================
    # Container Management Endpoints
    # ========================================================================
    
    @api.route('/containers', methods=['GET'])
    @require_auth
    def list_containers():
        """Get all Packet Tracer containers with user assignments"""
        try:
            containers = docker_mgr.list_containers(all=True)
            
            # Add user assignment info to each container
            for container in containers:
                container['users'] = get_users_by_container(container['name'])
            
            return jsonify({
                'success': True,
                'containers': containers,
                'count': len(containers)
            }), 200
        except Exception as e:
            logger.error(f"✗ Failed to list containers: {e}")
            return jsonify({'error': str(e)}), 500
    
    @api.route('/containers', methods=['POST'])
    @require_auth_or_internal
    def create_container_endpoint():
        """Create a new Packet Tracer container and automatically register in Guacamole"""
        try:
            data = request.get_json() or {}
            
            # Get container name
            container_name = data.get('name', '').strip()
            
            # If empty, auto-generate the next number
            if not container_name:
                # Get all existing ptvnc containers to find the next number
                containers = docker_mgr.list_containers()
                
                # Extract numbers from container names like ptvnc1, ptvnc10, etc.
                existing_numbers = []
                for container in containers:
                    name = container.get('name', '')
                    if name.startswith('ptvnc'):
                        suffix = name[5:]  # Everything after 'ptvnc'
                        if suffix.isdigit():
                            existing_numbers.append(int(suffix))
                
                # Find the next available number
                next_number = max(existing_numbers) + 1 if existing_numbers else 1
                container_name = f'ptvnc{next_number}'
                logger.info(f"Auto-generating container name: {container_name}")
            
            # Validate container naming: must start with 'ptvnc'
            if not container_name.startswith('ptvnc'):
                return jsonify({
                    'error': 'Invalid container name. Container names must start with "ptvnc" (e.g., ptvnc1, ptvnc-lab01, ptvnc12345)'
                }), 400
            
            # Validate container name format: only alphanumeric, hyphens, and underscores after 'ptvnc'
            suffix = container_name[5:]  # Everything after 'ptvnc'
            if suffix and not all(c.isalnum() or c in '-_' for c in suffix):
                return jsonify({
                    'error': 'Invalid container name suffix. Only alphanumeric characters, hyphens, and underscores are allowed'
                }), 400
            
            # Check if container already exists
            containers = docker_mgr.list_containers()
            if any(c.get('name') == container_name for c in containers):
                return jsonify({'error': f'Container {container_name} already exists'}), 400
            
            # Optional parameters
            image = data.get('image', 'ptvnc')
            environment = data.get('environment', {})
            # NOTE: Do NOT expose VNC ports to host - Guacamole connects via Docker internal network
            # This allows unlimited containers without port conflicts (multiple containers can use 5901 internally)
            ports = {}  # Force empty ports - VNC is not exposed to host
            
            logger.info(f"Creating container {container_name}...")
            
            # Use docker_mgr to create the container
            result = docker_mgr.create_container(image, container_name, environment, ports)
            
            if result:
                logger.info(f"✓ Successfully created container {container_name}")
                
                # Create symlink to /shared on Desktop for easy access
                try:
                    docker_mgr.exec_in_container(container_name, ['mkdir', '-p', '/home/ptuser/Desktop'])
                    docker_mgr.exec_in_container(container_name, ['ln', '-sf', '/shared', '/home/ptuser/Desktop/shared'])
                    logger.info(f"✓ Created /shared symlink on {container_name} Desktop")
                except Exception as symlink_err:
                    logger.warning(f"⚠ Failed to create /shared symlink: {symlink_err}")
                
                # Automatically register the container in Guacamole
                try:
                    # Generate connection name from container name
                    # Try to extract numeric part for zero-padding (ptvnc5 -> pt05, ptvnc10 -> pt10)
                    # If no numeric part, use the full suffix as connection name (ptvnc-test-vol -> pt-test-vol)
                    suffix = container_name.replace('ptvnc', '')
                    
                    # Check if suffix is numeric
                    if suffix.isdigit():
                        connection_name = f'pt{int(suffix):02d}'
                    else:
                        # For non-numeric suffixes, just use pt prefix
                        connection_name = f'pt{suffix}'
                    
                    vnc_port = data.get('vnc_port', 5901)
                    password = data.get('password', 'Cisco123')
                    
                    logger.info(f"Auto-registering container {container_name} as {connection_name}...")
                    connection_id = create_vnc_connection(connection_name, container_name, vnc_port, password)
                    
                    if connection_id:
                        logger.info(f"✓ Container auto-registered as connection {connection_name}")
                        return jsonify({
                            'success': True,
                            'message': f'Container {container_name} created and registered successfully',
                            'container_name': result,
                            'connection_name': connection_name,
                            'connection_id': connection_id
                        }), 201
                    else:
                        # Container created but registration failed - still return success but with warning
                        logger.warning(f"⚠ Container {container_name} created but registration failed")
                        return jsonify({
                            'success': True,
                            'message': f'Container {container_name} created but registration in Guacamole failed',
                            'container_name': result,
                            'warning': 'Container created but not registered in Guacamole'
                        }), 201
                except Exception as reg_err:
                    logger.warning(f"⚠ Failed to auto-register container: {reg_err}")
                    return jsonify({
                        'success': True,
                        'message': f'Container {container_name} created but registration failed',
                        'container_name': result,
                        'warning': str(reg_err)
                    }), 201
            else:
                logger.error(f"✗ Failed to create container {container_name}")
                return jsonify({'error': 'Failed to create container'}), 500
        except Exception as e:
            logger.error(f"✗ Error creating container: {e}")
            return jsonify({'error': str(e)}), 500
    
    @api.route('/containers/register', methods=['POST'])
    @require_auth_or_internal
    def register_container():
        """Register a container in Guacamole as a VNC connection"""
        try:
            data = request.get_json() or {}
            
            # Required parameters
            container_name = data.get('container_name')
            if not container_name:
                return jsonify({'error': 'container_name is required'}), 400
            
            # Optional parameters with defaults
            connection_name = data.get('connection_name', f'pt{container_name.replace("ptvnc", "")}')
            vnc_port = data.get('vnc_port', 5901)
            password = data.get('password', 'Cisco123')
            
            logger.info(f"Registering container {container_name} as connection {connection_name}...")
            
            # Create VNC connection in Guacamole
            connection_id = create_vnc_connection(connection_name, container_name, vnc_port, password)
            
            if connection_id:
                logger.info(f"✓ Successfully registered container {container_name}")
                return jsonify({
                    'success': True,
                    'message': f'Container {container_name} registered as {connection_name}',
                    'connection_id': connection_id,
                    'connection_name': connection_name
                }), 201
            else:
                logger.error(f"✗ Failed to register container {container_name}")
                return jsonify({'error': 'Failed to register container in Guacamole'}), 500
        except Exception as e:
            logger.error(f"✗ Error registering container: {e}")
            return jsonify({'error': str(e)}), 500
    
    # ========================================================================
    # Container Routes
    # ========================================================================
    
    @api.route('/containers/<container_name>', methods=['GET'])
    @require_auth
    def get_container(container_name):
        """Get container details"""
        try:
            info = docker_mgr.get_container_info(container_name)
            if not info:
                return jsonify({'error': 'Container not found'}), 404
            return jsonify({'success': True, 'container': info}), 200
        except Exception as e:
            logger.error(f"✗ Failed to get container {container_name}: {e}")
            return jsonify({'error': str(e)}), 500

    
    @api.route('/containers/<container_name>/logs', methods=['GET'])
    @require_auth
    def get_container_logs(container_name):
        """Get container logs"""
        try:
            tail = request.args.get('tail', 100, type=int)
            logs = docker_mgr.get_container_logs(container_name, tail=tail)
            return jsonify({'success': True, 'logs': logs}), 200
        except Exception as e:
            logger.error(f"✗ Failed to get logs for {container_name}: {e}")
            return jsonify({'error': str(e)}), 500
    
    @api.route('/containers/<container_name>/start', methods=['POST'])
    @require_auth
    def start_container(container_name):
        """Start a container"""
        try:
            if docker_mgr.start_container(container_name):
                return jsonify({'success': True, 'message': f'Container {container_name} started'}), 200
            else:
                return jsonify({'error': 'Failed to start container'}), 500
        except Exception as e:
            logger.error(f"✗ Failed to start container {container_name}: {e}")
            return jsonify({'error': str(e)}), 500
    
    @api.route('/containers/<container_name>/stop', methods=['POST'])
    @require_auth
    def stop_container(container_name):
        """Stop a container"""
        try:
            if docker_mgr.stop_container(container_name):
                return jsonify({'success': True, 'message': f'Container {container_name} stopped'}), 200
            else:
                return jsonify({'error': 'Failed to stop container'}), 500
        except Exception as e:
            logger.error(f"✗ Failed to stop container {container_name}: {e}")
            return jsonify({'error': str(e)}), 500
    
    @api.route('/containers/<container_name>/restart', methods=['POST'])
    @require_auth
    def restart_container(container_name):
        """Restart a container"""
        try:
            if docker_mgr.restart_container(container_name):
                return jsonify({'success': True, 'message': f'Container {container_name} restarted'}), 200
            else:
                return jsonify({'error': 'Failed to restart container'}), 500
        except Exception as e:
            logger.error(f"✗ Failed to restart container {container_name}: {e}")
            return jsonify({'error': str(e)}), 500
    
    @api.route('/containers/<container_name>', methods=['DELETE'])
    @require_auth
    def delete_container_endpoint(container_name):
        """Delete a container and its Guacamole connection"""
        try:
            # Delete from Docker
            docker_deleted = docker_mgr.delete_container(container_name, force=True)
            
            # Delete from Guacamole - try multiple matching patterns
            # For ptvnc3 -> try pt3, pt03, pt-3, pt-ptvnc3, etc.
            connections_to_check = [
                container_name,                              # ptvnc3
                f"pt-{container_name}",                      # pt-ptvnc3
                container_name.replace('ptvnc', 'pt'),       # pt3
                container_name.replace('ptvnc', 'pt0'),      # pt03
                f"pt-{container_name.replace('ptvnc', '')}",  # pt-3
            ]
            
            guac_deleted = True
            for conn_name in connections_to_check:
                # Check if connection exists
                conn_query = """
                SELECT connection_name FROM guacamole_connection 
                WHERE connection_name = %s
                """
                conn_result = execute_query(conn_query, (conn_name,), fetch_one=True)
                
                if conn_result:
                    logger.info(f"Found matching connection: {conn_name}")
                    if not delete_connection(conn_name):
                        guac_deleted = False
                        logger.warning(f"Failed to delete connection: {conn_name}")
                    else:
                        logger.info(f"✓ Deleted Guacamole connection: {conn_name}")
                        break  # Found and deleted, no need to check other patterns
            
            if docker_deleted:
                message = f'Container {container_name} deleted'
                if guac_deleted:
                    message += ' and removed from Guacamole'
                return jsonify({'success': True, 'message': message}), 200
            else:
                return jsonify({'error': 'Failed to delete container'}), 500
        except Exception as e:
            logger.error(f"✗ Failed to delete container {container_name}: {e}")
            return jsonify({'error': str(e)}), 500
    
    # ========================================================================
    # User Management Endpoints
    # ========================================================================
    
    @api.route('/users/<username>/reset-password', methods=['POST'])
    @require_auth
    def reset_user_password_endpoint(username):
        """Reset a user's password"""
        try:
            data = request.get_json()
            new_password = data.get('password')
            
            if not new_password:
                return jsonify({'error': 'Password is required'}), 400
            
            success, message = reset_user_password(username, new_password)
            
            if success:
                return jsonify({'success': True, 'message': message}), 200
            else:
                return jsonify({'error': message}), 400
        except Exception as e:
            logger.error(f"✗ Failed to reset password for {username}: {e}")
            return jsonify({'error': str(e)}), 500
    
    @api.route('/users/<username>/admin', methods=['POST'])
    @require_auth
    def set_admin_status(username):
        """Set admin status for a user"""
        try:
            data = request.get_json()
            is_admin = data.get('is_admin', False)
            
            if is_admin:
                success = grant_admin_permission(username)
                message = f"Granted admin permission to {username}"
            else:
                success = revoke_admin_permission(username)
                message = f"Revoked admin permission from {username}"
            
            if success:
                return jsonify({'success': True, 'message': message}), 200
            else:
                return jsonify({'error': f'Failed to set admin status for {username}'}), 400
        except Exception as e:
            logger.error(f"✗ Failed to set admin status for {username}: {e}")
            return jsonify({'error': str(e)}), 500
    
    @api.route('/users/<username>/containers', methods=['POST'])
    @require_auth
    def assign_user_containers(username):
        """Assign containers to a user"""
        try:
            data = request.get_json()
            container_names = data.get('containers', [])
            
            if not isinstance(container_names, list):
                return jsonify({'error': 'containers must be a list'}), 400
            
            entity_id = get_user_entity_id(username)
            if not entity_id:
                return jsonify({'error': f'User {username} not found'}), 404
            
            # First, remove all existing container permissions for this user
            remove_query = """
            DELETE FROM guacamole_connection_permission
            WHERE entity_id = %s
            """
            execute_query(remove_query, (entity_id,))
            
            # Assign new containers
            success_count = 0
            failed_containers = []
            
            for container_name in container_names:
                # Convert container name to connection name(s) to try
                # ptvnc1 -> try pt01 first, then pt1
                # ptvnc5 -> try pt05 first, then pt5
                # ptvnc10 -> try pt10 first, then pt10
                # ptvnc-lab -> try pt-lab
                connection_names_to_try = []
                
                if container_name.startswith('ptvnc'):
                    suffix = container_name.replace('ptvnc', '')
                    if suffix.isdigit():
                        # Try both zero-padded and non-padded versions
                        connection_names_to_try.append(f'pt{int(suffix):02d}')  # pt01, pt05, etc.
                        connection_names_to_try.append(f'pt{int(suffix)}')      # pt1, pt5, etc.
                    else:
                        connection_names_to_try.append(f'pt{suffix}')
                
                if not connection_names_to_try:
                    logger.warning(f"⚠ Could not derive connection name from container: {container_name}")
                    failed_containers.append(container_name)
                    continue
                
                # Try to find the connection using one of the names
                conn_result = None
                for connection_name in connection_names_to_try:
                    conn_query = """
                    SELECT connection_id, connection_name FROM guacamole_connection 
                    WHERE connection_name = %s
                    LIMIT 1
                    """
                    conn_result = execute_query(
                        conn_query, 
                        (connection_name,),
                        fetch_one=True
                    )
                    if conn_result:
                        break  # Found it!
                
                if conn_result:
                    connection_id = conn_result['connection_id']
                    
                    try:
                        # Grant READ permission via connection_permission table
                        perm_query = """
                        INSERT INTO guacamole_connection_permission 
                        (entity_id, connection_id, permission)
                        VALUES (%s, %s, 'READ')
                        """
                        execute_query(perm_query, (entity_id, connection_id))
                        success_count += 1
                        logger.info(f"✓ Assigned {conn_result['connection_name']} ({container_name}) to {username}")
                    except Exception as e:
                        logger.error(f"✗ Failed to assign permission for {container_name}: {e}")
                        failed_containers.append(container_name)
                else:
                    logger.warning(f"⚠ Connection not found for {container_name} (tried: {', '.join(connection_names_to_try)})")
                    failed_containers.append(container_name)
            
            logger.info(f"✓ Assigned {success_count} container(s) to {username}")
            return jsonify({
                'success': True, 
                'message': f'Assigned {success_count} container(s) to {username}',
                'containers_assigned': success_count,
                'failed': failed_containers if failed_containers else None
            }), 200
        except Exception as e:
            logger.error(f"✗ Failed to assign containers to {username}: {e}")
            return jsonify({'error': str(e)}), 500
    
    # ========================================================================
    # Resource Management Endpoints
    # ========================================================================
    
    @api.route('/containers/<container_name>/resources', methods=['GET'])
    @require_auth
    def get_container_resources(container_name):
        """Get current resource limits for a container"""
        try:
            # Get container inspect data
            containers = docker_mgr.list_containers(all=True)
            container = next((c for c in containers if c['name'] == container_name), None)
            
            if not container:
                return jsonify({'error': f'Container {container_name} not found'}), 404
            
            # Parse memory and CPU from inspect
            memory_limit = container.get('memory_limit', 'unlimited')
            cpu_limit = container.get('cpu_limit', 'unlimited')
            
            return jsonify({
                'success': True,
                'container': container_name,
                'memory': memory_limit,
                'cpus': cpu_limit
            }), 200
        except Exception as e:
            logger.error(f"✗ Failed to get container resources: {e}")
            return jsonify({'error': str(e)}), 500
    
    @api.route('/containers/<container_name>/resources', methods=['PUT'])
    @require_auth
    def update_container_resources(container_name):
        """Update memory and CPU limits for a specific container"""
        try:
            data = request.get_json()
            memory = data.get('memory', '').strip()
            cpus = data.get('cpus', '')
            
            if not memory or cpus == '':
                return jsonify({'error': 'Both memory and cpus parameters are required'}), 400
            
            # Validate memory format (e.g., 512M, 1G, 2048M)
            if not any(memory.upper().endswith(unit) for unit in ['M', 'G', 'K', 'B']):
                return jsonify({'error': 'Invalid memory format. Use M, G, K, or B suffix (e.g., 512M, 1G)'}), 400
            
            # Validate CPU is numeric
            try:
                cpu_val = float(cpus)
                if cpu_val <= 0:
                    raise ValueError()
            except (ValueError, TypeError):
                return jsonify({'error': 'CPU must be a positive number (e.g., 1, 2, 0.5)'}), 400
            
            # Update the container
            success = docker_mgr.update_container_resources(container_name, memory, cpus)
            
            if success:
                logger.info(f"✓ Updated {container_name} resources: memory={memory}, cpus={cpus}")
                return jsonify({
                    'success': True,
                    'message': f'Updated {container_name} resources',
                    'container': container_name,
                    'memory': memory,
                    'cpus': cpus
                }), 200
            else:
                logger.error(f"✗ Failed to update {container_name} resources")
                return jsonify({'error': 'Failed to update container resources'}), 500
        except Exception as e:
            logger.error(f"✗ Error updating container resources: {e}")
            return jsonify({'error': str(e)}), 500
    
    @api.route('/containers/resources/bulk-update', methods=['PUT'])
    @require_auth
    def bulk_update_container_resources():
        """Update memory and CPU limits for all Packet Tracer containers"""
        try:
            data = request.get_json()
            memory = data.get('memory', '').strip()
            cpus = data.get('cpus', '')
            
            if not memory or cpus == '':
                return jsonify({'error': 'Both memory and cpus parameters are required'}), 400
            
            # Validate memory format
            if not any(memory.upper().endswith(unit) for unit in ['M', 'G', 'K', 'B']):
                return jsonify({'error': 'Invalid memory format. Use M, G, K, or B suffix (e.g., 512M, 1G)'}), 400
            
            # Validate CPU is numeric
            try:
                cpu_val = float(cpus)
                if cpu_val <= 0:
                    raise ValueError()
            except (ValueError, TypeError):
                return jsonify({'error': 'CPU must be a positive number (e.g., 1, 2, 0.5)'}), 400
            
            # Get all ptvnc containers
            containers = docker_mgr.list_containers(all=True)
            pt_containers = [c for c in containers if c['name'].startswith('ptvnc')]
            
            if not pt_containers:
                return jsonify({'error': 'No Packet Tracer containers found'}), 404
            
            # Update all containers
            updated = []
            failed = []
            
            for container in pt_containers:
                try:
                    success = docker_mgr.update_container_resources(container['name'], memory, cpus)
                    if success:
                        updated.append(container['name'])
                        logger.info(f"✓ Updated {container['name']}: memory={memory}, cpus={cpus}")
                    else:
                        failed.append(container['name'])
                        logger.error(f"✗ Failed to update {container['name']}")
                except Exception as e:
                    failed.append(container['name'])
                    logger.error(f"✗ Error updating {container['name']}: {e}")
            
            return jsonify({
                'success': True,
                'message': f'Updated {len(updated)} container(s)',
                'updated': updated,
                'failed': failed if failed else None,
                'memory': memory,
                'cpus': cpus,
                'total_containers': len(pt_containers),
                'updated_count': len(updated)
            }), 200
        except Exception as e:
            logger.error(f"✗ Error in bulk update: {e}")
            return jsonify({'error': str(e)}), 500
    
    # ========================================================================
    # Statistics Endpoint
    # ========================================================================
    
    @api.route('/stats', methods=['GET'])
    @require_auth
    def get_stats():
        """Get statistics about users and containers"""
        try:
            users = get_all_users()
            docker_stats = docker_mgr.get_stats()
            
            return jsonify({
                'success': True,
                'users': {
                    'total': len(users)
                },
                'containers': docker_stats
            }), 200
        except Exception as e:
            logger.error(f"✗ Failed to get stats: {e}")
            return jsonify({'error': str(e)}), 500

    # ========================================================================
    # Logs Endpoint
    # ========================================================================

    @api.route('/logs', methods=['GET'])
    @require_auth
    def get_logs():
        """Get pt-management container logs"""
        try:
            lines = request.args.get('lines', 100, type=int)
            
            # Use Docker socket client directly to get raw logs
            from ptmanagement.docker_mgmt.container import DockerSocketClient
            import socket as sock_module
            import json as json_module
            
            docker_client = DockerSocketClient()
            
            # List all containers to find pt-management
            all_containers = docker_client.list_containers(all=True)
            
            pt_management_id = None
            for container in all_containers:
                names = container.get('Names', [])
                # Docker returns names with leading slash
                if '/pt-management' in names or 'pt-management' in names:
                    pt_management_id = container['Id']
                    break
            
            if not pt_management_id:
                return jsonify({'error': 'Container not found'}), 404
            
            # Get raw logs using socket (the built-in get_logs tries to JSON decode)
            try:
                sock = sock_module.socket(sock_module.AF_UNIX, sock_module.SOCK_STREAM)
                sock.connect(docker_client.socket_path)
                
                logs_path = f"/v1.41/containers/{pt_management_id}/logs?stdout=1&stderr=1&tail={lines}"
                request_line = f"GET {logs_path} HTTP/1.0\r\nHost: localhost\r\n\r\n"
                sock.sendall(request_line.encode('utf-8'))
                
                # Receive response
                response = b''
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response += chunk
                sock.close()
                
                # Parse HTTP response
                response_str = response.decode('utf-8', errors='ignore')
                parts = response_str.split('\r\n\r\n', 1)
                if len(parts) < 2:
                    return jsonify({'error': 'Invalid response format'}), 500
                
                headers, body_raw = parts[0], response[len(parts[0]) + 4:]  # +4 for \r\n\r\n
                
                # Parse Docker log format: [8 bytes header][payload]...
                # Header: [1 stream type][3 padding][4 size in big-endian]
                logs_lines = []
                i = 0
                while i < len(body_raw):
                    if i + 8 <= len(body_raw):
                        # Get the size (bytes 4-7, big-endian)
                        size = int.from_bytes(body_raw[i+4:i+8], 'big')
                        i += 8
                        
                        # Extract the log line
                        if i + size <= len(body_raw):
                            line = body_raw[i:i+size].decode('utf-8', errors='ignore').strip()
                            if line:
                                logs_lines.append(line)
                            i += size
                        else:
                            break
                    else:
                        break
                
                logs_text = '\n'.join(logs_lines[-lines:]) if logs_lines else "No logs available"
                
            except Exception as sock_err:
                logger.error(f"Socket error getting logs: {sock_err}")
                return jsonify({'error': f'Failed to get logs: {str(sock_err)}'}), 500
            
            return jsonify({
                'success': True,
                'logs': logs_text,
                'lines': len(logs_text.splitlines())
            }), 200
        except Exception as e:
            logger.error(f"✗ Failed to get logs: {e}")
            return jsonify({'error': str(e)}), 500

    # ========================================================================
    # Health Check Endpoint
    # ========================================================================

    @api.route('/health-check', methods=['GET', 'POST'])
    @require_auth
    def run_health_check():
        """Run the comprehensive health check script and return results"""
        try:
            import os
            import subprocess
            import socket
            
            # Get the project root from environment variable (default to /project for Docker)
            project_root = os.getenv('PROJECT_ROOT', '/project')
            health_check_path = os.path.join(project_root, 'health_check.sh')
            workdir = project_root
            
            if not os.path.exists(health_check_path):
                logger.error(f"health_check.sh not found at {health_check_path}")
                return jsonify({'error': f'health_check.sh not found at {health_check_path}'}), 404
            
            # Run the health check script
            # The script will use docker commands which are available on the host
            try:
                result = subprocess.run(
                    ['bash', health_check_path],
                    cwd=workdir,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )
                
                output = result.stdout + result.stderr
            except Exception as e:
                logger.error(f"Failed to run health_check.sh: {e}")
                output = f"Error running health check: {str(e)}"
            
            # Parse the output to extract pass/fail counts
            tests_passed = output.count('✅ PASS')
            tests_failed = output.count('❌ FAIL')
            
            # Determine overall status
            overall_status = 'healthy' if tests_failed == 0 else 'degraded' if tests_failed < 5 else 'unhealthy'
            
            logger.info(f"Health check: {tests_passed} passed, {tests_failed} failed, status={overall_status}")
            
            return jsonify({
                'success': True,
                'output': output,
                'tests_passed': tests_passed,
                'tests_failed': tests_failed,
                'overall_status': overall_status,
                'exit_code': result.returncode if 'result' in locals() else -1
            }), 200
        except subprocess.TimeoutExpired:
            logger.error("✗ Health check timed out")
            return jsonify({'error': 'Health check timed out (exceeded 5 minutes)'}), 504
        except Exception as e:
            logger.error(f"✗ Failed to run health check: {e}")
            return jsonify({'error': str(e)}), 500
    
    return api


