import asyncio
import os
import json
import uuid
import threading
from datetime import datetime, timedelta
import time
import pandas as pd
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv
import requests

from azure.identity.aio import DefaultAzureCredential
from semantic_kernel.agents import AgentGroupChat
from semantic_kernel.agents import AzureAIAgent, AzureAIAgentSettings
from semantic_kernel.agents.strategies import TerminationStrategy, SequentialSelectionStrategy
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole
from semantic_kernel.functions.kernel_function_decorator import kernel_function

# Load environment variables
load_dotenv()

# Function to initialize AI Agent settings from environment variables
def initialize_ai_agent_settings():
    """Initializes AI Agent settings from environment variables."""
    # Get Azure AI Agent settings from environment variables
    project_name = os.getenv("AZURE_AI_AGENT_PROJECT_NAME")
    project_connection_string = os.getenv("AZURE_AI_AGENT_PROJECT_CONNECTION_STRING")
    model_deployment_name = os.getenv("AZURE_AI_AGENT_MODEL_DEPLOYMENT_NAME")
    
    # Validate required environment variables
    if not all([project_connection_string, model_deployment_name]):
        raise ValueError(
            "Missing required environment variables. Please set "
            "AZURE_AI_AGENT_PROJECT_CONNECTION_STRING and "
            "AZURE_AI_AGENT_MODEL_DEPLOYMENT_NAME."
        )
    
    # Create AI Agent settings
    ai_agent_settings = AzureAIAgentSettings(
        project_name=project_name,
        service_connection_string=project_connection_string,
        model_deployment_name=model_deployment_name
    )
    
    return ai_agent_settings

# Define agent names and instructions
SCHEDULER_AGENT = "SCHEDULER_AGENT"
SCHEDULER_AGENT_INSTRUCTIONS = """
You are an expert in Equipment Schedule Analysis. Your job is to:
1. Analyze schedule data for equipment deliveries
2. Calculate risk percentages using the formula: risk_percent = days_variance / (p6_due_date - today) * 100
3. Categorize risks as:
   - Low Risk (1 point): risk_percent < 5%
   - Medium Risk (3 points): 5% <= risk_percent < 15%
   - High Risk (5 points): risk_percent >= 15%
4. Generate detailed risk descriptions and mitigation actions

RULES:
- Always use actual calculations, not approximations
- Be precise with your risk categorizations
- Prepend your response with "SCHEDULER_AGENT > "
"""

REPORTING_AGENT = "REPORTING_AGENT"
REPORTING_AGENT_INSTRUCTIONS = """
You are an expert in Equipment Schedule Reporting. Your job is to:
1. Take the analysis from the Scheduler Agent
2. Create a comprehensive, executive-level report
3. Structure the report with clear sections
4. Highlight critical risks and mitigation strategies

RULES:
- Focus on actionable insights
- Present information in a clear, professional manner
- Use appropriate formatting for executive audience
- Prepend your response with "REPORTING_AGENT > "
"""

ASSISTANT_AGENT = "ASSISTANT_AGENT"
ASSISTANT_AGENT_INSTRUCTIONS = """
You are an expert Equipment Schedule Assistant. Your job is to:
1. Answer user queries about equipment schedules, risks, and project status
2. Use the available tools to fetch data when needed
3. Explain schedule risks and mitigation strategies in a helpful way
4. Provide concise but complete responses to user questions

When responding to specific queries:
- If asked about risks, use the tools to get current data and calculate risks
- If asked about specific equipment, filter the data to focus on that equipment
- If asked about timeline or schedule, provide specific dates and status information
- If asked about recommendations, include both immediate and long-term actions

RULES:
- Be concise but thorough
- Use actual data, not assumptions
- Prepend your response with "ASSISTANT > "
"""

