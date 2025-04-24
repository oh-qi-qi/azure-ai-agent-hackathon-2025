"""Database utilities."""

import pyodbc
from config.settings import get_database_connection_string

def get_connection():
    """Gets a database connection.
    
    Returns:
        pyodbc.Connection: The database connection
        
    Raises:
        Exception: If the connection fails
    """
    connection_string = get_database_connection_string()
    try:
        conn = pyodbc.connect(connection_string)
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        raise
