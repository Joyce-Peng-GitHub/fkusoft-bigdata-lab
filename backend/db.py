"""Shared MySQL connection settings for publication and read-only API queries."""
import os

import mysql.connector


def database_connection():
    """Open a short-lived database connection using deployment environment.

    Returns:
        mysql.connector.MySQLConnection: Connection owned by the caller.

    Raises:
        mysql.connector.Error: Database is unavailable or credentials are invalid.
    """
    return mysql.connector.connect(
        host=os.getenv('MYSQL_HOST', 'mysql'),
        port=int(os.getenv('MYSQL_PORT', '3306')),
        database=os.getenv('MYSQL_DATABASE', 'bigdata'),
        user=os.getenv('MYSQL_USER', 'course'),
        password=os.getenv('MYSQL_PASSWORD', 'course_dev_only'),
        connection_timeout=5,
    )
