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

# Import our agent implementation if it exists in the same directory
agent_module = None
try:
    # Assuming the agent implementation is in equipment_agent.py
    spec = importlib.util.spec_from_file_location("equipment_agent", "equipment_agent.py")
    agent_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent_module)
except Exception as e:
    st.error(f"Could not load agent module: {e}")

# Load environment variables
dotenv.load_dotenv()

# Initialize session state
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "workflow_results" not in st.session_state:
    st.session_state.workflow_results = None

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "api_running" not in st.session_state:
    st.session_state.api_running = False

# Function to directly run the workflow without API
def run_workflow_directly():
    if agent_module:
        # Apply nest_asyncio to allow running asyncio in Streamlit
        nest_asyncio.apply()
        
        # Create a workflow scheduler
        connection_string = os.getenv("DB_CONNECTION_STRING")
        if not connection_string:
            st.error("DB_CONNECTION_STRING environment variable not set")
            return None
            
        workflow_scheduler = agent_module.WorkflowScheduler(connection_string)
        
        # Run the workflow
        with st.spinner("Running workflow analysis..."):
            result = workflow_scheduler.run_now()
            return result
    else:
        st.error("Agent module not loaded. Make sure equipment_agent.py is in the same directory.")
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
            timeout=60
        )
        return response.json()
    except Exception as e:
        return {"status": "error", "error": str(e)}

# Function to send a chat message directly
def send_chat_message_direct(message):
    if agent_module:
        # Apply nest_asyncio to allow running asyncio in Streamlit
        nest_asyncio.apply()
        
        # Create a chatbot manager
        connection_string = os.getenv("DB_CONNECTION_STRING")
        if not connection_string:
            return {"status": "error", "error": "DB_CONNECTION_STRING environment variable not set"}
            
        chatbot_manager = agent_module.ChatbotManager(connection_string)
        
        # Process the message
        loop = asyncio.get_event_loop()
        response = loop.run_until_complete(
            chatbot_manager.process_message(st.session_state.session_id, message)
        )
        return response
    else:
        return {"status": "error", "error": "Agent module not loaded"}

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
    api_mode = st.checkbox("Use API Mode", value=False)
    if api_mode and not st.session_state.api_running:
        st.warning("You'll need to run the API server separately:")
        st.code("python equipment_agent.py", language="bash")
    
    # Divider
    st.divider()
    
    # Clear data
    if st.button("Clear Chat History"):
        st.session_state.chat_history = []
        st.success("Chat history cleared!")

# Create tabs for different functionalities
tab1, tab2, tab3 = st.tabs(["Chat", "Schedule Analysis", "System Status"])

# Tab 1: Chat Interface
with tab1:
    st.header("Chat with Equipment Assistant")
    
    # Display chat history
    for message in st.session_state.chat_history:
        if message["role"] == "user":
            st.markdown(f"**You:** {message['content']}")
        else:
            content = message["content"]
            # Remove the "ASSISTANT > " prefix if it exists
            if content.startswith("ASSISTANT > "):
                content = content[12:]
            st.markdown(f"**Assistant:** {content}")
    
    # Input for new message
    user_message = st.text_input("Type your message here:", key="user_message")
    
    if st.button("Send", key="send_button") and user_message:
        # Add user message to chat history
        st.session_state.chat_history.append({"role": "user", "content": user_message})
        
        # Display the message immediately
        st.markdown(f"**You:** {user_message}")
        
        # Process message via API or directly
        with st.spinner("Assistant is thinking..."):
            if api_mode:
                response = send_chat_message_api(user_message)
            else:
                response = send_chat_message_direct(user_message)
        
        if response.get("status") == "success":
            assistant_message = response.get("response", "No response")
            # Remove the "ASSISTANT > " prefix if it exists
            if assistant_message.startswith("ASSISTANT > "):
                assistant_message = assistant_message[12:]
            
            # Add assistant message to chat history
            st.session_state.chat_history.append({"role": "assistant", "content": assistant_message})
            
            # Display the message
            st.markdown(f"**Assistant:** {assistant_message}")
        else:
            st.error(f"Error: {response.get('error', 'Unknown error')}")
        
        # Clear the input box
        st.session_state.user_message = ""

# Tab 2: Schedule Analysis
with tab2:
    st.header("Equipment Schedule Analysis")
    
    # Button to run analysis
    if st.button("Run Analysis Now"):
        # Run analysis via API or directly
        with st.spinner("Running schedule analysis..."):
            if api_mode:
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
    
    if agent_module:
        st.text("Agent Module: Loaded successfully")
    else:
        st.text("Agent Module: Not loaded")
    
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

# Footer
st.divider()
st.caption("Equipment Schedule Agent v1.0 | Built with Streamlit and Semantic Kernel")
