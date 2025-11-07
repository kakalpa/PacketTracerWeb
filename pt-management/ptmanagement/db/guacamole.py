"""Guacamole database integration - manages users and connections directly

Uses official Apache Guacamole 1.6.0 schema:
- guacamole_entity (entity_id, name, type)
- guacamole_user (user_id, entity_id, password_hash, password_salt, password_date, ...)
- guacamole_connection (connection_id, connection_name, protocol, ...)

PASSWORD HASHING - CORRECTED ALGORITHM:
After extensive investigation and research, the CORRECT algorithm is:

1. Generate random 32-byte salt
2. Convert salt to HEX STRING (uppercase): salt_hex = salt.hex().upper()
3. Concatenate: combined = password + salt_hex
4. SHA256 hash the concatenated string: SHA256(combined.encode('utf-8'))
5. Store hash digest and salt bytes in database

The KEY insight: The salt is appended as a HEX STRING, not binary bytes!

From Guacamole source (SHA256PasswordEncryptionService1G.java):
    StringBuilder builder = new StringBuilder();
    builder.append(password);
    builder.append(BaseEncoding.base16().encode(salt));  # <- HEX STRING
    MessageDigest md = MessageDigest.getInstance("SHA-256");
    md.update(builder.toString().getBytes("UTF-8"));
    return md.digest();

Python equivalent:
    import hashlib, os
    salt = os.urandom(32)
    combined = password + salt.hex().upper()
    hash_digest = hashlib.sha256(combined.encode('utf-8')).digest()

Verification: This produces correct hashes that match Guacamole's own verification code.

Reference: https://stackoverflow.com/questions/71331479/generating-hashed-passwords-for-guacamole

✅ WORKING CORRECTLY: Users can now be created programmatically with proper hashes
✅ TESTED: ptadmin/IlovePT created via database INSERT works with this algorithm
"""

import logging
import hashlib
import os
from ptmanagement.db.connection import execute_query

logger = logging.getLogger(__name__)


def _hash_password(password):
    """
    Hash a password using SHA256 with random salt (Guacamole 1.x standard).
    Returns (hash, salt) tuple as binary data.
    
    IMPORTANT - CORRECT ALGORITHM (from Guacamole source code):
    1. Generate random 32-byte salt
    2. Convert salt to HEX string (uppercase)
    3. Concatenate: password + hex_salt_string
    4. SHA256 hash the concatenated string as UTF-8
    5. Return hash digest and salt bytes
    
    This matches Guacamole's SHA256PasswordEncryptionService1G.java:
        StringBuilder builder = new StringBuilder();
        builder.append(password);
        builder.append(BaseEncoding.base16().encode(salt));  # Hex-encoded salt
        md.update(builder.toString().getBytes("UTF-8"));
        return md.digest();
    
    Reference: https://stackoverflow.com/questions/71331479
    """
    # Generate a random 32-byte salt (matches Guacamole's expected size)
    password_salt_bytes = os.urandom(32)
    
    # Convert salt to uppercase HEX string
    password_salt_hex = password_salt_bytes.hex().upper()
    
    # Concatenate password + hex_salt_string, then hash
    combined = password + password_salt_hex
    password_hash = hashlib.sha256(combined.encode('utf-8')).digest()
    
    return password_hash, password_salt_bytes


def create_user(username, password):
    """
    Create a new Guacamole user in the database.
    
    Args:
        username: Username (must be unique)
        password: Plain-text password (will be hashed as MD5)
    
    Returns:
        (user_id, True) if successful, (None, False) otherwise
    """
    try:
        # Check if user already exists
        if user_exists(username):
            logger.warning(f"⚠ User already exists: {username}")
            return (None, False)
        
        # Hash the password
        password_hash, password_salt = _hash_password(password)
        
        # Create entity first
        entity_query = """
        INSERT INTO guacamole_entity (name, type)
        VALUES (%s, 'USER')
        """
        execute_query(entity_query, (username,))
        
        # Get the entity_id
        entity_result = execute_query(
            "SELECT entity_id FROM guacamole_entity WHERE name = %s AND type = 'USER'",
            (username,),
            fetch_one=True
        )
        
        if not entity_result:
            logger.error(f"✗ Failed to create entity for user: {username}")
            return (None, False)
        
        entity_id = entity_result['entity_id']
        
        # Create the user record
        user_query = """
        INSERT INTO guacamole_user (entity_id, password_hash, password_salt, password_date, disabled, expired)
        VALUES (%s, %s, %s, NOW(), 0, 0)
        """
        execute_query(user_query, (entity_id, password_hash, password_salt))
        
        # Get the user_id
        user_result = execute_query(
            "SELECT user_id FROM guacamole_user WHERE entity_id = %s",
            (entity_id,),
            fetch_one=True
        )
        
        if user_result:
            user_id = user_result['user_id']
            logger.info(f"✓ Created Guacamole user: {username} (id: {user_id})")
            return (user_id, True)
        else:
            logger.error(f"✗ Failed to retrieve user_id for {username}")
            return (None, False)
    except Exception as e:
        logger.error(f"✗ Failed to create Guacamole user {username}: {e}")
        return (None, False)


