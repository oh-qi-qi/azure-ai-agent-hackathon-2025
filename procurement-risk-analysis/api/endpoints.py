"""API endpoints for the equipment schedule agent."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from config.settings import get_database_connection_string
from managers.chatbot_manager import ChatbotManager
from managers.scheduler import WorkflowScheduler

# Create router
router = APIRouter()

# Initialize managers
def get_chatbot_manager():
    """Gets the chatbot manager."""
    connection_string = get_database_connection_string()
    return ChatbotManager(connection_string)

def get_workflow_scheduler():
    """Gets the workflow scheduler."""
    connection_string = get_database_connection_string()
    return WorkflowScheduler(connection_string)

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

# Endpoint to trigger workflow immediately
@router.post("/workflow/run", response_model=WorkflowResponse)
async def run_workflow(scheduler: WorkflowScheduler = Depends(get_workflow_scheduler)):
    """Triggers the workflow to run immediately."""
    result = scheduler.run_now()
    return result

# Endpoint to get status of most recent workflow
@router.get("/workflow/status")
async def get_workflow_status():
    """Gets the status of the most recent workflow."""
    # Here you would implement logic to get the status from the database
    return {"message": "Not implemented yet"}

# REST endpoint for chat (alternative to WebSocket)
@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(message: ChatMessage, chatbot: ChatbotManager = Depends(get_chatbot_manager)):
    """REST endpoint for chat."""
    response = await chatbot.process_message(message.session_id, message.message)
    return response

# Endpoint to get risk summary
@router.get("/risks/summary")
async def get_risk_summary():
    """Gets a summary of current schedule risks."""
    connection_string = get_database_connection_string()
    from plugins.schedule_plugin import EquipmentSchedulePlugin
    schedule_plugin = EquipmentSchedulePlugin(connection_string)
    
    result = schedule_plugin.get_risk_summary()
    return result

# Endpoint to get schedule comparison data
@router.get("/schedule/comparison")
async def get_schedule_comparison(equipment_code: str = None, project_code: str = None):
    """Gets schedule comparison data."""
    connection_string = get_database_connection_string()
    from plugins.schedule_plugin import EquipmentSchedulePlugin
    schedule_plugin = EquipmentSchedulePlugin(connection_string)
    
    result = schedule_plugin.get_schedule_comparison_data(
        equipment_code=equipment_code,
        project_code=project_code
    )
    return result
