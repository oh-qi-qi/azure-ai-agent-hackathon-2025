<<<<<<< Updated upstream
"""Chatbot manager for equipment schedule agent."""
=======
"""Updated Chatbot manager with enhanced thinking logging and session creation locking."""
>>>>>>> Stashed changes

import uuid
import asyncio
from datetime import datetime
<<<<<<< Updated upstream
=======
import re
import json  # Make sure json is imported
>>>>>>> Stashed changes

from azure.identity.aio import DefaultAzureCredential
from semantic_kernel.agents import AgentGroupChat
from semantic_kernel.agents import AzureAIAgent
# Make sure this import is correct:
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from config.settings import initialize_ai_agent_settings
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
<<<<<<< Updated upstream
from plugins.thinking_logger_plugin import ThinkingLoggerPlugin
=======
from plugins.enhanced_thinking_logger import EnhancedThinkingLoggerPlugin
from plugins.event_log_plugin import EventLogPlugin
>>>>>>> Stashed changes

class ChatbotManager:
    """Manages the interactive chatbot for user queries."""
    
    def __init__(self, connection_string):
        self.connection_string = connection_string
        self.schedule_plugin = EquipmentSchedulePlugin(connection_string)
        self.risk_plugin = RiskCalculationPlugin()
<<<<<<< Updated upstream
        self.thinking_logger = ThinkingLoggerPlugin(connection_string)
=======
        self.thinking_logger = EnhancedThinkingLoggerPlugin(connection_string)
        self.event_logger = EventLogPlugin(connection_string)  # Add the new event logger
>>>>>>> Stashed changes
        self.chat_sessions = {}
        self._session_locks = {}  # Dictionary to store locks for each session ID
    
    async def get_session_lock(self, session_id):
        """Get a lock for a specific session ID, creating it if it doesn't exist."""
        # Use a lock to protect the creation of session locks themselves
        if not hasattr(self, '_session_locks_lock'):
            self._session_locks_lock = asyncio.Lock()
        
        async with self._session_locks_lock:
            if session_id not in self._session_locks:
                self._session_locks[session_id] = asyncio.Lock()
            return self._session_locks[session_id]
    
    async def initialize_session(self, session_id):
        """Initializes a new chat session with all three agents using a lock to prevent race conditions."""
        # Get the lock for this session ID
        lock = await self.get_session_lock(session_id)
        
        # Acquire the lock to ensure only one thread can initialize this session at a time
        async with lock:
            # Check again if the session exists now that we have the lock
            if session_id in self.chat_sessions and not self.chat_sessions[session_id].get("initializing", False):
                print(f"Reusing existing chat session (with lock): {session_id}")
                return self.chat_sessions[session_id]
            
            # Mark this session as "initializing" to prevent race conditions
            self.chat_sessions[session_id] = {"initializing": True, "last_activity": datetime.now()}
            
            print(f"Creating new chat session (with lock): {session_id}")
            
<<<<<<< Updated upstream
            # Create or reuse all three agents
            print("Creating/retrieving scheduler agent...")
            scheduler_agent = await create_or_reuse_agent(
                client=client,
                agent_name=SCHEDULER_AGENT,
                model_deployment_name=ai_agent_settings.model_deployment_name,
                instructions=SCHEDULER_AGENT_INSTRUCTIONS,
                plugins=[self.schedule_plugin, self.risk_plugin, self.thinking_logger]  # Include thinking logger here
            )

            print("Creating/retrieving reporting agent...")
            reporting_agent = await create_or_reuse_agent(
                client=client,
                agent_name=REPORTING_AGENT,
                model_deployment_name=ai_agent_settings.model_deployment_name,
                instructions=REPORTING_AGENT_INSTRUCTIONS,
                plugins=[self.schedule_plugin, self.thinking_logger]  # Include thinking logger here
            )

            print("Creating/retrieving assistant agent...")
            assistant_agent = await create_or_reuse_agent(
                client=client,
                agent_name=ASSISTANT_AGENT,
                model_deployment_name=ai_agent_settings.model_deployment_name,
                instructions=ASSISTANT_AGENT_INSTRUCTIONS,
                plugins=[self.schedule_plugin, self.risk_plugin, self.thinking_logger]  # Include thinking logger here
            )