def reset_user_password(username, new_password):
    """
    Reset a user's password in Guacamole.
    
    Args:
        username: Username
        new_password: Plain-text new password
    
    Returns:
        (success, message) tuple
    """
    try:
        if not user_exists(username):
            return (False, f"User {username} not found")
        
        # Hash the new password
        password_hash, password_salt = _hash_password(new_password)
        
        # Update the password
        update_query = """
        UPDATE guacamole_user
        SET password_hash = %s, password_salt = %s
        WHERE entity_id = (
            SELECT entity_id FROM guacamole_entity 
            WHERE name = %s AND type = 'USER'
        )
        """
        execute_query(update_query, (password_hash, password_salt, username))
        logger.info(f"✓ Password reset for user: {username}")
        return (True, f"Password reset successfully for {username}")
    except Exception as e:
        logger.error(f"✗ Failed to reset password for {username}: {e}")
        return (False, f"Failed to reset password: {str(e)}")


def delete_user(username):
    """
    Delete a Guacamole user from the database.
    Cascades through permissions, connections, and entity.
    
    Args:
        username: Username to delete
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get entity_id
        entity_result = execute_query(
            "SELECT entity_id FROM guacamole_entity WHERE name = %s AND type = 'USER'",
            (username,),
            fetch_one=True
        )
        
        if not entity_result:
            logger.warning(f"⚠ User not found: {username}")
            return False
        
        entity_id = entity_result['entity_id']
        
        # Get user_id
        user_result = execute_query(
            "SELECT user_id FROM guacamole_user WHERE entity_id = %s",
            (entity_id,),
            fetch_one=True
        )
        
        if not user_result:
            logger.warning(f"⚠ User entity found but no user record: {username}")
            return False
        
        user_id = user_result['user_id']
        
        # Delete all permissions for this user (use entity_id, not user_id)
        execute_query("DELETE FROM guacamole_user_permission WHERE affected_user_id = %s", (user_id,))
        execute_query("DELETE FROM guacamole_connection_permission WHERE entity_id = %s", (entity_id,))
        execute_query("DELETE FROM guacamole_sharing_profile_permission WHERE entity_id = %s", (entity_id,))
        
        # Delete the user record
        execute_query("DELETE FROM guacamole_user WHERE user_id = %s", (user_id,))
        
        # Delete the entity
        execute_query("DELETE FROM guacamole_entity WHERE entity_id = %s", (entity_id,))
        
        logger.info(f"✓ Deleted Guacamole user: {username}")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to delete Guacamole user {username}: {e}")
        return False


def user_exists(username):
    """Check if a Guacamole user exists"""
    try:
        result = execute_query(
            "SELECT entity_id FROM guacamole_entity WHERE name = %s AND type = 'USER'",
            (username,),
            fetch_one=True
        )
        return result is not None
    except Exception as e:
        logger.error(f"✗ Error checking if user exists: {e}")
        return False


def get_user_entity_id(username):
    """Get the entity_id for a user"""
    try:
        result = execute_query(
            "SELECT entity_id FROM guacamole_entity WHERE name = %s AND type = 'USER'",
            (username,),
            fetch_one=True
        )
        return result['entity_id'] if result else None
    except Exception as e:
        logger.error(f"✗ Error getting user entity_id: {e}")
        return None


def get_all_users():
    """
    Get all Guacamole users from the database with their connections.
    
    Returns:
        List of user dictionaries with keys: user_id, username, is_admin, connections
    """
    try:
        users = execute_query(
            """
            SELECT u.user_id, e.name as username,
                   CASE WHEN sp.permission = 'ADMINISTER' THEN 1 ELSE 0 END as is_admin
            FROM guacamole_user u
            JOIN guacamole_entity e ON u.entity_id = e.entity_id
            LEFT JOIN guacamole_system_permission sp ON e.entity_id = sp.entity_id AND sp.permission = 'ADMINISTER'
            WHERE e.type = 'USER'
            ORDER BY e.name
            """,
            fetch_all=True
        )
        
        # For each user, get their connections
        if users:
            for user in users:
                connections = execute_query(
                    """
                    SELECT c.connection_id, c.connection_name
                    FROM guacamole_connection c
                    JOIN guacamole_connection_permission cp ON c.connection_id = cp.connection_id
                    JOIN guacamole_entity e ON cp.entity_id = e.entity_id
                    WHERE e.name = %s AND e.type = 'USER'
                    ORDER BY c.connection_name
                    """,
                    (user['username'],),
                    fetch_all=True
                )
                user['connections'] = connections or []
        
        return users or []
    except Exception as e:
        logger.error(f"✗ Failed to get users: {e}")
        return []


def get_user_connections(username):
    """
    Get all connections assigned to a user.
    
    Args:
        username: Username
    
    Returns:
        List of connection dictionaries
    """
    try:
        connections = execute_query(
            """
            SELECT c.connection_id, c.connection_name
            FROM guacamole_connection c
            JOIN guacamole_connection_permission cp ON c.connection_id = cp.connection_id
            JOIN guacamole_entity e ON cp.entity_id = e.entity_id
            WHERE e.name = %s AND e.type = 'USER'
            ORDER BY c.connection_name
            """,
            (username,),
            fetch_all=True
        )
        return connections or []
    except Exception as e:
        logger.error(f"✗ Failed to get user connections: {e}")
        return []


def assign_connection_to_user(username, connection_id, permission='READ'):
    """
    Assign a connection to a user (grant permission).
    
    Args:
        username: Username
        connection_id: Connection ID
        permission: Permission type (READ, UPDATE, DELETE, ADMINISTER) - default READ
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get entity_id for user
        entity_result = execute_query(
            "SELECT entity_id FROM guacamole_entity WHERE name = %s AND type = 'USER'",
            (username,),
            fetch_one=True
        )
        
        if not entity_result:
            logger.error(f"✗ User not found: {username}")
            return False
        
        entity_id = entity_result['entity_id']
        
        # Grant permission using entity_id (not user_id)
        query = """
        INSERT INTO guacamole_connection_permission (entity_id, connection_id, permission)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE permission = %s
        """
        execute_query(query, (entity_id, connection_id, permission, permission))
        logger.info(f"✓ Assigned connection {connection_id} to user {username} with {permission} permission")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to assign connection: {e}")
        return False