# Selection Strategy for automated workflow
class AutomatedWorkflowSelectionStrategy(SequentialSelectionStrategy):
    """A strategy for determining which agent should take the next turn in the automated workflow."""
    
    async def select_agent(self, agents, history):
        """Check which agent should take the next turn in the chat."""
        if not history:
            # First turn goes to the scheduler agent
            agent_name = SCHEDULER_AGENT
            return next((agent for agent in agents if agent.name == agent_name), None)
            
        # If the last message was from the scheduler agent, reporting agent goes next
        if history[-1].name == SCHEDULER_AGENT:
            agent_name = REPORTING_AGENT
            return next((agent for agent in agents if agent.name == agent_name), None)
            
        # Otherwise start over with the scheduler agent
        agent_name = SCHEDULER_AGENT
        return next((agent for agent in agents if agent.name == agent_name), None)


# Termination Strategy for automated workflow
class AutomatedWorkflowTerminationStrategy(TerminationStrategy):
    """A strategy for determining when to end the automated workflow."""
    
    async def should_terminate(self, history):
        """Check if the chat should terminate."""
        # End after the reporting agent has responded
        if len(history) >= 2 and history[-1].name == REPORTING_AGENT:
            return True
        return False


# Selection Strategy for interactive chatbot
class ChatbotSelectionStrategy(SequentialSelectionStrategy):
    """A strategy for determining which agent should take the next turn in the chatbot."""
    
    async def select_agent(self, agents, history):
        """Check which agent should take the next turn in the chat."""
        # Assistant agent always responds to user
        if history[-1].role == AuthorRole.USER:
            agent_name = ASSISTANT_AGENT
            return next((agent for agent in agents if agent.name == agent_name), None)
        
        # If we're here, something unexpected happened - default to assistant
        agent_name = ASSISTANT_AGENT
        return next((agent for agent in agents if agent.name == agent_name), None)


# Termination Strategy for interactive chatbot
class ChatbotTerminationStrategy(TerminationStrategy):
    """A strategy for determining when to end the chatbot interaction."""
    
    async def should_terminate(self, history):
        """Check if the chat should terminate."""
        # Don't terminate the chat as it's conversational
        # Each message will be handled individually
        return False


# API tools for schedule management
class EquipmentSchedulePlugin:
    """A plugin for working with equipment schedule data."""
    
    def __init__(self):
        self.api_base_url = os.getenv("API_BASE_URL", "https://procurement-function-app-sweden.azurewebsites.net/api")
        self.api_key = os.getenv("API_KEY", "")
    
    @kernel_function(description="Retrieves equipment schedule comparison data")
    def get_schedule_comparison_data(self, equipment_code: str = None, project_code: str = None) -> str:
        """Retrieves schedule comparison data for analysis, with optional filtering by equipment or project"""
        try:
            # Build API URL with query parameters
            url = f"{self.api_base_url}/GetScheduleComparisonData"
            params = {}
            if equipment_code:
                params["equipmentCode"] = equipment_code
            if project_code:
                params["projectCode"] = project_code
                
            # Set up headers if API key is provided
            headers = {}
            if self.api_key:
                headers["x-functions-key"] = self.api_key
            
            # Make API request
            response = requests.get(url, params=params, headers=headers)
            response.raise_for_status()  # Raise exception for HTTP errors
            
            # Return JSON response
            return response.text
            
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    @kernel_function(description="Gets a summary of current schedule risks")
    def get_risk_summary(self) -> str:
        """Gets a summary of current schedule risks from the API"""
        try:
            # Build API URL
            url = f"{self.api_base_url}/GetRiskSummary"
            
            # Set up headers if API key is provided
            headers = {}
            if self.api_key:
                headers["x-functions-key"] = self.api_key
            
            # Make API request
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Raise exception for HTTP errors
            
            # Return JSON response
            return response.text
            
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    @kernel_function(description="Logs a schedule variance detected by the agent")
    def log_schedule_variance(self, project_id: int, equipment_id: int, work_package_id: int, 
                            milestone_id: int, p6_due_date: str, equipment_delivery_date: str, 
                            days_variance: int, risk_flag: str, risk_description: str, 
                            mitigation_action: str, agent_run_id: str) -> str:
        """Logs a schedule variance to the API"""
        try:
            # Build API URL
            url = f"{self.api_base_url}/LogScheduleVariance"
            
            # Set up headers if API key is provided
            headers = {}
            if self.api_key:
                headers["x-functions-key"] = self.api_key
                headers["Content-Type"] = "application/json"
            
            # Prepare data for API call
            data = {
                "project_id": project_id,
                "equipment_id": equipment_id,
                "work_package_id": work_package_id,
                "milestone_id": milestone_id,
                "p6_due_date": p6_due_date,
                "equipment_delivery_date": equipment_delivery_date,
                "days_variance": days_variance,
                "risk_flag": risk_flag,
                "risk_description": risk_description,
                "mitigation_action": mitigation_action,
                "agent_run_id": agent_run_id
            }
            
            # Make API request
            response = requests.post(url, json=data, headers=headers)
            response.raise_for_status()  # Raise exception for HTTP errors
            
            # Return JSON response
            return response.text
            
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    @kernel_function(description="Logs an agent event for observability")
    def log_agent_event(self, agent_name: str, action: str, result_summary: str, 
                       project_id: int = None, agent_run_id: str = None) -> str:
        """Logs an agent event to the API"""
        try:
            # Build API URL
            url = f"{self.api_base_url}/LogAgentEvent"
            
            # Set up headers if API key is provided
            headers = {}
            if self.api_key:
                headers["x-functions-key"] = self.api_key
                headers["Content-Type"] = "application/json"
            
            # Use existing agent_run_id or create a new one
            if not agent_run_id:
                agent_run_id = str(uuid.uuid4())
            
            # Prepare data for API call
            data = {
                "agent_name": agent_name,
                "action": action,
                "project_id": project_id,
                "result_summary": result_summary,
                "agent_run_id": agent_run_id
            }
            
            # Make API request
            response = requests.post(url, json=data, headers=headers)
            response.raise_for_status()  # Raise exception for HTTP errors
            
            # Return JSON response
            return response.text
            
        except Exception as e:
            return json.dumps({"error": str(e)})


