"""Updated Chatbot manager with enhanced thinking logging."""

import uuid
import asyncio
import traceback
from datetime import datetime
import re

from azure.identity.aio import DefaultAzureCredential

from semantic_kernel.agents import AgentGroupChat
from semantic_kernel.agents import AzureAIAgent
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from config.settings import initialize_ai_agent_settings
from config.settings import get_project_client

from agents.agent_definitions import (
    SCHEDULER_AGENT, SCHEDULER_AGENT_INSTRUCTIONS,
    REPORTING_AGENT, REPORTING_AGENT_INSTRUCTIONS,
    ASSISTANT_AGENT, ASSISTANT_AGENT_INSTRUCTIONS
)
from agents.agent_strategies import (
    ChatbotSelectionStrategy, ChatbotTerminationStrategy
)
from agents.agent_manager import create_or_reuse_agent
from plugins.schedule_plugin import EquipmentSchedulePlugin
from plugins.risk_plugin import RiskCalculationPlugin
from plugins.enhanced_thinking_logger import EnhancedThinkingLoggerPlugin

class ChatbotManager:
    """Manages the interactive chatbot for user queries with enhanced logging."""
    
    def __init__(self, connection_string):
        self.connection_string = connection_string
        self.schedule_plugin = EquipmentSchedulePlugin(connection_string)
        self.risk_plugin = RiskCalculationPlugin()
        self.thinking_logger = EnhancedThinkingLoggerPlugin(connection_string)
        self.chat_sessions = {}
    
    async def initialize_session(self, session_id):
        """Initializes a new chat session with all three agents."""
        if session_id in self.chat_sessions:
            print(f"Reusing existing chat session: {session_id}")
            return self.chat_sessions[session_id]
        
        print(f"Creating new chat session: {session_id}")
        
        # Get the Azure AI Agent settings
        try:
            ai_agent_settings = initialize_ai_agent_settings()
            print(f"AI Agent settings initialized: {ai_agent_settings.model_deployment_name}")
        except ValueError as e:
            print(f"Error initializing AI Agent settings: {e}")
            raise ValueError(f"Failed to initialize AI Agent settings: {str(e)}")
        
        try:
            # Create credentials - no await needed
            creds = DefaultAzureCredential(exclude_environment_credential=True, 
                                        exclude_managed_identity_credential=True)
            
            # Create client - no await needed
            client = AzureAIAgent.create_client(credential=creds)
            
            print("Client created successfully")
            
            # Create or reuse all three agents
            print("Creating/retrieving scheduler agent...")
            scheduler_agent = await create_or_reuse_agent(
                client=client,
                agent_name=SCHEDULER_AGENT,
                model_deployment_name=ai_agent_settings.model_deployment_name,
                instructions=SCHEDULER_AGENT_INSTRUCTIONS,
                plugins=[self.schedule_plugin, self.risk_plugin, self.thinking_logger]
            )

            print("Creating/retrieving reporting agent...")
            reporting_agent = await create_or_reuse_agent(
                client=client,
                agent_name=REPORTING_AGENT,
                model_deployment_name=ai_agent_settings.model_deployment_name,
                instructions=REPORTING_AGENT_INSTRUCTIONS,
                plugins=[self.schedule_plugin, self.thinking_logger]
            )

            print("Creating/retrieving assistant agent...")
            assistant_agent = await create_or_reuse_agent(
                client=client,
                agent_name=ASSISTANT_AGENT,
                model_deployment_name=ai_agent_settings.model_deployment_name,
                instructions=ASSISTANT_AGENT_INSTRUCTIONS,
                plugins=[self.schedule_plugin, self.risk_plugin, self.thinking_logger]
            )
            
            # Get agent IDs
            scheduler_agent_id = None
            reporting_agent_id = None
            assistant_agent_id = None
            
            # Extract IDs if available
            if hasattr(scheduler_agent, 'definition') and hasattr(scheduler_agent.definition, 'id'):
                scheduler_agent_id = scheduler_agent.definition.id
            if hasattr(reporting_agent, 'definition') and hasattr(reporting_agent.definition, 'id'):
                reporting_agent_id = reporting_agent.definition.id
            if hasattr(assistant_agent, 'definition') and hasattr(assistant_agent.definition, 'id'):
                assistant_agent_id = assistant_agent.definition.id
                
            print(f"Scheduler agent ready: {scheduler_agent.name} (ID: {scheduler_agent_id})")
            print(f"Reporting agent ready: {reporting_agent.name} (ID: {reporting_agent_id})")
            print(f"Assistant agent ready: {assistant_agent.name} (ID: {assistant_agent_id})")
            
            print("Creating agent group chat with all three agents...")
            
            # Create the agent group chat with all three agents
            chat = AgentGroupChat(
                agents=[assistant_agent, scheduler_agent, reporting_agent],
                termination_strategy=ChatbotTerminationStrategy(),
                selection_strategy=ChatbotSelectionStrategy()
            )
            
            print(f"Creating chat session...")
            
            # Store the chat session
            self.chat_sessions[session_id] = {
                "chat": chat,
                "client": client,
                "credential": creds,
                "last_activity": datetime.now(),
                "model_deployment_name": ai_agent_settings.model_deployment_name,
                "scheduler_agent_id": scheduler_agent_id,
                "reporting_agent_id": reporting_agent_id,
                "assistant_agent_id": assistant_agent_id
            }
            
            return self.chat_sessions[session_id]
        except Exception as e:
            print(f"Error in initialize_session: {e}")
            traceback.print_exc()
            raise
    
    async def process_message(self, session_id, message):
        """Processes a user message and returns the combined response from all agents."""
        # Generate a conversation ID for this message
        conversation_id = str(uuid.uuid4())
        project_client = get_project_client()
        # Keep track of thread ID if it becomes available
        thread_id = None
        
        # Log the user query
        try:
            self.schedule_plugin.log_agent_event(
                agent_name="Chatbot",
                action="User Query",
                result_summary=f"Processing user query: {message[:100]}...",
                conversation_id=conversation_id
            )
        except Exception as e:
            print(f"Error logging agent event: {e}")
        
        try:
            # Get or initialize the chat session
            session = await self.initialize_session(session_id)
            chat = session["chat"]
            
            # Update last activity time
            session["last_activity"] = datetime.now()
            
            # Get model deployment name from session
            model_deployment_name = session.get("model_deployment_name", "unknown")
            
            # Add the user message to the chat with thinking context
            print(f"Creating user message content")
            user_message = ChatMessageContent(
                role=AuthorRole.USER, 
                content=f"""USER > {message}
                When logging your thinking with log_agent_thinking, use these parameters:
                - conversation_id: "{conversation_id}"
                - session_id: "{session_id}"
                - model_deployment_name: "{model_deployment_name}"
                - user_query: "{message}"
                """
            )
            await chat.add_chat_message(user_message)

            print(f"Invoking chat...")
            # Get the responses from all agents - use a dictionary to track latest response from each agent
            latest_responses = {}
            
            # Add retry logic for rate limit errors
            max_retries = 3
            retry_delay = 5  # Start with 5 seconds
            attempt = 0
            
            while attempt < max_retries:
                try:
                    async for response in chat.invoke():
                        print(f"Response received: {response}")
                        if response is None:
                            print("Response is None, skipping")
                            continue
                        if not hasattr(response, 'name') or not response.name:
                            print(f"Response has no name attribute or name is empty, skipping: {response}")
                            continue
                        
                        # Store only the latest response from each agent
                        agent_name = response.name
                        print(f"Adding/updating response content from {agent_name}: {response.content[:50]}...")
                        latest_responses[agent_name] = response
                        
                        # For debugging, print current response state
                        print(f"Current agents with responses: {list(latest_responses.keys())}")
                        
                        # Check if we have completed a full conversation cycle
                        # This helps identify when the agents have finished their conversation
                        if (ASSISTANT_AGENT in latest_responses and 
                            ((SCHEDULER_AGENT in latest_responses and REPORTING_AGENT in latest_responses) or
                            (not any(keyword in message.lower() for keyword in 
                                    ["schedule", "risk", "delay", "variance", "late", "delivery", "milestone"])))):
                            print("Complete conversation cycle detected, breaking out of loop")
                            break
                    
                    # If we got here without an exception, break out of the retry loop
                    break
                    
                except Exception as e:
                    attempt += 1
                    error_message = str(e)
                    print(f"Error during chat.invoke() (attempt {attempt}/{max_retries}): {error_message}")
                    
                    # Get the thread id
                    with project_client:
                        thread_id = project_client.agents.list_threads(limit=1).first_id
                        print(f"Thread ID: {thread_id}")

                    # Log the error with the enhanced thinking logger
                    try:
                        if "Rate limit is exceeded" in error_message:
                            error_type = "rate_limit"
                        else:
                            error_type = "api_error"

                        self.thinking_logger.log_agent_error(
                            agent_name="SYSTEM",
                            error_type=error_type,
                            error_message=error_message,
                            conversation_id=conversation_id,
                            session_id=session_id,
                            azure_agent_id=None,
                            model_deployment_name=model_deployment_name,
                            thread_id=thread_id,
                            user_query=message
                        )
                    except Exception as log_error:
                        print(f"Error logging to enhanced thinking logger: {log_error}")
                    
                    # Check if it's a rate limit error
                    if "Rate limit is exceeded" in error_message and attempt < max_retries:
                        # Extract wait time if available
                        import re
                        wait_seconds = 20  # Default wait time
                        match = re.search(r'Try again in (\d+) seconds', error_message)
                        if match:
                            wait_seconds = int(match.group(1))
                            # Add a little buffer
                            wait_seconds += 2
                        
                        print(f"Rate limit exceeded. Waiting for {wait_seconds} seconds before retry...")
                        await asyncio.sleep(wait_seconds)
                        # Continue to next retry attempt
                        continue
                    elif attempt >= max_retries:
                        # We've exhausted our retries
                        print("Max retries exceeded. Creating a new chat session as fallback...")
                        
                        # Close the current session
                        if session_id in self.chat_sessions:
                            # Close the existing client and credential if they exist
                            if "client" in session:
                                try:
                                    if hasattr(session["client"], 'close'):
                                        await session["client"].close()
                                except:
                                    pass
                            
                            if "credential" in session:
                                try:
                                    if hasattr(session["credential"], 'close'):
                                        await session["credential"].close()
                                except:
                                    pass
                            
                            # Delete the session
                            del self.chat_sessions[session_id]
                        
                        # Return a graceful error message
                        return {
                            "status": "error",
                            "error": f"The agent encountered a rate limit error. Please wait a moment and try again.",
                            "conversation_id": conversation_id,
                            "thread_id": thread_id
                        }
                    else:
                        # For non-rate-limit errors, or if we're out of retries, break the loop and handle below
                        break
            
            # Process the responses - use the latest response from each agent
            final_response = ""
            
            # Define the preferred order for responses
            agent_order = [SCHEDULER_AGENT, REPORTING_AGENT, ASSISTANT_AGENT]
            
            # First, check if we have schedule-related responses
            if SCHEDULER_AGENT in latest_responses and REPORTING_AGENT in latest_responses:
                # Show responses in the desired order for schedule-related queries
                for agent_name in agent_order:
                    if agent_name in latest_responses:
                        response = latest_responses[agent_name]
                        if agent_name == ASSISTANT_AGENT:
                            content = response.content.replace("ASSISTANT > ", "")
                            final_response += f"Assistant: {content}\n\n"
                        elif agent_name == SCHEDULER_AGENT:
                            content = response.content.replace("SCHEDULER_AGENT > ", "")
                            final_response += f"Schedule Analysis: {content}\n\n"
                        elif agent_name == REPORTING_AGENT:
                            content = response.content.replace("REPORTING_AGENT > ", "")
                            final_response += f"Report: {content}\n\n"
            else:
                # For non-schedule queries, just show the assistant's response
                if ASSISTANT_AGENT in latest_responses:
                    response = latest_responses[ASSISTANT_AGENT]
                    content = response.content.replace("ASSISTANT > ", "")
                    final_response = content
            
            # If no responses were collected, provide a fallback
            if not final_response:
                if any(keyword in message.lower() for keyword in ["schedule", "risk", "delay", "variance", "late", "delivery", "milestone"]):
                    final_response = "I'm sorry, I couldn't analyze the schedule data at this time. Please try again later."
                else:
                    final_response = "I'm sorry, I couldn't process your request at this time. Please try again."
            
            # Log the assistant's response
            try:
                self.schedule_plugin.log_agent_event(
                    agent_name="Chatbot",
                    action="Assistant Response",
                    result_summary=f"Generated combined response to user query",
                    conversation_id=conversation_id
                )
            except Exception as e:
                print(f"Error logging assistant response: {e}")
            
            # Get the thread id
            with project_client:
                thread_id = project_client.agents.list_threads(limit=1).first_id
                print(f"Thread ID: {thread_id}")

            return {
                "status": "success",
                "response": final_response.strip(),
                "conversation_id": conversation_id,
                "thread_id": thread_id
            }
            
        except Exception as e:
            print(f"Error processing message: {e}")
            traceback.print_exc()
            
            # Get the thread id
            with project_client:
                thread_id = project_client.agents.list_threads(limit=1).first_id
                print(f"Thread ID: {thread_id}")
            
            # Log error with enhanced thinking logger
            try:

                self.thinking_logger.log_agent_error(
                    agent_name="SYSTEM",
                    error_type="process_error",
                    error_message=str(e),
                    conversation_id=conversation_id,
                    session_id=session_id,
                    thread_id=thread_id,
                    user_query=message
                )
            except Exception as log_error:
                print(f"Failed to log error to enhanced thinking logger: {log_error}")
            
            # Log error with schedule plugin
            try:
                self.schedule_plugin.log_agent_event(
                    agent_name="Chatbot",
                    action="Message Error",
                    result_summary=f"Error processing message: {str(e)}",
                    conversation_id=conversation_id
                )
            except Exception as log_error:
                print(f"Failed to log error: {log_error}")
            
            return {
                "status": "error",
                "error": str(e),
                "conversation_id": conversation_id,
                "thread_id": thread_id
            }