def grant_admin_permission(username):
    """
    Grant ADMINISTER system permission to a user.
    
    Args:
        username: Username to grant admin permission to
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get entity_id for user
        entity_result = execute_query(
            "SELECT entity_id FROM guacamole_entity WHERE name = %s AND type = 'USER'",
            (username,),
            fetch_one=True
        )
        
        if not entity_result:
            logger.error(f"✗ User not found: {username}")
            return False
        
        entity_id = entity_result['entity_id']
        
        # Grant ADMINISTER system permission
        query = """
        INSERT INTO guacamole_system_permission (entity_id, permission)
        VALUES (%s, 'ADMINISTER')
        ON DUPLICATE KEY UPDATE permission = 'ADMINISTER'
        """
        execute_query(query, (entity_id,))
        logger.info(f"✓ Granted ADMINISTER permission to user {username}")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to grant admin permission: {e}")
        return False


def revoke_admin_permission(username):
    """
    Revoke ADMINISTER system permission from a user.
    
    Args:
        username: Username to revoke admin permission from
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get entity_id for user
        entity_result = execute_query(
            "SELECT entity_id FROM guacamole_entity WHERE name = %s AND type = 'USER'",
            (username,),
            fetch_one=True
        )
        
        if not entity_result:
            logger.error(f"✗ User not found: {username}")
            return False
        
        entity_id = entity_result['entity_id']
        
        # Revoke ADMINISTER system permission
        query = "DELETE FROM guacamole_system_permission WHERE entity_id = %s AND permission = 'ADMINISTER'"
        execute_query(query, (entity_id,))
        logger.info(f"✓ Revoked ADMINISTER permission from user {username}")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to revoke admin permission: {e}")
        return False