=======
            # Get the Azure AI Agent settings
            try:
                ai_agent_settings = initialize_ai_agent_settings()
                print(f"AI Agent settings initialized: {ai_agent_settings.model_deployment_name}")
            except ValueError as e:
                print(f"Error initializing AI Agent settings: {e}")
                raise ValueError(f"Failed to initialize AI Agent settings: {str(e)}")
>>>>>>> Stashed changes
            
            try:
                # Create credentials - no await needed
                creds = DefaultAzureCredential(exclude_environment_credential=True, 
                                           exclude_managed_identity_credential=True)
                
<<<<<<< Updated upstream
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
            import traceback
            traceback.print_exc()
            raise
=======
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
                
                # When creating the final session, add the initializing: False flag
                self.chat_sessions[session_id] = {
                    "chat": chat,
                    "client": client,
                    "credential": creds,
                    "last_activity": datetime.now(),
                    "model_deployment_name": ai_agent_settings.model_deployment_name,
                    "scheduler_agent_id": scheduler_agent_id,
                    "reporting_agent_id": reporting_agent_id,
                    "assistant_agent_id": assistant_agent_id,
                    "initializing": False  # Mark as no longer initializing
                }
                
                return self.chat_sessions[session_id]
            except Exception as e:
                # Clean up if initialization fails
                if session_id in self.chat_sessions and self.chat_sessions[session_id].get("initializing"):
                    del self.chat_sessions[session_id]
                print(f"Error in initialize_session: {e}")
                traceback.print_exc()
                raise
