"""Consolidated logging plugin for all agent and event logging."""

import json
import uuid
import pyodbc
from semantic_kernel.functions.kernel_function_decorator import kernel_function
from azure.ai.projects import AIProjectClient

class LoggingPlugin:
    """A consolidated plugin for all logging functions."""
    
    def __init__(self, connection_string):
        self.connection_string = connection_string
        # Store agent ID in memory once retrieved
        self._current_agent_id = None
        self._current_thread_id = None
    
    @kernel_function(description="Get the current agent's ID")
    def log_agent_get_agent_id(self) -> str:
        """Retrieves the current agent's ID from context.
        
        Returns:
            The current agent's ID or a placeholder if not available
        """
        try:
            # If agent ID is already set, return it
            if self._current_agent_id:
                return self._current_agent_id
            
            # Otherwise, return placeholder
            return "AGENT_ID_NOT_SET"
        except Exception as e:
            print(f"Error in log_agent_get_agent_id: {e}")
            return "AGENT_ID_ERROR"
    
    def set_agent_id(self, agent_id: str):
        """Sets the current agent ID.
        
        Args:
            agent_id: The ID to set
        """
        try:
            self._current_agent_id = agent_id
        except Exception as e:
            print(f"Error in set_agent_id: {e}")
    
    @kernel_function(description="Retrieve agent thread id")
    def log_agent_get_thread_id(self) -> str:
        """Retrieves the latest thread ID.
    
        Returns:
            latest thread id or a placeholder if not available
        """
        try:
            # If thread ID is already cached, return it
            if self._current_thread_id:
                return self._current_thread_id
                
            # Try to get it from the project client
            try:
                from config.settings import get_project_client
                
                try:
                    project_client = get_project_client()
                    thread_id = None
    
                    # Get the thread id
                    with project_client:
                        try:
                            threads_list = project_client.agents.list_threads(limit=1)
                            if hasattr(threads_list, 'first_id'):
                                thread_id = threads_list.first_id
                            elif hasattr(threads_list, 'data') and threads_list.data:
                                thread_id = threads_list.data[0].id
                            else:
                                # Handle different response formats
                                threads_data = getattr(threads_list, 'data', None) or []
                                if threads_data and len(threads_data) > 0:
                                    thread_id = threads_data[0].get('id')
                            
                            print(f"Thread ID From Logging Plugin: {thread_id}")
                            
                            # Cache the thread ID for future use
                            if thread_id:
                                self._current_thread_id = thread_id
                        except Exception as e:
                            print(f"Error getting thread ID from client: {e}")
                            return "thread_id_not_available"
                    
                    return thread_id or "thread_id_not_found"
                    
                except Exception as e:
                    print(f"Error getting project client: {e}")
                    return "thread_id_not_available_client_error"
            except ImportError:
                print("Could not import get_project_client")
                return "thread_id_import_error"
                
        except Exception as e:
            print(f"Error getting thread ID: {e}")
            return "thread_id_error"
    
    @kernel_function(description="Log the agent's thinking process with improved error handling")
    def log_agent_thinking(self, agent_name: str, thinking_stage: str, thought_content: str, 
                        conversation_id: str = None, session_id: str = None, 
                        azure_agent_id: str = None, model_deployment_name: str = None,
                        thread_id: str = None, user_query: str = None, 
                        agent_output: str = None, thinking_stage_output: str = None,
                        status: str = "success") -> str:
        """Logs the agent's thinking process to the database with improved error handling.
        
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
            agent_output: The full agent response (including prefix like "POLITICAL_RISK_AGENT > ")
            thinking_stage_output: The output of this specific thinking stage (if different from agent_output)
            status: Status of this thinking step (success, error, rate_limited, etc.)
            
        Returns:
            JSON string with the result of the logging operation
        """
        try:
            import json
            import uuid
            import pyodbc
            
            # Generate conversation_id if not provided
            if not conversation_id:
                conversation_id = str(uuid.uuid4())
            
            # If thread_id is None, try to get it - with error handling
            if thread_id is None:
                try:
                    thread_id = self.log_agent_get_thread_id()
                except Exception as e:
                    print(f"Error getting thread ID: {e}")
                    thread_id = "thread_id_retrieval_error"
            
            # If azure_agent_id is None or "Get by calling log_agent_get_agent_id()", try to get it
            if azure_agent_id is None or azure_agent_id == "Get by calling log_agent_get_agent_id()":
                try:
                    azure_agent_id = self.log_agent_get_agent_id()
                except Exception as e:
                    print(f"Error getting agent ID: {e}")
                    azure_agent_id = "agent_id_retrieval_error"
            
            # Handle non-string thinking_stage_output
            if thinking_stage_output is not None and not isinstance(thinking_stage_output, str):
                try:
                    thinking_stage_output = json.dumps(thinking_stage_output)
                except Exception:
                    # Fallback to string conversion if JSON serialization fails
                    thinking_stage_output = str(thinking_stage_output)
            
            # Handle non-string agent_output
            if agent_output is not None and not isinstance(agent_output, str):
                try:
                    agent_output = json.dumps(agent_output)
                except Exception:
                    # Fallback to string conversion if JSON serialization fails
                    agent_output = str(agent_output)
            
            # Truncate fields that might be too long for the database
            max_text_length = 50000  # Example limit, adjust based on your database field sizes
            
            if thought_content and len(thought_content) > max_text_length:
                thought_content = thought_content[:max_text_length] + "... [TRUNCATED]"
                
            if thinking_stage_output and len(thinking_stage_output) > max_text_length:
                thinking_stage_output = thinking_stage_output[:max_text_length] + "... [TRUNCATED]"
                
            if agent_output and len(agent_output) > max_text_length:
                agent_output = agent_output[:max_text_length] + "... [TRUNCATED]"
            
            try:
                # Connect to database
                conn = pyodbc.connect(self.connection_string)
                cursor = conn.cursor()
                
                # Execute insert query - NOTE: Order matches exactly with table definition
                cursor.execute("""
                    INSERT INTO dim_agent_thinking_log
                    (agent_name, thinking_stage, thought_content, thinking_stage_output, agent_output, 
                    conversation_id, session_id, azure_agent_id, model_deployment_name, thread_id,
                    user_query, status, created_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
                """, (agent_name, thinking_stage, thought_content, thinking_stage_output, agent_output, 
                      conversation_id, session_id, azure_agent_id, model_deployment_name, thread_id,
                      user_query, status))
                
                # Commit and close connection
                conn.commit()
                cursor.close()
                conn.close()
                
                return json.dumps({"success": True, "conversation_id": conversation_id})
                
            except Exception as db_error:
                print(f"Database error in log_agent_thinking: {db_error}")
                
                try:
                    # Log to console as fallback
                    print(f"FALLBACK LOG - Agent: {agent_name}, Stage: {thinking_stage}")
                    print(f"FALLBACK LOG - Conversation: {conversation_id}, Session: {session_id}")
                    print(f"FALLBACK LOG - Content: {thought_content[:200]}...")
                    
                    return json.dumps({
                        "success": False, 
                        "error": str(db_error),
                        "fallback": "Logged to console", 
                        "conversation_id": conversation_id
                    })
                except Exception as fallback_error:
                    print(f"Fallback logging error: {fallback_error}")
                    return json.dumps({"error": f"Database error: {db_error}, Fallback error: {fallback_error}"})
                
        except Exception as e:
            print(f"Error in log_agent_thinking: {e}")
            import traceback
            traceback.print_exc()
            try:
                import json
                return json.dumps({"error": str(e)})
            except:
                return '{"error": "Unknown error in log_agent_thinking"}'

    @kernel_function(description="Log the complete agent response")
    def log_agent_response(self, agent_name: str, response_content: str, 
                           conversation_id: str = None, session_id: str = None,
                           azure_agent_id: str = None, model_deployment_name: str = None,
                           thread_id: str = None, user_query: str = None) -> str:
        """Logs a complete agent response to facilitate debugging
        
        Args:
            agent_name: Name of the agent (e.g., POLITICAL_RISK_AGENT)
            response_content: The full agent response including prefix
            conversation_id: Unique ID for this conversation
            session_id: ID of the current chat session
            azure_agent_id: ID of the Azure AI agent
            model_deployment_name: Name of the model deployment
            thread_id: ID of the Azure thread for this conversation
            user_query: The original user query that prompted this response
            
        Returns:
            JSON string with the result of the logging operation
        """
        # Use log_agent_thinking with specific thinking_stage for responses
        return self.log_agent_thinking(
            agent_name=agent_name,
            thinking_stage="complete_response",
            thought_content=f"Complete response from {agent_name}",
            conversation_id=conversation_id,
            session_id=session_id,
            azure_agent_id=azure_agent_id,
            model_deployment_name=model_deployment_name,
            thread_id=thread_id,
            user_query=user_query,
            agent_output=response_content,  # Store full response in agent_output
            thinking_stage_output=response_content  # Also store in thinking_stage_output
        )
    
    @kernel_function(description="Logs an agent event for observability")
    def log_agent_event(self, agent_name: str, action: str, result_summary: str = None, 
                    conversation_id: str = None, session_id: str = None,
                    user_query: str = None, agent_output: str = None) -> str:
        """Logs an agent event to the database."""
        try:
            # Connect to database
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            
            # Use existing conversation_id or create a new one
            if not conversation_id:
                conversation_id = str(uuid.uuid4())
            
            # Prepare parameters for stored procedure
            params = (agent_name, action, result_summary, conversation_id, 
                    session_id, user_query, agent_output)
            
            # Execute stored procedure
            cursor.execute("EXEC sp_LogAgentEvent ?, ?, ?, ?, ?, ?, ?", params)
            
            # Commit and close connection
            conn.commit()
            cursor.close()
            conn.close()
            
            # Return success message with the conversation_id
            return json.dumps({"success": True, "conversation_id": conversation_id})
            
        except Exception as e:
            print(f"Error in log_agent_event: {str(e)}")
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
    
    @kernel_function(description="Retrieves agent thinking logs")
    def get_agent_thinking_logs(self, conversation_id: str = None, 
                               session_id: str = None, 
                               agent_name: str = None,
                               limit: int = 100) -> str:
        """Retrieves the agent thinking logs with filtering options
        
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
            
            # Execute query with column order matching the table definition
            query = f"""
                SELECT TOP {limit} 
                    thinking_id, agent_name, thinking_stage, thought_content, 
                    thinking_stage_output, agent_output,
                    conversation_id, session_id, azure_agent_id, model_deployment_name, 
                    thread_id, user_query, status, created_date
                FROM dim_agent_thinking_log
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
            print(f"Error retrieving thinking logs: {e}")
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