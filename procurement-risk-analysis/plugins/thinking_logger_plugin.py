"""Thinking logger plugin for tracking agent reasoning."""

import json
import uuid
import pyodbc
from semantic_kernel.functions.kernel_function_decorator import kernel_function

class ThinkingLoggerPlugin:
    """A plugin for logging agent thinking processes."""
    
    def __init__(self, connection_string):
        self.connection_string = connection_string
    
    @kernel_function(description="Log the agent's thinking process")
    def log_agent_thinking(self, agent_name: str, thinking_stage: str, thought_content: str, 
                          conversation_id: str = None, session_id: str = None, 
                          azure_agent_id: str = None, model_deployment_name: str = None) -> str:
        """Logs the agent's thinking process to the database"""
        try:
            # Generate conversation_id if not provided
            if not conversation_id:
                conversation_id = str(uuid.uuid4())
                
            # Connect to database
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            
            # Execute insert query
            cursor.execute("""
                INSERT INTO dim_agent_thinking_log 
                (agent_name, thinking_stage, thought_content, conversation_id, 
                session_id, azure_agent_id, model_deployment_name, created_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE())
            """, (agent_name, thinking_stage, thought_content, conversation_id, 
                  session_id, azure_agent_id, model_deployment_name))
            
            # Commit and close connection
            conn.commit()
            cursor.close()
            conn.close()
            
            return json.dumps({"success": True, "conversation_id": conversation_id})
            
        except Exception as e:
            return json.dumps({"error": str(e)})