>>>>>>> Stashed changes
    
    async def process_message(self, session_id, message):
        """Processes a user message and returns the combined response from all agents."""
        # Generate a conversation ID for this message
        conversation_id = str(uuid.uuid4())
        
        # Log the user query with the event logger
        try:
            self.event_logger.log_agent_event(
                agent_name="Chatbot",
                action="User Query",
                result_summary=f"Processing user query: {message}",
                conversation_id=conversation_id,
                user_query=message  # Store the full user query
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
<<<<<<< Updated upstream
            user_message = ChatMessageContent(
                role=AuthorRole.USER, 
                content=f"""USER > {message}
                When logging your thinking with log_agent_thinking, use these parameters:
                - conversation_id: "{conversation_id}"
                - session_id: "{session_id}"
                - model_deployment_name: "{model_deployment_name}"
                """
            )
            
            print(f"Adding message to chat")
=======
            try:
                # Try importing the class directly if there's an issue with the earlier import
                from semantic_kernel.contents.chat_message_content import ChatMessageContent
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
            except ImportError:
                # Try alternative import path for older versions
                print("Trying alternative import path...")
                from semantic_kernel.contents import ChatMessageContent
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

>>>>>>> Stashed changes
            await chat.add_chat_message(user_message)
            
            print(f"Invoking chat...")
            # Get the responses from all agents - use a dictionary to track latest response from each agent
            latest_responses = {}
<<<<<<< Updated upstream
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
=======
            
            # Check if query is schedule-related
            is_schedule_related = any(keyword in message.lower() for keyword in 
                                    ["schedule", "risk", "delay", "variance", "late", "delivery", "milestone"])
            
            # For tracking which agent is currently responding
            current_agent = None
            last_agent = None
            
            # Track transitions between agents
            agent_transitions = []
            
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
                        
                        # Track agent transitions to detect when an agent has completed
                        if current_agent != agent_name:
                            if current_agent is not None:
                                # Record the transition
                                agent_transitions.append((last_agent, current_agent, agent_name))
                                print(f"Agent transition: {last_agent} -> {current_agent} -> {agent_name}")
                                
                                # Add a small delay when transitioning from SCHEDULER to REPORTING
                                if current_agent == SCHEDULER_AGENT and agent_name == REPORTING_AGENT:
                                    print("Adding delay after SCHEDULER_AGENT to avoid rate limit...")
                                    await asyncio.sleep(3)  # 3 second delay
                            
                            last_agent = current_agent
                            current_agent = agent_name
                        
                        print(f"Adding/updating response content from {agent_name}: {response.content[:50]}...")
                        latest_responses[agent_name] = response
                        
                        # Log each agent's response
                        try:
                            self.event_logger.log_agent_event(
                                agent_name=agent_name,
                                action=f"{agent_name} Response",
                                result_summary=f"Response from {agent_name}",
                                conversation_id=conversation_id,
                                user_query=message,
                                agent_output=response.content
                            )
                        except Exception as e:
                            print(f"Error logging {agent_name} response: {e}")
                        
                        # For debugging, print current response state
                        print(f"Current agents with responses: {list(latest_responses.keys())}")
                        
                        # Check if we have received the final response based on the query type
                        if is_schedule_related:
                            # For schedule-related queries, we need both SCHEDULER and REPORTING responses
                            if SCHEDULER_AGENT in latest_responses and REPORTING_AGENT in latest_responses:
                                # Make sure these aren't just partial responses (check if they've completed)
                                # We consider an agent complete if we've seen the next agent respond
                                scheduler_complete = False
                                for from_agent, to_agent, _ in agent_transitions:
                                    if from_agent == SCHEDULER_AGENT and to_agent == REPORTING_AGENT:
                                        scheduler_complete = True
                                        break
                                
                                if scheduler_complete:
                                    print("Schedule-related query complete with full REPORTING_AGENT response, breaking out of loop")
                                    break
                        else:
                            # For non-schedule queries, we just need the ASSISTANT response
                            if ASSISTANT_AGENT in latest_responses:
                                print("Non-schedule query complete with ASSISTANT_AGENT response, breaking out of loop")
                                break
                    
                    # If we got here without an exception, break out of the retry loop
                    break
                    
                except Exception as e:
                    attempt += 1
                    error_message = str(e)
                    print(f"Error during chat.invoke() (attempt {attempt}/{max_retries}): {error_message}")
                    
                    # Get the thread id
                    try:
                        with project_client:
                            thread_id = project_client.agents.list_threads(limit=1).first_id
                            print(f"Thread ID: {thread_id}")
                    except Exception as thread_error:
                        print(f"Error getting thread ID: {thread_error}")
                        thread_id = None

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
                        wait_seconds = 20  # Default wait time
                        match = re.search(r'Try again in (\d+) seconds', error_message)
                        if match:
                            wait_seconds = int(match.group(1))
                            # Add a little extra buffer
                            wait_seconds += 5
                        
                        print(f"Rate limit exceeded. Waiting for {wait_seconds} seconds before retry...")
                        await asyncio.sleep(wait_seconds)
                        
                        # If we have a SCHEDULER_AGENT response but no REPORTING_AGENT yet,
                        # we can use what we have for schedule-related queries
                        if is_schedule_related and SCHEDULER_AGENT in latest_responses and attempt >= max_retries - 1:
                            print("Using available SCHEDULER_AGENT response as REPORTING_AGENT couldn't be reached")
                            break
                        
                        # Continue to next retry attempt
                        continue
                    elif attempt >= max_retries:
                        # We've exhausted our retries
                        print("Max retries exceeded. Using available responses...")
                        break
                    else:
                        # For non-rate-limit errors, or if we're out of retries, break the loop and handle below
>>>>>>> Stashed changes
                        break
                    
            except Exception as e:
                print(f"Error during chat.invoke(): {e}")
                import traceback
                traceback.print_exc()
                
                # Try to create a new chat session as a fallback
                print("Attempting to create a new chat session as a fallback...")
                if session_id in self.chat_sessions:
                    # Close the existing client and credential if they exist
                    if "client" in session:
                        try:
                            await session["client"].close()
                        except:
                            pass
                    
                    if "credential" in session:
                        try:
                            await session["credential"].close()
                        except:
                            pass
                    
                    # Delete the session
                    del self.chat_sessions[session_id]
                
                # Instead of failing, return a graceful error message
                return {
                    "status": "error",
                    "error": f"The agent encountered an error: {str(e)}. Please try again.",
                    "conversation_id": conversation_id
                }
            
            # For schedule-related queries, ensure data is properly passed from SCHEDULER to REPORTING agent
            if is_schedule_related:
                # If we have a SCHEDULER_AGENT response but no REPORTING_AGENT response, 
                # or the REPORTING_AGENT response seems incomplete, help bridge the gap
                if SCHEDULER_AGENT in latest_responses and (REPORTING_AGENT not in latest_responses or 
                    len(latest_responses[REPORTING_AGENT].content) < 100):  # Basic check for incomplete response
                    
                    print("Reporting agent response missing or incomplete. Helping bridge the gap...")
                    
                    try:
                        # Get the conversation_id associated with this session
                        # First, try to extract it from log messages if available
                        extracted_conversation_id = None
                        scheduler_content = latest_responses[SCHEDULER_AGENT].content
                        conv_id_match = re.search(r'conversation_id["\']?\s*[:=]\s*["\']([a-f0-9-]+)["\']', scheduler_content)
                        if conv_id_match:
                            extracted_conversation_id = conv_id_match.group(1)
                            print(f"Extracted conversation_id from scheduler output: {extracted_conversation_id}")
                        
                        # If we couldn't extract it, use the current conversation_id
                        if not extracted_conversation_id:
                            extracted_conversation_id = conversation_id
                        
                        # Call get_risk_summary directly to retrieve the data that should have been passed
                        risk_summary_json = self.schedule_plugin.get_risk_summary(conversation_id=extracted_conversation_id)
                        
                        # Now we can construct a replacement for the missing reporting agent response
                        risk_summary = json.loads(risk_summary_json)
                        
                        # Only proceed if we actually have data
                        if "all_variances" in risk_summary and risk_summary["all_variances"]:
                            # Create a basic but useful report from the risk data
                            summary_counts = {item["risk_flag"]: item["count"] for item in risk_summary.get("summary", [])}
                            
                            high_count = summary_counts.get("High Risk", 0)
                            medium_count = summary_counts.get("Medium Risk", 0)
                            low_count = summary_counts.get("Low Risk", 0)
                            
                            report = f"""REPORTING_AGENT > 
                                # Equipment Schedule Risk Report

                                ## Executive Summary
                                Based on the schedule analysis, we have identified:
                                - {high_count} high-risk items requiring immediate attention
                                - {medium_count} medium-risk items to monitor
                                - {low_count} low-risk items to be aware of

                                ## High Risk Items
                                """
                            
                            # Add details for each risk category
                            for risk_level in ["High Risk", "Medium Risk", "Low Risk"]:
                                if risk_level == "High Risk":
                                    # We already started this section
                                    pass
                                else:
                                    report += f"\n## {risk_level} Items\n"
                                
                                # Filter variances by risk level
                                filtered_variances = [v for v in risk_summary.get("all_variances", []) 
                                                    if v.get("risk_flag") == risk_level]
                                
                                if filtered_variances:
                                    for variance in filtered_variances:
                                        report += f"""
                                        ### {variance.get('equipment_name', 'Unknown Equipment')} ({variance.get('equipment_code', 'Unknown Code')})
                                        - **Project**: {variance.get('project_name', 'Unknown Project')} ({variance.get('project_code', 'Unknown Code')})
                                        - **Work Package**: {variance.get('work_package_name', 'Unknown WP')}
                                        - **Milestone**: {variance.get('milestone_activity', 'Unknown Milestone')}
                                        - **Supplier**: {variance.get('supplier_name', 'Unknown Supplier')}
                                        - **P6 Due Date**: {variance.get('p6_due_date', 'Unknown')}
                                        - **Delivery Date**: {variance.get('equipment_delivery_date', 'Unknown')}
                                        - **Variance**: {variance.get('days_variance', 'Unknown')} days
                                        - **Risk Description**: {variance.get('risk_description', 'Unknown')}
                                        - **Mitigation**: {variance.get('mitigation_action', 'Unknown')}

                                        """
                                else:
                                    report += f"No {risk_level.lower()} items identified.\n"
                            
                            # Add recommendations section
                            report += """
                                ## Recommendations
                                1. For high-risk items: Immediate escalation to management and suppliers
                                2. For medium-risk items: Increase monitoring frequency and prepare contingency plans
                                3. For low-risk items: Regular monitoring according to standard procedures

                                ## Conclusion
                                This report is based on the schedule analysis conducted by the system. For detailed analysis of specific items, please contact the project management team.
                                """
                            
                            # Create a mock response for the reporting agent
                            if REPORTING_AGENT not in latest_responses:
                                try:
                                    # Try standard import path
                                    from semantic_kernel.contents.chat_message_content import ChatMessageContent
                                    latest_responses[REPORTING_AGENT] = ChatMessageContent(
                                        role=AuthorRole.ASSISTANT,
                                        name=REPORTING_AGENT,
                                        content=report
                                    )
                                except ImportError:
                                    # Try alternative import path
                                    from semantic_kernel.contents import ChatMessageContent
                                    latest_responses[REPORTING_AGENT] = ChatMessageContent(
                                        role=AuthorRole.ASSISTANT,
                                        name=REPORTING_AGENT,
                                        content=report
                                    )
                            else:
                                # Just update the content if we already have a response object
                                latest_responses[REPORTING_AGENT].content = report
                            
                            print(f"Generated replacement report for the reporting agent")
                            
                            # Log this action
                            try:
                                self.event_logger.log_agent_event(
                                    agent_name="SYSTEM",
                                    action="Report Generation Assistance",
                                    result_summary="Generated replacement report due to agent communication issues",
                                    conversation_id=conversation_id,
                                    user_query=message,
                                    agent_output=report
                                )
                            except Exception as e:
                                print(f"Error logging report generation assistance: {e}")
                        
                        else:
                            print("Could not generate replacement report - no variance data found")
                    
                    except Exception as e:
                        print(f"Error trying to bridge gap between scheduler and reporting agents: {e}")
                        traceback.print_exc()
            
            # More robust response formatting
            final_response = ""
            
            # For schedule-related queries, process both scheduler and reporting agent responses
            if is_schedule_related:
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
            
            # For non-schedule queries, just use the assistant's response
            elif ASSISTANT_AGENT in latest_responses:
                content = latest_responses[ASSISTANT_AGENT].content.replace("ASSISTANT > ", "")
                final_response = content
            
            # If no responses were collected, provide a fallback
            if not final_response:
                if is_schedule_related:
                    final_response = "I'm sorry, I couldn't analyze the schedule data at this time due to system limitations. Please try again in a few minutes."
                else:
                    final_response = "I'm sorry, I couldn't process your request at this time. Please try again in a moment."
            
            # Log the assistant's response
            try:
                self.event_logger.log_agent_event(
                    agent_name="Chatbot",
                    action="Assistant Response",
                    result_summary="Generated combined response to user query",
                    conversation_id=conversation_id,
                    user_query=message,
                    agent_output=final_response  # Log the final response
                )
            except Exception as e:
                print(f"Error logging assistant response: {e}")
            
<<<<<<< Updated upstream
=======
            # Get the thread id if we don't have it yet
            if not thread_id:
                try:
                    with project_client:
                        thread_id = project_client.agents.list_threads(limit=1).first_id
                        print(f"Thread ID: {thread_id}")
                except Exception as thread_error:
                    print(f"Error getting thread ID: {thread_error}")

>>>>>>> Stashed changes
            return {
                "status": "success",
                "response": final_response.strip(),
                "conversation_id": conversation_id
            }
            
        except Exception as e:
            print(f"Error processing message: {e}")
            import traceback
            traceback.print_exc()
            
<<<<<<< Updated upstream
            # Log error
=======
            # Get the thread id
            try:
                with project_client:
                    thread_id = project_client.agents.list_threads(limit=1).first_id
                    print(f"Thread ID: {thread_id}")
            except Exception as thread_error:
                print(f"Error getting thread ID: {thread_error}")
                thread_id = None
            
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
            
            # Log error with event logger
>>>>>>> Stashed changes
            try:
                self.event_logger.log_agent_event(
                    agent_name="Chatbot",
                    action="Message Error",
                    result_summary=f"Error processing message: {str(e)}",
                    conversation_id=conversation_id,
                    user_query=message
                )
            except Exception as log_error:
                print(f"Failed to log error: {log_error}")
            
            return {
                "status": "error",
                "error": str(e),
<<<<<<< Updated upstream
                "conversation_id": conversation_id
            }

    async def cleanup_sessions(self, max_age_minutes=30):
        """Cleans up inactive chat sessions."""
        now = datetime.now()
        sessions_to_remove = []
        
        for session_id, session in self.chat_sessions.items():
            # Check if session is older than max_age_minutes
            if (now - session["last_activity"]).total_seconds() > max_age_minutes * 60:
                sessions_to_remove.append(session_id)
        
        # Remove inactive sessions
        for session_id in sessions_to_remove:
            await self.close_session(session_id)
            print(f"Removed inactive session: {session_id}")
                
        return len(sessions_to_remove)

    async def close_session(self, session_id):
        """Properly closes a chat session and all associated resources."""
        if session_id not in self.chat_sessions:
            return False
            
        session = self.chat_sessions[session_id]
        
        # Close the client if it exists
        if "client" in session:
            try:
                client = session["client"]
                # Check if it has a close method that's async
                if hasattr(client, 'close') and callable(client.close):
                    if asyncio.iscoroutinefunction(client.close):
                        await client.close()
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
                        await credential.close()
                    else:
                        credential.close()
                    print(f"Closed credential for session {session_id}")
            except Exception as e:
                print(f"Error closing credential for session {session_id}: {e}")
        
        # Delete the session
        del self.chat_sessions[session_id]
        return True
=======
                "conversation_id": conversation_id,
                "thread_id": thread_id
            }
            
    async def cleanup_sessions(self, max_age_minutes=60):
        """Cleans up inactive chat sessions older than the specified age."""
        current_time = datetime.now()
        sessions_to_remove = []
        
        # Identify sessions to clean up
        for session_id, session in self.chat_sessions.items():
            last_activity = session.get("last_activity", datetime.min)
            age_minutes = (current_time - last_activity).total_seconds() / 60
            
            if age_minutes > max_age_minutes:
                sessions_to_remove.append(session_id)
        
        # Clean up each identified session
        for session_id in sessions_to_remove:
            try:
                session = self.chat_sessions[session_id]
                
                # Close the client if it exists
                if "client" in session:
                    try:
                        if hasattr(session["client"], 'close'):
                            await session["client"].close()
                    except Exception as e:
                        print(f"Error closing client for session {session_id}: {e}")
                
                # Close the credential if it exists
                if "credential" in session:
                    try:
                        if hasattr(session["credential"], 'close'):
                            await session["credential"].close()
                    except Exception as e:
                        print(f"Error closing credential for session {session_id}: {e}")
                
                # Remove the session
                del self.chat_sessions[session_id]
                
                # Also remove the lock if it exists
                if session_id in self._session_locks:
                    del self._session_locks[session_id]
                
                print(f"Cleaned up session {session_id}")
            except Exception as e:
                print(f"Error cleaning up session {session_id}: {e}")
        
        return {"cleaned_sessions": len(sessions_to_remove)}

    async def get_thread_info(self, conversation_id=None, session_id=None):
        """Retrieves information about threads used in chats."""
        try:
            # Get the thread information from the database
            thread_info = {}
            
            # Try to get thread information from the thinking logs
            logs_json = self.thinking_logger.get_enhanced_thinking_logs(
                conversation_id=conversation_id,
                session_id=session_id,
                limit=1000
            )
            
            logs = json.loads(logs_json)
            
            if isinstance(logs, dict) and "error" in logs:
                return {"error": logs["error"]}
            
            # Process the logs to extract thread information
            thread_data = {}
            
            for log in logs:
                thread_id = log.get("thread_id")
                if not thread_id or thread_id == "null" or thread_id == "undefined":
                    continue
                
                # Initialize thread data if this is a new thread
                if thread_id not in thread_data:
                    thread_data[thread_id] = {
                        "first_seen": log.get("created_date"),
                        "last_seen": log.get("created_date"),
                        "thinking_steps": 0,
                        "errors": 0,
                        "agents": set(),
                        "conversation_ids": set(),
                        "session_ids": set()
                    }
                
                # Update thread data
                current = thread_data[thread_id]
                
                # Update timestamps
                if log.get("created_date") < current["first_seen"]:
                    current["first_seen"] = log.get("created_date")
                if log.get("created_date") > current["last_seen"]:
                    current["last_seen"] = log.get("created_date")
                
                # Count thinking steps and errors
                if log.get("thinking_stage") == "error" or log.get("status") == "error":
                    current["errors"] += 1
                else:
                    current["thinking_steps"] += 1
                
                # Add agent, conversation, and session IDs to sets
                if log.get("agent_name"):
                    current["agents"].add(log.get("agent_name"))
                if log.get("conversation_id"):
                    current["conversation_ids"].add(log.get("conversation_id"))
                if log.get("session_id"):
                    current["session_ids"].add(log.get("session_id"))
            
            # Convert sets to lists for JSON serialization
            for thread_id, data in thread_data.items():
                data["agents"] = list(data["agents"])
                data["conversation_ids"] = list(data["conversation_ids"])
                data["session_ids"] = list(data["session_ids"])
            
            return {
                "total_threads": len(thread_data),
                "threads": thread_data
            }
            
        except Exception as e:
            print(f"Error getting thread info: {e}")
            traceback.print_exc()
            return {"error": str(e)}
>>>>>>> Stashed changes
