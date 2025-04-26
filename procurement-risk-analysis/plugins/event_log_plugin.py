"""Event logging plugin for tracking agent events and conversations."""

import json
import uuid
import pyodbc
from semantic_kernel.functions.kernel_function_decorator import kernel_function

class EventLogPlugin:
    """A plugin for logging agent events and conversation history."""
    
    def __init__(self, connection_string):
        self.connection_string = connection_string
    
    @kernel_function(description="Logs an agent event for observability")
    def log_agent_event(self, agent_name: str, action: str, result_summary: str = None, 
                       conversation_id: str = None, user_query: str = None, 
                       agent_output: str = None) -> str:
        """Logs an agent event to the database
        
        Args:
            agent_name: Name of the agent (e.g., SCHEDULER_AGENT)
            action: Action being performed (e.g., User Query, Schedule Analysis)
            result_summary: Brief summary of the result
            conversation_id: Unique ID for this conversation
            user_query: The user's question or prompt
            agent_output: The agent's response or output
            
        Returns:
            JSON string with result information
        """
        try:
            # Connect to database
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            
            # Use existing conversation_id or create a new one
            if not conversation_id:
                conversation_id = str(uuid.uuid4())
            
            # Prepare parameters for stored procedure
            params = (agent_name, action, result_summary, conversation_id, user_query, agent_output)
            
            # Execute stored procedure
            cursor.execute("EXEC sp_LogAgentEvent ?, ?, ?, ?, ?, ?", params)
            
            # Commit and close connection
            conn.commit()
            cursor.close()
            conn.close()
            
            # Return success message with the conversation_id
            return json.dumps({"success": True, "conversation_id": conversation_id})
            
        except Exception as e:
            print(f"Error in log_agent_event: {str(e)}")
            return json.dumps({"error": str(e)})
    
    @kernel_function(description="Retrieves conversation history")
    def get_conversation_history(self, conversation_id: str) -> str:
        """Retrieves the conversation history for a specific conversation ID
        
        Args:
            conversation_id: The conversation ID to retrieve history for
            
        Returns:
            JSON string with conversation history
        """
        try:
            # Connect to database
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            
            # Execute query to get conversation history
            cursor.execute("""
                SELECT 
                    log_id, 
                    agent_name, 
                    event_time, 
                    action, 
                    result_summary, 
                    user_query, 
                    agent_output
                FROM 
                    dim_agent_event_log
                WHERE 
                    conversation_id = ?
                ORDER BY 
                    event_time
            """, (conversation_id,))
            
            # Fetch results
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()
            
            # Convert to list of dictionaries
            events = []
            for row in rows:
                events.append(dict(zip(columns, row)))
            
            # Close connection
            cursor.close()
            conn.close()
            
            # Return as JSON string
            return json.dumps({"conversation_id": conversation_id, "events": events}, default=str)
            
        except Exception as e:
            print(f"Error in get_conversation_history: {str(e)}")
            return json.dumps({"error": str(e)})
    
    @kernel_function(description="Retrieves recent conversations")
    def get_recent_conversations(self, limit: int = 10) -> str:
        """Retrieves a list of recent conversations
        
        Args:
            limit: Maximum number of conversations to retrieve
            
        Returns:
            JSON string with recent conversations
        """
        try:
            # Connect to database
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            
            # Execute query to get recent conversations
            cursor.execute(f"""
                SELECT 
                    conversation_id,
                    MIN(event_time) as start_time,
                    MAX(event_time) as end_time,
                    COUNT(*) as event_count,
                    MAX(CASE WHEN action = 'User Query' THEN user_query ELSE NULL END) as last_query
                FROM 
                    dim_agent_event_log
                GROUP BY 
                    conversation_id
                ORDER BY 
                    MAX(event_time) DESC
                OFFSET 0 ROWS
                FETCH NEXT {limit} ROWS ONLY
            """)
            
            # Fetch results
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()
            
            # Convert to list of dictionaries
            conversations = []
            for row in rows:
                conversations.append(dict(zip(columns, row)))
            
            # Close connection
            cursor.close()
            conn.close()
            
            # Return as JSON string
            return json.dumps({"conversations": conversations}, default=str)
            
        except Exception as e:
            print(f"Error in get_recent_conversations: {str(e)}")
            return json.dumps({"error": str(e)})