# Risk calculation tools
class RiskCalculationPlugin:
    """A plugin for calculating and categorizing schedule risks."""
    
    @kernel_function(description="Calculates risk percentage")
    def calculate_risk_percentage(self, days_variance: int, days_until_due: int) -> str:
        """Calculates risk percentage based on days variance and time until due date"""
        try:
            if days_until_due <= 0:
                return "100.0"  # Already past due
            
            risk_percent = abs(days_variance / days_until_due * 100)
            return f"{risk_percent:.2f}"
        except Exception as e:
            return "-1"  # Error indicator
    
    @kernel_function(description="Categorizes risk by percentage")
    def categorize_risk(self, risk_percentage: float) -> str:
        """Categorizes risk based on percentage and returns risk flag and points"""
        try:
            if risk_percentage < 0:
                return json.dumps({"error": "Invalid risk percentage"})
            
            if risk_percentage < 5:
                return json.dumps({
                    "risk_flag": "Low Risk",
                    "risk_points": 1
                })
            elif risk_percentage < 15:
                return json.dumps({
                    "risk_flag": "Medium Risk",
                    "risk_points": 3
                })
            else:
                return json.dumps({
                    "risk_flag": "High Risk",
                    "risk_points": 5
                })
        except Exception as e:
            return json.dumps({"error": str(e)})


