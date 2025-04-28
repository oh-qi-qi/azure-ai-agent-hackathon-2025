"""Chatbot manager for equipment schedule agent."""

import uuid
import asyncio
import json
import re
import os
import time
from datetime import datetime
from dotenv import load_dotenv

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

# Load environment variables from .env file
load_dotenv()

class ChatbotManager:
    """Manages the interactive chatbot for user queries."""
    
    def __init__(self, connection_string):
        self.connection_string = connection_string
        self.schedule_plugin = EquipmentSchedulePlugin(connection_string)
        self.risk_plugin = RiskCalculationPlugin()
        self.logging_plugin = LoggingPlugin(connection_string)
        self.report_file_plugin = ReportFilePlugin(connection_string)
        self.chat_sessions = {}
        # Use a single lock for all session management operations
        self._session_lock = asyncio.Lock()
        # Add rate limiter for parallel execution
        self.rate_limiter = RateLimitedExecutor(max_concurrent=2, requests_per_minute=20)
        # Add processing lock for preventing race conditions
        self._processing_locks = {}
        # Add task tracking dictionary
        self._session_tasks = {}
        
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
                loop.run_until_complete(self.cleanup_all_sessions())
                
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
    
    async def initialize_session(self, session_id):
        """Initializes a new chat session with all agents using a lock to prevent race conditions."""
        
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
        # Other threads will see it's being initialized and wait
        
        try:
            # Get Azure AI Agent settings
            ai_agent_settings = initialize_ai_agent_settings()
            
            # Create credentials - no await needed
            creds = DefaultAzureCredential(exclude_environment_credential=True, 
                                       exclude_managed_identity_credential=True)
            
            # Create client - no await needed
            client = AzureAIAgent.create_client(credential=creds)
            
            # Create separate logging plugins for each agent
            scheduler_logging = LoggingPlugin(self.connection_string)
            reporting_logging = LoggingPlugin(self.connection_string)
            assistant_logging = LoggingPlugin(self.connection_string)
            political_logging = LoggingPlugin(self.connection_string)
            tariff_logging = LoggingPlugin(self.connection_string)
            logistics_logging = LoggingPlugin(self.connection_string)
            
            # Create or reuse all agents
            agents = {}
            
            # Create Bing connection configuration if API key is available
            bing_connection = None
            if self.bing_api_key:
                bing_connection = {
                    "type": "BingGrounding",
                    "connection_name": "bing",
                    "api_key": self.bing_api_key
                }
                print(f"Bing connection configured with API key: {'*' * 10}{self.bing_api_key[-4:]}")
            else:
                print("WARNING: Bing search will not be available for risk agents due to missing API key")
            
            # Create scheduler agent
            print(f"Creating/retrieving scheduler agent for session {session_id}...")
            agents[SCHEDULER_AGENT] = await create_or_reuse_agent(
                client=client,
                agent_name=SCHEDULER_AGENT,
                model_deployment_name=ai_agent_settings.model_deployment_name,
                instructions=get_scheduler_agent_instructions(),
                plugins=[self.schedule_plugin, self.risk_plugin, scheduler_logging]
            )

            # Create political risk agent with Bing search
            print(f"Creating/retrieving political risk agent for session {session_id}...")
            agents[POLITICAL_RISK_AGENT] = await create_or_reuse_agent(
                client=client,
                agent_name=POLITICAL_RISK_AGENT,
                model_deployment_name=ai_agent_settings.model_deployment_name,
                instructions=get_political_risk_agent_instructions(),
                plugins=[political_logging],
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
            
            # Get agent IDs
            agent_ids = {}
            for agent_name, agent in agents.items():
                if hasattr(agent, 'definition') and hasattr(agent.definition, 'id'):
                    agent_ids[agent_name] = agent.definition.id
                else:
                    agent_ids[agent_name] = None
            
            # Set agent IDs in their respective logging plugins
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
            
            # Now recreate agents with instructions that include their IDs (if the function exists)
            import inspect
            
            # Recreate each agent with ID-specific instructions if supported
            for agent_name, agent_id in agent_ids.items():
                if agent_id:
                    instruction_func = globals().get(f"get_{agent_name.lower()}_instructions")
                    if instruction_func and callable(instruction_func):
                        if len(inspect.signature(instruction_func).parameters) > 0:
                            # Get the corresponding logging plugin
                            logging_plugin = {
                                SCHEDULER_AGENT: scheduler_logging,
                                POLITICAL_RISK_AGENT: political_logging,
                                TARIFF_RISK_AGENT: tariff_logging,
                                LOGISTICS_RISK_AGENT: logistics_logging,
                                REPORTING_AGENT: reporting_logging,
                                ASSISTANT_AGENT: assistant_logging
                            }.get(agent_name)
                            
                            # Get the plugins for each agent
                            agent_plugins = {
                                SCHEDULER_AGENT: [self.schedule_plugin, self.risk_plugin, scheduler_logging],
                                POLITICAL_RISK_AGENT: [political_logging],
                                TARIFF_RISK_AGENT: [tariff_logging],
                                LOGISTICS_RISK_AGENT: [logistics_logging],
                                REPORTING_AGENT: [self.schedule_plugin, reporting_logging, self.report_file_plugin],
                                ASSISTANT_AGENT: [self.schedule_plugin, self.risk_plugin, assistant_logging]
                            }.get(agent_name, [])
                            
                            # Get the connections for each agent
                            agent_connections = None
                            if agent_name in [POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT]:
                                agent_connections = bing_connection
                            
                            agents[agent_name] = await create_or_reuse_agent(
                                client=client,
                                agent_name=agent_name,
                                model_deployment_name=ai_agent_settings.model_deployment_name,
                                instructions=instruction_func(agent_id),
                                plugins=agent_plugins,
                                connections=agent_connections
                            )
            
            # Print agent status
            for agent_name, agent in agents.items():
                print(f"{agent_name} agent ready: {agent.name} (ID: {agent_ids.get(agent_name, 'None')})")
            
            print(f"Creating agent group chat for session {session_id}...")
            
            # Create the agent group chat with all agents
            chat = AgentGroupChat(
                agents=list(agents.values()),
                termination_strategy=ChatbotTerminationStrategy(),
                selection_strategy=ChatbotSelectionStrategy()
            )
            
            # Create a parallel risk analysis chat for comprehensive analysis
            parallel_chat = AgentGroupChat(
                agents=list(agents.values()),
                termination_strategy=ChatbotTerminationStrategy(),
                selection_strategy=ParallelRiskAnalysisStrategy()
            )
            
            print(f"Chat session created successfully: {session_id}")
            
            # Initialize task tracking list
            self._session_tasks[session_id] = []
            
            # Update the chat session with the full data
            async with self._session_lock:
                # Check if session still exists (might have been cleaned up during initialization)
                if session_id in self.chat_sessions:
                    self.chat_sessions[session_id].update({
                        "chat": chat,
                        "parallel_chat": parallel_chat,
                        "client": client,
                        "credential": creds,
                        "last_activity": datetime.now(),
                        "model_deployment_name": ai_agent_settings.model_deployment_name,
                        "agents": agents,
                        "agent_ids": agent_ids,
                        "conversation_id": conversation_id,
                        "initializing": False  # Mark as fully initialized
                    })
                    # Return the fully initialized session
                    return self.chat_sessions[session_id]
                else:
                    # Session was cleaned up during initialization
                    # Clean up resources we created
                    if hasattr(client, 'close') and callable(client.close):
                        try:
                            await client.close()
                        except Exception as e:
                            print(f"Error closing client during cleanup: {e}")
                    
                    if hasattr(creds, 'close') and callable(creds.close):
                        try:
                            await creds.close()
                        except Exception as e:
                            print(f"Error closing credentials during cleanup: {e}")
                    
                    # Recreate the session
                    self.chat_sessions[session_id] = {
                        "chat": chat,
                        "parallel_chat": parallel_chat,
                        "client": client,
                        "credential": creds,
                        "last_activity": datetime.now(),
                        "model_deployment_name": ai_agent_settings.model_deployment_name,
                        "agents": agents,
                        "agent_ids": agent_ids,
                        "conversation_id": conversation_id,
                        "initializing": False,  # Mark as fully initialized
                        "cancellation_token": asyncio.Future()  # Add cancellation token
                    }
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
    
    async def process_agent_with_rate_limit(self, chat, agent_name, message_content):
        """Process an agent with rate limiting and timeout."""
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
                # Set a timeout for this specific agent - increased for reliability
                agent_timeout = 60  # seconds (increased from 30)
                
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
        """Process chat invocation with timeout, adding responses to latest_responses dictionary."""
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
            
            # Add cancellation token if provided - FIX HERE
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

    async def process_message(self, session_id, message):
        """Processes a user message and returns the combined response from all agents."""
        
        # Create session-specific lock if it doesn't exist to prevent race conditions
        # for consecutive messages from the same session
        if session_id not in self._processing_locks:
            self._processing_locks[session_id] = asyncio.Lock()
        
        # Acquire the processing lock for this session
        async with self._processing_locks[session_id]:
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
                
                # Use the conversation ID from the session, or generate a new one if missing
                conversation_id = session.get("conversation_id", str(uuid.uuid4()))
                
                # If conversation_id was missing, update the session
                if "conversation_id" not in session:
                    async with self._session_lock:
                        session["conversation_id"] = conversation_id
                
                # Log the user query with the logging plugin
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
                
                # Update last activity time
                async with self._session_lock:
                    session["last_activity"] = datetime.now()
                
                # Get model deployment name from session
                model_deployment_name = session.get("model_deployment_name", "unknown")
                
                # Determine if this is a comprehensive risk analysis request
                is_comprehensive_risk = any(keyword in message.lower() 
                                        for keyword in ["all risks", "comprehensive", "full risk", "complete risk", "risk analysis"])
                
                # Check if the message is schedule-related
                is_schedule_related = any(keyword in message.lower() for keyword in 
                                        ["schedule", "risk", "delay", "variance", "late", "delivery", "milestone"])
                
                # Determine specific risk type queries
                is_political_risk = any(keyword in message.lower() for keyword in 
                                    ["political risk", "political risks", "government", "political unrest"])
                is_tariff_risk = any(keyword in message.lower() for keyword in 
                                ["tariff risk", "tariff risks", "trade risk", "customs", "import duties"])
                is_logistics_risk = any(keyword in message.lower() for keyword in 
                                    ["logistics risk", "logistics risks", "shipping risk", "port risk"])
                
                # Determine if this requires a specific risk agent
                is_specific_risk = is_political_risk or is_tariff_risk or is_logistics_risk
                
                # Add the user message to the chat with thinking context
                print(f"Creating user message content for session {session_id}")
                user_message = ChatMessageContent(
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
                
                # Choose the appropriate chat based on the query type
                if is_comprehensive_risk:
                    chat = session["parallel_chat"]  # Use parallel chat for comprehensive analysis
                    print(f"Using parallel chat for comprehensive risk analysis in session {session_id}")
                else:
                    chat = session["chat"]  # Use regular chat for other queries
                    print(f"Using regular chat for session {session_id}")
                
                print(f"Adding message to chat for session {session_id}")
                await chat.add_chat_message(user_message)
                
                print(f"Invoking chat for session {session_id}...")
                # Get the responses from all agents - use a dictionary to track latest response from each agent
                latest_responses = {}
                
                # Get the cancellation token from the session
                cancellation_token = session.get("cancellation_token")
                
                # Set a timeout for the entire chat invocation process
                invoke_timeout = 180  # seconds (increased from 120)
                
                try:
                    if is_specific_risk:
                        # Handle specific risk query with improved flow
                        print(f"Handling specific risk query: {'Political' if is_political_risk else 'Tariff' if is_tariff_risk else 'Logistics'}")
                        
                        # Step 1: Get the scheduler response first with timeout
                        scheduler_response = None
                        scheduler_timeout = 60  # seconds (increased from 30)
                        
                        try:
                            # Create a task to get scheduler response with timeout
                            async def get_scheduler_response():
                                nonlocal scheduler_response
                                async for response in chat.invoke():
                                    # Check for cancellation
                                    if cancellation_token and cancellation_token.done():
                                        print("Scheduler processing cancelled via token")
                                        return
                                    
                                    if response and hasattr(response, 'name') and response.name == SCHEDULER_AGENT:
                                        scheduler_response = response
                                        latest_responses[SCHEDULER_AGENT] = response
                                        return
                            
                            # Add retry mechanism for scheduler
                            retry_count = 0
                            max_retries = 2
                            
                            while retry_count <= max_retries:
                                try:
                                    # Create a task for the operation
                                    scheduler_task = asyncio.create_task(get_scheduler_response())
                                    
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
                            
                        except asyncio.CancelledError:
                            print("Scheduler task cancelled")
                            raise
                        except Exception as e:
                            print(f"Error getting scheduler response: {e}")
                            import traceback
                            traceback.print_exc()
                        
                        # Check for cancellation
                        if cancellation_token and cancellation_token.done():
                            return {
                                "status": "cancelled",
                                "error": "Operation was cancelled",
                                "conversation_id": conversation_id
                            }
                        
                        if scheduler_response:
                            print("Scheduler response received, preparing for risk agent")
                            scheduler_content = scheduler_response.content
                            
                            # Step 2: Extract JSON data or create structured data for risk agent
                            structured_data = None
                            
                            # Try to find JSON in the response
                            json_match = re.search(r'```json\s*(.*?)\s*```', scheduler_content, re.DOTALL)
                            
                            if json_match:
                                # Extract the JSON string
                                try:
                                    json_data = json.loads(json_match.group(1))
                                    structured_data = json.dumps(json_data, indent=2)
                                    print("Successfully extracted JSON data from scheduler response")
                                except Exception as e:
                                    print(f"Error parsing JSON: {e}")
                            
                            # If JSON extraction failed, create a simplified version
                            if not structured_data:
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
                                
                                structured_data = json.dumps(simplified_data, indent=2)
                            
                            # Step 3: Prepare concise message for risk agent
                            concise_message = f"""SCHEDULER_AGENT > ```json
{structured_data}
```"""
                            
                            # Step 4: Determine which specific risk agent to use
                            target_risk_agent = None
                            if is_political_risk:
                                target_risk_agent = POLITICAL_RISK_AGENT
                            elif is_tariff_risk:
                                target_risk_agent = TARIFF_RISK_AGENT
                            elif is_logistics_risk:
                                target_risk_agent = LOGISTICS_RISK_AGENT
                            
                            if target_risk_agent:
                                # Create a message for the target risk agent with the concise data
                                print(f"Creating concise message for {target_risk_agent}")
                                risk_agent_message = ChatMessageContent(
                                    role=AuthorRole.ASSISTANT,
                                    name=SCHEDULER_AGENT,
                                    content=concise_message
                                )
                                
                                # Add the message to the chat
                                await chat.add_chat_message(risk_agent_message)
                                
                                # Now get the risk agent's response with timeout
                                risk_timeout = 80  # seconds (increased from 60)
                                try:
                                    # Create a task to get risk agent response with timeout
                                    async def get_risk_response():
                                        async for response in chat.invoke():
                                            # Check for cancellation
                                            if cancellation_token and cancellation_token.done():
                                                print(f"{target_risk_agent} processing cancelled via token")
                                                return
                                                
                                            if response and hasattr(response, 'name') and response.name == target_risk_agent:
                                                latest_responses[target_risk_agent] = response
                                                return
                                    
                                    # Add retry logic for risk agent
                                    retry_count = 0
                                    max_retries = 2
                                    
                                    while retry_count <= max_retries:
                                        try:
                                            # Create a task for the operation
                                            risk_task = asyncio.create_task(get_risk_response())
                                            
                                            # Track the task
                                            if session_id in self._session_tasks:
                                                self._session_tasks[session_id].append(risk_task)
                                            
                                            # Wait for risk agent response with timeout
                                            await asyncio.wait_for(risk_task, timeout=risk_timeout)
                                            break  # Success, exit the retry loop
                                        except asyncio.TimeoutError:
                                            retry_count += 1
                                            if retry_count <= max_retries:
                                                print(f"{target_risk_agent} timeout, retry {retry_count}/{max_retries}")
                                                await asyncio.sleep(1)  # Brief pause before retry
                                            else:
                                                print(f"Risk agent {target_risk_agent} timed out after {risk_timeout} seconds and {max_retries} retries")
                                        finally:
                                            # Clean up the task reference
                                            if session_id in self._session_tasks and risk_task in self._session_tasks[session_id]:
                                                self._session_tasks[session_id].remove(risk_task)
                                    
                                except asyncio.CancelledError:
                                    print(f"{target_risk_agent} task cancelled")
                                    raise
                                except Exception as e:
                                    print(f"Error getting {target_risk_agent} response: {e}")
                                
                                # Check for cancellation
                                if cancellation_token and cancellation_token.done():
                                    return {
                                        "status": "cancelled",
                                        "error": "Operation was cancelled",
                                        "conversation_id": conversation_id
                                    }
                                
                                # If we got a risk response, now get the reporting agent's response
                                if target_risk_agent in latest_responses:
                                    print(f"{target_risk_agent} response received, continuing to reporting agent")
                                    reporting_timeout = 60  # seconds (increased from 30)
                                    try:
                                        # Create a task to get reporting agent response with timeout
                                        async def get_reporting_response():
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
                                                reporting_task = asyncio.create_task(get_reporting_response())
                                                
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
                                            finally:
                                                # Clean up the task reference
                                                if session_id in self._session_tasks and reporting_task in self._session_tasks[session_id]:
                                                    self._session_tasks[session_id].remove(reporting_task)
                                        
                                    except asyncio.CancelledError:
                                        print("Reporting task cancelled")
                                        raise
                                    except Exception as e:
                                        print(f"Error getting reporting agent response: {e}")
                                else:
                                    print(f"No response from {target_risk_agent}, falling back to regular flow")
                                    # Continue with normal flow if risk agent didn't respond
                                    process_task = asyncio.create_task(
                                        self._process_with_timeout(
                                            chat, 
                                            latest_responses,
                                            max(1, invoke_timeout - (time.time() - time.time())),
                                            cancellation_token
                                        )
                                    )
                                    # Track the task
                                    if session_id in self._session_tasks:
                                        self._session_tasks[session_id].append(process_task)
                                    
                                    try:
                                        await process_task
                                    finally:
                                        # Clean up the task reference
                                        if session_id in self._session_tasks and process_task in self._session_tasks[session_id]:
                                            self._session_tasks[session_id].remove(process_task)
                            else:
                                print("No specific risk agent identified, falling back to normal flow")
                                # Continue with normal flow if no risk agent was identified
                                process_task = asyncio.create_task(
                                    self._process_with_timeout(
                                        chat, 
                                        latest_responses,
                                        max(1, invoke_timeout - (time.time() - time.time())),
                                        cancellation_token
                                    )
                                )
                                # Track the task
                                if session_id in self._session_tasks:
                                    self._session_tasks[session_id].append(process_task)
                                
                                try:
                                    await process_task
                                finally:
                                    # Clean up the task reference
                                    if session_id in self._session_tasks and process_task in self._session_tasks[session_id]:
                                        self._session_tasks[session_id].remove(process_task)
                        else:
                            print("No scheduler response received, falling back to normal flow")
                            # Fall back to normal flow if scheduler didn't respond
                            process_task = asyncio.create_task(
                                self._process_with_timeout(
                                    chat, 
                                    latest_responses,
                                    max(1, invoke_timeout - (time.time() - time.time())),
                                    cancellation_token
                                )
                            )
                            # Track the task
                            if session_id in self._session_tasks:
                                self._session_tasks[session_id].append(process_task)
                            
                            try:
                                await process_task
                            finally:
                                # Clean up the task reference
                                if session_id in self._session_tasks and process_task in self._session_tasks[session_id]:
                                    self._session_tasks[session_id].remove(process_task)
                    
                    elif is_comprehensive_risk:
                        # For comprehensive risk analysis, we use parallel execution with timeouts
                        risk_agents = [POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT]
                        
                        # First, get scheduler response with timeout
                        scheduler_timeout = 60  # seconds (increased from 30)
                        try:
                            # Create a task to get scheduler response with timeout
                            async def get_scheduler_response():
                                async for response in chat.invoke():
                                    # Check for cancellation
                                    if cancellation_token and cancellation_token.done():
                                        print("Scheduler processing cancelled via token")
                                        return
                                
                                    if response and hasattr(response, 'name') and response.name == SCHEDULER_AGENT:
                                        latest_responses[SCHEDULER_AGENT] = response
                                        return
                            
                            # Add retry mechanism for scheduler
                            retry_count = 0
                            max_retries = 2
                            
                            while retry_count <= max_retries:
                                try:
                                    # Create a task for the operation
                                    scheduler_task = asyncio.create_task(get_scheduler_response())
                                    
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
                            
                        except asyncio.CancelledError:
                            print("Scheduler task cancelled")
                            raise
                        except Exception as e:
                            print(f"Error getting scheduler response: {e}")
                        
                        # Check for cancellation
                        if cancellation_token and cancellation_token.done():
                            return {
                                "status": "cancelled",
                                "error": "Operation was cancelled",
                                "conversation_id": conversation_id
                            }
                        
                        # If we have scheduler response, process risk agents in parallel
                        if SCHEDULER_AGENT in latest_responses:
                            # Try to extract JSON data from scheduler response
                            scheduler_content = latest_responses[SCHEDULER_AGENT].content
                            json_match = re.search(r'```json\s*(.*?)\s*```', scheduler_content, re.DOTALL)
                            
                            if json_match:
                                try:
                                    json_data = json.loads(json_match.group(1))
                                    structured_data = json.dumps(json_data, indent=2)
                                    
                                    # Use structured data for risk agents
                                    concise_message = f"""SCHEDULER_AGENT > ```json
{structured_data}
```"""
                                    
                                    # Replace the original message with the concise one
                                    latest_responses[SCHEDULER_AGENT].content = concise_message
                                except Exception as e:
                                    print(f"Error parsing JSON for comprehensive analysis: {e}")
                            
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
                            
                            # Check for cancellation
                            if cancellation_token and cancellation_token.done():
                                return {
                                    "status": "cancelled", 
                                    "error": "Operation was cancelled",
                                    "conversation_id": conversation_id
                                }
                            
                            # Now get reporting agent response with timeout
                            reporting_timeout = 60  # seconds (increased from 30)
                            try:
                                # Create a task to get reporting agent response with timeout
                                async def get_reporting_response():
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
                                        reporting_task = asyncio.create_task(get_reporting_response())
                                        
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
                                    finally:
                                        # Clean up the task reference
                                        if session_id in self._session_tasks and reporting_task in self._session_tasks[session_id]:
                                            self._session_tasks[session_id].remove(reporting_task)
                                
                            except asyncio.CancelledError:
                                print("Reporting task cancelled")
                                raise
                            except Exception as e:
                                print(f"Error getting reporting agent response: {e}")
                        else:
                            # If no scheduler response, try to get responses from other agents
                            process_task = asyncio.create_task(
                                self._process_with_timeout(
                                    chat, 
                                    latest_responses, 
                                    max(1, invoke_timeout - (time.time() - time.time())),
                                    cancellation_token
                                )
                            )
                            # Track the task
                            if session_id in self._session_tasks:
                                self._session_tasks[session_id].append(process_task)
                            
                            try:
                                await process_task
                            finally:
                                # Clean up the task reference
                                if session_id in self._session_tasks and process_task in self._session_tasks[session_id]:
                                    self._session_tasks[session_id].remove(process_task)
                    else:
                        # For non-comprehensive queries, use the normal flow with timeout
                        process_task = asyncio.create_task(
                            self._process_with_timeout(
                                chat, 
                                latest_responses, 
                                invoke_timeout,
                                cancellation_token
                            )
                        )
                        # Track the task
                        if session_id in self._session_tasks:
                            self._session_tasks[session_id].append(process_task)
                        
                        try:
                            await process_task
                        finally:
                            # Clean up the task reference
                            if session_id in self._session_tasks and process_task in self._session_tasks[session_id]:
                                self._session_tasks[session_id].remove(process_task)
                    
                except asyncio.CancelledError:
                    print(f"Processing for session {session_id} was cancelled")
                    return {
                        "status": "cancelled",
                        "error": "Operation was cancelled",
                        "conversation_id": conversation_id
                    }
                
                except asyncio.TimeoutError:
                    print(f"Chat invocation timed out after {invoke_timeout} seconds")
                    # Don't return error, just continue with what we have
                
                except Exception as e:
                    print(f"Error during chat.invoke(): {e}")
                    import traceback
                    traceback.print_exc()
                    
                    # Log the error but don't return error response yet - try to salvage what we can
                    try:
                        self.logging_plugin.log_agent_event(
                            agent_name="Chatbot",
                            action="Chat Error",
                            result_summary=f"Error during chat invocation: {str(e)}",
                            conversation_id=conversation_id,
                            session_id=session_id,
                            user_query=message
                        )
                    except Exception as log_error:
                        print(f"Failed to log error: {log_error}")
                    
                    # If we have no responses at all, return error
                    if not latest_responses:
                        return {
                            "status": "error",
                            "error": f"The agent encountered an error: {str(e)}. Please try again.",
                            "conversation_id": conversation_id
                        }
                    # Otherwise continue with what we have
                
                # Check if operation was cancelled
                if cancellation_token and cancellation_token.done():
                    return {
                        "status": "cancelled",
                        "error": "Operation was cancelled",
                        "conversation_id": conversation_id
                    }
                
                # For schedule-related queries, ensure data is properly passed from SCHEDULER to REPORTING agent
                if is_schedule_related:
                    if SCHEDULER_AGENT in latest_responses and (REPORTING_AGENT not in latest_responses or 
                        (len(latest_responses.get(REPORTING_AGENT, ChatMessageContent(role=AuthorRole.ASSISTANT, content="")).content) < 100)):
                        
                        print("Reporting agent response missing or incomplete. Helping bridge the gap...")
                        
                        try:
                            # If the scheduler agent has run the analysis but reporting agent failed,
                            # we can use the scheduler's output to create a report
                            scheduler_content = latest_responses[SCHEDULER_AGENT].content
                            
                            # Check if the scheduler has actually performed analysis
                            if "Executive Summary" in scheduler_content or "Equipment Comparison Table" in scheduler_content:
                                print("Scheduler has data, creating report from scheduler output...")
                                
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
                                
                                # Create a mock response for the reporting agent
                                if REPORTING_AGENT not in latest_responses:
                                    latest_responses[REPORTING_AGENT] = ChatMessageContent(
                                        role=AuthorRole.ASSISTANT,
                                        name=REPORTING_AGENT,
                                        content=report
                                    )
                                else:
                                    # Just update the content if we already have a response object
                                    latest_responses[REPORTING_AGENT].content = report
                                
                                print(f"Generated report from scheduler output")
                                
                                # Log this action
                                try:
                                    self.logging_plugin.log_agent_event(
                                        agent_name="SYSTEM",
                                        action="Report Generation Assistance",
                                        result_summary="Generated report from scheduler output due to reporting agent communication issues",
                                        conversation_id=conversation_id,
                                        session_id=session_id,
                                        user_query=message,
                                        agent_output=report
                                    )
                                except Exception as e:
                                    print(f"Error logging report generation assistance: {e}")
                            
                            else:
                                # Since we don't have database fallback anymore, generate a basic report
                                print("Scheduler output doesn't contain analysis and no database fallback available")
                                
                                # Generate a simplified report based on scheduler content
                                if scheduler_content:
                                    report = "REPORTING_AGENT > \n"
                                    report += "# Schedule Analysis Summary\n\n"
                                    report += "The scheduler has analyzed the equipment schedule data. However, due to communication limitations, a detailed report could not be generated at this time.\n\n"
                                    report += "## Scheduler Analysis Output\n\n"
                                    report += scheduler_content + "\n\n"
                                    report += "## Next Steps\n\n"
                                    report += "Please try again or contact the project management team for support with the schedule analysis."
                                else:
                                    report = "REPORTING_AGENT > \n"
                                    report += "# Schedule Analysis Summary\n\n"
                                    report += "The scheduler encountered issues while analyzing the equipment schedule data. No detailed report could be generated.\n\n"
                                    report += "## Recommendations\n\n"
                                    report += "1. Please try your request again\n"
                                    report += "2. If the issue persists, contact technical support\n"
                                    report += "3. Consider breaking down your request into smaller, more specific queries\n\n"
                                    report += "## Next Steps\n\n"
                                    report += "Please ensure your request is clear and specific. Try asking about:\n"
                                    report += "- Specific equipment items\n"
                                    report += "- Specific risk categories\n"
                                    report += "- Specific time periods"
                                
                                latest_responses[REPORTING_AGENT] = ChatMessageContent(
                                    role=AuthorRole.ASSISTANT,
                                    name=REPORTING_AGENT,
                                    content=report
                                )

                        except Exception as e:
                            print(f"Error trying to bridge gap between scheduler and reporting agents: {e}")
                            import traceback
                            traceback.print_exc()
                
                # More robust response formatting
                final_response = ""
                
                # For comprehensive risk analysis
                if is_comprehensive_risk and REPORTING_AGENT in latest_responses:
                    final_response = latest_responses[REPORTING_AGENT].content.replace("REPORTING_AGENT > ", "")
                
                # For specific risk queries
                elif is_specific_risk:
                    # Check if we have responses from the right agents
                    if REPORTING_AGENT in latest_responses:
                        final_response = latest_responses[REPORTING_AGENT].content.replace("REPORTING_AGENT > ", "")
                    elif any(agent in latest_responses for agent in [POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT]):
                        # If we have a risk agent response but no reporting agent
                        risk_agent = next(agent for agent in [POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT] if agent in latest_responses)
                        final_response = latest_responses[risk_agent].content.replace(f"{risk_agent} > ", "")
                
                # For schedule-related queries
                elif is_schedule_related:
                    # Check if we have both scheduler and reporting responses
                    if SCHEDULER_AGENT in latest_responses and REPORTING_AGENT in latest_responses:
                        # Use the reporting agent's response as the primary content since it's meant for human consumption
                        report_response = latest_responses[REPORTING_AGENT].content.replace("REPORTING_AGENT > ", "")
                        
                        # Check if the report is substantial enough (basic sanity check)
                        if len(report_response) > 200:  # Arbitrary threshold for a meaningful report
                            final_response = report_response
                        else:
                            # Fall back to combining both if the report seems too short
                            scheduler_response = latest_responses[SCHEDULER_AGENT].content.replace("SCHEDULER_AGENT > ", "")
                            final_response = f"# Schedule Analysis Report\n\n{report_response}\n\n## Additional Details\n{scheduler_response}"
                    
                    # If we only have scheduler response but not reporting
                    elif SCHEDULER_AGENT in latest_responses:
                        scheduler_response = latest_responses[SCHEDULER_AGENT].content.replace("SCHEDULER_AGENT > ", "")
                        final_response = f"# Schedule Analysis\n\n{scheduler_response}\n\n*Note: The detailed report could not be generated at this time.*"
                    
                    # If we only have reporting response but not scheduler (unlikely but possible)
                    elif REPORTING_AGENT in latest_responses:
                        report_response = latest_responses[REPORTING_AGENT].content.replace("REPORTING_AGENT > ", "")
                        final_response = report_response
                
                # For general queries
                elif latest_responses:
                    # Get the last agent's response
                    last_agent = list(latest_responses.keys())[-1]
                    final_response = latest_responses[last_agent].content.replace(f"{last_agent} > ", "")
                
                # If no responses were collected, provide a fallback
                if not final_response:
                    if is_specific_risk:
                        final_response = "I'm sorry, I couldn't analyze the specific risk at this time. Please try again."
                    elif is_schedule_related:
                        final_response = "I'm sorry, I couldn't analyze the schedule data at this time due to system limitations. Please try again in a few minutes."
                    else:
                        final_response = "I'm sorry, I couldn't process your request at this time. Please try again in a moment."
                
                # Log the assistant's response
                try:
                    self.logging_plugin.log_agent_event(
                        agent_name="Chatbot",
                        action="Assistant Response",
                        result_summary="Generated combined response to user query",
                        conversation_id=conversation_id,
                        session_id=session_id,
                        user_query=message,
                        agent_output=final_response
                    )
                except Exception as e:
                    print(f"Error logging assistant response: {e}")
                
                return {
                    "status": "success",
                    "response": final_response.strip(),
                    "conversation_id": conversation_id
                }
                
            except Exception as e:
                print(f"Error processing message: {e}")
                import traceback
                traceback.print_exc()
                
                # Log error
                try:
                    self.logging_plugin.log_agent_event(
                        agent_name="Chatbot",
                        action="Message Error",
                        result_summary=f"Error processing message: {str(e)}",
                        conversation_id=conversation_id if 'conversation_id' in locals() else None,
                        session_id=session_id,
                        user_query=message
                    )
                except Exception as log_error:
                    print(f"Failed to log error: {log_error}")
                
                return {
                    "status": "error",
                    "error": str(e),
                    "conversation_id": conversation_id if 'conversation_id' in locals() else None
                }
                
            finally:
                # Clean up any processing locks for sessions that no longer exist
                # This prevents memory leaks from abandoned sessions
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
    
    async def cleanup_sessions(self, max_age_minutes=30):
        """Cleans up inactive chat sessions with improved resource management."""
        now = datetime.now()
        sessions_to_remove = []
        
        async with self._session_lock:
            for session_id, session in self.chat_sessions.items():
                # Check if session is older than max_age_minutes or requested to clean all (max_age_minutes=0)
                if max_age_minutes == 0 or (now - session["last_activity"]).total_seconds() > max_age_minutes * 60:
                    sessions_to_remove.append(session_id)
        
        # Remove inactive sessions
        for session_id in sessions_to_remove:
            try:
                await self.close_session(session_id)
                print(f"Removed inactive session: {session_id}")
            except Exception as e:
                print(f"Error removing session {session_id}: {e}")
                
        return len(sessions_to_remove)

    async def close_session(self, session_id):
        """Properly closes a chat session and all associated resources with improved error handling."""
        session = None
        
        async with self._session_lock:
            if session_id not in self.chat_sessions:
                return False
                
            session = self.chat_sessions[session_id]
            # Mark the session as closing to prevent new operations
            session["closing"] = True
        
        # Set a timeout for closing resources
        close_timeout = 5  # seconds
        
        try:
            # Cancel any pending tasks first
            if session_id in self._session_tasks:
                tasks_to_cancel = self._session_tasks[session_id].copy()
                for task in tasks_to_cancel:
                    if not task.done():
                        task.cancel()
                        
                # Wait briefly for tasks to cancel
                if tasks_to_cancel:
                    try:
                        await asyncio.wait(tasks_to_cancel, timeout=1.0)
                    except Exception as e:
                        print(f"Error waiting for tasks to cancel in session {session_id}: {e}")
                        
                # Clear the task list
                self._session_tasks[session_id] = []
            
            # Cancel the cancellation token if it exists
            if "cancellation_token" in session and not session["cancellation_token"].done():
                session["cancellation_token"].set_result(True)
            
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
        
        except Exception as e:
            print(f"Error during session cleanup for {session_id}: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            # Always delete the session and its processing lock regardless of errors
            async with self._session_lock:
                if session_id in self.chat_sessions:
                    del self.chat_sessions[session_id]
                
                # Also clean up the processing lock if it exists
                if session_id in self._processing_locks:
                    del self._processing_locks[session_id]
                    
                # Clean up session tasks if they exist
                if session_id in self._session_tasks:
                    del self._session_tasks[session_id]
        
        return True