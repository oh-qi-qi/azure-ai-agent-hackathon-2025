"""Automated workflow manager for schedule analysis."""

import os
import uuid
import asyncio

from azure.identity.aio import DefaultAzureCredential
from semantic_kernel.agents import AgentGroupChat
from semantic_kernel.agents import AzureAIAgent
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from config.settings import initialize_ai_agent_settings
from agents.agent_definitions import (
    SCHEDULER_AGENT, SCHEDULER_AGENT_INSTRUCTIONS,
    REPORTING_AGENT, REPORTING_AGENT_INSTRUCTIONS
)
from agents.agent_strategies import (
    AutomatedWorkflowSelectionStrategy, 
    AutomatedWorkflowTerminationStrategy
)
from agents.agent_manager import create_or_reuse_agent
from plugins.schedule_plugin import EquipmentSchedulePlugin
from plugins.risk_plugin import RiskCalculationPlugin
from plugins.logging_plugin import LoggingPlugin  # Updated import

class AutomatedWorkflowManager:
    """Manages the automated workflow for schedule analysis."""
    
    def __init__(self, connection_string):
        self.connection_string = connection_string
        self.schedule_plugin = EquipmentSchedulePlugin(connection_string)
        self.risk_plugin = RiskCalculationPlugin()
        self.logging_plugin = LoggingPlugin(connection_string)  # Updated to use consolidated logging
    
    async def run_workflow(self):
        """Runs the automated workflow for schedule analysis."""
        # Clear the console
        os.system('cls' if os.name=='nt' else 'clear')
        
        # Get the Azure AI Agent settings
        try:
            ai_agent_settings = initialize_ai_agent_settings()
            print(f"AI Agent settings initialized: {ai_agent_settings.model_deployment_name}")
        except ValueError as e:
            print(f"Error initializing AI Agent settings: {e}")
            return {
                "status": "error",
                "error": f"Failed to initialize AI Agent settings: {str(e)}",
                "workflow_run_id": str(uuid.uuid4())
            }
        
        # Generate a workflow run ID and session ID
        workflow_run_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        print(f"Workflow run ID: {workflow_run_id}")
        print(f"Session ID: {session_id}")
        
        # Log workflow start
        try:
            self.logging_plugin.log_agent_event(  # Updated to use consolidated logging
                agent_name="Orchestrator",
                action="Start Workflow",
                result_summary="Starting equipment schedule analysis workflow",
                conversation_id=workflow_run_id
            )
            print("Logged workflow start event")
        except Exception as e:
            print(f"Error logging workflow start: {e}")
        
        try:
            # Create credentials - no await needed
            creds = DefaultAzureCredential(exclude_environment_credential=True, 
                                        exclude_managed_identity_credential=True)
            print("Created DefaultAzureCredential")
            
            # Use try...finally to ensure resources are properly closed
            try:
                # Create client - no await needed
                client = AzureAIAgent.create_client(credential=creds)
                print("Created AzureAIAgent client")
                
                # Create or reuse the scheduler agent
                scheduler_agent = await create_or_reuse_agent(
                    client=client,
                    agent_name=SCHEDULER_AGENT,
                    model_deployment_name=ai_agent_settings.model_deployment_name,
                    instructions=SCHEDULER_AGENT_INSTRUCTIONS,
                    plugins=[self.schedule_plugin, self.risk_plugin, self.logging_plugin]  # Updated plugin list
                )

                # Create or reuse the reporting agent
                reporting_agent = await create_or_reuse_agent(
                    client=client,
                    agent_name=REPORTING_AGENT,
                    model_deployment_name=ai_agent_settings.model_deployment_name,
                    instructions=REPORTING_AGENT_INSTRUCTIONS,
                    plugins=[self.schedule_plugin, self.logging_plugin]  # Updated plugin list
                )
                
                # Get agent IDs
                scheduler_agent_id = None
                reporting_agent_id = None
                
                # Extract IDs if available
                if hasattr(scheduler_agent, 'definition') and hasattr(scheduler_agent.definition, 'id'):
                    scheduler_agent_id = scheduler_agent.definition.id
                if hasattr(reporting_agent, 'definition') and hasattr(reporting_agent.definition, 'id'):
                    reporting_agent_id = reporting_agent.definition.id
                
                print(f"Scheduler agent ready: {scheduler_agent.name} (ID: {scheduler_agent_id})")
                print(f"Reporting agent ready: {reporting_agent.name} (ID: {reporting_agent_id})")
                
                
                # Create the agent group chat
                print("Creating agent group chat")
                chat = AgentGroupChat(
                    agents=[scheduler_agent, reporting_agent],
                    termination_strategy=AutomatedWorkflowTerminationStrategy(),
                    selection_strategy=AutomatedWorkflowSelectionStrategy()
                )
                
                # Start the workflow with initial instruction that includes thinking context
                print("Creating initial message")
                initial_message = ChatMessageContent(
                    role=AuthorRole.USER, 
                    content=f"""USER > Please analyze the equipment schedule data and generate a risk report.
                    
                    When logging your thinking with log_agent_thinking, use these parameters:
                    - conversation_id: "{workflow_run_id}"
                    - session_id: "{session_id}"
                    - model_deployment_name: "{ai_agent_settings.model_deployment_name}"
                    """
                )
                
                # Add the initial message to start the chat
                print("Adding message to chat")
                await chat.add_chat_message(initial_message)
                
                try:
                    print("\nStarting equipment schedule analysis...\n")
                    
                    # Invoke the chat and capture responses
                    final_report = ""
                    
                    print("Invoking chat")
                    saved_responses = {}
                    async for response in chat.invoke():
                        if response is None or not response.name:
                            print("Received empty response, skipping")
                            continue
                            
                        agent_name = response.name
                        print(f"Response from {agent_name}: {response.content[:100]}...")
                        
                        # Store the latest response from each agent
                        saved_responses[agent_name] = response.content
                        
                        # Specifically track the reporting agent's final response
                        if agent_name == REPORTING_AGENT:
                            final_report = response.content
                    
                    # Log workflow completion
                    try:
                        self.logging_plugin.log_agent_event(  # Updated to use consolidated logging
                            agent_name="Orchestrator",
                            action="Complete Workflow",
                            result_summary="Equipment schedule analysis workflow completed successfully",
                            conversation_id=workflow_run_id
                        )
                    except Exception as e:
                        print(f"Error logging workflow completion: {e}")
                    
                    print("\nWorkflow completed successfully!\n")
                    return {
                        "status": "success",
                        "report": final_report,
                        "workflow_run_id": workflow_run_id
                    }
                    
                except Exception as e:
                    print(f"Error during workflow execution: {e}")
                    import traceback
                    traceback.print_exc()
                    
                    # Log error
                    try:
                        self.logging_plugin.log_agent_event(  # Updated to use consolidated logging
                            agent_name="Orchestrator",
                            action="Workflow Error",
                            result_summary=f"Error during workflow execution: {str(e)}",
                            conversation_id=workflow_run_id
                        )
                    except Exception as log_error:
                        print(f"Failed to log workflow error: {log_error}")
                    
                    return {
                        "status": "error",
                        "error": str(e),
                        "workflow_run_id": workflow_run_id
                    }
            finally:
                # Close resources appropriately
                if 'client' in locals():
                    # For non-async clients, no await needed for closing
                    if hasattr(client, 'close') and callable(client.close):
                        client.close()
                        print("Client closed")
        except Exception as e:
            print(f"Error setting up workflow: {e}")
            import traceback
            traceback.print_exc()
            
            # Log error
            try:
                self.logging_plugin.log_agent_event(  # Updated to use consolidated logging
                    agent_name="Orchestrator",
                    action="Workflow Setup Error",
                    result_summary=f"Error setting up workflow: {str(e)}",
                    conversation_id=workflow_run_id
                )
            except Exception as log_error:
                print(f"Failed to log setup error: {log_error}")
            
            return {
                "status": "error",
                "error": f"Failed to set up workflow: {str(e)}",
                "workflow_run_id": workflow_run_id
            }
        finally:
            # For non-async credentials, no await needed for closing
            if 'creds' in locals():
                if hasattr(creds, 'close') and callable(creds.close):
                    creds.close()
                    print("Credentials closed")