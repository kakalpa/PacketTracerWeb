"""API authentication module - validates ptadmin credentials"""

import os
import hashlib
import logging
from ptmanagement.db.connection import get_db_connection

logger = logging.getLogger(__name__)


def md5_hash(text):
    """Generate MD5 hash (used by Guacamole for password hashing)"""
    return hashlib.md5(text.encode()).hexdigest()


def verify_password_hash(password, stored_hash_bytes, stored_salt_bytes):
    """
    Verify a plaintext password against Guacamole's SHA256+salt hash.
    
    Guacamole uses SHA256 with salt: SHA256(password + salt_as_hex_uppercase)
    
    Args:
        password: Plaintext password to verify
        stored_hash_bytes: Binary hash from database
        stored_salt_bytes: Binary salt from database
    
    Returns:
        True if password matches, False otherwise
    """
    try:
        if not stored_salt_bytes:
            logger.warning("No salt found for password verification")
            return False
        
        # Convert salt bytes to uppercase HEX string (this is what Guacamole does)
        salt_hex = stored_salt_bytes.hex().upper()
        
        # Combine password + salt_hex and hash with SHA256
        combined = password + salt_hex
        computed_hash = hashlib.sha256(combined.encode('utf-8')).digest()
        
        # Compare the computed hash with the stored hash
        return computed_hash == stored_hash_bytes
    except Exception as e:
        logger.error(f"Error verifying password: {e}")
        return False


def is_user_admin(username):
    """
    Check if a user has admin (ADMINISTER) permission in Guacamole.
    
    Args:
        username: Username to check
    
    Returns:
        True if user is an admin, False otherwise
    """
    try:
        db = get_db_connection()
        if not db:
            logger.error("Failed to connect to database")
            return False
        
        cursor = db.cursor()
        
        # Get user entity_id
        cursor.execute(
            "SELECT entity_id FROM guacamole_entity WHERE name = %s AND type = 'USER'",
            (username,)
        )
        result = cursor.fetchone()
        
        if not result:
            cursor.close()
            db.close()
            return False
        
        entity_id = result[0]
        
        # Check if user has ADMINISTER permission
        cursor.execute(
            "SELECT permission FROM guacamole_system_permission WHERE entity_id = %s AND permission = 'ADMINISTER'",
            (entity_id,)
        )
        has_admin = cursor.fetchone() is not None
        
        cursor.close()
        db.close()
        return has_admin
    except Exception as e:
        logger.error(f"Error checking admin status for {username}: {e}")
        return False


def verify_user_credentials(username, password):
    """
    Verify user credentials against Guacamole database.
    
    Args:
        username: Username
        password: Password in plaintext
    
    Returns:
        Tuple (success: bool, is_admin: bool)
    """
    try:
        db = get_db_connection()
        if not db:
            logger.error("Failed to connect to database")
            return False, False
        
        cursor = db.cursor()
        
        # Get the entity_id for this username
        cursor.execute(
            "SELECT entity_id FROM guacamole_entity WHERE name = %s AND type = 'USER'",
            (username,)
        )
        entity_result = cursor.fetchone()
        
        if not entity_result:
            logger.warning(f"User {username} not found in entity table")
            cursor.close()
            db.close()
            return False, False
        
        entity_id = entity_result[0]
        
        # Get user's password hash and salt
        cursor.execute(
            "SELECT password_hash, password_salt FROM guacamole_user WHERE entity_id = %s",
            (entity_id,)
        )
        user_result = cursor.fetchone()
        
        if not user_result:
            logger.warning(f"User {username} not found in user table")
            cursor.close()
            db.close()
            return False, False
        
        stored_hash, stored_salt = user_result
        
        # Verify the password using SHA256+salt
        if not verify_password_hash(password, stored_hash, stored_salt):
            logger.warning(f"Invalid password for user {username}")
            cursor.close()
            db.close()
            return False, False
        
        # Get user's admin status
        cursor.execute(
            "SELECT permission FROM guacamole_system_permission WHERE entity_id = %s AND permission = 'ADMINISTER'",
            (entity_id,)
        )
        is_admin = cursor.fetchone() is not None
        
        cursor.close()
        db.close()
        logger.info(f"✓ User {username} authenticated successfully (admin: {is_admin})")
        return True, is_admin
    
    except Exception as e:
        logger.error(f"Error during authentication: {e}")
        return False, False


def verify_ptadmin_credentials(username, password):
    """
    Verify ptadmin credentials - user must be an admin or the default ptadmin user.
    
    Args:
        username: Username
        password: Password in plaintext
    
    Returns:
        True if credentials are valid and user is admin, False otherwise
    """
    # First try the hardcoded ptadmin user (for emergency access)
    ptadmin_password = os.environ.get('PTADMIN_PASSWORD', 'IlovePT')
    
    if username == 'ptadmin' and password == ptadmin_password:
        logger.info(f"✓ Default ptadmin authentication successful")
        return True
    
    # Otherwise, verify against database and check admin status
    success, is_admin = verify_user_credentials(username, password)
    
    if success and is_admin:
        logger.info(f"✓ Admin user {username} authentication successful")
        return True
    elif success and not is_admin:
        logger.warning(f"✗ User {username} authenticated but is not an admin")
        return False
    else:
        logger.warning(f"✗ Authentication failed for user {username}")
        return False
