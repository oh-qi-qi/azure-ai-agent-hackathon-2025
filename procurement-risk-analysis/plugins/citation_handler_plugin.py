"""Plugin for logging and displaying citations from Bing search."""

import json
import uuid
from datetime import datetime
import pyodbc
from semantic_kernel.functions.kernel_function_decorator import kernel_function

class CitationLoggerPlugin:
    """A plugin for logging and displaying citations from Bing search."""
    
    def __init__(self, connection_string=None):
        """Initialize the plugin.
        
        Args:
            connection_string: Database connection string for storing citations
        """
        self.connection_string = connection_string
    
    @kernel_function(description="Log citations to database")
    def log_citations(self, citations_json: str, conversation_id: str, session_id: str = None, thread_id: str = None) -> str:
        """Log citations to database.
        
        Args:
            citations_json: JSON string with citation data
            conversation_id: The conversation ID
            session_id: Optional session ID
            thread_id: Optional thread ID
            
        Returns:
            str: JSON string with the result of the operation
        """
        try:
            if not self.connection_string:
                return json.dumps({"error": "No database connection string provided"})
            
            # Parse the citation data
            try:
                citations = json.loads(citations_json)
            except json.JSONDecodeError:
                return json.dumps({"error": "Invalid JSON in citations_json"})
            
            # Connect to database
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            
            # Check if the table exists
            try:
                cursor.execute("SELECT TOP 1 * FROM dim_citation_log")
                cursor.fetchone()
            except Exception as e:
                # Table might not exist, try to create it
                if "Invalid object name" in str(e):
                    try:
                        cursor.execute("""
                            CREATE TABLE dim_citation_log (
                                citation_id VARCHAR(50) PRIMARY KEY,
                                conversation_id VARCHAR(100) NOT NULL,
                                session_id VARCHAR(100),
                                thread_id VARCHAR(100),
                                source_title VARCHAR(255),
                                source_url VARCHAR(1000),
                                source_name VARCHAR(100),
                                created_date DATETIME DEFAULT GETDATE()
                            )
                        """)
                        conn.commit()
                        print("Created dim_citation_log table")
                    except Exception as create_err:
                        print(f"Error creating table: {create_err}")
                        return json.dumps({"error": f"Could not create table: {str(create_err)}"})
                else:
                    return json.dumps({"error": f"Database error: {str(e)}"})
            
            # Store each citation
            stored_count = 0
            for citation in citations:
                # Generate a unique ID
                citation_id = str(uuid.uuid4())
                
                try:
                    # Insert into the citation log table
                    cursor.execute("""
                        INSERT INTO dim_citation_log
                        (citation_id, conversation_id, session_id, thread_id, 
                         source_title, source_url, source_name, created_date)
                        VALUES
                        (?, ?, ?, ?, ?, ?, ?, GETDATE())
                    """, (
                        citation_id,
                        conversation_id,
                        session_id,
                        thread_id,
                        citation.get("title", "Unknown"),
                        citation.get("url", "None"),
                        citation.get("source", "Unknown")
                    ))
                    
                    stored_count += 1
                except Exception as insert_error:
                    print(f"Error inserting citation: {insert_error}")
            
            # Commit and close
            conn.commit()
            cursor.close()
            conn.close()
            
            return json.dumps({
                "success": True,
                "message": f"Successfully stored {stored_count} citations in database",
                "citation_count": stored_count
            })
            
        except Exception as e:
            print(f"Error logging citations: {e}")
            import traceback
            traceback.print_exc()
            return json.dumps({
                "error": str(e),
                "message": "Failed to log citations to database"
            })
    
    @kernel_function(description="Format citations as markdown")
    def format_citations_as_markdown(self, citations_json: str) -> str:
        """Format citations as markdown.
        
        Args:
            citations_json: JSON string with citation data
            
        Returns:
            str: Formatted citation section as markdown
        """
        try:
            # Parse the citation data
            try:
                citations = json.loads(citations_json)
            except json.JSONDecodeError:
                return "Error: Invalid JSON in citations_json"
            
            # Create formatted citation section
            citation_section = "## References\n\n"
            
            for i, citation in enumerate(citations):
                title = citation.get("title", "Unknown Source")
                url = citation.get("url", "#")
                source = citation.get("source", "Unknown")
                
                citation_section += f"{i+1}. [{title}]({url}) - {source}\n\n"
            
            return citation_section
            
        except Exception as e:
            print(f"Error formatting citations: {e}")
            return f"Error formatting citations: {str(e)}"