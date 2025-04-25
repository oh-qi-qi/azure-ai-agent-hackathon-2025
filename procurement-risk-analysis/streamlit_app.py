"""Streamlit UI for the equipment schedule agent."""

import streamlit as st
import requests
import json
import pandas as pd
import os
import asyncio
import nest_asyncio
from datetime import datetime
import uuid
import dotenv
import pyodbc
import sys
import importlib.util

# Load environment variables
dotenv.load_dotenv()

# Try to import modules from our application
try:
    from config.settings import get_database_connection_string
    from managers.chatbot_manager import ChatbotManager
    from managers.scheduler import WorkflowScheduler
    modules_imported = True
except ImportError:
    modules_imported = False
    st.warning("Could not import modules directly. Will try to use API or direct module loading.")

# Initialize session state
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "workflow_results" not in st.session_state:
    st.session_state.workflow_results = None

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "api_running" not in st.session_state:
    st.session_state.api_running = False

# Function to clear input
def clear_input():
    st.session_state.user_message = ""

# Function to dynamically load the scheduler module
def load_scheduler_module():
    if modules_imported:
        connection_string = get_database_connection_string()
        return WorkflowScheduler(connection_string)
    
    # Try to import the module dynamically
    try:
        spec = importlib.util.spec_from_file_location("managers.scheduler", "managers/scheduler.py")
        scheduler_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scheduler_module)
        
        connection_string = os.getenv("DB_CONNECTION_STRING")
        if not connection_string:
            st.error("DB_CONNECTION_STRING environment variable not set")
            return None
            
        return scheduler_module.WorkflowScheduler(connection_string)
    except Exception as e:
        st.error(f"Could not load scheduler module: {e}")
        return None

# Function to dynamically load the chatbot module
def load_chatbot_module():
    if modules_imported:
        connection_string = get_database_connection_string()
        return ChatbotManager(connection_string)
    
    # Try to import the module dynamically
    try:
        spec = importlib.util.spec_from_file_location("managers.chatbot_manager", "managers/chatbot_manager.py")
        chatbot_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(chatbot_module)
        
        connection_string = os.getenv("DB_CONNECTION_STRING")
        if not connection_string:
            st.error("DB_CONNECTION_STRING environment variable not set")
            return None
            
        return chatbot_module.ChatbotManager(connection_string)
    except Exception as e:
        st.error(f"Could not load chatbot module: {e}")
        return None

# Function to directly run the workflow without API
def run_workflow_directly():
    workflow_scheduler = load_scheduler_module()
    if workflow_scheduler:
        # Apply nest_asyncio to allow running asyncio in Streamlit
        nest_asyncio.apply()
        
        # Run the workflow
        with st.spinner("Running workflow analysis..."):
            result = workflow_scheduler.run_now()
            return result
    else:
        st.error("Could not load workflow scheduler. Make sure all modules are properly installed.")
        return None

# Function to check database connection
def test_db_connection():
    connection_string = os.getenv("DB_CONNECTION_STRING")
    
    if not connection_string:
        return "DB_CONNECTION_STRING environment variable not set"
    
    try:
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        return "Connection successful!"
    except Exception as e:
        return f"Connection failed: {str(e)}"

# Function to check Azure AI Agent settings
def test_azure_settings():
    project_name = os.getenv("AZURE_AI_AGENT_PROJECT_NAME")
    project_connection_string = os.getenv("AZURE_AI_AGENT_PROJECT_CONNECTION_STRING")
    model_deployment_name = os.getenv("AZURE_AI_AGENT_MODEL_DEPLOYMENT_NAME")
    
    missing = []
    if not project_connection_string:
        missing.append("AZURE_AI_AGENT_PROJECT_CONNECTION_STRING")
    if not model_deployment_name:
        missing.append("AZURE_AI_AGENT_MODEL_DEPLOYMENT_NAME")
    
    if missing:
        return f"Missing environment variables: {', '.join(missing)}"
    return "Azure settings look good!"

# Function to send a chat message via API
def send_chat_message_api(message):
    try:
        response = requests.post(
            "http://localhost:8000/chat",
            json={"session_id": st.session_state.session_id, "message": message},
            timeout=240
        )
        return response.json()
    except Exception as e:
        return {"status": "error", "error": str(e)}

