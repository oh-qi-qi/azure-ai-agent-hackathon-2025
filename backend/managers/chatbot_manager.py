"""Chatbot manager for equipment schedule agent."""

import uuid
import asyncio
import json
import re
import os
import pyodbc
import time
from datetime import datetime
from dotenv import load_dotenv
from typing import Dict, List, Any, Optional, Set

from azure.identity.aio import DefaultAzureCredential
from semantic_kernel.agents import AgentGroupChat
from semantic_kernel.agents import AzureAIAgent
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from config.settings import initialize_ai_agent_settings
from agents.agent_definitions import (
    SCHEDULER_AGENT, get_scheduler_agent_instructions,
    REPORTING_AGENT, get_reporting_agent_instructions,
    ASSISTANT_AGENT, get_assistant_agent_instructions,
    POLITICAL_RISK_AGENT, get_political_risk_agent_instructions,
    TARIFF_RISK_AGENT, get_tariff_risk_agent_instructions,
    LOGISTICS_RISK_AGENT, get_logistics_risk_agent_instructions
)
from agents.agent_strategies import (
    ChatbotSelectionStrategy, ChatbotTerminationStrategy,
    ParallelRiskAnalysisStrategy, RateLimitedExecutor
)
from agents.agent_manager import create_or_reuse_agent
from plugins.schedule_plugin import EquipmentSchedulePlugin
from plugins.risk_plugin import RiskCalculationPlugin
from plugins.logging_plugin import LoggingPlugin
from plugins.report_file_plugin import ReportFilePlugin
from plugins.political_risk_json_plugin import PoliticalRiskJsonPlugin
from plugins.citation_handler_plugin import CitationLoggerPlugin

# Load environment variables from .env file
load_dotenv()

