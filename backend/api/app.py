"""FastAPI application for the equipment schedule agent."""

import uuid
import json
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config.settings import get_database_connection_string
from managers.chatbot_manager import ChatbotManager
from managers.scheduler import WorkflowScheduler
from api.endpoints import router

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

# Get connection string
connection_string = get_database_connection_string()

# Initialize managers
chatbot_manager = ChatbotManager(connection_string)
workflow_scheduler = WorkflowScheduler(connection_string)

# Include router
app.include_router(router)

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
    
    # Clean up any remaining chat sessions
    print("Cleaning up all chat sessions...")
    await chatbot_manager.cleanup_sessions(max_age_minutes=0)
    
    # Add a small delay to allow resources to clean up properly
    await asyncio.sleep(1)
    
    print("Shutdown complete")
    
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