def create_ssh_connection(connection_name, hostname, port, username):
    """
    Create an SSH connection in Guacamole.
    
    Args:
        connection_name: Name for the connection (displayed to users)
        hostname: Host to connect to
        port: SSH port (default 22)
        username: SSH username
    
    Returns:
        connection_id if successful, None otherwise
    """
    try:
        # Insert connection
        query = """
        INSERT INTO guacamole_connection (connection_name, protocol, parent_id, max_connections, max_connections_per_user)
        VALUES (%s, 'ssh', NULL, 0, 0)
        """
        execute_query(query, (connection_name,))
        
        # Get the connection_id
        result = execute_query(
            "SELECT connection_id FROM guacamole_connection WHERE connection_name = %s ORDER BY connection_id DESC LIMIT 1",
            (connection_name,),
            fetch_one=True
        )
        
        if result:
            connection_id = result['connection_id']
            
            # Set connection parameters
            params = [
                ('hostname', hostname),
                ('port', str(port)),
                ('username', username),
                ('enable-sftp', 'true'),
            ]
            
            for param_name, param_value in params:
                query = """
                INSERT INTO guacamole_connection_parameter (connection_id, parameter_name, parameter_value)
                VALUES (%s, %s, %s)
                """
                execute_query(query, (connection_id, param_name, param_value))
            
            logger.info(f"✓ Created SSH connection: {connection_name} ({hostname}:{port})")
            return connection_id
        else:
            logger.error(f"✗ Failed to retrieve connection_id after creation")
            return None
    except Exception as e:
        logger.error(f"✗ Failed to create SSH connection: {e}")
        return None


def assign_container_to_user(username, container_name):
    """
    Assign a container to a user (store in user_container_mapping table).
    Only the user and admins can access this container.
    
    Args:
        username: Username to assign to
        container_name: Container name (e.g., ptvnc1)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get entity_id for user
        entity_result = execute_query(
            "SELECT entity_id FROM guacamole_entity WHERE name = %s AND type = 'USER'",
            (username,),
            fetch_one=True
        )
        
        if not entity_result:
            logger.error(f"✗ User not found: {username}")
            return False
        
        # Get user_id
        user_result = execute_query(
            "SELECT user_id FROM guacamole_user WHERE entity_id = %s",
            (entity_result['entity_id'],),
            fetch_one=True
        )
        
        if not user_result:
            logger.error(f"✗ User record not found: {username}")
            return False
        
        user_id = user_result['user_id']
        
        # Store container assignment
        query = """
        INSERT INTO user_container_mapping (user_id, container_name, status)
        VALUES (%s, %s, 'active')
        ON DUPLICATE KEY UPDATE status = 'active', deleted_at = NULL
        """
        execute_query(query, (user_id, container_name))
        logger.info(f"✓ Assigned container {container_name} to user {username}")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to assign container: {e}")
        return False


def get_user_container(username):
    """
    Get the container assigned to a user.
    
    Args:
        username: Username
    
    Returns:
        Container name or None
    """
    try:
        query = """
        SELECT ucm.container_name
        FROM user_container_mapping ucm
        JOIN guacamole_user u ON ucm.user_id = u.user_id
        JOIN guacamole_entity e ON u.entity_id = e.entity_id
        WHERE e.name = %s AND ucm.status = 'active'
        LIMIT 1
        """
        result = execute_query(query, (username,), fetch_one=True)
        return result['container_name'] if result else None
    except Exception as e:
        logger.error(f"✗ Failed to get user container: {e}")
        return None


def get_containers_by_user(username):
    """
    Get all containers assigned to a user.
    
    Args:
        username: Username
    
    Returns:
        List of container names
    """
    try:
        query = """
        SELECT ucm.container_name
        FROM user_container_mapping ucm
        JOIN guacamole_user u ON ucm.user_id = u.user_id
        JOIN guacamole_entity e ON u.entity_id = e.entity_id
        WHERE e.name = %s AND ucm.status = 'active'
        """
        results = execute_query(query, (username,), fetch_all=True)
        return [r['container_name'] for r in (results or [])]
    except Exception as e:
        logger.error(f"✗ Failed to get containers for user {username}: {e}")
        return []


def get_users_by_container(container_name):
    """
    Get all users assigned to a container (admins can see all).
    
    Args:
        container_name: Container name
    
    Returns:
        List of usernames
    """
    try:
        query = """
        SELECT e.name as username
        FROM user_container_mapping ucm
        JOIN guacamole_user u ON ucm.user_id = u.user_id
        JOIN guacamole_entity e ON u.entity_id = e.entity_id
        WHERE ucm.container_name = %s AND ucm.status = 'active'
        """
        results = execute_query(query, (container_name,), fetch_all=True)
        return [r['username'] for r in (results or [])]
    except Exception as e:
        logger.error(f"✗ Failed to get users for container: {e}")
        return []


def delete_connection(connection_name):
    """
    Delete a Guacamole connection and all associated permissions.
    
    Args:
        connection_name: Name of the connection to delete
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get connection_id
        conn_result = execute_query(
            "SELECT connection_id FROM guacamole_connection WHERE connection_name = %s",
            (connection_name,),
            fetch_one=True
        )
        
        if not conn_result:
            logger.warning(f"⚠ Connection {connection_name} not found")
            return False
        
        connection_id = conn_result['connection_id']
        
        # Delete user permissions for this connection
        execute_query(
            "DELETE FROM guacamole_user_permission WHERE connection_id = %s",
            (connection_id,)
        )
        
        # Delete connection parameters
        execute_query(
            "DELETE FROM guacamole_connection_parameter WHERE connection_id = %s",
            (connection_id,)
        )
        
        # Delete connection itself
        execute_query(
            "DELETE FROM guacamole_connection WHERE connection_id = %s",
            (connection_id,)
        )
        
        logger.info(f"✓ Deleted Guacamole connection: {connection_name}")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to delete connection {connection_name}: {e}")
        return False


