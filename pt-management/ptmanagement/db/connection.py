"""Database connection module"""

import os
import mysql.connector
from mysql.connector import Error
import logging

logger = logging.getLogger(__name__)


def get_db_connection():
    """
    Get a connection to the MariaDB/MySQL database.
    Uses environment variables: DB_HOST, DB_USER, DB_PASS, DB_NAME
    """
    try:
        connection = mysql.connector.connect(
            host=os.environ.get('DB_HOST', 'guacamole-mariadb'),
            user=os.environ.get('DB_USER', 'ptdbuser'),
            password=os.environ.get('DB_PASS', 'ptdbpass'),
            database=os.environ.get('DB_NAME', 'guacamole_db'),
            raise_on_warnings=False,
            autocommit=True
        )
        return connection
    except Error as e:
        logger.error(f"Database connection failed: {e}")
        return None


def execute_query(query, params=None, fetch_one=False, fetch_all=False):
    """
    Execute a database query and optionally fetch results.
    
    Args:
        query: SQL query string
        params: Optional tuple of parameters for parameterized query
        fetch_one: If True, return one row as dict
        fetch_all: If True, return all rows as list of dicts
    
    Returns:
        If fetch_one: dict or None
        If fetch_all: list of dicts
        Otherwise: None (for INSERT/UPDATE/DELETE)
    """
    connection = get_db_connection()
    if not connection:
        logger.error("Could not establish database connection")
        return None if fetch_all else None
    
    try:
        cursor = connection.cursor(dictionary=True)
        
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        result = None
        if fetch_one:
            result = cursor.fetchone()
        elif fetch_all:
            result = cursor.fetchall()
        
        cursor.close()
        return result
    except Error as e:
        logger.error(f"Query execution failed: {e}")
        logger.error(f"Failed query: {query}")
        if params:
            logger.error(f"Parameters: {params}")
        return None if fetch_all else None
    finally:
        connection.close()
