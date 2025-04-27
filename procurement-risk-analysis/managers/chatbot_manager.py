"""Chatbot manager for equipment schedule agent."""

import uuid
import asyncio
import json
import re
from datetime import datetime

from azure.identity.aio import DefaultAzureCredential
from semantic_kernel.agents import AgentGroupChat
from semantic_kernel.agents import AzureAIAgent
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from config.settings import initialize_ai_agent_settings
from agents.agent_definitions import (
    SCHEDULER_AGENT, get_scheduler_agent_instructions,
    REPORTING_AGENT, get_reporting_agent_instructions,
    ASSISTANT_AGENT, get_assistant_agent_instructions
)
from agents.agent_strategies import (
    ChatbotSelectionStrategy, ChatbotTerminationStrategy
)
from agents.agent_manager import create_or_reuse_agent
from plugins.schedule_plugin import EquipmentSchedulePlugin
from plugins.risk_plugin import RiskCalculationPlugin
from plugins.logging_plugin import LoggingPlugin

class ChatbotManager:
    """Manages the interactive chatbot for user queries."""
    
    def __init__(self, connection_string):
        self.connection_string = connection_string
        self.schedule_plugin = EquipmentSchedulePlugin(connection_string)
        self.risk_plugin = RiskCalculationPlugin()
        self.logging_plugin = LoggingPlugin(connection_string)
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
            
            # Get Azure AI Agent settings
            ai_agent_settings = initialize_ai_agent_settings()
            
            try:
                # Create credentials - no await needed
                creds = DefaultAzureCredential(exclude_environment_credential=True, 
                                           exclude_managed_identity_credential=True)
                
                # Create client - no await needed
                client = AzureAIAgent.create_client(credential=creds)
                
                # Create separate logging plugins for each agent
                scheduler_logging = LoggingPlugin(self.connection_string)
                reporting_logging = LoggingPlugin(self.connection_string)
                assistant_logging = LoggingPlugin(self.connection_string)
                
                # Create or reuse all three agents
                print("Creating/retrieving scheduler agent...")
                scheduler_agent = await create_or_reuse_agent(
                    client=client,
                    agent_name=SCHEDULER_AGENT,
                    model_deployment_name=ai_agent_settings.model_deployment_name,
                    instructions=get_scheduler_agent_instructions(),  # Use dynamic instruction function
                    plugins=[self.schedule_plugin, self.risk_plugin, scheduler_logging]
                )

                print("Creating/retrieving reporting agent...")
                reporting_agent = await create_or_reuse_agent(
                    client=client,
                    agent_name=REPORTING_AGENT,
                    model_deployment_name=ai_agent_settings.model_deployment_name,
                    instructions=get_reporting_agent_instructions(),  # Use dynamic instruction function
                    plugins=[self.schedule_plugin, reporting_logging]
                )

                print("Creating/retrieving assistant agent...")
                assistant_agent = await create_or_reuse_agent(
                    client=client,
                    agent_name=ASSISTANT_AGENT,
                    model_deployment_name=ai_agent_settings.model_deployment_name,
                    instructions=get_assistant_agent_instructions(),  # Use dynamic instruction function
                    plugins=[self.schedule_plugin, self.risk_plugin, assistant_logging]
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
                
                # Set agent IDs in their respective logging plugins
                if scheduler_agent_id:
                    scheduler_logging.set_agent_id(scheduler_agent_id)
                if reporting_agent_id:
                    reporting_logging.set_agent_id(reporting_agent_id)
                if assistant_agent_id:
                    assistant_logging.set_agent_id(assistant_agent_id)
                
                # Now recreate agents with instructions that include their IDs
                if scheduler_agent_id:
                    scheduler_agent = await create_or_reuse_agent(
                        client=client,
                        agent_name=SCHEDULER_AGENT,
                        model_deployment_name=ai_agent_settings.model_deployment_name,
                        instructions=get_scheduler_agent_instructions(scheduler_agent_id),
                        plugins=[self.schedule_plugin, self.risk_plugin, scheduler_logging]
                    )
                
                if reporting_agent_id:
                    reporting_agent = await create_or_reuse_agent(
                        client=client,
                        agent_name=REPORTING_AGENT,
                        model_deployment_name=ai_agent_settings.model_deployment_name,
                        instructions=get_reporting_agent_instructions(reporting_agent_id),
                        plugins=[self.schedule_plugin, reporting_logging]
                    )
                
                if assistant_agent_id:
                    assistant_agent = await create_or_reuse_agent(
                        client=client,
                        agent_name=ASSISTANT_AGENT,
                        model_deployment_name=ai_agent_settings.model_deployment_name,
                        instructions=get_assistant_agent_instructions(assistant_agent_id),
                        plugins=[self.schedule_plugin, self.risk_plugin, assistant_logging]
                    )
                
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
    
    async def process_message(self, session_id, message):
        """Processes a user message and returns the combined response from all agents."""
        # Generate a conversation ID for this message
        conversation_id = str(uuid.uuid4())
        
        # Log the user query with the logging plugin
        try:
            self.logging_plugin.log_agent_event(
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
            
            # Check if the message is schedule-related
            is_schedule_related = any(keyword in message.lower() for keyword in 
                                    ["schedule risk", "schedule delay", "schedule variance", "late", "delivery", "milestone", "schedule"])
            
            # Add the user message to the chat with thinking context
            print(f"Creating user message content")
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
            await chat.add_chat_message(user_message)
            
            print(f"Invoking chat...")
            # Get the responses from all agents - use a dictionary to track latest response from each agent
            latest_responses = {}
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
                    if (ASSISTANT_AGENT in latest_responses and 
                        ((SCHEDULER_AGENT in latest_responses and REPORTING_AGENT in latest_responses) or
                        (not is_schedule_related))):
                        print("Complete conversation cycle detected, breaking out of loop")
                        break
                    
            except Exception as e:
                print(f"Error during chat.invoke(): {e}")
                import traceback
                traceback.print_exc()
                
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
                                self.logging_plugin.log_agent_event(
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
                        import traceback
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
                self.logging_plugin.log_agent_event(
                    agent_name="Chatbot",
                    action="Assistant Response",
                    result_summary="Generated combined response to user query",
                    conversation_id=conversation_id,
                    user_query=message,
                    agent_output=final_response  # Log the final response
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
                    conversation_id=conversation_id,
                    user_query=message
                )
            except Exception as log_error:
                print(f"Failed to log error: {log_error}")
            
            return {
                "status": "error",
                "error": str(e),
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