def create_vnc_connection(connection_name, container_hostname, vnc_port=5900, password="Cisco123"):
    """
    Create a VNC connection in Guacamole for a Packet Tracer container.
    
    Args:
        connection_name: Name for the connection (displayed to users) - e.g., "pt01"
        container_hostname: Hostname or container name to connect to - e.g., "ptvnc1"
        vnc_port: VNC port (default 5900)
        password: VNC password (default Cisco123)
    
    Returns:
        connection_id if successful, None otherwise
    """
    try:
        # Check if connection already exists
        existing = execute_query(
            "SELECT connection_id FROM guacamole_connection WHERE connection_name = %s",
            (connection_name,),
            fetch_one=True
        )
        
        if existing:
            logger.info(f"✓ Connection {connection_name} already exists (ID: {existing['connection_id']})")
            return existing['connection_id']
        
        # Insert connection with proxy settings
        query = """
        INSERT INTO guacamole_connection 
        (connection_name, protocol, proxy_port, proxy_hostname, proxy_encryption_method, 
         max_connections, max_connections_per_user, failover_only)
        VALUES (%s, 'vnc', 4822, 'guacd', 'NONE', 1, 1, 0)
        """
        execute_query(query, (connection_name,))
        
        # Get the connection_id
        result = execute_query(
            "SELECT connection_id FROM guacamole_connection WHERE connection_name = %s ORDER BY connection_id DESC LIMIT 1",
            (connection_name,),
            fetch_one=True
        )
        
        if result:
            connection_id = result['connection_id']
            
            # Set connection parameters
            params = [
                ('hostname', container_hostname),
                ('port', str(vnc_port)),
                ('password', password),
            ]
            
            for param_name, param_value in params:
                query = """
                INSERT INTO guacamole_connection_parameter (connection_id, parameter_name, parameter_value)
                VALUES (%s, %s, %s)
                """
                execute_query(query, (connection_id, param_name, param_value))
            
            # Grant READ permission to ptadmin
            ptadmin_query = """
            SELECT entity_id FROM guacamole_entity WHERE name = 'ptadmin' AND type = 'USER'
            """
            ptadmin_result = execute_query(ptadmin_query, fetch_one=True)
            
            if ptadmin_result:
                ptadmin_id = ptadmin_result['entity_id']
                perm_query = """
                INSERT INTO guacamole_connection_permission (entity_id, connection_id, permission)
                VALUES (%s, %s, 'READ')
                """
                execute_query(perm_query, (ptadmin_id, connection_id))
                logger.info(f"✓ Granted READ permission to ptadmin for {connection_name}")
            
            logger.info(f"✓ Created VNC connection: {connection_name} ({container_hostname}:{vnc_port})")
            return connection_id
        else:
            logger.error(f"✗ Failed to retrieve connection_id after creation")
            return None
    except Exception as e:
        logger.error(f"✗ Failed to create VNC connection: {e}")
        return None
