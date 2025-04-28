"""Chatbot manager for equipment schedule agent."""

import uuid
import asyncio
import json
import re
import os
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
from plugins.report_file_plugin import ReportFilePlugin  # Add this import

# Load environment variables from .env file
load_dotenv()

class ChatbotManager:
    """Manages the interactive chatbot for user queries."""
    
    def __init__(self, connection_string):
        self.connection_string = connection_string
        self.schedule_plugin = EquipmentSchedulePlugin(connection_string)
        self.risk_plugin = RiskCalculationPlugin()
        self.logging_plugin = LoggingPlugin(connection_string)
        self.report_file_plugin = ReportFilePlugin(connection_string)  # Add report file plugin
        self.chat_sessions = {}
        # Use a single lock for all session management operations
        self._session_lock = asyncio.Lock()
        # Add rate limiter for parallel execution
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
                loop.run_until_complete(self.cleanup_all_sessions())
        except Exception as e:
            print(f"Error in destructor: {e}")
    
    async def cleanup_all_sessions(self):
        """Cleanup all sessions."""
        session_ids = list(self.chat_sessions.keys())
        for session_id in session_ids:
            await self.close_session(session_id)
    
    async def initialize_session(self, session_id):
        """Initializes a new chat session with all agents using a lock to prevent race conditions."""
        
        # Use a single lock for all session operations to ensure serial access
        async with self._session_lock:
            # Check if the session already exists
            if session_id in self.chat_sessions:
                session = self.chat_sessions[session_id]
                # If it's not initializing and has a chat object, return it
                if not session.get("initializing", False) and "chat" in session:
                    print(f"Reusing existing chat session: {session_id}")
                    return session
                elif session.get("initializing", False):
                    # If it's already initializing, wait a moment and let the other thread complete
                    print(f"Session {session_id} is already being initialized, waiting...")
                    await asyncio.sleep(0.5)
                    # Try to get the session again
                    if session_id in self.chat_sessions:
                        session = self.chat_sessions[session_id]
                        if not session.get("initializing", False) and "chat" in session:
                            return session
            
            # Now we can start initialization
            print(f"Creating new chat session: {session_id}")
            
            # Generate a conversation ID that will be used for this entire session
            conversation_id = str(uuid.uuid4())
            
            # Mark this session as "initializing" to prevent race conditions
            self.chat_sessions[session_id] = {
                "initializing": True, 
                "last_activity": datetime.now(),
                "conversation_id": conversation_id
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
            
            # Create Bing connection configuration
            bing_connection = None
            if self.bing_api_key:
                bing_connection = {
                    "bing": {
                        "api_key": self.bing_api_key,
                        "endpoint": "https://api.bing.microsoft.com/v7.0/search"
                    }
                }
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
                plugins=[self.schedule_plugin, reporting_logging, self.report_file_plugin]  # Add report file plugin here
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
                            
                            # Get the plugins for each agent (update to include report file plugin)
                            agent_plugins = {
                                SCHEDULER_AGENT: [self.schedule_plugin, self.risk_plugin, scheduler_logging],
                                POLITICAL_RISK_AGENT: [political_logging],
                                TARIFF_RISK_AGENT: [tariff_logging],
                                LOGISTICS_RISK_AGENT: [logistics_logging],
                                REPORTING_AGENT: [self.schedule_plugin, reporting_logging, self.report_file_plugin],  # Include report file plugin
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
                selection_strategy=ParallelRiskAnalysisStrategy()  # Now using the parallel strategy
            )
            
            print(f"Chat session created successfully: {session_id}")
            
            # Update the chat session with the full data
            async with self._session_lock:
                self.chat_sessions[session_id] = {
                    "chat": chat,
                    "parallel_chat": parallel_chat,  # Add parallel chat for comprehensive analysis
                    "client": client,
                    "credential": creds,
                    "last_activity": datetime.now(),
                    "model_deployment_name": ai_agent_settings.model_deployment_name,
                    "agents": agents,
                    "agent_ids": agent_ids,
                    "conversation_id": conversation_id,
                    "initializing": False  # Mark as fully initialized
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
        """Process an agent with rate limiting."""
        async def execute():
            # Add the message to chat
            msg = ChatMessageContent(
                role=AuthorRole.ASSISTANT,
                name=agent_name,
                content=message_content
            )
            await chat.add_chat_message(msg)
            
            # Get agent response
            responses = []
            async for response in chat.invoke():
                if response and hasattr(response, 'name') and response.name == agent_name:
                    responses.append(response)
                    break
            
            return responses[0] if responses else None
        
        # Execute with rate limiting
        return await self.rate_limiter.execute_with_limit(execute)
    
    async def process_message(self, session_id, message):
        """Processes a user message and returns the combined response from all agents."""
        try:
            # Get or initialize the chat session
            session = await self.initialize_session(session_id)
            
            # Wait if session is still initializing
            retry_count = 0
            while session.get("initializing", False) and retry_count < 50:
                await asyncio.sleep(0.1)
                session = self.chat_sessions.get(session_id, {})
                retry_count += 1
            
            if session.get("initializing", False):
                return {
                    "status": "error",
                    "error": "Session initialization timed out. Please try again.",
                    "conversation_id": None
                }
            
            # Make sure the session has a chat object
            if "chat" not in session:
                # Session exists but no chat object - reinitialize
                print(f"Session {session_id} exists but has no chat object, reinitializing...")
                async with self._session_lock:
                    del self.chat_sessions[session_id]
                session = await self.initialize_session(session_id)
            
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
            scheduler_attempts = 0
            max_scheduler_attempts = 2
            
            try:
                if is_comprehensive_risk:
                    # For comprehensive risk analysis, we use parallel execution
                    risk_agents = [POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT]
                    
                    # First, get scheduler response
                    async for response in chat.invoke():
                        if response and hasattr(response, 'name'):
                            agent_name = response.name
                            if agent_name == SCHEDULER_AGENT:
                                latest_responses[agent_name] = response
                                break
                    
                    # If we have scheduler response, process risk agents in parallel
                    if SCHEDULER_AGENT in latest_responses:
                        # Create tasks for parallel execution of risk agents
                        risk_tasks = []
                        for risk_agent in risk_agents:
                            # Create a task for each risk agent using rate limiter
                            task = self.process_agent_with_rate_limit(
                                chat=chat,
                                agent_name=risk_agent,
                                message_content=latest_responses[SCHEDULER_AGENT].content
                            )
                            risk_tasks.append(task)
                        
                        # Execute all risk agents in parallel with rate limiting
                        risk_results = await asyncio.gather(*risk_tasks, return_exceptions=True)
                        
                        # Process results
                        for i, result in enumerate(risk_results):
                            if isinstance(result, Exception):
                                print(f"Error executing {risk_agents[i]}: {result}")
                            elif result:
                                latest_responses[risk_agents[i]] = result
                        
                        # Now get reporting agent response
                        async for response in chat.invoke():
                            if response and hasattr(response, 'name'):
                                agent_name = response.name
                                if agent_name == REPORTING_AGENT:
                                    latest_responses[agent_name] = response
                                    break
                else:
                    # For non-comprehensive queries, use the normal flow
                    async for response in chat.invoke():
                        if response is None:
                            continue
                        if not hasattr(response, 'name') or not response.name:
                            continue
                        
                        agent_name = response.name
                        latest_responses[agent_name] = response
                        
                        # Count scheduler attempts to avoid infinite loops
                        if agent_name == SCHEDULER_AGENT:
                            scheduler_attempts += 1
                        
                        # Check termination conditions based on query type
                        if (ASSISTANT_AGENT in latest_responses and not is_schedule_related):
                            break
                        
                        if (is_schedule_related and REPORTING_AGENT in latest_responses):
                            break
                        
                        # Handle specific risk agent responses
                        if agent_name in [POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT]:
                            # For specific risk queries, might terminate after risk agent responds
                            if not is_comprehensive_risk:
                                break
                    
            except Exception as e:
                print(f"Error during chat.invoke(): {e}")
                import traceback
                traceback.print_exc()
                
                return {
                    "status": "error",
                    "error": f"The agent encountered an error: {str(e)}. Please try again.",
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
                            report = """REPORTING_AGENT > 
                                # Equipment Schedule Risk Report

                                """
                            
                            # Add executive summary
                            if report_sections["executive_summary"].strip():
                                report += f"""## Executive Summary
                                    {report_sections["executive_summary"]}

                                    """
                            
                            # Add risk items
                            for risk_level in ["high_risk", "medium_risk", "low_risk"]:
                                if report_sections[risk_level].strip():
                                    level_name = risk_level.replace("_", " ").title()
                                    report += f"""## {level_name} Items
                                    {report_sections[risk_level]}

                                    """
                            
                            # Add recommendations based on findings
                            report += """## Recommendations

                                Based on the analysis:
                                """
                            
                            if "High Risk" in scheduler_content:
                                report += "- **For high-risk items**: Immediate escalation to management and suppliers required\n"
                            if "Medium Risk" in scheduler_content:
                                report += "- **For medium-risk items**: Increase monitoring frequency and prepare contingency plans\n"
                            if "Low Risk" in scheduler_content:
                                report += "- **For low-risk items**: Continue regular monitoring according to standard procedures\n"
                            
                            report += """
                                ## Next Steps

                                1. Review all identified risks with project stakeholders
                                2. Implement recommended mitigation actions
                                3. Update tracking mechanisms to monitor progress
                                4. Schedule follow-up reviews for high and medium risk items

                                ## Conclusion

                                This report provides a comprehensive view of the current equipment schedule status and associated risks. Immediate attention is recommended for all high-risk items to prevent potential project delays.
                                """
                            
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
                                report = f"""REPORTING_AGENT > 
                                            # Schedule Analysis Summary

                                            The scheduler has analyzed the equipment schedule data. However, due to communication limitations, a detailed report could not be generated at this time.

                                            ## Scheduler Analysis Output

                                            {scheduler_content}

                                            ## Next Steps

                                            Please try again or contact the project management team for support with the schedule analysis.
                                        """
                            else:
                                report = """REPORTING_AGENT > 
                                    # Schedule Analysis Summary

                                    The scheduler encountered issues while analyzing the equipment schedule data. No detailed report could be generated.

                                    ## Recommendations

                                    1. Please try your request again
                                    2. If the issue persists, contact technical support
                                    3. Consider breaking down your request into smaller, more specific queries

                                    ## Next Steps

                                    Please ensure your request is clear and specific. Try asking about:
                                    - Specific equipment items
                                    - Specific risk categories
                                    - Specific time periods
                                    """
                            
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
            
            # For specific risk queries or general queries
            elif latest_responses:
                # Get the last agent's response
                last_agent = list(latest_responses.keys())[-1]
                final_response = latest_responses[last_agent].content.replace(f"{last_agent} > ", "")
            
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

    # [Keep all existing cleanup_sessions and close_session methods unchanged]
    async def cleanup_sessions(self, max_age_minutes=30):
        """Cleans up inactive chat sessions."""
        now = datetime.now()
        sessions_to_remove = []
        
        async with self._session_lock:
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
        async with self._session_lock:
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
        
        # Close any HTTP client sessions that might be open in the agents
        if "chat" in session:
            try:
                chat = session["chat"]
                # Check each agent in the chat
                if hasattr(chat, 'agents'):
                    for agent in chat.agents:
                        if hasattr(agent, 'client') and hasattr(agent.client, '_session'):
                            try:
                                await agent.client._session.close()
                                print(f"Closed HTTP session for agent {agent.name}")
                            except Exception as e:
                                print(f"Error closing HTTP session for agent {agent.name}: {e}")
            except Exception as e:
                print(f"Error closing agent HTTP sessions: {e}")
        
        # Delete the session
        async with self._session_lock:
            if session_id in self.chat_sessions:
                del self.chat_sessions[session_id]
        
        return True