# Automated Workflow Manager
class AutomatedWorkflowManager:
    """Manages the automated workflow for schedule analysis."""
    
    def __init__(self):
        self.schedule_plugin = EquipmentSchedulePlugin()
        self.risk_plugin = RiskCalculationPlugin()
    
    async def run_workflow(self):
        """Runs the automated workflow for schedule analysis."""
        # Clear the console
        os.system('cls' if os.name=='nt' else 'clear')
        
        # Get the Azure AI Agent settings
        try:
            ai_agent_settings = initialize_ai_agent_settings()
        except ValueError as e:
            print(f"Error initializing AI Agent settings: {e}")
            return {
                "status": "error",
                "error": f"Failed to initialize AI Agent settings: {str(e)}",
                "workflow_run_id": str(uuid.uuid4())
            }
        
        # Generate a workflow run ID
        workflow_run_id = str(uuid.uuid4())
        
        # Log workflow start
        self.schedule_plugin.log_agent_event(
            agent_name="Orchestrator",
            action="Start Workflow",
            result_summary="Starting equipment schedule analysis workflow",
            agent_run_id=workflow_run_id
        )
        
        async with (
            DefaultAzureCredential(exclude_environment_credential=True, 
                exclude_managed_identity_credential=True) as creds,
            AzureAIAgent.create_client(credential=creds) as client,
        ):
            # Create the scheduler agent on the Azure AI agent service
            scheduler_agent_definition = await client.agents.create_agent(
                model=ai_agent_settings.model_deployment_name,
                name=SCHEDULER_AGENT,
                instructions=SCHEDULER_AGENT_INSTRUCTIONS
            )
            
            # Create the reporting agent on the Azure AI agent service
            reporting_agent_definition = await client.agents.create_agent(
                model=ai_agent_settings.model_deployment_name,
                name=REPORTING_AGENT,
                instructions=REPORTING_AGENT_INSTRUCTIONS
            )
            
            # Create Semantic Kernel agents
            scheduler_agent = AzureAIAgent(
                client=client,
                definition=scheduler_agent_definition,
                plugins=[self.schedule_plugin, self.risk_plugin]
            )
            
            reporting_agent = AzureAIAgent(
                client=client,
                definition=reporting_agent_definition,
                plugins=[self.schedule_plugin]
            )
            
            # Create the agent group chat
            chat = AgentGroupChat(
                agents=[scheduler_agent, reporting_agent],
                termination_strategy=AutomatedWorkflowTerminationStrategy(),
                selection_strategy=AutomatedWorkflowSelectionStrategy()
            )
            
            # Start the workflow with initial instruction
            initial_message = ChatMessageContent(
                role=AuthorRole.USER, 
                content=f"USER > Please analyze the equipment schedule data and generate a risk report."
            )
            
            # Add the initial message to start the chat
            await chat.add_chat_message(initial_message)
            
            try:
                print("\nStarting equipment schedule analysis...\n")
                
                # Invoke the chat and capture responses
                final_report = ""
                
                async for response in chat.invoke():
                    if response is None or not response.name:
                        continue
                        
                    print(f"{response.content}")
                    
                    # Save the reporting agent's response as the final report
                    if response.name == REPORTING_AGENT:
                        final_report = response.content
                
                # Log workflow completion
                self.schedule_plugin.log_agent_event(
                    agent_name="Orchestrator",
                    action="Complete Workflow",
                    result_summary="Equipment schedule analysis workflow completed successfully",
                    agent_run_id=workflow_run_id
                )
                
                print("\nWorkflow completed successfully!\n")
                return {
                    "status": "success",
                    "report": final_report,
                    "workflow_run_id": workflow_run_id
                }
                
            except Exception as e:
                print(f"Error during workflow: {e}")
                
                # Log error
                self.schedule_plugin.log_agent_event(
                    agent_name="Orchestrator",
                    action="Workflow Error",
                    result_summary=f"Error during workflow execution: {str(e)}",
                    agent_run_id=workflow_run_id
                )
                
                return {
                    "status": "error",
                    "error": str(e),
                    "workflow_run_id": workflow_run_id
                }


