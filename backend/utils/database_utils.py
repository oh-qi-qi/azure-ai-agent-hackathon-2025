# In utils/database_utils.py, implement a connection pool:
import pyodbc
import threading
from config.settings import get_database_connection_string

# Create a thread-local storage for connection pooling
_thread_local = threading.local()

def get_connection():
    """Gets a database connection from the pool.
    
    Returns:
        pyodbc.Connection: The database connection
        
    Raises:
        Exception: If the connection fails
    """
    # Check if this thread already has a connection
    if not hasattr(_thread_local, "connection") or _thread_local.connection is None:
        connection_string = get_database_connection_string()
        try:
            _thread_local.connection = pyodbc.connect(connection_string)
            print("Created new database connection")
        except Exception as e:
            print(f"Error connecting to database: {e}")
            raise
    
    # Test the connection before returning it
    try:
        cursor = _thread_local.connection.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        return _thread_local.connection
    except Exception:
        # Connection is stale, create a new one
        try:
            _thread_local.connection.close()
        except:
            pass
        
        connection_string = get_database_connection_string()
        _thread_local.connection = pyodbc.connect(connection_string)
        print("Created new database connection after stale connection")
        return _thread_local.connection

def execute_query_with_retry(query, params=None, max_retries=3):
    """Executes a database query with retry logic.
    
    Args:
        query: The SQL query to execute
        params: Query parameters (optional)
        max_retries: Maximum number of retry attempts
        
    Returns:
        The query results
        
    Raises:
        Exception: If all retries fail
    """
    retry_count = 0
    last_error = None
    
    while retry_count < max_retries:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
                
            # For SELECT queries, fetch results
            if query.strip().upper().startswith("SELECT"):
                columns = [column[0] for column in cursor.description]
                rows = cursor.fetchall()
                
                # Convert to list of dictionaries
                results = []
                for row in rows:
                    results.append(dict(zip(columns, row)))
                
                cursor.close()
                return results
            
            # For other queries, commit changes
            else:
                conn.commit()
                cursor.close()
                return True
                
        except Exception as e:
            retry_count += 1
            last_error = e
            print(f"Database query failed (attempt {retry_count}/{max_retries}): {e}")
            
            if retry_count < max_retries:
                import time
                time.sleep(0.5)  # Wait before retrying
            else:
                print(f"Failed to execute query after {max_retries} attempts")
                raise last_error
            
def close_connections():
    """Closes all connections in the thread pool."""
    if hasattr(_thread_local, "connection") and _thread_local.connection is not None:
        try:
            _thread_local.connection.close()
            _thread_local.connection = None
            print("Closed thread-local database connection")
        except Exception as e:
            print(f"Error closing connection: {e}")