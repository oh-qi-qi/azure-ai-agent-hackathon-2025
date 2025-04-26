"""Enhanced thinking logger plugin for tracking agent reasoning with more context."""

import json
import uuid
import pyodbc
from datetime import datetime
from semantic_kernel.functions.kernel_function_decorator import kernel_function
from config.settings import get_project_client

class EnhancedThinkingLoggerPlugin:
    """An enhanced plugin for logging agent thinking processes with more contextual information."""
    
    def __init__(self, connection_string):
        self.connection_string = connection_string
    
    @kernel_function(description="Retrieve agent thread id")
    def log_agent_get_thread_id(self) -> str:
        """Logs the agent's thinking process to the database with extended context
     
        Returns:
            latest thread id
        """
        try:
            project_client = get_project_client()
            thread_id = None

            # Get the thread id
            with project_client:
                thread_id = project_client.agents.list_threads(limit=1).first_id
                print(f"Thread ID: {thread_id}")
            
            return thread_id
            
        except Exception as e:
            print(f"Error logging agent thinking: {e}")
            return json.dumps({"error": str(e)})

    @kernel_function(description="Log the agent's thinking process with extended context")
    def log_agent_thinking(self, agent_name: str, thinking_stage: str, thought_content: str, 
                          conversation_id: str = None, session_id: str = None, 
                          azure_agent_id: str = None, model_deployment_name: str = None,
                          thread_id: str = None, user_query: str = None, 
                          status: str = "success") -> str:
        """Logs the agent's thinking process to the database with extended context
        
        Args:
            agent_name: Name of the agent (e.g., SCHEDULER_AGENT)
            thinking_stage: Current thinking stage (e.g., analysis_start)
            thought_content: The agent's thoughts at this stage
            conversation_id: Unique ID for this conversation
            session_id: ID of the current chat session
            azure_agent_id: ID of the Azure AI agent
            model_deployment_name: Name of the model deployment
            thread_id: ID of the Azure thread for this conversation (if available)
            user_query: The original user query that initiated this thinking process
            status: Status of this thinking step (success, error, rate_limited, etc.)
            
        Returns:
            JSON string with the result of the logging operation
        """
        try:
            # Generate conversation_id if not provided
            if not conversation_id:
                conversation_id = str(uuid.uuid4())
                
            # Connect to database
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            
            # Check if the enhanced table exists, if not create it
            self._ensure_enhanced_table_exists(cursor)
            
            # Execute insert query
            cursor.execute("""
                INSERT INTO dim_agent_thinking_log_enhanced
                (agent_name, thinking_stage, thought_content, conversation_id, 
                session_id, azure_agent_id, model_deployment_name, thread_id,
                user_query, status, created_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
            """, (agent_name, thinking_stage, thought_content, conversation_id, 
                  session_id, azure_agent_id, model_deployment_name, thread_id,
                  user_query, status))
            
            # Commit and close connection
            conn.commit()
            cursor.close()
            conn.close()
            
            return json.dumps({"success": True, "conversation_id": conversation_id})
            
        except Exception as e:
            print(f"Error logging agent thinking: {e}")
            return json.dumps({"error": str(e)})
    
    @kernel_function(description="Log an error that occurred during agent thinking")
    def log_agent_error(self, agent_name: str, error_type: str, error_message: str,
                      conversation_id: str = None, session_id: str = None,
                      azure_agent_id: str = None, model_deployment_name: str = None,
                      thread_id: str = None, user_query: str = None) -> str:
        """Logs an error that occurred during agent thinking
        
        Args:
            agent_name: Name of the agent (e.g., SCHEDULER_AGENT)
            error_type: Type of error (e.g., rate_limit, api_error, etc.)
            error_message: Detailed error message
            conversation_id: Unique ID for this conversation
            session_id: ID of the current chat session
            azure_agent_id: ID of the Azure AI agent
            model_deployment_name: Name of the model deployment
            thread_id: ID of the Azure thread for this conversation (if available)
            user_query: The original user query that triggered this error
            
        Returns:
            JSON string with the result of the logging operation
        """
        # Use the log_agent_thinking method with error status
        return self.log_agent_thinking(
            agent_name=agent_name,
            thinking_stage="error",
            thought_content=f"Error type: {error_type}\nError message: {error_message}",
            conversation_id=conversation_id,
            session_id=session_id,
            azure_agent_id=azure_agent_id,
            model_deployment_name=model_deployment_name,
            thread_id=thread_id,
            user_query=user_query,
            status="error"
        )
    
    @kernel_function(description="Retrieves agent thinking logs with enhanced context")
    def get_enhanced_thinking_logs(self, conversation_id: str = None, 
                                 session_id: str = None, 
                                 agent_name: str = None,
                                 limit: int = 100) -> str:
        """Retrieves the enhanced agent thinking logs with filtering options
        
        Args:
            conversation_id: Filter by conversation ID
            session_id: Filter by session ID
            agent_name: Filter by agent name
            limit: Maximum number of logs to return
            
        Returns:
            JSON string with the logs
        """
        try:
            # Connect to database
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            
            # Ensure the table exists
            self._ensure_enhanced_table_exists(cursor)
            
            # Build the WHERE clause based on provided filters
            where_clauses = []
            params = []
            
            if conversation_id:
                where_clauses.append("conversation_id = ?")
                params.append(conversation_id)
            
            if session_id:
                where_clauses.append("session_id = ?")
                params.append(session_id)
            
            if agent_name:
                where_clauses.append("agent_name = ?")
                params.append(agent_name)
            
            # Create the full WHERE clause if any filters were provided
            where_clause = ""
            if where_clauses:
                where_clause = "WHERE " + " AND ".join(where_clauses)
            
            # Execute query
            query = f"""
                SELECT TOP {limit} 
                    thinking_id, agent_name, thinking_stage, thought_content, 
                    conversation_id, session_id, azure_agent_id, model_deployment_name, 
                    thread_id, user_query, status, created_date
                FROM dim_agent_thinking_log_enhanced
                {where_clause}
                ORDER BY created_date DESC
            """
            
            cursor.execute(query, params)
            
            # Fetch results
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()
            
            # Convert to list of dictionaries
            logs = []
            for row in rows:
                logs.append(dict(zip(columns, row)))
            
            # Close connection
            cursor.close()
            conn.close()
            
            # Return as JSON string
            return json.dumps(logs, default=str)
            
        except Exception as e:
            print(f"Error retrieving enhanced thinking logs: {e}")
            return json.dumps({"error": str(e)})
    
    def _ensure_enhanced_table_exists(self, cursor):
        """Ensures that the enhanced thinking log table exists"""
        try:
            # Check if the table exists
            cursor.execute("""
                IF NOT EXISTS (
                    SELECT * FROM sys.tables 
                    WHERE name = 'dim_agent_thinking_log_enhanced'
                )
                BEGIN
                    CREATE TABLE dim_agent_thinking_log_enhanced (
                        thinking_id INT IDENTITY(1,1) PRIMARY KEY,
                        agent_name VARCHAR(100) NOT NULL,
                        thinking_stage VARCHAR(50) NOT NULL,
                        thought_content NVARCHAR(MAX) NOT NULL,
                        conversation_id VARCHAR(100) NOT NULL,
                        session_id VARCHAR(100) NULL,
                        azure_agent_id VARCHAR(100) NULL,
                        model_deployment_name VARCHAR(100) NULL,
                        thread_id VARCHAR(100) NULL,
                        user_query NVARCHAR(MAX) NULL,
                        status VARCHAR(50) DEFAULT 'success',
                        created_date DATETIME DEFAULT GETDATE()
                    )
                END
            """)
            cursor.commit()
        except Exception as e:
            print(f"Error ensuring enhanced table exists: {e}")
            raise