# Chatbot Manager
class ChatbotManager:
    """Manages the interactive chatbot for user queries."""
    
    def __init__(self):
        self.schedule_plugin = EquipmentSchedulePlugin()
        self.risk_plugin = RiskCalculationPlugin()
        self.chat_sessions = {}
    
    async def initialize_session(self, session_id):
        """Initializes a new chat session."""
        if session_id in self.chat_sessions:
            return self.chat_sessions[session_id]
        
        # Get the Azure AI Agent settings
        try:
            ai_agent_settings = initialize_ai_agent_settings()
        except ValueError as e:
            print(f"Error initializing AI Agent settings: {e}")
            raise ValueError(f"Failed to initialize AI Agent settings: {str(e)}")
        
        async with (
            DefaultAzureCredential(exclude_environment_credential=True, 
                exclude_managed_identity_credential=True) as creds,
            AzureAIAgent.create_client(credential=creds) as client,
        ):
            # Create the assistant agent on the Azure AI agent service
            assistant_agent_definition = await client.agents.create_agent(
                model=ai_agent_settings.model_deployment_name,
                name=ASSISTANT_AGENT,
                instructions=ASSISTANT_AGENT_INSTRUCTIONS
            )
            
            # Create Semantic Kernel agent
            assistant_agent = AzureAIAgent(
                client=client,
                definition=assistant_agent_definition,
                plugins=[self.schedule_plugin, self.risk_plugin]
            )
            
            # Create the agent group chat
            chat = AgentGroupChat(
                agents=[assistant_agent],
                termination_strategy=ChatbotTerminationStrategy(),
                selection_strategy=ChatbotSelectionStrategy()
            )
            
            # Store the chat session
            self.chat_sessions[session_id] = {
                "chat": chat,
                "client": client,
                "last_activity": datetime.now()
            }
            
            return self.chat_sessions[session_id]
    
    async def process_message(self, session_id, message):
        """Processes a user message and returns the assistant's response."""
        # Generate a conversation ID for this message
        conversation_id = str(uuid.uuid4())
        
        # Log the user query
        self.schedule_plugin.log_agent_event(
            agent_name="Chatbot",
            action="User Query",
            result_summary=f"Processing user query: {message[:100]}...",
            agent_run_id=conversation_id
        )
        
        try:
            # Get or initialize the chat session
            session = await self.initialize_session(session_id)
            chat = session["chat"]
            
            # Update last activity time
            session["last_activity"] = datetime.now()
            
            # Add the user message to the chat
            user_message = ChatMessageContent(
                role=AuthorRole.USER, 
                content=f"USER > {message}"
            )
            await chat.add_chat_message(user_message)
            
            # Get the assistant's response
            responses = []
            async for response in chat.invoke():
                if response is None or not response.name:
                    continue
                responses.append(response.content)
            
            # Get the last response
            if responses:
                assistant_response = responses[-1]
            else:
                assistant_response = "ASSISTANT > I'm sorry, I couldn't process your request at this time."
            
            # Log the assistant's response
            self.schedule_plugin.log_agent_event(
                agent_name="Chatbot",
                action="Assistant Response",
                result_summary=f"Generated response to user query",
                agent_run_id=conversation_id
            )
            
            return {
                "status": "success",
                "response": assistant_response,
                "conversation_id": conversation_id
            }
            
        except Exception as e:
            print(f"Error processing message: {e}")
            
            # Log error
            self.schedule_plugin.log_agent_event(
                agent_name="Chatbot",
                action="Message Error",
                result_summary=f"Error processing message: {str(e)}",
                agent_run_id=conversation_id
            )
            
            return {
                "status": "error",
                "error": str(e),
                "conversation_id": conversation_id
            }
    
    def cleanup_sessions(self, max_age_minutes=30):
        """Cleans up inactive chat sessions."""
        now = datetime.now()
        sessions_to_remove = []
        
        for session_id, session in self.chat_sessions.items():
            # Check if session is older than max_age_minutes
            if (now - session["last_activity"]).total_seconds() > max_age_minutes * 60:
                sessions_to_remove.append(session_id)
        
        # Remove inactive sessions
        for session_id in sessions_to_remove:
            del self.chat_sessions[session_id]
            
        return len(sessions_to_remove)