# Function to send a chat message directly
def send_chat_message_direct(message):
    chatbot_manager = load_chatbot_module()
    if chatbot_manager:
        # Store the chatbot manager in session state for cleanup later
        if "chatbot_manager" not in st.session_state:
            st.session_state.chatbot_manager = chatbot_manager
        
        # Apply nest_asyncio to allow running asyncio in Streamlit
        nest_asyncio.apply()
        
        # Process the message
        try:
            loop = asyncio.get_event_loop()
            response = loop.run_until_complete(
                chatbot_manager.process_message(st.session_state.session_id, message)
            )
            return response
        except Exception as e:
            st.error(f"Error processing message: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # If the session is corrupted, create a new one
            if "Rate limit is exceeded" in str(e):
                st.warning("Rate limit exceeded. Please wait a moment before trying again.")
                # Generate a new session ID to force session recreation
                st.session_state.session_id = str(uuid.uuid4())
            
            return {
                "status": "error", 
                "error": f"Error: {str(e)}. Please try again in a moment."
            }
    else:
        return {"status": "error", "error": "Could not load chatbot manager"}

# Add a function to reset the chat session if needed
def reset_chat_session():
    # Generate a new session ID
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.chat_history = []
    
    # Clean up any existing chatbot manager
    if "chatbot_manager" in st.session_state:
        try:
            chatbot_manager = st.session_state.chatbot_manager
            # Apply nest_asyncio to allow running asyncio in Streamlit
            nest_asyncio.apply()
            
            # Run the cleanup in the event loop
            loop = asyncio.get_event_loop()
            loop.run_until_complete(
                chatbot_manager.cleanup_sessions(max_age_minutes=0)
            )
        except Exception as e:
            print(f"Error cleaning up sessions: {e}")
        
        # Remove the chatbot manager from session state
        del st.session_state.chatbot_manager
    
    st.success("Chat session has been reset!")

# Function to handle message sending and processing
def process_message():
    # Get message from session state
    user_message = st.session_state.user_message
    
    if not user_message:
        return
        
    # Add user message to chat history
    st.session_state.chat_history.append({"role": "user", "content": user_message})
    
    # Clear the input box BEFORE processing (this is key to fixing the StreamlitAPIException)
    # We store the message temporarily and clear the input right away
    temp_message = user_message
    st.session_state.user_message = ""
    
    # Process message via API or directly
    api_mode = st.session_state.get("api_mode", False)
    
    with st.spinner("Assistant is thinking..."):
        if api_mode:
            response = send_chat_message_api(temp_message)
        else:
            response = send_chat_message_direct(temp_message)
    
    if response.get("status") == "success":
        assistant_message = response.get("response", "No response")
        # Add assistant message to chat history
        st.session_state.chat_history.append({"role": "assistant", "content": assistant_message})
    else:
        error_message = response.get('error', 'Unknown error')
        st.error(f"Error: {error_message}")
        # Add error message to chat history so user knows what happened
        st.session_state.chat_history.append({"role": "assistant", "content": f"I encountered an error: {error_message}. Please try again."})

# Streamlit interface
st.title("Equipment Schedule Agent")

# Sidebar for configuration and tools
with st.sidebar:
    st.header("Configuration")
    
    # Environment setup section
    st.subheader("Environment Setup")
    if st.button("Test Database Connection"):
        st.info(test_db_connection())
    
    if st.button("Test Azure AI Settings"):
        st.info(test_azure_settings())
    
    # Debugging info
    st.subheader("Debug Info")
    st.write(f"Session ID: {st.session_state.session_id}")
    
    # Run as API option
    st.subheader("API Mode")
    st.session_state.api_mode = st.checkbox("Use API Mode", value=False)
    if st.session_state.api_mode:
        st.warning("You'll need to run the API server separately:")
        st.code("python main.py", language="bash")
    
    # Divider
    st.divider()
    
    # Chat management
    st.subheader("Chat Management")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Clear Chat History"):
            st.session_state.chat_history = []
            st.success("Chat history cleared!")
    with col2:
        if st.button("Reset Chat Session"):
            reset_chat_session()
            
    st.caption("Reset Chat Session will create a new session ID and clean up resources.")

# Create tabs for different functionalities
tab1, tab2, tab3, tab4 = st.tabs(["Chat", "Schedule Analysis", "System Status", "Thinking Logs"])

# Tab 1: Chat Interface
with tab1:
    st.header("Chat with Equipment Assistant")
    
    # Display chat history
    for message in st.session_state.chat_history:
        if message["role"] == "user":
            st.markdown(f"**You:** {message['content']}")
        else:
            st.markdown(f"**Assistant:** {message['content']}")
    
    # Input for new message with on_change callback
    user_message = st.text_input("Type your message here:", key="user_message", on_change=process_message)
    
    # Optional send button (the text_input will also trigger on Enter)
    if st.button("Send", key="send_button"):
        if st.session_state.user_message:  # Only process if there's text
            process_message()

# Tab 2: Schedule Analysis
with tab2:
    st.header("Equipment Schedule Analysis")
    
    # Button to run analysis
    if st.button("Run Analysis Now"):
        # Run analysis via API or directly
        with st.spinner("Running schedule analysis..."):
            if st.session_state.get("api_mode", False):
                try:
                    response = requests.post("http://localhost:8000/workflow/run", timeout=120)
                    st.session_state.workflow_results = response.json()
                except Exception as e:
                    st.error(f"API Error: {str(e)}")
            else:
                st.session_state.workflow_results = run_workflow_directly()
    
    # Display results if available
    if st.session_state.workflow_results:
        if st.session_state.workflow_results.get("status") == "success":
            st.success("Analysis completed successfully!")
            
            report = st.session_state.workflow_results.get("report", "")
            # Remove the agent prefix if it exists
            if report.startswith("REPORTING_AGENT > "):
                report = report[18:]
            
            st.markdown("## Analysis Report")
            st.markdown(report)
            
            st.markdown("## Run Details")
            st.json({
                "workflow_run_id": st.session_state.workflow_results.get("workflow_run_id"),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        else:
            st.error(f"Analysis failed: {st.session_state.workflow_results.get('error', 'Unknown error')}")

# Tab 3: System Status
with tab3:
    st.header("System Status")
    
    # Environment variables status
    st.subheader("Environment Variables")
    env_vars = [
        "DB_CONNECTION_STRING", 
        "AZURE_AI_AGENT_PROJECT_NAME",
        "AZURE_AI_AGENT_PROJECT_CONNECTION_STRING", 
        "AZURE_AI_AGENT_MODEL_DEPLOYMENT_NAME"
    ]
    
    env_status = {}
    for var in env_vars:
        value = os.getenv(var)
        if value:
            # Mask sensitive info
            if "CONNECTION_STRING" in var or "KEY" in var:
                masked = value[:5] + "..." + value[-5:] if len(value) > 10 else "***"
                env_status[var] = f"Set: {masked}"
            else:
                env_status[var] = f"Set: {value}"
        else:
            env_status[var] = "Not set"
    
    for var, status in env_status.items():
        st.text(f"{var}: {status}")
    
    # System info
    st.subheader("System Information")
    st.text(f"Python Version: {sys.version}")
    st.text(f"Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if modules_imported:
        st.text("Modules: Loaded successfully")
    else:
        st.text("Modules: Not loaded directly")
    
    # Database query test
    if st.button("Test Database Query"):
        connection_string = os.getenv("DB_CONNECTION_STRING")
        if not connection_string:
            st.error("DB_CONNECTION_STRING environment variable not set")
        else:
            try:
                conn = pyodbc.connect(connection_string)
                cursor = conn.cursor()
                
                # Try to query the project table
                cursor.execute("SELECT TOP 5 * FROM dim_project")
                
                # Fetch results
                columns = [column[0] for column in cursor.description]
                rows = cursor.fetchall()
                
                # Convert to dataframe
                df = pd.DataFrame.from_records(rows, columns=columns)
                
                # Close connection
                cursor.close()
                conn.close()
                
                # Display results
                st.success("Query successful!")
                st.dataframe(df)
                
            except Exception as e:
                st.error(f"Database query failed: {str(e)}")

    # Add this to your streamlit_app.py in the System Status tab
    if "workflow_results" in st.session_state and st.session_state.workflow_results:
        workflow_run_id = st.session_state.workflow_results.get("workflow_run_id")
        if workflow_run_id and st.button("View Agent Thinking Logs"):
            from plugins.schedule_plugin import EquipmentSchedulePlugin
            connection_string = os.getenv("DB_CONNECTION_STRING")
            plugin = EquipmentSchedulePlugin(connection_string)
            logs_json = plugin.get_agent_thinking_logs(workflow_run_id)
            logs = json.loads(logs_json)
            
            if logs:
                st.subheader("Agent Thinking Logs")
                for log in logs:
                    with st.expander(f"{log['agent_name']} - {log['thinking_stage']} ({log['created_date']})"):
                        st.write(log['thought_content'])
            else:
                st.info("No thinking logs found for this run")

# Tab 4: Thinking Logs
with tab4:
    # Import and render the thinking log viewer
    from utils.thinking_log_viewer import render_thinking_log_viewer
    render_thinking_log_viewer()

# Footer
st.divider()
st.caption("Equipment Schedule Agent v1.0 | Built with Streamlit and Semantic Kernel")

# Add session cleanup function
def cleanup_resources():
    """Clean up any resources when the app is done."""
    if "chatbot_manager" in st.session_state:
        chatbot_manager = st.session_state.chatbot_manager
        if hasattr(chatbot_manager, "cleanup_sessions") and callable(chatbot_manager.cleanup_sessions):
            # Apply nest_asyncio to allow running asyncio in Streamlit
            nest_asyncio.apply()
            # Run the cleanup
            loop = asyncio.get_event_loop()
            loop.run_until_complete(chatbot_manager.cleanup_sessions(max_age_minutes=0))
            print("Cleaned up chat sessions")


# Main entry point
if __name__ == "__main__":
    # Register the cleanup function to run when Streamlit is done
    import atexit
    atexit.register(cleanup_resources)