class ChatbotManager:
    """Manages the interactive chatbot for user queries."""
    
    # In ChatbotManager.__init__:
    def __init__(self, connection_string):
        """Initialize the chatbot manager.
        
        Args:
            connection_string: The database connection string.
        """
        self.connection_string = connection_string
        
        # Initialize plugins with proper error handling
        try:
            self.schedule_plugin = EquipmentSchedulePlugin(connection_string)
        except Exception as e:
            print(f"Error initializing schedule plugin: {e}")
            self.schedule_plugin = None
            
        try:
            self.risk_plugin = RiskCalculationPlugin()
        except Exception as e:
            print(f"Error initializing risk plugin: {e}")
            self.risk_plugin = None
            
        try:
            self.logging_plugin = LoggingPlugin(connection_string)
        except Exception as e:
            print(f"Error initializing logging plugin: {e}")
            self.logging_plugin = None
            
        try:
            self.report_file_plugin = ReportFilePlugin(connection_string)
        except Exception as e:
            print(f"Error initializing report file plugin: {e}")
            self.report_file_plugin = None
            
        try:
            self.political_risk_json_plugin = PoliticalRiskJsonPlugin(connection_string)
        except Exception as e:
            print(f"Error initializing political risk JSON plugin: {e}")
            self.political_risk_json_plugin = None
        
        # Session management
        self.chat_sessions = {}
        self._session_lock = asyncio.Lock()
        self._processing_locks = {}
        self._session_tasks = {}
        
        # Rate limiting
        self.rate_limiter = RateLimitedExecutor(max_concurrent=2, requests_per_minute=20)
        
        # Get Bing API key from environment
        self.bing_api_key = os.getenv("BING_SEARCH_API_KEY")
        if not self.bing_api_key:
            print("WARNING: BING_SEARCH_API_KEY not found in environment variables")
    
    def __del__(self):
        """Destructor to ensure resources are cleaned up."""
        try:
            # Create a new event loop for cleanup if none exists
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Run the cleanup in the event loop
            if self.chat_sessions:
                # Use cleanup_sessions not cleanup_all_sessions
                loop.run_until_complete(self.cleanup_sessions(max_age_minutes=0))
                    
            # Cancel any tracked tasks
            for session_id, tasks in self._session_tasks.items():
                for task in tasks:
                    if not task.done():
                        task.cancel()
        except Exception as e:
            print(f"Error in destructor: {e}")

    async def cleanup_all_sessions(self):
        """Cleanup all sessions."""
        session_ids = list(self.chat_sessions.keys())
        for session_id in session_ids:
            await self.close_session(session_id)
    
    # Improve reset_chat_activity in chatbot_manager.py:
    async def reset_chat_activity(self, chat):
        """Reset a chat's activity state to allow it to be used again."""
        print("Resetting chat activity...")
        
        try:
            # Reset internal state variables
            if hasattr(chat, '_current_agent'):
                chat._current_agent = None
                print("Reset _current_agent")
                
            if hasattr(chat, '_current_chat_task'):
                # Cancel the task if it's running
                if chat._current_chat_task and not chat._current_chat_task.done():
                    try:
                        chat._current_chat_task.cancel()
                        print("Cancelled _current_chat_task")
                    except Exception as e:
                        print(f"Error cancelling chat task: {e}")
                chat._current_chat_task = None
                
            if hasattr(chat, '_current_chat_complete'):
                chat._current_chat_complete = False
                print("Reset _current_chat_complete to False")
            
            # Reset _is_active flag if it exists
            if hasattr(chat, '_is_active'):
                chat._is_active = False
                print("Reset _is_active to False")
            
            # Reset turn counter
            if hasattr(chat, '_current_turn'):
                chat._current_turn = 0
                print("Reset _current_turn to 0")
                
            # CRITICAL: Reset termination strategy state
            if hasattr(chat, 'termination_strategy'):
                if hasattr(chat.termination_strategy, 'reset') and callable(chat.termination_strategy.reset):
                    try:
                        chat.termination_strategy.reset()
                        print("Called termination_strategy.reset()")
                    except Exception as e:
                        print(f"Error resetting termination strategy: {e}")
                else:
                    # Manual reset of termination strategy state
                    if hasattr(chat.termination_strategy, '_already_terminated'):
                        chat.termination_strategy._already_terminated = False
                        print("Reset _already_terminated to False")
                        
                    if hasattr(chat.termination_strategy, '_start_time'):
                        chat.termination_strategy._start_time = time.time()
                        print("Reset _start_time")
                        
                    if hasattr(chat.termination_strategy, '_agent_start_times'):
                        chat.termination_strategy._agent_start_times = {}
                        print("Reset _agent_start_times")
                        
                    if hasattr(chat.termination_strategy, '_termination_count'):
                        chat.termination_strategy._termination_count = 0
                        print("Reset _termination_count to 0")
            
            # Make sure the event loop has a chance to process other tasks
            await asyncio.sleep(0)
                    
            print("Chat activity state has been fully reset")
            return True
        except Exception as e:
            print(f"Error resetting chat activity: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def initialize_session(self, session_id):
        """Initialize or reuse a chat session.
        
        Args:
            session_id: The session ID to initialize
            
        Returns:
            dict: The initialized session
        """
        # First check if session exists without locking for efficiency
        if session_id in self.chat_sessions:
            session = self.chat_sessions[session_id]
            if not session.get("initializing", False) and "chat" in session:
                print(f"Reusing existing chat session: {session_id}")
                # Update last activity time
                async with self._session_lock:
                    session["last_activity"] = datetime.now()
                return session
        
        # Now acquire the lock for initialization
        async with self._session_lock:
            # Double-check after acquiring the lock
            if session_id in self.chat_sessions:
                session = self.chat_sessions[session_id]
                if not session.get("initializing", False) and "chat" in session:
                    session["last_activity"] = datetime.now()
                    return session
                elif session.get("initializing", False):
                    # If it's already initializing, wait a moment and let the other thread complete
                    print(f"Session {session_id} is already being initialized, waiting...")
            
            # Now we can start initialization
            print(f"Creating new chat session: {session_id}")
            
            # Generate a conversation ID that will be used for this entire session
            conversation_id = str(uuid.uuid4())
            
            # Mark this session as "initializing" to prevent race conditions
            self.chat_sessions[session_id] = {
                "initializing": True, 
                "last_activity": datetime.now(),
                "conversation_id": conversation_id,
                "cancellation_token": asyncio.Future()  # Add cancellation token
            }
        
        # After this point, we can release the lock as the session is marked as initializing
        try:
            # Get Azure AI Agent settings
            ai_agent_settings = initialize_ai_agent_settings()
            
            # Create credentials and client
            creds = DefaultAzureCredential(
                exclude_environment_credential=True, 
                exclude_managed_identity_credential=True
            )
            client = AzureAIAgent.create_client(credential=creds)
            
            # Create session with all agents
            session = await self._create_agents_for_session(
                client, 
                ai_agent_settings, 
                session_id, 
                conversation_id
            )
            
            # Update the chat session with the full data
            async with self._session_lock:
                # Check if session still exists (might have been cleaned up during initialization)
                if session_id in self.chat_sessions:
                    self.chat_sessions[session_id].update(session)
                    # Return the fully initialized session
                    return self.chat_sessions[session_id]
                else:
                    # Session was cleaned up during initialization
                    await self._cleanup_resources(session)
                    
                    # Recreate the session
                    self.chat_sessions[session_id] = session
                    return self.chat_sessions[session_id]
            
        except Exception as e:
            print(f"Error in initialize_session for {session_id}: {e}")
            import traceback
            traceback.print_exc()
            # Clean up the failed session
            async with self._session_lock:
                if session_id in self.chat_sessions:
                    del self.chat_sessions[session_id]
            raise
    
    async def _create_agents_for_session(self, client, ai_agent_settings, session_id, conversation_id):
        """Create or reuse all agents for a session with added political risk JSON plugin.
        
        Args:
            client: The Azure AI Agent client
            ai_agent_settings: The agent settings
            session_id: The session ID
            conversation_id: The conversation ID
                
        Returns:
            dict: The session data with initialized agents
        """
        # Create credentials
        credential = DefaultAzureCredential(
            exclude_environment_credential=True, 
            exclude_managed_identity_credential=True
        )

        # Create separate logging plugins for each agent
        scheduler_logging = LoggingPlugin(self.connection_string)
        reporting_logging = LoggingPlugin(self.connection_string)
        assistant_logging = LoggingPlugin(self.connection_string)
        political_logging = LoggingPlugin(self.connection_string)
        tariff_logging = LoggingPlugin(self.connection_string)
        logistics_logging = LoggingPlugin(self.connection_string)
        
        # Create the political risk JSON plugin
        political_risk_json_plugin = PoliticalRiskJsonPlugin(self.connection_string)
        citation_logger_plugin = CitationLoggerPlugin()
        
        # Create or reuse all agents
        agents = {}
        
        # Create Bing connection configuration if API key is available
        bing_connection = None
        if self.bing_api_key:
            # Use the direct API key method which is more reliable
            bing_connection = {
                "type": "BingGrounding",
                "api_key": self.bing_api_key
            }
            print(f"Bing connection configured with API key: {'*' * 10}{self.bing_api_key[-4:]}")
        else:
            # Try to get connection name from environment
            bing_connection_name = os.getenv("BING_CONNECTION_NAME")
            if bing_connection_name:
                try:
                    # Get the connection by name
                    print(f"Trying to use named Bing connection: {bing_connection_name}")
                    bing_conn = client.connections.get(connection_name=bing_connection_name)
                    bing_connection = {
                        "type": "BingGrounding",
                        "connection_id": bing_conn.id
                    }
                    print(f"Retrieved Bing connection with ID: {bing_conn.id}")
                except Exception as e:
                    print(f"Error getting Bing connection by name: {e}")
                    print("Bing search will not be available")
            else:
                print("WARNING: Neither BING_SEARCH_API_KEY nor BING_CONNECTION_NAME is set")
                print("Bing search will not be available")
        
        # Create scheduler agent
        print(f"Creating/retrieving scheduler agent for session {session_id}...")
        agents[SCHEDULER_AGENT] = await create_or_reuse_agent(
            client=client,
            agent_name=SCHEDULER_AGENT,
            model_deployment_name=ai_agent_settings.model_deployment_name,
            instructions=get_scheduler_agent_instructions(),
            plugins=[self.schedule_plugin, self.risk_plugin, scheduler_logging]
        )

        # Create political risk agent with Bing search and political risk JSON plugin
        print(f"Creating/retrieving political risk agent for session {session_id}...")
        agents[POLITICAL_RISK_AGENT] = await create_or_reuse_agent(
            client=client,
            agent_name=POLITICAL_RISK_AGENT,
            model_deployment_name=ai_agent_settings.model_deployment_name,
            instructions=get_political_risk_agent_instructions(),
            plugins=[political_logging, political_risk_json_plugin, citation_logger_plugin],  # Added the JSON plugin
            connections=bing_connection
        )

        # Create tariff risk agent with Bing search
        print(f"Creating/retrieving tariff risk agent for session {session_id}...")
        agents[TARIFF_RISK_AGENT] = await create_or_reuse_agent(
            client=client,
            agent_name=TARIFF_RISK_AGENT,
            model_deployment_name=ai_agent_settings.model_deployment_name,
            instructions=get_tariff_risk_agent_instructions(),
            plugins=[tariff_logging],
            connections=bing_connection
        )

        # Create logistics risk agent with Bing search
        print(f"Creating/retrieving logistics risk agent for session {session_id}...")
        agents[LOGISTICS_RISK_AGENT] = await create_or_reuse_agent(
            client=client,
            agent_name=LOGISTICS_RISK_AGENT,
            model_deployment_name=ai_agent_settings.model_deployment_name,
            instructions=get_logistics_risk_agent_instructions(),
            plugins=[logistics_logging],
            connections=bing_connection
        )

        # Create reporting agent with report file plugin
        print(f"Creating/retrieving reporting agent for session {session_id}...")
        agents[REPORTING_AGENT] = await create_or_reuse_agent(
            client=client,
            agent_name=REPORTING_AGENT,
            model_deployment_name=ai_agent_settings.model_deployment_name,
            instructions=get_reporting_agent_instructions(),
            plugins=[self.schedule_plugin, reporting_logging, self.report_file_plugin]
        )

        # Create assistant agent
        print(f"Creating/retrieving assistant agent for session {session_id}...")
        agents[ASSISTANT_AGENT] = await create_or_reuse_agent(
            client=client,
            agent_name=ASSISTANT_AGENT,
            model_deployment_name=ai_agent_settings.model_deployment_name,
            instructions=get_assistant_agent_instructions(),
            plugins=[self.schedule_plugin, self.risk_plugin, assistant_logging]
        )
        
        # Get agent IDs and set them in their respective logging plugins
        agent_ids = self._extract_agent_ids(agents)
        self._set_agent_ids_in_plugins(
            agent_ids,
            scheduler_logging,
            political_logging,
            tariff_logging,
            logistics_logging,
            reporting_logging,
            assistant_logging
        )
        
        # Print agent status
        for agent_name, agent in agents.items():
            print(f"{agent_name} agent ready: {agent.name} (ID: {agent_ids.get(agent_name, 'None')})")
        
        # Create chat objects
        chat = AgentGroupChat(
            agents=list(agents.values()),
            termination_strategy=ChatbotTerminationStrategy(),
            selection_strategy=ChatbotSelectionStrategy()
        )
        
        parallel_chat = AgentGroupChat(
            agents=list(agents.values()),
            termination_strategy=ChatbotTerminationStrategy(),
            selection_strategy=ParallelRiskAnalysisStrategy()
        )
        
        print(f"Chat session created successfully: {session_id}")
        
        # Initialize task tracking list
        self._session_tasks[session_id] = []
        
        # Return session data
        return {
            "chat": chat,
            "parallel_chat": parallel_chat,
            "client": client,
            "credential": credential,
            "last_activity": datetime.now(),
            "model_deployment_name": ai_agent_settings.model_deployment_name,
            "agents": agents,
            "agent_ids": agent_ids,
            "conversation_id": conversation_id,
            "initializing": False,  # Mark as fully initialized
            "cancellation_token": asyncio.Future()  # Add cancellation token
        }

    def _extract_agent_ids(self, agents):
        """Extract agent IDs from agent objects.
        
        Args:
            agents: Dictionary of agent objects
            
        Returns:
            dict: Dictionary of agent IDs
        """
        agent_ids = {}
        for agent_name, agent in agents.items():
            if hasattr(agent, 'definition') and hasattr(agent.definition, 'id'):
                agent_ids[agent_name] = agent.definition.id
            else:
                agent_ids[agent_name] = None
        return agent_ids
    
    def _set_agent_ids_in_plugins(self, agent_ids, scheduler_logging, political_logging, 
                                 tariff_logging, logistics_logging, reporting_logging, assistant_logging):
        """Set agent IDs in their respective logging plugins.
        
        Args:
            agent_ids: Dictionary of agent IDs
            scheduler_logging: Scheduler logging plugin
            political_logging: Political risk logging plugin
            tariff_logging: Tariff risk logging plugin
            logistics_logging: Logistics risk logging plugin
            reporting_logging: Reporting logging plugin
            assistant_logging: Assistant logging plugin
        """
        if agent_ids.get(SCHEDULER_AGENT):
            scheduler_logging.set_agent_id(agent_ids[SCHEDULER_AGENT])
        if agent_ids.get(POLITICAL_RISK_AGENT):
            political_logging.set_agent_id(agent_ids[POLITICAL_RISK_AGENT])
        if agent_ids.get(TARIFF_RISK_AGENT):
            tariff_logging.set_agent_id(agent_ids[TARIFF_RISK_AGENT])
        if agent_ids.get(LOGISTICS_RISK_AGENT):
            logistics_logging.set_agent_id(agent_ids[LOGISTICS_RISK_AGENT])
        if agent_ids.get(REPORTING_AGENT):
            reporting_logging.set_agent_id(agent_ids[REPORTING_AGENT])
        if agent_ids.get(ASSISTANT_AGENT):
            assistant_logging.set_agent_id(agent_ids[ASSISTANT_AGENT])
    
    async def _cleanup_resources(self, session):
        """Clean up resources for a session.
        
        Args:
            session: The session to clean up
        """
        # Close the client if it exists
        if "client" in session:
            client = session["client"]
            if hasattr(client, 'close') and callable(client.close):
                try:
                    await client.close()
                except Exception as e:
                    print(f"Error closing client during cleanup: {e}")
        
        # Close the credential if it exists
        if "credential" in session:
            credential = session["credential"]
            if hasattr(credential, 'close') and callable(credential.close):
                try:
                    await credential.close()
                except Exception as e:
                    print(f"Error closing credentials during cleanup: {e}")
    
    async def process_agent_with_rate_limit(self, chat, agent_name, message_content):
        """Process an agent with rate limiting and timeout.
        
        Args:
            chat: The chat object
            agent_name: The name of the agent to process
            message_content: The message content to send to the agent
            
        Returns:
            The agent's response or None if timeout
        """
        async def execute():
            # Add the message to chat
            msg = ChatMessageContent(
                role=AuthorRole.ASSISTANT,
                name=agent_name,
                content=message_content
            )
            await chat.add_chat_message(msg)
            
            # Get agent response with timeout
            responses = []
            try:
                # Set a timeout for this specific agent
                agent_timeout = 420  # seconds
                
                # Create a task with timeout
                async def get_response():
                    async for response in chat.invoke():
                        if response and hasattr(response, 'name') and response.name == agent_name:
                            responses.append(response)
                            return
                
                # Add retry mechanism
                retry_count = 0
                max_retries = 2
                
                while retry_count <= max_retries:
                    try:
                        # Wait for response with timeout
                        await asyncio.wait_for(get_response(), timeout=agent_timeout)
                        break  # Success, exit the retry loop
                    except asyncio.TimeoutError:
                        retry_count += 1
                        if retry_count <= max_retries:
                            print(f"{agent_name} timeout, retry {retry_count}/{max_retries}")
                            await asyncio.sleep(1)  # Brief pause before retry
                        else:
                            print(f"Timeout waiting for {agent_name} response after {agent_timeout} seconds and {max_retries} retries")
                
            except Exception as e:
                print(f"Error processing {agent_name}: {e}")
            
            return responses[0] if responses else None
        
        # Execute with rate limiting
        return await self.rate_limiter.execute_with_limit(execute)
    
    async def _process_with_timeout(self, chat, latest_responses, timeout_seconds, cancellation_token=None):
        """Process chat invocation with timeout, adding responses to latest_responses dictionary.
        
        Args:
            chat: The chat to process
            latest_responses: Dictionary to store the latest responses from each agent
            timeout_seconds: Timeout in seconds
            cancellation_token: Optional cancellation token
        """
        start_time = time.time()
        scheduler_attempts = 0
        max_scheduler_attempts = 2
        
        try:
            # Track all running tasks to ensure proper cleanup
            running_tasks = set()
            
            async def process_stream():
                nonlocal scheduler_attempts
                
                try:
                    async for response in chat.invoke():
                        # Check for cancellation
                        if cancellation_token and cancellation_token.done():
                            print("Processing cancelled via token")
                            return
                            
                        # Check for timeout
                        if time.time() - start_time > timeout_seconds:
                            print(f"Process timeout after {timeout_seconds} seconds")
                            return
                            
                        if response is None:
                            continue
                        if not hasattr(response, 'name') or not response.name:
                            continue
                        
                        agent_name = response.name
                        latest_responses[agent_name] = response
                        
                        # Count scheduler attempts to avoid infinite loops
                        if agent_name == SCHEDULER_AGENT:
                            scheduler_attempts += 1
                            if scheduler_attempts >= max_scheduler_attempts:
                                print(f"Reached maximum scheduler attempts ({max_scheduler_attempts})")
                        
                        # Check if we've got responses from all expected agents
                        if all(agent in latest_responses for agent in [SCHEDULER_AGENT, REPORTING_AGENT]):
                            print("Received responses from all required agents, terminating early")
                            return
                            
                except asyncio.CancelledError:
                    print("Process stream task was cancelled")
                    raise
                except Exception as e:
                    print(f"Error in process_stream: {e}")
                    import traceback
                    traceback.print_exc()
                finally:
                    # Remove this task from the running set when done
                    if process_task in running_tasks:
                        running_tasks.remove(process_task)
            
            # Create the main processing task
            process_task = asyncio.create_task(process_stream())
            running_tasks.add(process_task)
            
            # Create a timeout task
            timeout_task = asyncio.create_task(asyncio.sleep(timeout_seconds))
            
            # Set up tasks to wait for
            wait_tasks = {process_task, timeout_task}
            
            # Add cancellation token if provided
            if cancellation_token:
                # Create a task that will complete when the cancellation token is done
                async def wait_for_cancellation():
                    # Wait for the future to complete
                    await asyncio.shield(cancellation_token)
                    return True
                    
                cancellation_task = asyncio.create_task(wait_for_cancellation())
                wait_tasks.add(cancellation_task)
            
            # Wait for completion or timeout
            done, pending = await asyncio.wait(
                wait_tasks,
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel any pending tasks
            for task in pending:
                task.cancel()
                
            # Clean up running tasks if needed
            for task in running_tasks.copy():
                if not task.done():
                    task.cancel()
                    
            # Handle timeout
            if timeout_task in done:
                print(f"Process timed out after {timeout_seconds} seconds")
            
            # Handle cancellation
            if cancellation_token and cancellation_token.done():
                print("Process was cancelled")
            
        except asyncio.TimeoutError:
            print(f"Process timed out after {timeout_seconds} seconds")
        except Exception as e:
            print(f"Error during _process_with_timeout: {e}")
            import traceback
            traceback.print_exc()

    async def generate_report_directly(self, session, risk_agent_name, latest_responses, conversation_id, session_id, original_message):
        """Directly invokes the reporting agent with improved political risk integration.
        
        Args:
            session: The session data
            risk_agent_name: The name of the risk agent
            latest_responses: Dictionary of the latest responses from each agent
            conversation_id: The conversation ID
            session_id: The session ID
            original_message: The original user message
            
        Returns:
            bool: True if report generation was successful
        """
        try:
            print("Attempting direct report generation as fallback")

            # Get the reporting agent from the session
            if REPORTING_AGENT not in session["agents"]:
                print("Reporting agent not found in session")
                return False

            reporting_agent = session["agents"][REPORTING_AGENT]

            # Get content from available agents
            risk_content = ""
            if risk_agent_name in latest_responses:
                risk_content = latest_responses[risk_agent_name].content.replace(f"{risk_agent_name} > ", "")

            scheduler_content = ""
            if SCHEDULER_AGENT in latest_responses:
                scheduler_content = latest_responses[SCHEDULER_AGENT].content.replace("SCHEDULER_AGENT > ", "")

            # Extract schedule data from scheduler content
            schedule_data = self._extract_schedule_data(scheduler_content)

            # Check if there's political risk JSON data available
            political_risk_data = None
            political_risk_table = None
            
            # First, try to extract the political risk table directly from the content
            if risk_agent_name == POLITICAL_RISK_AGENT and risk_content:
                # Extract the political risk table if available
                import re
                table_match = re.search(r'Political Risk Table(.*?)(?=###|$)', risk_content, re.DOTALL)
                if table_match:
                    political_risk_table = table_match.group(1).strip()
                    print(f"Extracted political risk table: {len(political_risk_table)} characters")
            
            # Then try to get structured data from the database
            if risk_agent_name == POLITICAL_RISK_AGENT:
                try:
                    # Query the event log for political risk JSON data
                    conn = pyodbc.connect(self.connection_string)
                    cursor = conn.cursor()
                    
                    # Look for political risk JSON data for this conversation
                    cursor.execute("""
                        SELECT TOP 1 agent_output
                        FROM dim_agent_event_log
                        WHERE agent_name = 'POLITICAL_RISK_AGENT'
                        AND action = 'Political Risk JSON Data'
                        AND conversation_id = ?
                        ORDER BY event_time DESC
                    """, (conversation_id,))
                    
                    row = cursor.fetchone()
                    if row and row[0]:
                        try:
                            political_risk_data = json.loads(row[0])
                            print(f"Retrieved political risk JSON data with {len(political_risk_data.get('political_risks', []))} risks")
                        except Exception as json_error:
                            print(f"Error parsing political risk JSON data: {json_error}")
                    
                    cursor.close()
                    conn.close()
                except Exception as db_error:
                    print(f"Error retrieving political risk data: {db_error}")
            
            # Prepare additional context for political risk data
            political_risk_context = ""
            
            # Add the table if available
            if political_risk_table:
                political_risk_context += "\n\n### POLITICAL RISK TABLE:\n" + political_risk_table
                
            # Add the structured data if available
            if political_risk_data:
                political_risk_context += "\n\n### STRUCTURED POLITICAL RISK DATA:\n```json\n"
                political_risk_context += json.dumps(political_risk_data, indent=2)
                political_risk_context += "\n```\n\n"
                
            # Add explicit instructions to include the political risk data
            if political_risk_context:
                political_risk_context += "\nIMPORTANT: Include the above political risk data in your report. Make sure to include the full political risk table in the Political Risk Analysis section.\n"

            # Format schedule data if available
            schedule_context = ""
            if schedule_data:
                schedule_context = "\n\n### STRUCTURED SCHEDULE DATA:\n```json\n"
                schedule_context += json.dumps(schedule_data, indent=2)
                schedule_context += "\n```\n\n"

            # Create input for reporting agent
            report_input = f"""
            I need to generate a comprehensive risk report based on the available data.

            SETUP INFORMATION:
            - azure_agent_id: "REPORTING_AGENT"
            - thread_id: "thread_unknown"
            - conversation_id: "{conversation_id}"
            - session_id: "{session_id}"

            DATA SOURCES:
            
            SCHEDULER DATA:
            {scheduler_content}
            {schedule_context}

            RISK ANALYSIS:
            {risk_content}
            {political_risk_context}

            CRITICAL FORMATTING INSTRUCTIONS:
            1. ONLY include the final report in your response - no debugging info, no step explanations
            2. Format the report professionally with clear sections
            3. If political risk data is available, include the complete political risk table
            4. Make sure tables are formatted properly with even column widths
            5. Keep your tables simple enough to display well in word format
            6. For political risks, directly quote from the political risk agent's analysis
            7. Include the file information block at the end

            FORMAT YOUR REPORT WITH THESE EXACT SECTIONS:
            1. Executive Summary
            2. Comprehensive Risk Summary Table (keep this simple with 4-5 columns max)
            3. Detailed Risk Analysis by Category
            - A. Schedule Risk Analysis
            - B. Political Risk Analysis (include the full political risk table)
            - C. Other Risk Types (if available)
            4. Consolidated Recommendations

            When saving reports, use these parameters:
            - session_id: "{session_id}"
            - conversation_id: "{conversation_id}"
            - report_title: "Comprehensive Equipment Schedule Risk Analysis"
            
            Include file information at the end in this format:
            
            ```
            📄 Report Generated Successfully
            
            Filename: [filename]
            Download URL: [blob_url]
            Report ID: [report_id]
            ```
            
            If file saving fails, use this format instead:
            ```
            ⚠️ Report Generation Notice
            
            The report was generated but could not be saved to a file.
            Please try again or contact support if the issue persists.
            ```
            """

            # Invoke the reporting agent directly with timeout
            try:
                reporting_timeout = 420
                reporting_response = await asyncio.wait_for(
                    reporting_agent.invoke(report_input),
                    timeout=reporting_timeout
                )

                if reporting_response:
                    # Format as a ChatMessageContent
                    # Check if response already has the prefix
                    if not reporting_response.startswith("REPORTING_AGENT >"):
                        formatted_response = f"REPORTING_AGENT > {reporting_response}"
                    else:
                        formatted_response = reporting_response
                    
                    # Clean the response to remove any debugging info
                    cleaned_response = f"REPORTING_AGENT > {self._clean_report_output(reporting_response)}"
                    
                    latest_responses[REPORTING_AGENT] = ChatMessageContent(
                        role=AuthorRole.ASSISTANT,
                        name=REPORTING_AGENT,
                        content=cleaned_response
                    )
                    print("Successfully generated report through direct agent invocation")

                    # Store the directly generated report in the event log
                    await self._store_agent_output(
                        session_id=session_id,
                        agent_name=REPORTING_AGENT,
                        agent_output=cleaned_response,
                        action="Direct Report Generation"
                    )

                    # Log this action
                    try:
                        self.logging_plugin.log_agent_event(
                            agent_name="SYSTEM",
                            action="Direct Report Generation",
                            result_summary="Used direct agent invocation to generate report when normal flow failed",
                            conversation_id=conversation_id,
                            session_id=session_id,
                            user_query=original_message,
                            agent_output=cleaned_response
                        )
                    except Exception as e:
                        print(f"Error logging direct report generation: {e}")

                    return True
            except asyncio.TimeoutError:
                print(f"Direct reporting agent invocation timed out after {reporting_timeout} seconds")
            except Exception as e:
                print(f"Error during direct reporting agent invocation: {e}")

        except Exception as e:
            print(f"Direct report generation failed: {e}")
            import traceback
            traceback.print_exc()

        return False

    def _extract_schedule_data(self, scheduler_content):
        """Extract structured schedule data from scheduler content.
        
        Args:
            scheduler_content: The scheduler agent's output content
            
        Returns:
            dict: Structured schedule data or None if extraction fails
        """
        try:
            # Try to find JSON in the response
            json_match = re.search(r'```json\s*(.*?)\s*```', scheduler_content, re.DOTALL)
            
            if json_match:
                # Extract the JSON string
                try:
                    json_data = json.loads(json_match.group(1))
                    return json_data
                except Exception as e:
                    print(f"Error parsing JSON: {e}")
            
            # If JSON extraction failed, try to extract structured data from Markdown table
            table_pattern = r'\|\s*Equipment Code\s*\|\s*Equipment Name\s*\|\s*P6 Due Date\s*\|\s*Delivery Date\s*\|\s*Variance \(days\)\s*\|\s*Risk %\s*\|\s*Risk Level\s*\|(.*?)(?=\n\n|$)'
            table_match = re.search(table_pattern, scheduler_content, re.DOTALL)
            
            if table_match:
                table_content = table_match.group(1)
                # Extract rows
                rows = re.findall(r'\|\s*(\d+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|', table_content)
                
                equipment_items = []
                for row in rows:
                    if len(row) >= 7:
                        item = {
                            "code": row[0].strip(),
                            "name": row[1].strip(),
                            "p6DueDate": row[2].strip(),
                            "deliveryDate": row[3].strip(),
                            "variance": row[4].strip(),
                            "riskPercentage": row[5].strip(),
                            "riskLevel": row[6].strip()
                        }
                        equipment_items.append(item)
                
                # Create structured data
                return {
                    "equipmentItems": equipment_items
                }
            
            return None
        except Exception as e:
            print(f"Error extracting schedule data: {e}")
            return None
    
    async def process_message(self, session_id, message):
        """Process a user message and return the appropriate response.
        
        Args:
            session_id: The session ID
            message: The user message
            
        Returns:
            dict: The response data
        """
        # Create session-specific lock if it doesn't exist
        if session_id not in self._processing_locks:
            self._processing_locks[session_id] = asyncio.Lock()
        
        # Variables to track resources to be cleaned up
        response = None
        session_to_close = None
        
        # Acquire the processing lock for this session
        async with self._processing_locks[session_id]:
            try:
                # Initialize or get existing session
                session = await self._prepare_session(session_id)
                if "status" in session and session["status"] == "error":
                    return session
                
                # Get conversation details and model name
                conversation_id = session.get("conversation_id", str(uuid.uuid4()))
                model_deployment_name = session.get("model_deployment_name", "unknown")
                
                # Log the user query
                await self._log_user_query(conversation_id, session_id, message)
                
                # Update last activity time
                async with self._session_lock:
                    session["last_activity"] = datetime.now()
                
                # Analyze the query type
                query_type = self._analyze_query_type(message)
                
                # Create user message
                user_message = self._create_user_message(
                    message, 
                    conversation_id, 
                    session_id, 
                    model_deployment_name
                )
                
                # Process based on query type
                if query_type["is_specific_risk"]:
                    response = await self._process_specific_risk_query(
                        session, 
                        user_message, 
                        query_type["risk_type"],
                        conversation_id,
                        session_id,
                        message
                    )
                elif query_type["is_comprehensive_risk"]:
                    response = await self._process_comprehensive_risk_query(
                        session, 
                        user_message, 
                        conversation_id,
                        session_id,
                        message
                    )
                else:
                    response = await self._process_standard_query(
                        session, 
                        user_message, 
                        query_type["is_schedule_related"],
                        conversation_id,
                        session_id,
                        message
                    )
                
                # Log the assistant's response
                await self._log_assistant_response(
                    conversation_id, 
                    session_id, 
                    message, 
                    response.get("response", "")
                )
                
                # CRITICAL: Check if chat has been completed after processing
                if "chat" in session:
                    chat = session["chat"]
                    if hasattr(chat, "termination_strategy") and hasattr(chat.termination_strategy, "_already_terminated"):
                        if chat.termination_strategy._already_terminated:
                            print(f"Chat session {session_id} has been terminated, will close resources after response")
                            # Mark the session for closing after we return the response
                            session_to_close = session_id
                    
                return response
                    
            except Exception as e:
                return await self._handle_process_message_error(e, session_id, message, conversation_id)
            finally:
                # Clean up processing locks and tasks
                await self._clean_up_after_processing(session_id)
                
                # IMPORTANT: If the session was terminated, close it SYNCHRONOUSLY here
                # This ensures the close operation completes before we return
                if session_to_close:
                    print(f"Closing terminated session {session_to_close} synchronously")
                    try:
                        await self.close_session(session_to_close)
                    except Exception as e:
                        print(f"Error closing session {session_to_close}: {e}")
    
    async def _store_agent_output(self, session_id, agent_name, agent_output, action="Complete Analysis"):
        """Store agent output in the event log.
        
        Args:
            session_id: The session ID
            agent_name: The name of the agent
            agent_output: The agent's output
            action: The action label for this output
            
        Returns:
            bool: True if storage was successful
        """
        try:
            # Get conversation ID from session
            conversation_id = None
            if session_id in self.chat_sessions:
                conversation_id = self.chat_sessions[session_id].get("conversation_id")
            
            if not conversation_id:
                print(f"Warning: No conversation ID found for session {session_id}")
                conversation_id = str(uuid.uuid4())  # Generate one as fallback
            
            print(f"Storing {agent_name} output in event log (length: {len(agent_output)})")
            
            # Log the output in the event log
            log_result = self.logging_plugin.log_agent_event(
                agent_name=agent_name,
                action=action,
                result_summary=f"{agent_name} generated output: {agent_output[:100]}...",
                conversation_id=conversation_id,
                session_id=session_id,
                user_query=None,  # No direct user query to this agent
                agent_output=agent_output
            )
            
            # Parse the result
            result = json.loads(log_result)
            if result.get("success"):
                print(f"Successfully stored {agent_name} output in event log")
                return True
            else:
                print(f"Failed to store {agent_name} output: {result.get('error')}")
                return False
        
        except Exception as e:
            print(f"Error storing {agent_name} output: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def wait_for_tasks(self, tasks, timeout=10):
        """Properly wait for tasks to complete with timeout.
        
        Args:
            tasks: List of tasks to wait for
            timeout: Timeout in seconds
            
        Returns:
            tuple: (done, pending) tasks
        """
        if not tasks:
            return [], []
            
        try:
            return await asyncio.wait(tasks, timeout=timeout)
        except asyncio.TimeoutError:
            print(f"Timeout waiting for {len(tasks)} tasks")
            return [], tasks

    async def _prepare_session(self, session_id):
        """Prepare a session for processing.
        
        Args:
            session_id: The session ID
            
        Returns:
            dict: The prepared session or error response
        """
        try:
            # Get or initialize the chat session
            session = await self.initialize_session(session_id)
            
            # Wait if session is still initializing
            retry_count = 0
            max_retry = 50
            while session.get("initializing", False) and retry_count < max_retry:
                await asyncio.sleep(0.1)
                
                # Re-get the session in case it was updated
                if session_id in self.chat_sessions:
                    session = self.chat_sessions[session_id]
                else:
                    break
                    
                retry_count += 1
            
            if session.get("initializing", False):
                return {
                    "status": "error",
                    "error": f"Session initialization timed out after {max_retry * 0.1} seconds. Please try again.",
                    "conversation_id": None
                }
            
            # Make sure the session has a chat object
            if "chat" not in session:
                # Session exists but no chat object - reinitialize
                print(f"Session {session_id} exists but has no chat object, reinitializing...")
                async with self._session_lock:
                    if session_id in self.chat_sessions:
                        del self.chat_sessions[session_id]
                session = await self.initialize_session(session_id)
            
            # Reset the cancellation token for this new message
            if "cancellation_token" in session and session["cancellation_token"].done():
                async with self._session_lock:
                    session["cancellation_token"] = asyncio.Future()
            
            return session
        except Exception as e:
            print(f"Error preparing session: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "error": f"Failed to prepare session: {str(e)}",
                "conversation_id": None
            }
    
    async def _log_user_query(self, conversation_id, session_id, message):
        """Log a user query.
        
        Args:
            conversation_id: The conversation ID
            session_id: The session ID
            message: The user message
        """
        try:
            self.logging_plugin.log_agent_event(
                agent_name="Chatbot",
                action="User Query",
                result_summary=f"Processing user query: {message}",
                conversation_id=conversation_id,
                session_id=session_id,
                user_query=message
            )
        except Exception as e:
            print(f"Error logging agent event: {e}")
    
    def _analyze_query_type(self, message):
        """Analyze the type of query.
        
        Args:
            message: The user message
            
        Returns:
            dict: The query type information
        """
        # Check if this is a comprehensive risk analysis request
        is_comprehensive_risk = any(
            keyword in message.lower() 
            for keyword in ["all risks", "comprehensive", "full risk", "complete risk", "risk analysis"]
        )
        
        # Check if the message is schedule-related
        is_schedule_related = any(
            keyword in message.lower() 
            for keyword in ["schedule risk","schedule", "delay", "variance", "late", "delivery", "milestone"]
        )
        
        # Determine specific risk type queries
        is_political_risk = any(
            keyword in message.lower() 
            for keyword in ["political risk","politics", "politic", "political risks", "government", "political unrest"]
        )
        is_tariff_risk = any(
            keyword in message.lower() 
            for keyword in ["tariff risk", "tariff risks", "trade risk", "customs", "import duties"]
        )
        is_logistics_risk = any(
            keyword in message.lower() 
            for keyword in ["logistics risk", "logistics risks", "shipping risk", "port risk"]
        )
        
        # Determine if this requires a specific risk agent
        is_specific_risk = is_political_risk or is_tariff_risk or is_logistics_risk
        
        # Determine the risk type
        risk_type = None
        if is_political_risk:
            risk_type = POLITICAL_RISK_AGENT
        elif is_tariff_risk:
            risk_type = TARIFF_RISK_AGENT
        elif is_logistics_risk:
            risk_type = LOGISTICS_RISK_AGENT
        
        return {
            "is_comprehensive_risk": is_comprehensive_risk,
            "is_schedule_related": is_schedule_related,
            "is_specific_risk": is_specific_risk,
            "risk_type": risk_type
        }
    
    def _create_user_message(self, message, conversation_id, session_id, model_deployment_name):
        """Create a user message with context for the agents.
        
        Args:
            message: The user message
            conversation_id: The conversation ID
            session_id: The session ID
            model_deployment_name: The model deployment name
            
        Returns:
            ChatMessageContent: The formatted user message
        """
        return ChatMessageContent(
            role=AuthorRole.USER, 
            content=f"""USER > {message}
            When logging your thinking with log_agent_thinking, use these parameters:
            - conversation_id: "{conversation_id}"
            - session_id: "{session_id}"
            - model_deployment_name: "{model_deployment_name}"
            
            When saving reports, use these parameters:
            - session_id: "{session_id}"
            - conversation_id: "{conversation_id}"
            """
        )
    
    async def _process_specific_risk_query(self, session, user_message, risk_type, conversation_id, session_id, original_message):
        """Process a specific risk query with thread ID tracking."""
        print(f"Processing specific risk query: {risk_type}")
        
        # Get the chat and cancellation token
        chat = session["chat"]
        cancellation_token = session.get("cancellation_token")
        
        # Dictionary to store latest responses from agents
        latest_responses = {}
        
        # Dictionary to store thread IDs
        thread_ids = {}
        
        # Get initial thread ID
        if self.logging_plugin:
            initial_thread_id = self.logging_plugin.log_agent_get_thread_id()
            thread_ids['initial'] = initial_thread_id
            print(f"Initial thread ID: {initial_thread_id}")
        
        # Add the user message to the chat
        await chat.add_chat_message(user_message)
        
        # Set a timeout for the entire process
        overall_timeout = 600  # 10 minutes total
        start_time = time.time()
        
        try:
            # Step 1: Get scheduler response
            try:
                # Get thread ID before scheduler response
                if self.logging_plugin:
                    scheduler_before_thread_id = self.logging_plugin.log_agent_get_thread_id()
                    thread_ids['scheduler_before'] = scheduler_before_thread_id
                    print(f"Thread ID before scheduler response: {scheduler_before_thread_id}")
                
                remaining_timeout = overall_timeout - (time.time() - start_time)
                if remaining_timeout <= 0:
                    raise asyncio.TimeoutError("Overall process timeout exceeded")
                    
                scheduler_response = await asyncio.wait_for(
                    self._get_scheduler_response(
                        chat, 
                        latest_responses, 
                        session_id, 
                        cancellation_token
                    ),
                    timeout=min(180, remaining_timeout)  # 3 minutes max or remaining time
                )
                
                # Get thread ID after scheduler response
                if self.logging_plugin:
                    scheduler_after_thread_id = self.logging_plugin.log_agent_get_thread_id()
                    thread_ids['scheduler_after'] = scheduler_after_thread_id
                    print(f"Thread ID after scheduler response: {scheduler_after_thread_id}")
                    
                    # Store the scheduler thread ID in the session
                    async with self._session_lock:
                        if session_id in self.chat_sessions:
                            self.chat_sessions[session_id]['scheduler_thread_id'] = scheduler_after_thread_id
                            print(f"Stored scheduler thread ID in session: {scheduler_after_thread_id}")
            except asyncio.TimeoutError:
                print("Timeout waiting for scheduler response")
                scheduler_response = None
            except Exception as e:
                print(f"Error getting scheduler response: {e}")
                scheduler_response = None
            
            # Check for cancellation
            if cancellation_token and cancellation_token.done():
                return {
                    "status": "cancelled",
                    "error": "Operation was cancelled",
                    "conversation_id": conversation_id
                }
            
            if not scheduler_response:
                # Fall back to standard processing if scheduler didn't respond
                print("No scheduler response, falling back to standard processing")
                return await self._process_standard_query(
                    session, 
                    user_message, 
                    True, 
                    conversation_id, 
                    session_id, 
                    original_message
                )
            
            # Step 2: Extract structured data for the risk agent
            structured_data = self._extract_structured_data(scheduler_response.content)
            
            # Step 3: Get risk agent response
            try:
                # Get thread ID before risk agent response
                if self.logging_plugin:
                    risk_before_thread_id = self.logging_plugin.log_agent_get_thread_id()
                    thread_ids['risk_before'] = risk_before_thread_id
                    print(f"Thread ID before {risk_type} response: {risk_before_thread_id}")
                
                remaining_timeout = overall_timeout - (time.time() - start_time)
                if remaining_timeout <= 0:
                    raise asyncio.TimeoutError("Overall process timeout exceeded")
                    
                risk_agent_response = await asyncio.wait_for(
                    self._get_risk_agent_response(
                        chat, 
                        risk_type, 
                        structured_data, 
                        latest_responses, 
                        session_id, 
                        cancellation_token
                    ),
                    timeout=min(240, remaining_timeout)  # 4 minutes max or remaining time
                )
                
                # Get thread ID after risk agent response
                if self.logging_plugin:
                    risk_after_thread_id = self.logging_plugin.log_agent_get_thread_id()
                    thread_ids['risk_after'] = risk_after_thread_id
                    print(f"Thread ID after {risk_type} response: {risk_after_thread_id}")
                    
                    # CRITICAL: Store the risk thread ID for later use
                    async with self._session_lock:
                        if session_id in self.chat_sessions:
                            self.chat_sessions[session_id][f'{risk_type}_thread_id'] = risk_after_thread_id
                            print(f"Stored {risk_type} thread ID in session: {risk_after_thread_id}")
                    
                    # CRITICAL: Write thread ID to a file for debugging
                    try:
                        if risk_type == POLITICAL_RISK_AGENT:
                            with open("political_thread_id.txt", "w") as f:
                                f.write(f"Political Risk Thread ID: {risk_after_thread_id}\n")
                                f.write(f"Session ID: {session_id}\n")
                                f.write(f"Conversation ID: {conversation_id}\n")
                                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                            print(f"Wrote political risk thread ID to file: {risk_after_thread_id}")
                    except Exception as file_error:
                        print(f"Error writing thread ID to file: {file_error}")
                    
            except asyncio.TimeoutError:
                print(f"Timeout waiting for {risk_type} response")
                risk_agent_response = None
            except Exception as e:
                print(f"Error getting {risk_type} response: {e}")
                risk_agent_response = None
            
            # Check for cancellation
            if cancellation_token and cancellation_token.done():
                return {
                    "status": "cancelled",
                    "error": "Operation was cancelled",
                    "conversation_id": conversation_id
                }
            
            # Step 4: Get reporting agent response (with thread ID context)
            try:
                # Get thread ID before reporting agent response
                if self.logging_plugin:
                    reporting_before_thread_id = self.logging_plugin.log_agent_get_thread_id()
                    thread_ids['reporting_before'] = reporting_before_thread_id
                    print(f"Thread ID before reporting agent response: {reporting_before_thread_id}")
                
                remaining_timeout = overall_timeout - (time.time() - start_time)
                if remaining_timeout <= 0:
                    raise asyncio.TimeoutError("Overall process timeout exceeded")
                    
                # Create extra context for the reporting agent with thread IDs
                thread_context = {
                    'risk_type': risk_type,
                    'thread_ids': thread_ids,
                }
                
                reporting_response = await asyncio.wait_for(
                    self._get_reporting_agent_response(
                        chat, 
                        risk_type, 
                        latest_responses, 
                        session_id, 
                        cancellation_token,
                        thread_context  # Pass the thread context
                    ),
                    timeout=min(180, remaining_timeout)  # 3 minutes max or remaining time
                )
                
                # Get thread ID after reporting agent response
                if self.logging_plugin:
                    reporting_after_thread_id = self.logging_plugin.log_agent_get_thread_id()
                    thread_ids['reporting_after'] = reporting_after_thread_id
                    print(f"Thread ID after reporting agent response: {reporting_after_thread_id}")
                    
                    # Store the reporting thread ID
                    async with self._session_lock:
                        if session_id in self.chat_sessions:
                            self.chat_sessions[session_id]['reporting_thread_id'] = reporting_after_thread_id
                            print(f"Stored reporting thread ID in session: {reporting_after_thread_id}")
                    
            except asyncio.TimeoutError:
                print("Timeout waiting for reporting agent response")
                reporting_response = None
                    
                # Try direct report generation
                try:
                    print("Attempting direct report generation after timeout")
                    direct_success = await self.generate_report_directly(
                        session, 
                        risk_type, 
                        latest_responses, 
                        conversation_id, 
                        session_id, 
                        original_message,
                        thread_ids  # Pass thread IDs
                    )
                    
                    if not direct_success:
                        print("Direct report generation failed after timeout")
                        
                        # Try emergency force method
                        try:
                            print("Attempting emergency force method")
                            emergency_success = await self.force_report_generation(
                                session, 
                                risk_type, 
                                latest_responses, 
                                conversation_id, 
                                session_id, 
                                original_message,
                                thread_ids  # Pass thread IDs
                            )
                            
                            if not emergency_success:
                                print("Emergency force method failed")
                        except Exception as emergency_error:
                            print(f"Error in emergency force method: {emergency_error}")
                            
                except Exception as direct_error:
                    print(f"Error in direct report generation after timeout: {direct_error}")
                    
            except Exception as e:
                print(f"Error getting reporting agent response: {e}")
                reporting_response = None
                
                # Try direct report generation
                try:
                    print("Attempting direct report generation after error")
                    direct_success = await self.generate_report_directly(
                        session, 
                        risk_type, 
                        latest_responses, 
                        conversation_id, 
                        session_id, 
                        original_message,
                        thread_ids  # Pass thread IDs
                    )
                    
                    if not direct_success:
                        print("Direct report generation failed after error")
                except Exception as direct_error:
                    print(f"Error in direct report generation after error: {direct_error}")
            
            # Check for cancellation
            if cancellation_token and cancellation_token.done():
                return {
                    "status": "cancelled",
                    "error": "Operation was cancelled",
                    "conversation_id": conversation_id
                }
            
            # Format the final response
            final_response = self._format_specific_risk_response(latest_responses, risk_type)
            
            # Log completion
            try:
                self.logging_plugin.log_agent_event(
                    agent_name="ChatbotManager",
                    action="Complete Risk Query",
                    result_summary=f"Successfully processed {risk_type} query",
                    conversation_id=conversation_id,
                    session_id=session_id,
                    user_query=original_message
                )
            except Exception as log_error:
                print(f"Error logging completion: {log_error}")
            
            return {
                "status": "success",
                "response": final_response,
                "conversation_id": conversation_id
            }
            
        except Exception as e:
            print(f"Error processing specific risk query: {e}")
            import traceback
            traceback.print_exc()
            
            # Try to recover with what we have
            if latest_responses:
                final_response = self._format_specific_risk_response(latest_responses, risk_type)
                return {
                    "status": "partial_success",
                    "response": final_response,
                    "conversation_id": conversation_id
                }
            else:
                return {
                    "status": "error",
                    "error": f"Failed to process risk query: {str(e)}",
                    "conversation_id": conversation_id
                }

    async def force_report_generation(self, session, risk_type, latest_responses, conversation_id, session_id, original_message):
        """Force the reporting agent to generate a report when the normal flow hangs.
        
        Args:
            session: The session data
            risk_type: The name of the risk agent
            latest_responses: Dictionary of the latest responses from each agent
            conversation_id: The conversation ID
            session_id: The session ID
            original_message: The original user message
            
        Returns:
            bool: True if report generation was successful
        """
        print("Forcing report generation for hanging process")
        
        try:
            # If the reporting agent isn't in the session, we can't continue
            if REPORTING_AGENT not in session["agents"]:
                print("Reporting agent not found in session")
                return False
            
            # Get the reporting agent
            reporting_agent = session["agents"][REPORTING_AGENT]
            
            # Collect all available information
            available_data = {}
            for agent_name, response in latest_responses.items():
                available_data[agent_name] = response.content.replace(f"{agent_name} > ", "")
            
            # Try to get political risk data from the database if it's not in latest_responses
            if risk_type == POLITICAL_RISK_AGENT and risk_type not in available_data:
                try:
                    conn = pyodbc.connect(self.connection_string)
                    cursor = conn.cursor()
                    
                    # Query to find the political risk agent response
                    cursor.execute("""
                        SELECT TOP 1 agent_output
                        FROM dim_agent_event_log
                        WHERE conversation_id = ? 
                        AND agent_name = 'POLITICAL_RISK_AGENT'
                        ORDER BY event_time DESC
                    """, (conversation_id,))
                    
                    row = cursor.fetchone()
                    if row and row[0]:
                        available_data[POLITICAL_RISK_AGENT] = row[0].replace("POLITICAL_RISK_AGENT > ", "")
                        print(f"Retrieved political risk data from database: {len(available_data[POLITICAL_RISK_AGENT])} characters")
                    
                    cursor.close()
                    conn.close()
                except Exception as db_error:
                    print(f"Error retrieving political risk data from database: {db_error}")
            
            # Create a simplified input for the reporting agent
            report_input = f"""
            EMERGENCY REPORT GENERATION:
            A timeout or hang has occurred in the normal agent flow. You need to generate a report 
            with the available data.
            
            CRITICAL INSTRUCTIONS:
            1. Generate a report with ONLY what's available
            2. Do NOT wait for more data or mention waiting
            3. Skip any thinking steps and log calls that might fail
            4. ONLY include the final report in your response
            
            AVAILABLE DATA:
            
            """
            
            # Add any data we have
            if SCHEDULER_AGENT in available_data:
                report_input += f"SCHEDULER DATA:\n{available_data[SCHEDULER_AGENT][:2000]}...\n\n"
            
            if risk_type in available_data:
                report_input += f"RISK ANALYSIS:\n{available_data[risk_type][:2000]}...\n\n"
            
            # Extract any political risk table if it exists
            political_risk_table = None
            if risk_type == POLITICAL_RISK_AGENT and risk_type in available_data:
                table_match = re.search(r'Political Risk Table(.*?)(?=###|$)', available_data[risk_type], re.DOTALL)
                if table_match:
                    political_risk_table = table_match.group(1).strip()
                    report_input += f"POLITICAL RISK TABLE:\n{political_risk_table}\n\n"
            
            # Add report generation instructions
            report_input += f"""
            Generate a professional report with:
            1. Executive Summary
            2. Risk Summary Table (simple format)
            3. Detailed Analysis
            4. Recommendations
            
            When saving the report, use:
            - session_id: "{session_id}"
            - conversation_id: "{conversation_id}"
            - report_title: "Emergency Risk Report"
            
            Include file information at the end in this format:
            
            ```
            📄 Report Generated Successfully
            
            Filename: [filename]
            Download URL: [blob_url]
            Report ID: [report_id]
            ```
            
            If file saving fails, use this format instead:
            ```
            ⚠️ Report Generation Notice
            
            The report was generated but could not be saved to a file.
            Please try again or contact support if the issue persists.
            ```
            """
            
            # Set a strict timeout
            try:
                reporting_timeout = 120  # 2 minutes max
                reporting_response = await asyncio.wait_for(
                    reporting_agent.invoke(report_input),
                    timeout=reporting_timeout
                )
                
                if reporting_response:
                    # Format the response
                    if not reporting_response.startswith("REPORTING_AGENT >"):
                        formatted_response = f"REPORTING_AGENT > {reporting_response}"
                    else:
                        formatted_response = reporting_response
                    
                    # Clean the response
                    cleaned_response = self._clean_report_output(formatted_response)
                    formatted_response = f"REPORTING_AGENT > {cleaned_response}"
                    
                    # Add to the latest responses
                    latest_responses[REPORTING_AGENT] = ChatMessageContent(
                        role=AuthorRole.ASSISTANT,
                        name=REPORTING_AGENT,
                        content=formatted_response
                    )
                    
                    # Store the response in the event log
                    await self._store_agent_output(
                        session_id=session_id,
                        agent_name=REPORTING_AGENT,
                        agent_output=formatted_response,
                        action="Emergency Report Generation"
                    )
                    
                    # Log this action
                    try:
                        self.logging_plugin.log_agent_event(
                            agent_name="SYSTEM",
                            action="Emergency Report Generation",
                            result_summary="Used emergency method to generate report due to hanging process",
                            conversation_id=conversation_id,
                            session_id=session_id,
                            user_query=original_message,
                            agent_output=formatted_response
                        )
                    except Exception as e:
                        print(f"Error logging emergency report generation: {e}")
                    
                    return True
                    
            except asyncio.TimeoutError:
                print(f"Emergency report generation timed out after {reporting_timeout} seconds")
            except Exception as e:
                print(f"Error during emergency report generation: {e}")
                import traceback
                traceback.print_exc()
                
        except Exception as e:
            print(f"Failed to force report generation: {e}")
            import traceback
            traceback.print_exc()
            
        return False

    async def _get_scheduler_response(self, chat, latest_responses, session_id, cancellation_token):
        """Get the scheduler agent's response and store it in the event log.
        
        Args:
            chat: The chat object
            latest_responses: Dictionary to store the latest responses
            session_id: The session ID
            cancellation_token: Cancellation token
            
        Returns:
            The scheduler response or None if timeout/error
        """
        scheduler_response = None
        scheduler_timeout = 420  # seconds
        
        try:
            # Reset chat activity before invoking
            await self.reset_chat_activity(chat)
            
            # Create a task to get scheduler response with timeout
            async def get_response():
                nonlocal scheduler_response
                async for response in chat.invoke():
                    # Check for cancellation
                    if cancellation_token and cancellation_token.done():
                        print("Scheduler processing cancelled via token")
                        return
                    
                    if response and hasattr(response, 'name') and response.name == SCHEDULER_AGENT:
                        scheduler_response = response
                        latest_responses[SCHEDULER_AGENT] = response
                        
                        # Store the scheduler agent's output in the event log
                        await self._store_agent_output(
                            session_id=session_id,
                            agent_name=SCHEDULER_AGENT,
                            agent_output=response.content,
                            action="Schedule Analysis"
                        )
                        
                        return
            
            # Add retry mechanism
            retry_count = 0
            max_retries = 2
            
            while retry_count <= max_retries:
                try:
                    # Create a task for the operation
                    scheduler_task = asyncio.create_task(get_response())
                    
                    # Track the task
                    if session_id in self._session_tasks:
                        self._session_tasks[session_id].append(scheduler_task)
                    
                    # Wait for scheduler response with timeout
                    await asyncio.wait_for(scheduler_task, timeout=scheduler_timeout)
                    break  # Success, exit the retry loop
                except asyncio.TimeoutError:
                    retry_count += 1
                    if retry_count <= max_retries:
                        print(f"Scheduler timeout, retry {retry_count}/{max_retries}")
                        await asyncio.sleep(1)  # Brief pause before retry
                    else:
                        print(f"Scheduler agent timed out after {scheduler_timeout} seconds and {max_retries} retries")
                finally:
                    # Clean up the task reference
                    if session_id in self._session_tasks and scheduler_task in self._session_tasks[session_id]:
                        self._session_tasks[session_id].remove(scheduler_task)
            
        except Exception as e:
            print(f"Error getting scheduler response: {e}")
            import traceback
            traceback.print_exc()
        
        return scheduler_response

    def _extract_structured_data(self, scheduler_content):
        """Extract structured data for the risk agent.
        
        Args:
            scheduler_content: The scheduler agent's response content
            
        Returns:
            str: The structured data in JSON format
        """
        # Try to find JSON in the response
        json_match = re.search(r'```json\s*(.*?)\s*```', scheduler_content, re.DOTALL)
        
        if json_match:
            # Extract the JSON string
            try:
                json_data = json.loads(json_match.group(1))
                structured_data = json.dumps(json_data, indent=2)
                print("Successfully extracted JSON data from scheduler response")
                return structured_data
            except Exception as e:
                print(f"Error parsing JSON: {e}")
        
        # If JSON extraction failed, create a simplified version
        print("No JSON found, creating simplified data structure")
        
        # Extract key location information using regex
        project_info = []
        manufacturing_locations = []
        shipping_ports = []
        receiving_ports = []
        equipment_items = []
        
        # Try to extract project info
        project_match = re.search(r'Project\s+(\w+).*?(?:located|in)\s+(\w+)', scheduler_content, re.IGNORECASE)
        if project_match:
            project_info.append({"name": project_match.group(1), "location": project_match.group(2)})
        
        # Try to extract manufacturing locations
        manufacturing_matches = re.findall(r'Manufacturing\s+(?:Location|Hub):\s*([^,\n]+)', scheduler_content, re.IGNORECASE)
        if manufacturing_matches:
            manufacturing_locations.extend(manufacturing_matches)
        
        # Try to extract shipping ports
        shipping_matches = re.findall(r'Shipping\s+Ports?:.*?([A-Za-z]+,\s*[A-Za-z]+)', scheduler_content, re.IGNORECASE)
        if shipping_matches:
            shipping_ports.extend(shipping_matches)
        
        # Try to extract receiving ports
        receiving_matches = re.findall(r'Receiving\s+Ports?:.*?([A-Za-z]+)', scheduler_content, re.IGNORECASE)
        if receiving_matches:
            receiving_ports.extend(receiving_matches)
        
        # Create simplified JSON
        simplified_data = {
            "projectInfo": project_info if project_info else [{"name": "Project", "location": "Unknown"}],
            "manufacturingLocations": manufacturing_locations,
            "shippingPorts": shipping_ports,
            "receivingPorts": receiving_ports,
            "equipmentItems": equipment_items
        }
        
        return json.dumps(simplified_data, indent=2)
    
    async def _get_risk_agent_response(self, chat, risk_type, structured_data, latest_responses, session_id, cancellation_token):
        """Get a risk agent's response with special handling for political risk citations.
        
        Args:
            chat: The chat object
            risk_type: The risk agent type
            structured_data: The structured data in JSON format
            latest_responses: Dictionary to store the latest responses
            session_id: The session ID
            cancellation_token: Cancellation token
                
        Returns:
            The risk agent response or None if timeout/error
        """
        # Prepare concise message for risk agent
        concise_message = f"""SCHEDULER_AGENT > ```json
    {structured_data}
    ```"""
        
        # Create a message for the risk agent
        risk_agent_message = ChatMessageContent(
            role=AuthorRole.ASSISTANT,
            name=SCHEDULER_AGENT,
            content=concise_message
        )
        
        # Add the message to the chat
        await chat.add_chat_message(risk_agent_message)
        
        # Reset chat activity if needed
        await self.reset_chat_activity(chat)
        
        # Try to get the thread ID for political risk agent
        thread_id = None
        if risk_type == POLITICAL_RISK_AGENT:
            try:
                # Try various ways to get the thread ID
                if hasattr(chat, '_thread_id'):
                    thread_id = chat._thread_id
                elif hasattr(chat, 'thread_id'):
                    thread_id = chat.thread_id
                else:
                    # Try to get it from the logging plugin
                    logging_plugin = self.logging_plugin
                    if logging_plugin:
                        thread_id_result = logging_plugin.log_agent_get_thread_id()
                        if thread_id_result and thread_id_result != "thread_id_not_available":
                            thread_id = thread_id_result
                
                if thread_id:
                    print(f"Found thread ID for political risk agent: {thread_id}")
                    # Store the thread ID in the session
                    if session_id in self.chat_sessions:
                        self.chat_sessions[session_id]['political_risk_thread_id'] = thread_id
            except Exception as e:
                print(f"Error getting thread ID for political risk agent: {e}")
        
        # Risk agent response timeout
        risk_timeout = 420  # seconds
        
        try:
            # Create a task to get risk agent response with timeout
            async def get_response():
                interim_message_received = False
                
                async for response in chat.invoke():
                    # Check for cancellation
                    if cancellation_token and cancellation_token.done():
                        print(f"{risk_type} processing cancelled via token")
                        return
                            
                    if response and hasattr(response, 'name') and response.name == risk_type:
                        risk_content = response.content
                        
                        # More robust check for interim messages
                        if (len(risk_content) < 500 and 
                            ("will provide" in risk_content.lower() or 
                            "analyzing" in risk_content.lower() or
                            "working on" in risk_content.lower() or
                            "processing" in risk_content.lower() or
                            "searching" in risk_content.lower() or
                            "retrieving" in risk_content.lower())):
                            print(f"Received interim message from {risk_type}, continuing to wait for full response")
                            
                            interim_message_received = True
                            
                            # Store the interim message but continue waiting
                            latest_responses[f"{risk_type}_interim"] = response
                            
                            # Store the interim message in the event log
                            await self._store_agent_output(
                                session_id=session_id,
                                agent_name=f"{risk_type}_interim",
                                agent_output=risk_content,
                                action="Interim Response"
                            )
                            
                            # Don't process JSON data for interim messages
                            continue
                        
                        # If we've received an interim message and now have a substantial response
                        # or if this is just a substantial response directly
                        if interim_message_received or len(risk_content) > 300:
                            latest_responses[risk_type] = response
                            
                            # Store the standard output in the event log
                            await self._store_agent_output(
                                session_id=session_id,
                                agent_name=risk_type,
                                agent_output=risk_content,
                                action="Complete Analysis"
                            )
                            
                            # Special handling for political risk agent
                            if risk_type == POLITICAL_RISK_AGENT:
                                try:
                                    # Use the political risk JSON plugin
                                    political_risk_json_plugin = self.political_risk_json_plugin
                                    
                                    if political_risk_json_plugin:
                                        try:
                                            result = political_risk_json_plugin.store_political_json_output_agent_event(
                                                risk_content,
                                                POLITICAL_RISK_AGENT,
                                                self.chat_sessions[session_id]["conversation_id"],
                                                session_id
                                            )
                                            print(f"Stored political risk JSON using plugin: {result}")
                                        except Exception as json_e:
                                            print(f"Error storing political risk JSON data: {json_e}")
                                            import traceback
                                            traceback.print_exc()
                                    else:
                                        print("Political risk JSON plugin not found")
                                        
                                    # If we have a thread ID, get citations
                                    if thread_id:
                                        try:
                                            # Get citations after a brief delay to ensure they're available
                                            await asyncio.sleep(1)
                                            citations = await self._get_citations_from_thread(thread_id)
                                            if citations:
                                                print(f"Found {len(citations)} citations in political risk response")
                                                
                                                # Store the citations in the session
                                                if session_id in self.chat_sessions:
                                                    self.chat_sessions[session_id]['political_risk_citations'] = citations
                                                    print(f"Stored {len(citations)} citations in session {session_id}")
                                        except Exception as citation_err:
                                            print(f"Error getting citations: {citation_err}")
                                            import traceback
                                            traceback.print_exc()
                                except Exception as e:
                                    print(f"Error processing political risk JSON: {e}")
                                    import traceback
                                    traceback.print_exc()
                            
                            return
            
            # Add retry logic for risk agent
            retry_count = 0
            max_retries = 2
            
            while retry_count <= max_retries:
                try:
                    # Create a task for the operation
                    risk_task = asyncio.create_task(get_response())
                    
                    # Track the task
                    if session_id in self._session_tasks:
                        self._session_tasks[session_id].append(risk_task)
                    
                    # Wait for risk agent response with timeout
                    await asyncio.wait_for(risk_task, timeout=risk_timeout)
                    print(f"Received response from {risk_type}")
                    break  # Success, exit the retry loop
                except asyncio.TimeoutError:
                    retry_count += 1
                    if retry_count <= max_retries:
                        print(f"{risk_type} timeout, retry {retry_count}/{max_retries}")
                        await asyncio.sleep(1)  # Brief pause before retry
                    else:
                        print(f"Risk agent {risk_type} timed out after {risk_timeout} seconds and {max_retries} retries")
                except Exception as e:
                    retry_count += 1
                    print(f"Error in risk agent {risk_type}: {e}")
                    
                    if retry_count <= max_retries:
                        print(f"Retrying {retry_count}/{max_retries}...")
                        await asyncio.sleep(1)  # Brief pause before retry
                    else:
                        print(f"Risk agent {risk_type} failed after {max_retries} retries")
                        import traceback
                        traceback.print_exc()
                finally:
                    # Clean up the task reference
                    if session_id in self._session_tasks and risk_task in self._session_tasks[session_id]:
                        self._session_tasks[session_id].remove(risk_task)
            
        except Exception as e:
            print(f"Error getting risk agent response: {e}")
            import traceback
            traceback.print_exc()
        
        # Return the most substantial response available
        if risk_type in latest_responses:
            return latest_responses[risk_type]
        elif f"{risk_type}_interim" in latest_responses:
            print(f"Returning interim response for {risk_type} as final response")
            return latest_responses[f"{risk_type}_interim"]
        
        return None

    async def _get_reporting_agent_response(self, chat, risk_type, latest_responses, session_id, cancellation_token, thread_context=None):
        """Get the reporting agent's response with thread ID context.
        
        Args:
            chat: The chat object
            risk_type: The risk agent type
            latest_responses: Dictionary to store the latest responses
            session_id: The session ID
            cancellation_token: Cancellation token
            thread_context: Optional dictionary with thread IDs and context
            
        Returns:
            The reporting agent response or None if timeout/error
        """
        # Reset chat activity before continuing
        await self.reset_chat_activity(chat)
        
        # Reset chat state if it's marked as complete
        if hasattr(chat, '_current_chat_complete') and chat._current_chat_complete:
            print("Reset chat complete state before reporting agent")
            chat._current_chat_complete = False
        
        # Get political risk thread ID
        political_risk_thread_id = None
        
        # Try to get from thread_context first
        if thread_context and 'thread_ids' in thread_context:
            thread_ids = thread_context['thread_ids']
            if 'risk_after' in thread_ids and thread_context.get('risk_type') == POLITICAL_RISK_AGENT:
                political_risk_thread_id = thread_ids['risk_after']
                print(f"Got political risk thread ID from context: {political_risk_thread_id}")
        
        # If not in context, try to get from session
        if not political_risk_thread_id:
            try:
                async with self._session_lock:
                    if session_id in self.chat_sessions:
                        political_risk_thread_id = self.chat_sessions[session_id].get(f'{POLITICAL_RISK_AGENT}_thread_id')
                        if political_risk_thread_id:
                            print(f"Got political risk thread ID from session: {political_risk_thread_id}")
            except Exception as e:
                print(f"Error getting political risk thread ID from session: {e}")
        
        # If still not found, try to read from file
        if not political_risk_thread_id:
            try:
                if os.path.exists("political_thread_id.txt"):
                    with open("political_thread_id.txt", "r") as f:
                        for line in f:
                            if line.startswith("Political Risk Thread ID:"):
                                political_risk_thread_id = line.split(":", 1)[1].strip()
                                print(f"Got political risk thread ID from file: {political_risk_thread_id}")
                                break
            except Exception as e:
                print(f"Error reading political risk thread ID from file: {e}")
        
        # Get political risk data from the event log if available
        political_risk_data = None
        if risk_type == POLITICAL_RISK_AGENT:
            try:
                # Get the conversation ID
                conversation_id = self.chat_sessions[session_id]["conversation_id"]
                
                # Query the event log for political risk JSON data
                conn = pyodbc.connect(self.connection_string)
                cursor = conn.cursor()
                
                # Look for political risk JSON data for this conversation
                cursor.execute("""
                    SELECT TOP 1 agent_output
                    FROM dim_agent_event_log
                    WHERE agent_name = 'POLITICAL_RISK_AGENT'
                    AND action = 'Political Risk JSON Data'
                    AND conversation_id = ?
                    ORDER BY event_time DESC
                """, (conversation_id,))
                
                row = cursor.fetchone()
                if row and row[0]:
                    try:
                        political_risk_data = json.loads(row[0])
                        print(f"Retrieved political risk JSON data with {len(political_risk_data.get('political_risks', []))} risks")
                    except:
                        print("Error parsing political risk JSON data")
                
                cursor.close()
                conn.close()
            except Exception as e:
                print(f"Error retrieving political risk data: {e}")
        
        # Create additional context for the reporting agent if political risk data is available
        additional_context = ""
        if political_risk_data:
            additional_context = "\n\nAdditional political risk data is available in the database and has been logged for reference."
            
            # Add explicit thread ID information if available
            if political_risk_thread_id:
                additional_context += f"\n\nIMPORTANT: Use thread_id: {political_risk_thread_id} for any citations you need to reference."
                additional_context += f"\n\nCRITICAL: When saving the report, ensure you call save_report_to_file and parse the result correctly:"
                additional_context += f"\n\n```python"
                additional_context += f"\nresult = save_report_to_file(report_content, session_id, conversation_id, 'Comprehensive Equipment Schedule Risk Analysis')"
                additional_context += f"\nimport json"
                additional_context += f"\nfile_info = json.loads(result)"
                additional_context += f"\nfilename = file_info.get('filename', 'report.docx')"
                additional_context += f"\nblob_url = file_info.get('blob_url', 'No URL available')"
                additional_context += f"\nreport_id = file_info.get('report_id', 'No ID available')"
                additional_context += f"\n```"
                additional_context += f"\n\nThen include these ACTUAL values in your response, NOT placeholders."
        
        # Create a message from the risk agent to the reporting agent
        reporting_agent_message = ""
        if risk_type in latest_responses:
            risk_content = latest_responses[risk_type].content
            
            # Add additional context if available
            if additional_context:
                risk_content += additional_context
            
            # Create the message
            reporting_agent_message = ChatMessageContent(
                role=AuthorRole.ASSISTANT,
                name=risk_type,
                content=risk_content
            )
        else:
            # If no risk agent response, create a placeholder directing to scheduler data
            scheduler_content = ""
            if SCHEDULER_AGENT in latest_responses:
                scheduler_content = f"See the scheduler output for relevant schedule data: {latest_responses[SCHEDULER_AGENT].content[:100]}..."
                
            reporting_agent_message = ChatMessageContent(
                role=AuthorRole.ASSISTANT,
                name=risk_type,
                content=f"{risk_type} > Creating report based on available data. {scheduler_content}"
            )
        
        # Add the message to the chat
        await chat.add_chat_message(reporting_agent_message)
        
        # Reporting agent timeout
        reporting_timeout = 420  # seconds
        
        try:
            # Create a task to get reporting agent response with timeout
            async def get_response():
                response_found = False
                async for response in chat.invoke():
                    # Check for cancellation
                    if cancellation_token and cancellation_token.done():
                        print("Reporting agent processing cancelled via token")
                        return
                    
                    if response and hasattr(response, 'name') and response.name == REPORTING_AGENT:
                        latest_responses[REPORTING_AGENT] = response
                        response_found = True
                        
                        # Store the reporting agent's output in the event log
                        await self._store_agent_output(
                            session_id=session_id,
                            agent_name=REPORTING_AGENT,
                            agent_output=response.content,
                            action="Comprehensive Report"
                        )
                        
                        return
                
                # If we got here and no response was found, the chat might have terminated early
                if not response_found:
                    print("Chat terminated without reporting agent response, will try direct agent invocation")
                    raise Exception("No reporting agent response received")
            
            # Add retry logic for reporting agent
            retry_count = 0
            max_retries = 2
            
            while retry_count <= max_retries:
                try:
                    # Create a task for the operation
                    reporting_task = asyncio.create_task(get_response())
                    
                    # Track the task
                    if session_id in self._session_tasks:
                        self._session_tasks[session_id].append(reporting_task)
                    
                    # Wait for reporting agent response with timeout
                    await asyncio.wait_for(reporting_task, timeout=reporting_timeout)
                    print("Reporting agent responded successfully")
                    break  # Success, exit the retry loop
                except asyncio.TimeoutError:
                    retry_count += 1
                    if retry_count <= max_retries:
                        print(f"Reporting agent timeout, retry {retry_count}/{max_retries}")
                        await asyncio.sleep(1)  # Brief pause before retry
                    else:
                        print(f"Reporting agent timed out after {reporting_timeout} seconds and {max_retries} retries")
                        # Fall back to direct agent invocation
                        conversation_id = self.chat_sessions[session_id]["conversation_id"]
                        original_message = "Generate comprehensive report"  # Default message
                        await self.generate_report_directly(
                            session, 
                            risk_type, 
                            latest_responses, 
                            conversation_id, 
                            session_id, 
                            original_message
                        )
                except Exception as e:
                    # If chat is already complete, try direct agent invocation
                    if "Chat is already complete" in str(e) or "No reporting agent response received" in str(e):
                        print("Chat already complete or no response, will try direct agent invocation")
                        conversation_id = self.chat_sessions[session_id]["conversation_id"]
                        original_message = "Generate comprehensive report"  # Default message
                        direct_success = await self.generate_report_directly(
                            session, 
                            risk_type, 
                            latest_responses, 
                            conversation_id, 
                            session_id, 
                            original_message
                        )
                        if direct_success:
                            print("Successfully generated report via direct invocation")
                            break
                            
                    retry_count += 1
                    if retry_count <= max_retries:
                        print(f"Reporting agent error, retry {retry_count}/{max_retries}: {e}")
                        await asyncio.sleep(1)  # Brief pause before retry
                    else:
                        print(f"Reporting agent failed after {max_retries} retries: {e}")
                finally:
                    # Clean up the task reference
                    if session_id in self._session_tasks and reporting_task in self._session_tasks[session_id]:
                        self._session_tasks[session_id].remove(reporting_task)
            
        except Exception as e:
            print(f"Error getting reporting agent response: {e}")
            import traceback
            traceback.print_exc()
        
        return latest_responses.get(REPORTING_AGENT)

    def _format_specific_risk_response(self, latest_responses, risk_type):
        """Format the response for a specific risk query.
        
        Args:
            latest_responses: Dictionary of the latest responses from each agent
            risk_type: The risk agent type
            
        Returns:
            str: The formatted response
        """
        # If we have the reporting agent's response, use that
        if REPORTING_AGENT in latest_responses:
            # Clean the response to remove thinking logs and debug info
            report_response = self._clean_report_output(latest_responses[REPORTING_AGENT].content.replace("REPORTING_AGENT > ", ""))
            
            # Check if the report is substantial enough
            if len(report_response) > 200:
                return report_response
            else:
                # Fall back to risk agent's response if the report is too short
                if risk_type in latest_responses:
                    risk_response = latest_responses[risk_type].content.replace(f"{risk_type} > ", "")
                    return f"# {risk_type.replace('_AGENT', '').title()} Analysis\n\n{risk_response}"
                else:
                    # If no risk response, use scheduler response
                    if SCHEDULER_AGENT in latest_responses:
                        scheduler_response = latest_responses[SCHEDULER_AGENT].content.replace("SCHEDULER_AGENT > ", "")
                        return f"# Schedule Analysis\n\n{scheduler_response}\n\n*Note: Detailed risk analysis could not be generated at this time.*"
                    else:
                        return "I'm sorry, I couldn't complete the risk analysis at this time. Please try again."
        
        # If we have the risk agent's response but not the reporting agent's, use the risk agent's
        if risk_type in latest_responses:
            risk_response = latest_responses[risk_type].content.replace(f"{risk_type} > ", "")
            if SCHEDULER_AGENT in latest_responses:
                scheduler_response = latest_responses[SCHEDULER_AGENT].content.replace("SCHEDULER_AGENT > ", "")
                
                # Extract key information from scheduler response
                key_info = ""
                schedule_match = re.search(r'Equipment Comparison Table(.*?)(?=##|\Z)', scheduler_response, re.DOTALL)
                if schedule_match:
                    key_info = f"## Schedule Information\n\n{schedule_match.group(1).strip()}\n\n"
                
                return f"# {risk_type.replace('_AGENT', '').title()} Analysis\n\n{risk_response}\n\n{key_info}"
            else:
                return f"# {risk_type.replace('_AGENT', '').title()} Analysis\n\n{risk_response}"
        
        # If we only have the scheduler's response, use that with a note
        if SCHEDULER_AGENT in latest_responses:
            scheduler_response = latest_responses[SCHEDULER_AGENT].content.replace("SCHEDULER_AGENT > ", "")
            return f"# Schedule Analysis\n\n{scheduler_response}\n\n*Note: Detailed risk analysis could not be generated at this time.*"
        
        # If no responses were collected, provide a fallback
        return "I'm sorry, I couldn't analyze the specific risk at this time. Please try again."

    async def _process_comprehensive_risk_query(self, session, user_message, conversation_id, session_id, original_message):
        """Process a comprehensive risk query using parallel execution.
        
        Args:
            session: The session data
            user_message: The formatted user message
            conversation_id: The conversation ID
            session_id: The session ID
            original_message: The original user message
            
        Returns:
            dict: The response data
        """
        print("Processing comprehensive risk query")
        
        # Get the parallel chat and cancellation token
        chat = session["parallel_chat"]
        cancellation_token = session.get("cancellation_token")
        
        # Dictionary to store latest responses from agents
        latest_responses = {}
        
        # List of risk agents to process in parallel
        risk_agents = [POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT]
        
        # Add the user message to the chat
        await chat.add_chat_message(user_message)
        
        try:
            # Step 1: Get scheduler response
            scheduler_response = await self._get_scheduler_response(
                chat, 
                latest_responses, 
                session_id, 
                cancellation_token
            )
            
            # Check for cancellation
            if cancellation_token and cancellation_token.done():
                return {
                    "status": "cancelled",
                    "error": "Operation was cancelled",
                    "conversation_id": conversation_id
                }
            
            if SCHEDULER_AGENT in latest_responses:
                # Extract structured data for risk agents
                structured_data = self._extract_structured_data(latest_responses[SCHEDULER_AGENT].content)
                
                # Use structured data for risk agents
                concise_message = f"""SCHEDULER_AGENT > ```json
{structured_data}
```"""
                
                # Replace the original message with the concise one
                latest_responses[SCHEDULER_AGENT].content = concise_message
                
                # Process risk agents in parallel
                await self._process_risk_agents_in_parallel(
                    chat, 
                    risk_agents, 
                    latest_responses,
                    session_id, 
                    cancellation_token
                )
                
                # Check for cancellation
                if cancellation_token and cancellation_token.done():
                    return {
                        "status": "cancelled",
                        "error": "Operation was cancelled",
                        "conversation_id": conversation_id
                    }
                
                # Get reporting agent response
                await self._get_comprehensive_reporting_response(
                    chat, 
                    latest_responses, 
                    session_id, 
                    cancellation_token,
                    session,
                    conversation_id,
                    original_message
                )
            else:
                # If no scheduler response, fall back to standard processing
                print("No scheduler response, falling back to standard processing")
                await self._process_with_timeout(
                    chat, 
                    latest_responses, 
                    180,  # 3 minutes timeout
                    cancellation_token
                )
            
            # Format the final response
            final_response = self._format_comprehensive_risk_response(latest_responses)
            
            return {
                "status": "success",
                "response": final_response,
                "conversation_id": conversation_id
            }
            
        except Exception as e:
            print(f"Error processing comprehensive risk query: {e}")
            import traceback
            traceback.print_exc()
            
            # Try to recover with what we have
            if latest_responses:
                final_response = self._format_comprehensive_risk_response(latest_responses)
                return {
                    "status": "partial_success",
                    "response": final_response,
                    "conversation_id": conversation_id
                }
            else:
                return {
                    "status": "error",
                    "error": f"Failed to process comprehensive risk query: {str(e)}",
                    "conversation_id": conversation_id
                }
    
    async def _process_risk_agents_in_parallel(self, chat, risk_agents, latest_responses, session_id, cancellation_token):
        """Process risk agents in parallel.
        
        Args:
            chat: The chat object
            risk_agents: List of risk agent types
            latest_responses: Dictionary to store the latest responses
            session_id: The session ID
            cancellation_token: Cancellation token
        """
        # Create tasks for parallel execution of risk agents with timeouts
        risk_tasks = []
        for risk_agent in risk_agents:
            # Create a task for each risk agent using rate limiter
            task = asyncio.create_task(
                self.process_agent_with_rate_limit(
                    chat=chat,
                    agent_name=risk_agent,
                    message_content=latest_responses[SCHEDULER_AGENT].content
                )
            )
            risk_tasks.append(task)
            
            # Track the task
            if session_id in self._session_tasks:
                self._session_tasks[session_id].append(task)
        
        # Execute all risk agents in parallel with rate limiting
        try:
            risk_results = await asyncio.gather(*risk_tasks, return_exceptions=True)
            
            # Process results
            for i, result in enumerate(risk_results):
                if isinstance(result, Exception):
                    print(f"Error executing {risk_agents[i]}: {result}")
                elif result:
                    latest_responses[risk_agents[i]] = result
        finally:
            # Clean up task references
            if session_id in self._session_tasks:
                for task in risk_tasks:
                    if task in self._session_tasks[session_id]:
                        self._session_tasks[session_id].remove(task)
    
    async def _get_comprehensive_reporting_response(self, chat, latest_responses, session_id, cancellation_token, session, conversation_id, original_message):
        """Get reporting agent response for comprehensive risk analysis.
        
        Args:
            chat: The chat object
            latest_responses: Dictionary to store the latest responses
            session_id: The session ID
            cancellation_token: Cancellation token
            session: The session data
            conversation_id: The conversation ID
            original_message: The original user message
        """
        # Reset chat state if needed
        if hasattr(chat, '_current_chat_complete') and chat._current_chat_complete:
            print("Reset chat complete state before reporting agent")
            chat._current_chat_complete = False
        
        # Reset chat activity
        await self.reset_chat_activity(chat)
        
        # Reporting agent timeout
        reporting_timeout = 420  # seconds
        
        try:
            # Create a task to get reporting agent response with timeout
            async def get_response():
                async for response in chat.invoke():
                    # Check for cancellation
                    if cancellation_token and cancellation_token.done():
                        print("Reporting agent processing cancelled via token")
                        return
                    
                    if response and hasattr(response, 'name') and response.name == REPORTING_AGENT:
                        latest_responses[REPORTING_AGENT] = response
                        return
            
            # Add retry logic for reporting agent
            retry_count = 0
            max_retries = 2
            
            while retry_count <= max_retries:
                try:
                    # Create a task for the operation
                    reporting_task = asyncio.create_task(get_response())
                    
                    # Track the task
                    if session_id in self._session_tasks:
                        self._session_tasks[session_id].append(reporting_task)
                    
                    # Wait for reporting agent response with timeout
                    await asyncio.wait_for(reporting_task, timeout=reporting_timeout)
                    break  # Success, exit the retry loop
                except asyncio.TimeoutError:
                    retry_count += 1
                    if retry_count <= max_retries:
                        print(f"Reporting agent timeout, retry {retry_count}/{max_retries}")
                        await asyncio.sleep(1)  # Brief pause before retry
                    else:
                        print(f"Reporting agent timed out after {reporting_timeout} seconds and {max_retries} retries")
                except Exception as e:
                    if "Chat is already complete" in str(e):
                        # Try direct invocation as fallback
                        recovery_successful = await self.generate_report_directly(
                            session,
                            POLITICAL_RISK_AGENT,  # Use the first risk agent for recovery
                            latest_responses,
                            conversation_id,
                            session_id,
                            original_message
                        )
                        if recovery_successful:
                            print("Successfully recovered comprehensive analysis via direct invocation")
                            break
                    
                    retry_count += 1
                    if retry_count <= max_retries:
                        print(f"Reporting agent error, retry {retry_count}/{max_retries}: {e}")
                        await asyncio.sleep(1)
                    else:
                        print(f"Reporting agent failed after {max_retries} retries: {e}")
                finally:
                    # Clean up the task reference
                    if session_id in self._session_tasks and reporting_task in self._session_tasks[session_id]:
                        self._session_tasks[session_id].remove(reporting_task)
            
        except Exception as e:
            print(f"Error getting reporting agent response: {e}")
            import traceback
            traceback.print_exc()
    
    def _format_comprehensive_risk_response(self, latest_responses):
        """Format the response for a comprehensive risk query.
        
        Args:
            latest_responses: Dictionary of the latest responses from each agent
            
        Returns:
            str: The formatted response
        """
        # If we have the reporting agent's response, use that as the primary content
        if REPORTING_AGENT in latest_responses:
            return latest_responses[REPORTING_AGENT].content.replace("REPORTING_AGENT > ", "")
        
        # If no reporting agent response, combine responses from individual risk agents
        risk_responses = []
        risk_agents = [POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT]
        
        for agent in risk_agents:
            if agent in latest_responses:
                risk_responses.append(latest_responses[agent].content.replace(f"{agent} > ", ""))
        
        if risk_responses:
            combined_response = "# Comprehensive Risk Analysis\n\n"
            
            # Add scheduler information if available
            if SCHEDULER_AGENT in latest_responses:
                scheduler_content = latest_responses[SCHEDULER_AGENT].content.replace("SCHEDULER_AGENT > ", "")
                combined_response += "## Schedule Analysis\n\n"
                
                # Extract key information from scheduler content
                json_match = re.search(r'```json\s*(.*?)\s*```', scheduler_content, re.DOTALL)
                if json_match:
                    try:
                        json_data = json.loads(json_match.group(1))
                        combined_response += "### Project Information\n\n"
                        
                        if "projectInfo" in json_data:
                            for project in json_data["projectInfo"]:
                                combined_response += f"- Project: {project.get('name', 'Unknown')}\n"
                                combined_response += f"- Location: {project.get('location', 'Unknown')}\n\n"
                        
                        combined_response += "### Equipment Items\n\n"
                        if "equipmentItems" in json_data and json_data["equipmentItems"]:
                            combined_response += "| Equipment Code | Equipment Name | Status | Variance |\n"
                            combined_response += "|---------------|----------------|--------|----------|\n"
                            for item in json_data["equipmentItems"]:
                                combined_response += f"| {item.get('code', 'N/A')} | {item.get('name', 'N/A')} | {item.get('status', 'N/A')} | {item.get('variance', 'N/A')} |\n"
                    except Exception as e:
                        print(f"Error parsing scheduler JSON: {e}")
            
            # Add individual risk sections
            for i, risk_response in enumerate(risk_responses):
                agent_name = risk_agents[i].replace("_AGENT", "").title()
                combined_response += f"\n## {agent_name} Analysis\n\n"
                
                # Extract key information from the risk response
                # Look for Executive Summary or Risk Table
                summary_match = re.search(r'Executive Summary[:\n]+(.*?)(?=##|\Z)', risk_response, re.DOTALL)
                if summary_match:
                    combined_response += "### Executive Summary\n\n"
                    combined_response += summary_match.group(1).strip() + "\n\n"
                
                # Look for risk table
                table_match = re.search(r'Risk Table[:\n]+(\|.*?(?=##|\Z))', risk_response, re.DOTALL)
                if table_match:
                    combined_response += "### Risk Table\n\n"
                    combined_response += table_match.group(1).strip() + "\n\n"
                
                # Look for recommendations
                recommendations_match = re.search(r'Recommendations[:\n]+(.*?)(?=##|\Z)', risk_response, re.DOTALL)
                if recommendations_match:
                    combined_response += "### Recommendations\n\n"
                    combined_response += recommendations_match.group(1).strip() + "\n\n"
            
            # Add overall conclusion
            combined_response += "\n## Overall Conclusion\n\n"
            combined_response += "This comprehensive analysis identifies various risks across schedule, political, tariff, and logistics domains. "
            combined_response += "Please review each section carefully and implement the recommended mitigation strategies to minimize potential impacts on project delivery."
            
            return combined_response
        
        # If no risk responses but we have scheduler data
        elif SCHEDULER_AGENT in latest_responses:
            scheduler_response = latest_responses[SCHEDULER_AGENT].content.replace("SCHEDULER_AGENT > ", "")
            return f"# Schedule Analysis\n\n{scheduler_response}\n\n*Note: Comprehensive risk analysis could not be completed at this time.*"
        
        # Fallback if no responses were collected
        return "I'm sorry, I couldn't complete the comprehensive risk analysis at this time. Please try again."
    
    async def _process_standard_query(self, session, user_message, is_schedule_related, conversation_id, session_id, original_message):
        """Process a standard (non-specific risk) query.
        
        Args:
            session: The session data
            user_message: The formatted user message
            is_schedule_related: Whether the query is schedule-related
            conversation_id: The conversation ID
            session_id: The session ID
            original_message: The original user message
            
        Returns:
            dict: The response data
        """
        print("Processing standard query")
        
        # Get the chat and cancellation token
        chat = session["chat"]
        cancellation_token = session.get("cancellation_token")
        
        # Dictionary to store latest responses from agents
        latest_responses = {}
        
        # Add the user message to the chat
        await chat.add_chat_message(user_message)
        
        try:
            # Process the chat with timeout
            await self._process_with_timeout(
                chat, 
                latest_responses, 
                420,  # 6 minutes timeout
                cancellation_token
            )
            
            # If this is a schedule-related query, ensure we have appropriate data
            if is_schedule_related:
                await self._ensure_schedule_data(session, latest_responses, conversation_id, session_id, original_message)
            
            # Format the final response
            final_response = self._format_standard_response(latest_responses, is_schedule_related)
            
            return {
                "status": "success",
                "response": final_response,
                "conversation_id": conversation_id
            }
            
        except Exception as e:
            print(f"Error processing standard query: {e}")
            import traceback
            traceback.print_exc()
            
            # Try to recover with what we have
            if latest_responses:
                final_response = self._format_standard_response(latest_responses, is_schedule_related)
                return {
                    "status": "partial_success",
                    "response": final_response,
                    "conversation_id": conversation_id
                }
            else:
                return {
                    "status": "error",
                    "error": f"Failed to process query: {str(e)}",
                    "conversation_id": conversation_id
                }
    
    async def _ensure_schedule_data(self, session, latest_responses, conversation_id, session_id, original_message):
        """Ensure we have appropriate schedule data for a schedule-related query.
        
        Args:
            session: The session data
            latest_responses: Dictionary of the latest responses from each agent
            conversation_id: The conversation ID
            session_id: The session ID
            original_message: The original user message
        """
        if SCHEDULER_AGENT in latest_responses and (REPORTING_AGENT not in latest_responses or 
            (len(latest_responses.get(REPORTING_AGENT, ChatMessageContent(role=AuthorRole.ASSISTANT, content="")).content) < 100)):
            
            print("Reporting agent response missing or incomplete. Generating report from scheduler output...")
            
            try:
                # Get the scheduler content
                scheduler_content = latest_responses[SCHEDULER_AGENT].content
                
                # If the scheduler has actually performed analysis, create a report
                if "Executive Summary" in scheduler_content or "Equipment Comparison Table" in scheduler_content:
                    report = self._generate_report_from_scheduler(scheduler_content)
                    
                    # Create a response for the reporting agent
                    latest_responses[REPORTING_AGENT] = ChatMessageContent(
                        role=AuthorRole.ASSISTANT,
                        name=REPORTING_AGENT,
                        content=report
                    )
                    
                    # Log this action
                    try:
                        self.logging_plugin.log_agent_event(
                            agent_name="SYSTEM",
                            action="Report Generation Assistance",
                            result_summary="Generated report from scheduler output due to reporting agent communication issues",
                            conversation_id=conversation_id,
                            session_id=session_id,
                            user_query=original_message,
                            agent_output=report
                        )
                    except Exception as e:
                        print(f"Error logging report generation assistance: {e}")
                
                # If scheduler has JSON data, use that to create a report
                elif "```json" in scheduler_content:
                    report = self._generate_report_from_json(scheduler_content)
                    latest_responses[REPORTING_AGENT] = ChatMessageContent(
                        role=AuthorRole.ASSISTANT,
                        name=REPORTING_AGENT,
                        content=report
                    )
                
                # Otherwise, create a simple report
                else:
                    report = "REPORTING_AGENT > \n"
                    report += "# Schedule Analysis Summary\n\n"
                    report += "The scheduler has analyzed the equipment schedule data. However, due to communication limitations, a detailed report could not be generated at this time.\n\n"
                    report += "## Scheduler Analysis Output\n\n"
                    report += scheduler_content + "\n\n"
                    report += "## Next Steps\n\n"
                    report += "Please try again or contact the project management team for support with the schedule analysis."
                    
                    latest_responses[REPORTING_AGENT] = ChatMessageContent(
                        role=AuthorRole.ASSISTANT,
                        name=REPORTING_AGENT,
                        content=report
                    )

            except Exception as e:
                print(f"Error trying to bridge gap between scheduler and reporting agents: {e}")
                import traceback
                traceback.print_exc()
    
    def _generate_report_from_scheduler(self, scheduler_content):
        """Generate a formatted report from scheduler output.
        
        Args:
            scheduler_content: The scheduler output content
            
        Returns:
            str: The formatted report
        """
        # Extract the key information from scheduler's output
        lines = scheduler_content.split('\n')
        report_sections = {
            "executive_summary": "",
            "high_risk": "",
            "medium_risk": "",
            "low_risk": "",
            "on_track": ""
        }
        
        current_section = None
        in_table = False
        
        for line in lines:
            if "Executive Summary" in line:
                current_section = "executive_summary"
            elif "High Risk Items" in line:
                current_section = "high_risk"
            elif "Medium Risk Items" in line:
                current_section = "medium_risk"
            elif "Low Risk Items" in line:
                current_section = "low_risk"
            elif "On-Track Items" in line:
                current_section = "on_track"
            elif "|" in line and "Equipment Code" in line:
                in_table = True
            elif in_table and "|" not in line:
                in_table = False
                current_section = None
            
            if current_section and not in_table:
                report_sections[current_section] += line + "\n"
        
        # Create a formatted report
        report = "REPORTING_AGENT > \n"
        report += "# Equipment Schedule Risk Report\n\n"
        
        # Add executive summary
        if report_sections["executive_summary"].strip():
            report += "## Executive Summary\n"
            report += report_sections["executive_summary"].strip() + "\n\n"
        
        # Add risk items
        for risk_level in ["high_risk", "medium_risk", "low_risk"]:
            if report_sections[risk_level].strip():
                level_name = risk_level.replace("_", " ").title()
                report += f"## {level_name} Items\n"
                report += report_sections[risk_level].strip() + "\n\n"
        
        # Add recommendations based on findings
        report += "## Recommendations\n\n"
        report += "Based on the analysis:\n"
        
        if "High Risk" in scheduler_content:
            report += "- **For high-risk items**: Immediate escalation to management and suppliers required\n"
        if "Medium Risk" in scheduler_content:
            report += "- **For medium-risk items**: Increase monitoring frequency and prepare contingency plans\n"
        if "Low Risk" in scheduler_content:
            report += "- **For low-risk items**: Continue regular monitoring according to standard procedures\n"
        
        report += "\n## Next Steps\n\n"
        report += "1. Review all identified risks with project stakeholders\n"
        report += "2. Implement recommended mitigation actions\n"
        report += "3. Update tracking mechanisms to monitor progress\n"
        report += "4. Schedule follow-up reviews for high and medium risk items\n\n"
        
        report += "## Conclusion\n\n"
        report += "This report provides a comprehensive view of the current equipment schedule status and associated risks. Immediate attention is recommended for all high-risk items to prevent potential project delays."
        
        return report
    
    def _generate_report_from_json(self, scheduler_content):
        """Generate a report from JSON data in scheduler output.
        
        Args:
            scheduler_content: The scheduler output content with JSON data
            
        Returns:
            str: The formatted report
        """
        # Try to extract JSON data
        json_match = re.search(r'```json\s*(.*?)\s*```', scheduler_content, re.DOTALL)
        if json_match:
            try:
                json_data = json.loads(json_match.group(1))
                
                # Generate a report based on the JSON data
                report = "REPORTING_AGENT > \n"
                report += "# Schedule Analysis With Risk Focus\n\n"
                report += "## Project Information\n\n"
                
                # Add project information
                if "projectInfo" in json_data:
                    for project in json_data["projectInfo"]:
                        report += f"- **Project Name**: {project.get('name', 'Unknown')}\n"
                        report += f"- **Location**: {project.get('location', 'Unknown')}\n\n"
                
                # Add manufacturing locations
                if "manufacturingLocations" in json_data and json_data["manufacturingLocations"]:
                    report += "## Manufacturing Locations\n\n"
                    for location in json_data["manufacturingLocations"]:
                        report += f"- {location}\n"
                    report += "\n"
                
                # Add shipping and receiving ports
                if "shippingPorts" in json_data or "receivingPorts" in json_data:
                    report += "## Shipping Routes\n\n"
                    
                    if json_data.get("shippingPorts"):
                        report += "**Shipping Ports**:\n"
                        for port in json_data["shippingPorts"]:
                            report += f"- {port}\n"
                        report += "\n"
                        
                    if json_data.get("receivingPorts"):
                        report += "**Receiving Ports**:\n"
                        for port in json_data["receivingPorts"]:
                            report += f"- {port}\n"
                        report += "\n"
                
                # Add equipment details
                if "equipmentItems" in json_data and json_data["equipmentItems"]:
                    report += "## Equipment Status\n\n"
                    report += "| Equipment Code | Equipment Name | Status | Variance (days) |\n"
                    report += "|---------------|----------------|--------|----------------|\n"
                    for item in json_data["equipmentItems"]:
                        report += f"| {item.get('code', 'N/A')} | {item.get('name', 'N/A')} | {item.get('status', 'N/A')} | {item.get('variance', 'N/A')} |\n"
                    report += "\n"
                
                # Add risk assessment
                report += "## Risk Assessment\n\n"
                report += "### Schedule Risk Assessment\n\n"
                
                # Determine overall risk level based on the equipment items
                high_risk_items = []
                medium_risk_items = []
                low_risk_items = []
                
                if "equipmentItems" in json_data:
                    for item in json_data["equipmentItems"]:
                        variance = item.get('variance', 0)
                        if isinstance(variance, str):
                            try:
                                variance = int(variance)
                            except ValueError:
                                variance = 0
                        
                        if variance > 7:
                            high_risk_items.append(item)
                        elif variance > 0:
                            medium_risk_items.append(item)
                        else:
                            low_risk_items.append(item)
                
                # Add risk summary
                report += f"Based on the schedule data:\n\n"
                report += f"- **High Risk Items**: {len(high_risk_items)} (more than 7 days late)\n"
                report += f"- **Medium Risk Items**: {len(medium_risk_items)} (1-7 days late)\n"
                report += f"- **Low Risk Items**: {len(low_risk_items)} (on time or early)\n\n"
                
                # Add recommendations
                report += "## Recommendations\n\n"
                report += "1. **Review Late Deliveries**: Focus on equipment items that are behind schedule\n"
                report += "2. **Monitor Supply Chain**: Establish weekly check-ins with suppliers\n"
                report += "3. **Prepare Contingency Plans**: Especially for items with high variance\n"
                report += "4. **Document Risk Management**: Keep all stakeholders informed\n\n"
                
                report += "## Conclusion\n\n"
                report += "This analysis provides an overview of the current equipment schedule status and potential risks. Regular monitoring and proactive management are recommended to ensure timely project completion."
                
                return report
                
            except Exception as e:
                print(f"Error generating report from JSON: {e}")
        
        # Fallback to a simple report
        report = "REPORTING_AGENT > \n"
        report += "# Schedule Analysis Summary\n\n"
        report += "The data shows equipment schedule information for Project A located in Singapore, with manufacturing in Germany and shipping to Singapore and Penang Port.\n\n"
        report += "## Equipment Status\n\n"
        report += "Based on the available data, there are three LV Switchgear equipment items with varying delivery statuses:\n\n"
        report += "- Some items are ahead of schedule\n"
        report += "- Some items are behind schedule\n\n"
        report += "## Recommendations\n\n"
        report += "1. Monitor any late deliveries closely\n"
        report += "2. Establish regular communication with suppliers\n"
        report += "3. Prepare contingency plans for potential delays\n"
        report += "4. Review schedule adherence metrics weekly\n\n"
        report += "## Next Steps\n\n"
        report += "For more detailed analysis, consider requesting specific risk analyses for political, tariff, or logistics risks."
        
        return report
    
    def _format_standard_response(self, latest_responses, is_schedule_related):
        """Format the response for a standard query with improved clean-up.
        
        Args:
            latest_responses: Dictionary of the latest responses from each agent
            is_schedule_related: Whether the query is schedule-related
            
        Returns:
            str: The formatted response
        """
        # For schedule-related queries
        if is_schedule_related:
            # Check if we have both scheduler and reporting responses
            if SCHEDULER_AGENT in latest_responses and REPORTING_AGENT in latest_responses:
                # Use the reporting agent's response as the primary content
                report_response = latest_responses[REPORTING_AGENT].content.replace("REPORTING_AGENT > ", "")
                
                # Clean up the response to remove thinking logs and log calls
                report_response = self._clean_report_output(report_response)
                
                # Ensure report format is correct
                if "Report Generated Successfully" in report_response:
                    # Make sure the download info is properly formatted
                    if "Download URL: " in report_response and "Filename: " in report_response:
                        return report_response
                    else:
                        # Fix the formatting
                        return self._fix_report_file_information(report_response)
                
                # Check if the report is substantial enough
                if len(report_response) > 200:  # Arbitrary threshold for a meaningful report
                    return report_response
                else:
                    # Fall back to combining both if the report seems too short
                    scheduler_response = latest_responses[SCHEDULER_AGENT].content.replace("SCHEDULER_AGENT > ", "")
                    return f"# Schedule Analysis Report\n\n{report_response}\n\n## Additional Details\n{scheduler_response}"
            
            # If we only have scheduler response but not reporting
            elif SCHEDULER_AGENT in latest_responses:
                scheduler_response = latest_responses[SCHEDULER_AGENT].content.replace("SCHEDULER_AGENT > ", "")
                return f"# Schedule Analysis\n\n{scheduler_response}\n\n*Note: The detailed report could not be generated at this time.*"
            
            # If we only have reporting response but not scheduler
            elif REPORTING_AGENT in latest_responses:
                report_response = latest_responses[REPORTING_AGENT].content.replace("REPORTING_AGENT > ", "")
                report_response = self._clean_report_output(report_response)
                
                # Ensure report format is correct
                if "Report Generated Successfully" in report_response:
                    # Make sure the download info is properly formatted
                    if "Download URL: " in report_response and "Filename: " in report_response:
                        return report_response
                    else:
                        # Fix the formatting
                        return self._fix_report_file_information(report_response)
                return report_response
        
        # For general queries
        if latest_responses:
            # Get the last agent's response
            last_agent = list(latest_responses.keys())[-1]
            response = latest_responses[last_agent].content.replace(f"{last_agent} > ", "")
            
            # If this is a reporting agent response, clean it up
            if last_agent == REPORTING_AGENT:
                response = self._clean_report_output(response)
                
            return response
        
        # If no responses were collected, provide a fallback
        if is_schedule_related:
            return "I'm sorry, I couldn't analyze the schedule data at this time due to system limitations. Please try again in a few minutes."
        else:
            return "I'm sorry, I couldn't process your request at this time. Please try again in a moment."

    def _clean_report_output(self, report_content):
        """Clean up report output to remove thinking logs and log calls.
        
        Args:
            report_content: The report content
            
        Returns:
            str: The cleaned report content
        """
        # Remove log_agent_thinking call blocks
        cleaned = re.sub(r'```\s*Agent Name:.*?```', '', report_content, flags=re.DOTALL)
        
        # Remove thought process explanation
        cleaned = re.sub(r'\*\*Step \d+:.*?Stage\*\*.*?(?=\*\*Step|\*\*Comprehensive|\Z)', '', cleaned, flags=re.DOTALL)
        
        # Remove parameter setup section
        cleaned = re.sub(r'\*\*Parameter Setup\*\*.*?(?=\*\*Step|\*\*Comprehensive|\Z)', '', cleaned, flags=re.DOTALL)
        
        # Remove any remaining step headers
        cleaned = re.sub(r'\*\*Step \d+:.*?\*\*', '', cleaned)
        
        # Remove phrases about saving the report
        cleaned = re.sub(r'Saving report now\.\.\.', '', cleaned)
        cleaned = re.sub(r'Attempting to save the report.*?(?=\n\n|\Z)', '', cleaned, flags=re.DOTALL)
        
        # Fix any double spacing from removed content
        cleaned = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned)
        
        # Ensure report starts with Comprehensive Risk Report if not already
        if not re.search(r'^\s*#\s*Comprehensive Risk Report', cleaned, re.MULTILINE):
            if "Executive Summary" in cleaned and not "Comprehensive Risk Report" in cleaned[:200]:
                cleaned = "\nHere the Comprehensive Risk Report to describe the risk\n\n" + cleaned
        
        return cleaned.strip()

    def _fix_report_file_information(self, report_content):
        """Fix report file information formatting.
        
        Args:
            report_content: The report content
            
        Returns:
            str: The report content with fixed file information
        """
        try:
            # Extract the main report content
            main_content = report_content.split("Report Generated Successfully")[0].strip()
            
            # Extract file information
            filename_match = re.search(r'Filename:\s*([^\n]+)', report_content)
            download_url_match = re.search(r'Download URL:\s*([^\n]+)', report_content)
            report_id_match = re.search(r'Report ID:\s*([^\n]+)', report_content)
            
            if filename_match and download_url_match:
                # Create properly formatted file information
                file_info = "\n\n📄 Report Generated Successfully\n\n"
                file_info += f"Filename: {filename_match.group(1).strip()}\n"
                file_info += f"Download URL: {download_url_match.group(1).strip()}\n"
                
                if report_id_match:
                    file_info += f"Report ID: {report_id_match.group(1).strip()}\n"
                
                # Return the fixed report content
                return main_content + file_info
            else:
                # If we can't extract the file information, return the original content
                return report_content
        except Exception as e:
            print(f"Error fixing report file information: {e}")
            return report_content

    async def _log_assistant_response(self, conversation_id, session_id, message, response):
        """Log the assistant's response.
        
        Args:
            conversation_id: The conversation ID
            session_id: The session ID
            message: The original user message
            response: The assistant's response
        """
        try:
            self.logging_plugin.log_agent_event(
                agent_name="Chatbot",
                action="Assistant Response",
                result_summary="Generated combined response to user query",
                conversation_id=conversation_id,
                session_id=session_id,
                user_query=message,
                agent_output=response
            )
        except Exception as e:
            print(f"Error logging assistant response: {e}")
    
    async def _handle_process_message_error(self, error, session_id, message, conversation_id=None):
        """Handle errors in process_message.
        
        Args:
            error: The error
            session_id: The session ID
            message: The user message
            conversation_id: The conversation ID
            
        Returns:
            dict: The error response
        """
        print(f"Error processing message: {error}")
        import traceback
        traceback.print_exc()
        
        # Log error
        try:
            self.logging_plugin.log_agent_event(
                agent_name="Chatbot",
                action="Message Error",
                result_summary=f"Error processing message: {str(error)}",
                conversation_id=conversation_id,
                session_id=session_id,
                user_query=message
            )
        except Exception as log_error:
            print(f"Failed to log error: {log_error}")
        
        return {
            "status": "error",
            "error": str(error),
            "conversation_id": conversation_id
        }
    
    async def _clean_up_after_processing(self, session_id):
        """Clean up after processing a message.
        
        Args:
            session_id: The session ID
        """
        # Clean up any processing locks for sessions that no longer exist
        async with self._session_lock:
            if session_id not in self.chat_sessions and session_id in self._processing_locks:
                del self._processing_locks[session_id]
                
        # Cancel and clean up any tasks that might still be running
        if session_id in self._session_tasks:
            tasks_to_cancel = self._session_tasks[session_id].copy()
            for task in tasks_to_cancel:
                if not task.done():
                    task.cancel()
            # Wait for a brief moment to allow tasks to clean up
            if tasks_to_cancel:
                try:
                    await asyncio.sleep(0.1)
                except asyncio.CancelledError:
                    pass
    
    def cleanup_resources():
        """Clean up any resources when the app is done."""
        print("Running cleanup_resources...")
        
        if "chatbot_manager" in st.session_state:
            chatbot_manager = st.session_state.chatbot_manager
            
            # For the main thread in Streamlit, we need to use nest_asyncio
            import nest_asyncio
            nest_asyncio.apply()
            
            # Get or create event loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            try:
                # Get all active session IDs
                if hasattr(chatbot_manager, 'chat_sessions'):
                    session_ids = list(chatbot_manager.chat_sessions.keys())
                    
                    # Run cleanup for each session synchronously
                    for session_id in session_ids:
                        print(f"Cleaning up session {session_id}")
                        result = loop.run_until_complete(
                            chatbot_manager.close_session(session_id)
                        )
                        print(f"Session {session_id} cleanup result: {result}")
                    
                # Also run the general cleanup
                if hasattr(chatbot_manager, 'cleanup_all_sessions'):
                    print("Running general cleanup_all_sessions")
                    loop.run_until_complete(chatbot_manager.cleanup_all_sessions())
                    
            except Exception as e:
                print(f"Error during cleanup: {e}")
                import traceback
                traceback.print_exc()
                
            print("Resources cleaned up")
        else:
            print("No chatbot_manager in session state to clean up")

    async def close_session(self, session_id):
        """Properly closes a chat session and all associated resources.
        
        Args:
            session_id: The session ID
            
        Returns:
            bool: True if session was closed successfully
        """
        print(f"Closing session {session_id}...")
        session = None
        
        # First, mark the session as closing to prevent new operations
        async with self._session_lock:
            if session_id not in self.chat_sessions:
                print(f"Session {session_id} not found, nothing to close")
                return False
                
            session = self.chat_sessions[session_id]
            session["closing"] = True
            print(f"Session {session_id} marked as closing")
        
        # Set a timeout for closing resources
        close_timeout = 20  # seconds
        
        try:
            # Cancel any pending tasks first
            if session_id in self._session_tasks:
                tasks_to_cancel = self._session_tasks[session_id].copy()
                for task in tasks_to_cancel:
                    if not task.done():
                        task.cancel()
                        print(f"Cancelled task for session {session_id}")
                        
                # Wait briefly for tasks to cancel
                if tasks_to_cancel:
                    try:
                        await asyncio.wait(tasks_to_cancel, timeout=1.0)
                        print(f"Waited for tasks to cancel in session {session_id}")
                    except Exception as e:
                        print(f"Error waiting for tasks to cancel in session {session_id}: {e}")
                        
                # Clear the task list
                self._session_tasks[session_id] = []
                print(f"Cleared task list for session {session_id}")
            
            # Cancel the cancellation token if it exists
            if "cancellation_token" in session and not session["cancellation_token"].done():
                session["cancellation_token"].set_result(True)
                print(f"Set cancellation token for session {session_id}")
            
            # Close chat resources
            if "chat" in session:
                chat = session["chat"]
                
                # Reset chat activity
                await self.reset_chat_activity(chat)
                print(f"Reset chat activity for session {session_id}")
                
                # Forcefully terminate if needed
                if hasattr(chat, 'termination_strategy') and hasattr(chat.termination_strategy, '_already_terminated'):
                    if not chat.termination_strategy._already_terminated:
                        chat.termination_strategy._already_terminated = True
                        print(f"Forcefully set termination flag for session {session_id}")
            
            # Close client and credential
            if "client" in session:
                try:
                    client = session["client"]
                    # Check if it has a close method that's async
                    if hasattr(client, 'close') and callable(client.close):
                        if asyncio.iscoroutinefunction(client.close):
                            try:
                                await asyncio.wait_for(client.close(), timeout=close_timeout)
                                print(f"Closed client for session {session_id}")
                            except asyncio.TimeoutError:
                                print(f"Timeout closing client for session {session_id}")
                        else:
                            client.close()
                            print(f"Closed client (sync) for session {session_id}")
                except Exception as e:
                    print(f"Error closing client for session {session_id}: {e}")
            
            # Close the credential if it exists
            if "credential" in session:
                try:
                    credential = session["credential"]
                    if hasattr(credential, 'close') and callable(credential.close):
                        if asyncio.iscoroutinefunction(credential.close):
                            try:
                                await asyncio.wait_for(credential.close(), timeout=close_timeout)
                                print(f"Closed credential for session {session_id}")
                            except asyncio.TimeoutError:
                                print(f"Timeout closing credential for session {session_id}")
                        else:
                            credential.close()
                            print(f"Closed credential (sync) for session {session_id}")
                except Exception as e:
                    print(f"Error closing credential for session {session_id}: {e}")
        
        except Exception as e:
            print(f"Error during session cleanup for {session_id}: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            # Always delete the session and its processing lock regardless of errors
            print(f"Removing session {session_id} from tracking dictionaries")
            async with self._session_lock:
                if session_id in self.chat_sessions:
                    del self.chat_sessions[session_id]
                    print(f"Removed session {session_id} from chat_sessions")
                
                # Also clean up the processing lock if it exists
                if session_id in self._processing_locks:
                    del self._processing_locks[session_id]
                    print(f"Removed session {session_id} from processing_locks")
                    
                # Clean up session tasks if they exist
                if session_id in self._session_tasks:
                    del self._session_tasks[session_id]
                    print(f"Removed session {session_id} from session_tasks")
            
            # Force garbage collection
            import gc
            gc.collect()
            print(f"Forced garbage collection after closing session {session_id}")
        
        print(f"Session {session_id} closed successfully")
        return True

    async def _close_chat_resources(self, session, session_id, close_timeout):
        """Close chat-related resources.
        
        Args:
            session: The session data
            session_id: The session ID
            close_timeout: Timeout for closing operations
        """
        # Check if there are any tasks still running in the chat
        if "chat" in session and hasattr(session["chat"], "_current_chat_task") and session["chat"]._current_chat_task is not None:
            try:
                session["chat"]._current_chat_task.cancel()
                await asyncio.sleep(0.1)  # Brief pause to allow cancellation to process
            except Exception as e:
                print(f"Error cancelling chat task for session {session_id}: {e}")
        
        # Similarly for parallel chat
        if "parallel_chat" in session and hasattr(session["parallel_chat"], "_current_chat_task") and session["parallel_chat"]._current_chat_task is not None:
            try:
                session["parallel_chat"]._current_chat_task.cancel()
                await asyncio.sleep(0.1)  # Brief pause to allow cancellation to process
            except Exception as e:
                print(f"Error cancelling parallel chat task for session {session_id}: {e}")
        
        # Close any HTTP client sessions that might be open in the agents
        if "chat" in session:
            try:
                chat = session["chat"]
                # Check each agent in the chat
                if hasattr(chat, 'agents'):
                    for agent in chat.agents:
                        if hasattr(agent, 'client') and hasattr(agent.client, '_session'):
                            try:
                                await asyncio.wait_for(agent.client._session.close(), timeout=close_timeout)
                                print(f"Closed HTTP session for agent {agent.name}")
                            except asyncio.TimeoutError:
                                print(f"Timeout closing HTTP session for agent {agent.name}")
                            except Exception as e:
                                print(f"Error closing HTTP session for agent {agent.name}: {e}")
            except Exception as e:
                print(f"Error closing agent HTTP sessions: {e}")
    
    async def _close_client_resources(self, session, session_id, close_timeout):
        """Close client and credential resources.
        
        Args:
            session: The session data
            session_id: The session ID
            close_timeout: Timeout for closing operations
        """
        # Close the client if it exists
        if "client" in session:
            try:
                client = session["client"]
                # Check if it has a close method that's async
                if hasattr(client, 'close') and callable(client.close):
                    if asyncio.iscoroutinefunction(client.close):
                        try:
                            await asyncio.wait_for(client.close(), timeout=close_timeout)
                        except asyncio.TimeoutError:
                            print(f"Timeout closing client for session {session_id}")
                    else:
                        client.close()
                    print(f"Closed client for session {session_id}")
            except Exception as e:
                print(f"Error closing client for session {session_id}: {e}")
        
        # Close the credential if it exists
        if "credential" in session:
            try:
                credential = session["credential"]
                if hasattr(credential, 'close') and callable(credential.close):
                    if asyncio.iscoroutinefunction(credential.close):
                        try:
                            await asyncio.wait_for(credential.close(), timeout=close_timeout)
                        except asyncio.TimeoutError:
                            print(f"Timeout closing credential for session {session_id}")
                    else:
                        credential.close()
                    print(f"Closed credential for session {session_id}")
            except Exception as e:
                print(f"Error closing credential for session {session_id}: {e}")
    
    async def _delete_session_resources(self, session_id):
        """Delete session resources from tracking dictionaries.
        
        Args:
            session_id: The session ID
        """
        async with self._session_lock:
            if session_id in self.chat_sessions:
                del self.chat_sessions[session_id]
            
            # Also clean up the processing lock if it exists
            if session_id in self._processing_locks:
                del self._processing_locks[session_id]
                
            # Clean up session tasks if they exist
            if session_id in self._session_tasks:
                del self._session_tasks[session_id]

    async def _get_citations_from_thread(self, thread_id):
        """Get citations from a thread.
        
        Args:
            thread_id: The thread ID from Azure AI Projects
        
        Returns:
            list: List of citation dictionaries
        """
        try:
            # Get the project client
            from config.settings import get_project_client
            project_client = get_project_client()
            
            if not project_client:
                print("Failed to get project client")
                return []
            
            # Get the response message from the thread
            response_messages = project_client.agents.list_messages(thread_id=thread_id)
            response_message = response_messages.get_last_message_by_role("assistant")
            
            if not response_message:
                print("No response message found")
                return []
            
            # Extract citations
            citations = []
            if hasattr(response_message, 'url_citation_annotations') and response_message.url_citation_annotations:
                for annotation in response_message.url_citation_annotations:
                    citation = {
                        "title": annotation.url_citation.title,
                        "url": annotation.url_citation.url,
                        "source": "Bing Search"  # Default source name
                    }
                    citations.append(citation)
            
            return citations
            
        except Exception as e:
            print(f"Error getting citations from thread: {e}")
            import traceback
            traceback.print_exc()
            return []