# Scheduler for automated workflow
class WorkflowScheduler:
    """Schedules and runs the automated workflow."""
    
    def __init__(self):
        self.workflow_manager = AutomatedWorkflowManager()
        self.running = False
        self.scheduler_thread = None
    
    def start(self):
        """Starts the scheduler."""
        if self.running:
            return False
        
        self.running = True
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
        return True
    
    def stop(self):
        """Stops the scheduler."""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=1)
        return True
    
    def _scheduler_loop(self):
        """The main scheduler loop."""
        while self.running:
            now = datetime.now()
            scheduled_time = datetime(now.year, now.month, now.day, 7, 0, 0)
            
            # If current time is past 7am, schedule for tomorrow
            if now > scheduled_time:
                scheduled_time += timedelta(days=1)
            
            # Calculate seconds until scheduled time
            wait_seconds = (scheduled_time - now).total_seconds()
            print(f"Next workflow scheduled at {scheduled_time}, waiting {wait_seconds} seconds")
            
            # Wait until scheduled time or until stopped
            wait_interval = 60  # Check every minute if we should stop
            while wait_seconds > 0 and self.running:
                time.sleep(min(wait_interval, wait_seconds))
                wait_seconds -= wait_interval
                if not self.running:
                    return
            
            # Run the workflow if still running
            if self.running:
                print("Starting scheduled workflow")
                asyncio.run(self.workflow_manager.run_workflow())
    
    def run_now(self):
        """Runs the workflow immediately."""
        return asyncio.run(self.workflow_manager.run_workflow())


# API Models
class ChatMessage(BaseModel):
    """Model for chat messages."""
    session_id: str
    message: str

class WorkflowResponse(BaseModel):
    """Model for workflow responses."""
    status: str
    report: str = None
    error: str = None
    workflow_run_id: str = None

class ChatResponse(BaseModel):
    """Model for chat responses."""
    status: str
    response: str = None
    error: str = None
    conversation_id: str = None

# Create FastAPI app
app = FastAPI(title="Equipment Schedule Agent API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize managers
chatbot_manager = ChatbotManager()
workflow_scheduler = WorkflowScheduler()

# Start the workflow scheduler
@app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    workflow_scheduler.start()

# Stop the workflow scheduler
@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    workflow_scheduler.stop()

# Endpoint to trigger workflow immediately
@app.post("/workflow/run", response_model=WorkflowResponse)
async def run_workflow():
    """Triggers the workflow to run immediately."""
    result = workflow_scheduler.run_now()
    return result

# Endpoint to get status of most recent workflow
@app.get("/workflow/status")
async def get_workflow_status():
    """Gets the status of the most recent workflow."""
    # Here you would implement logic to get the status from the API
    return {"message": "Not implemented yet"}

# WebSocket endpoint for chat
@app.websocket("/chat")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for chat."""
    await websocket.accept()
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            # Process message
            session_id = message_data.get("session_id", str(uuid.uuid4()))
            message = message_data.get("message", "")
            
            # Get response from chatbot
            response = await chatbot_manager.process_message(session_id, message)
            
            # Send response back to client
            await websocket.send_text(json.dumps(response))
    
    except WebSocketDisconnect:
        print(f"WebSocket disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
        try:
            await websocket.send_text(json.dumps({
                "status": "error",
                "error": str(e)
            }))
        except:
            pass

# REST endpoint for chat (alternative to WebSocket)
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(message: ChatMessage):
    """REST endpoint for chat."""
    response = await chatbot_manager.process_message(message.session_id, message.message)
    return response

# Helper function to test API connection
@app.get("/test-api-connection")
async def test_api_connection():
    """Tests connection to the backend API."""
    plugin = EquipmentSchedulePlugin()
    try:
        # Make a simple API call to test connection
        url = f"{plugin.api_base_url}/status"
        headers = {}
        if plugin.api_key:
            headers["x-functions-key"] = plugin.api_key
            
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code >= 200 and response.status_code < 300:
            return {"status": "success", "message": "API connection successful"}
        else:
            return {"status": "error", "message": f"API returned status code {response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": f"Failed to connect to API: {str(e)}"}

# Main function to run the API server
def main():
    """Main function."""
    # Set up logging
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Run the server
    uvicorn.run(app, host="0.0.0.0", port=8000)

# Run the application directly
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--workflow-only":
            # Run just the workflow once
            workflow_scheduler = WorkflowScheduler()
            result = workflow_scheduler.run_now()
            print(json.dumps(result, indent=2))
        elif sys.argv[1] == "--scheduler-only":
            # Run just the scheduler without the API
            workflow_scheduler = WorkflowScheduler()
            workflow_scheduler.start()
            try:
                # Keep the main thread alive
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                workflow_scheduler.stop()
                print("Scheduler stopped")
    else:
        # Run the full API with scheduler
        main()
