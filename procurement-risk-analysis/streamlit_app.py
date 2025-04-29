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
import re
from plugins.report_file_plugin import ReportFilePlugin

# Load environment variables
dotenv.load_dotenv()

# Try to import modules from our application
try:
    from config.settings import get_database_connection_string
    from managers.chatbot_manager import ChatbotManager
    from managers.scheduler import WorkflowScheduler
    modules_imported = True
except ImportError as e:
    modules_imported = False
    print(f"Import error: {e}")
    print(f"Python path: {sys.path}")
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
    """Load the chatbot module dynamically with improved error handling."""
    if modules_imported:
        try:
            connection_string = get_database_connection_string()
            return ChatbotManager(connection_string)
        except Exception as e:
            st.error(f"Failed to load ChatbotManager normally: {e}")
            # Fall back to dynamic loading
    
    # Try to import the module dynamically
    try:
        spec = importlib.util.spec_from_file_location("managers.chatbot_manager", "managers/chatbot_manager.py")
        if spec is None:
            st.error("Could not find chatbot_manager.py in managers directory")
            return None
            
        chatbot_module = importlib.util.module_from_spec(spec)
        if chatbot_module is None:
            st.error("Failed to create module from spec")
            return None
            
        try:
            spec.loader.exec_module(chatbot_module)
        except Exception as e:
            st.error(f"Failed to execute chatbot module: {e}")
            return None
        
        connection_string = os.getenv("DB_CONNECTION_STRING")
        if not connection_string:
            st.error("DB_CONNECTION_STRING environment variable not set")
            return None
            
        # Try to instantiate the ChatbotManager
        try:
            return chatbot_module.ChatbotManager(connection_string)
        except Exception as e:
            st.error(f"Failed to instantiate ChatbotManager: {e}")
            return None
            
    except Exception as e:
        st.error(f"Could not load chatbot module: {e}")
        import traceback
        traceback.print_exc()
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
    """Send a chat message directly without using the API."""
    try:
        chatbot_manager = load_chatbot_module()
        if chatbot_manager:
            # Store the chatbot manager in session state for cleanup later
            if "chatbot_manager" not in st.session_state:
                st.session_state.chatbot_manager = chatbot_manager
            
            # Apply nest_asyncio to allow running asyncio in Streamlit
            nest_asyncio.apply()
            
            # Process the message with a timeout
            try:
                # Create a new event loop if needed
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError as e:
                    if str(e).startswith('There is no current event loop'):
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    else:
                        raise
                
                # Set a timeout for the message processing
                future = asyncio.ensure_future(
                    chatbot_manager.process_message(st.session_state.session_id, message)
                )
                
                # Wait for the result with a timeout
                try:
                    response = loop.run_until_complete(
                        asyncio.wait_for(future, timeout=300)  # 5 minute timeout
                    )
                except asyncio.TimeoutError:
                    st.warning("The request timed out after 5 minutes. The agent might be processing complex requests or experiencing high load.")
                    # Generate a new session ID to force session recreation
                    st.session_state.session_id = str(uuid.uuid4())
                    return {
                        "status": "error",
                        "error": "Request timed out. Please try a simpler request or wait a moment before retrying."
                    }
                
                # Check if the error is a timeout
                if response.get("status") == "error" and ("timed out" in response.get("error", "").lower() or 
                                                         "timeout" in response.get("error", "").lower()):
                    st.warning("The request timed out. This might be due to complex processing. Please try a simpler request or wait a moment before retrying.")
                    # Generate a new session ID to force session recreation
                    st.session_state.session_id = str(uuid.uuid4())
                
                return response
                
            except Exception as e:
                st.error(f"Error processing message: {str(e)}")
                import traceback
                traceback.print_exc()
                
                # If the session is corrupted, create a new one
                if "Rate limit is exceeded" in str(e) or "timed out" in str(e).lower() or "Polling timed out" in str(e):
                    st.warning("The agent encountered issues. Creating a new session...")
                    # Generate a new session ID to force session recreation
                    st.session_state.session_id = str(uuid.uuid4())
                
                return {
                    "status": "error", 
                    "error": f"Error: {str(e)}. Please try again in a moment."
                }
        else:
            st.error("Could not load chatbot manager. Please check your environment and module installation.")
            return {"status": "error", "error": "Could not load chatbot manager"}
    except Exception as e:
        st.error(f"Failed to process message: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": f"System error: {str(e)}"}


# Add a function to reset the chat session if needed
def reset_chat_session():
    """Reset the chat session and clean up resources."""
    
    # Store the old session ID for cleanup
    old_session_id = st.session_state.session_id
    
    # Generate a new session ID
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.chat_history = []
    
    # Clean up any existing chatbot manager
    if "chatbot_manager" in st.session_state:
        try:
            chatbot_manager = st.session_state.chatbot_manager
            
            # Apply nest_asyncio to allow running asyncio in Streamlit
            import nest_asyncio
            nest_asyncio.apply()
            
            # Create a new event loop if needed
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Run the cleanup for the specific session
            if old_session_id:
                try:
                    print(f"Cleaning up old session {old_session_id}")
                    future = chatbot_manager.close_session(old_session_id)
                    loop.run_until_complete(asyncio.wait_for(future, timeout=10))
                    print(f"Successfully cleaned up session {old_session_id}")
                except Exception as e:
                    print(f"Error cleaning up session {old_session_id}: {e}")
                    import traceback
                    traceback.print_exc()
        except Exception as e:
            print(f"Error during chatbot manager cleanup: {e}")
            import traceback
            traceback.print_exc()
        
        # Remove the chatbot manager from session state
        del st.session_state.chatbot_manager
    
    # Remove any other session-specific state
    for key in list(st.session_state.keys()):
        if key.startswith("cache_") or key.startswith("temp_"):
            del st.session_state[key]
    
    st.success("Chat session has been reset!")

# Function to handle message sending and processing
def process_message():
    # Get message from session state
    user_message = st.session_state.user_message
    
    if not user_message:
        return
        
    # Add user message to chat history
    st.session_state.chat_history.append({"role": "user", "content": user_message})
    
    # Clear the input box BEFORE processing
    temp_message = user_message
    st.session_state.user_message = ""
    
    # Process message via API or directly
    api_mode = st.session_state.get("api_mode", False)
    
    with st.spinner("Assistant is thinking..."):
        try:
            if api_mode:
                response = send_chat_message_api(temp_message)
            else:
                response = send_chat_message_direct(temp_message)
                
            if response.get("status") == "success":
                assistant_message = response.get("response", "No response")
                # Add assistant message to chat history
                st.session_state.chat_history.append({"role": "assistant", "content": assistant_message})
                
                # Store conversation_id in session state if available
                if response.get("conversation_id"):
                    st.session_state.conversation_id = response["conversation_id"]
            elif response.get("status") == "error":
                error_message = response.get('error', 'Unknown error')
                st.error(f"Error: {error_message}")
                # Add error message to chat history
                st.session_state.chat_history.append({"role": "assistant", "content": f"I encountered an error: {error_message}. Please try again."})
                
                # If certain kinds of errors occur, reset the session
                if "timeout" in error_message.lower() or "rate limit" in error_message.lower():
                    st.warning("Resetting chat session due to timeout or rate limit...")
                    reset_chat_session()
            else:
                st.warning("Received unexpected response status")
                st.session_state.chat_history.append({"role": "assistant", "content": "I received an unexpected response. Please try again."})
                
        except Exception as e:
            st.error(f"Unexpected error: {str(e)}")
            st.session_state.chat_history.append({"role": "assistant", "content": f"An unexpected error occurred: {str(e)}. Please try again."})
            
            # Log the error
            import traceback
            error_traceback = traceback.format_exc()
            print(f"Error in process_message: {error_traceback}")


def display_political_risk_citations(session_id=None):
    """Display political risk citations from the current session.
    
    Args:
        session_id: The session ID (optional, uses current session if not provided)
    """
    if not session_id:
        session_id = st.session_state.get("session_id")
        if not session_id:
            st.info("No active session")
            return
    
    # Get chatbot manager
    chatbot_manager = st.session_state.get("chatbot_manager")
    if not chatbot_manager or not hasattr(chatbot_manager, 'chat_sessions'):
        st.info("No active chat session")
        return
    
    # Get session data
    session = chatbot_manager.chat_sessions.get(session_id)
    if not session:
        st.info(f"Session {session_id} not found")
        return
    
    # Get citations
    citations = session.get('political_risk_citations', [])
    if not citations:
        st.info("No citations found for this session")
        return
    
    # Display citations
    st.subheader(f"Political Risk Citations ({len(citations)})")
    
    for i, citation in enumerate(citations):
        title = citation.get('title', 'Unknown Source')
        url = citation.get('url', '#')
        source = citation.get('source', 'Unknown')
        
        with st.expander(f"{i+1}. {title}"):
            st.write(f"**Source:** {source}")
            st.markdown(f"**URL:** [{url}]({url})")
            
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
tab1, tab2, tab3, tab4, tab5 = st.tabs(["Chat", "Schedule Analysis", "System Status", "Thinking Logs", "Reports"])

# Tab 1: Chat Interface
with tab1:
    st.header("Chat with Equipment Assistant")
    
    # Display chat history
    for message in st.session_state.chat_history:
        if message["role"] == "user":
            st.markdown(f"**You:** {message['content']}")
        else:
            assistant_content = message['content']
            
            # Check if the response contains report file information
            if "📄 Report Generated Successfully" in assistant_content:
                # Split the content to extract file information
                parts = assistant_content.split("📄 Report Generated Successfully")
                
                # Display the report content first
                st.markdown(f"**Assistant:** {parts[0]}")
                
                # Extract and display file information
                if len(parts) > 1:
                    file_info = parts[1].strip()
                    
                    # Extract the URL from the file information
                    url_match = re.search(r'Download URL: (.+)', file_info)
                    filename_match = re.search(r'Filename: (.+)', file_info)
                    
                    if url_match and filename_match:
                        url = url_match.group(1).strip()
                        filename = filename_match.group(1).strip()
                        
                        # Create a more visible download section
                        st.info("📄 Report Generated Successfully")
                        st.markdown(f"**Filename:** {filename}")
                        st.markdown(f"[🔗 Download Report]({url})")
                    else:
                        # Fallback to showing the raw file info
                        st.info(file_info)
            else:
                # Regular message display
                st.markdown(f"**Assistant:** {assistant_content}")
    
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

    # Updated section for viewing thinking logs
    if "workflow_results" in st.session_state and st.session_state.workflow_results:
        workflow_run_id = st.session_state.workflow_results.get("workflow_run_id")
        if workflow_run_id and st.button("View Agent Thinking Logs"):
            from plugins.logging_plugin import LoggingPlugin  # Updated import
            connection_string = os.getenv("DB_CONNECTION_STRING")
            logging_plugin = LoggingPlugin(connection_string)  # Use logging plugin instead of schedule plugin
            logs_json = logging_plugin.get_agent_thinking_logs(conversation_id=workflow_run_id)  # Updated method
            logs = json.loads(logs_json)
            
            if logs and not isinstance(logs, dict):  # Check if logs is list of dicts
                st.subheader("Agent Thinking Logs")
                for log in logs:
                    with st.expander(f"{log['agent_name']} - {log['thinking_stage']} ({log['created_date']})"):
                        st.write(log['thought_content'])
                        if log.get('agent_output'):  # Show agent output if available
                            st.markdown("**Agent Output:**")
                            st.code(log['agent_output'])
            else:
                st.info("No thinking logs found for this run")

# Tab 4: Thinking Logs
with tab4:
    # Import and render the thinking log viewer
    try:
        from utils.thinking_log_viewer import render_thinking_log_viewer
        render_thinking_log_viewer()
    except ImportError:
        st.error("Could not import thinking log viewer. Make sure utils/thinking_log_viewer.py exists.")
        
        # Provide a basic thinking logs viewer if import fails
        st.subheader("Agent Thinking Logs")
        
        # Add filters
        col1, col2, col3 = st.columns(3)
        with col1:
            conversation_id = st.text_input("Conversation ID (optional)")
        with col2:
            session_id = st.text_input("Session ID (optional)", 
                                      value=st.session_state.get("session_id", ""))
        with col3:
            agent_filter = st.selectbox("Agent", 
                                      ["All", "SCHEDULER_AGENT", "REPORTING_AGENT", "ASSISTANT_AGENT", "SYSTEM"])
        
        # View logs button
        if st.button("View Logs", key="view_logs_tab4"):
            try:
                # Use the logging plugin to get logs
                from plugins.logging_plugin import LoggingPlugin
                connection_string = os.getenv("DB_CONNECTION_STRING")
                logging_plugin = LoggingPlugin(connection_string)
                
                # Build query parameters
                agent_name = None if agent_filter == "All" else agent_filter
                
                # Get logs
                logs_json = logging_plugin.get_agent_thinking_logs(
                    conversation_id=conversation_id if conversation_id else None,
                    session_id=session_id if session_id else None,
                    agent_name=agent_name,
                    limit=1000
                )
                
                logs = json.loads(logs_json)
                
                if isinstance(logs, dict) and "error" in logs:
                    st.error(f"Error retrieving logs: {logs['error']}")
                elif logs:
                    st.write(f"Found {len(logs)} logs")
                    
                    # Display logs in an expandable format
                    for log in logs:
                        with st.expander(f"{log.get('agent_name', 'Unknown')} - {log.get('thinking_stage', 'Unknown')} - {log.get('created_date', 'Unknown date')}"):
                            # Show status indicator
                            status = log.get("status", "unknown")
                            if status == "success":
                                st.success(f"Status: {status}")
                            elif status == "error":
                                st.error(f"Status: {status}")
                            else:
                                st.info(f"Status: {status}")
                            
                            # Show key metadata
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write(f"**Conversation ID:** {log.get('conversation_id', 'N/A')}")
                                st.write(f"**Session ID:** {log.get('session_id', 'N/A')}")
                                st.write(f"**Thread ID:** {log.get('thread_id', 'N/A')}")
                            with col2:
                                st.write(f"**Agent ID:** {log.get('azure_agent_id', 'N/A')}")
                                st.write(f"**Model:** {log.get('model_deployment_name', 'N/A')}")
                                st.write(f"**Created:** {log.get('created_date', 'N/A')}")
                            
                            # Show user query if available
                            if log.get("user_query"):
                                st.write("**User Query:**")
                                st.info(log.get("user_query"))
                            
                            # Show thought content
                            st.write("**Thought Content:**")
                            st.write(log.get("thought_content", "No content"))
                            
                            # Show agent output if available
                            if log.get("agent_output"):
                                st.write("**Agent Output:**")
                                st.code(log.get("agent_output"))
                else:
                    st.info("No logs found")
                    
            except Exception as e:
                st.error(f"Error retrieving logs: {str(e)}")
                import traceback
                st.code(traceback.format_exc())

# Tab 5: Reports
with tab5:
    st.header("Report Management")
    
    # Show current session and conversation ID
    st.subheader("Current Session")
    st.text(f"Session ID: {st.session_state.session_id}")
    if st.session_state.get('conversation_id'):
        st.text(f"Conversation ID: {st.session_state.conversation_id}")
    
    st.divider()
    
    # Generate report from current conversation
    st.subheader("Generate Report")
    if st.button("Generate Report from Current Conversation"):
        if st.session_state.chat_history:
            with st.spinner("Generating report..."):
                try:
                    connection_string = os.getenv("DB_CONNECTION_STRING")
                    report_plugin = ReportFilePlugin(connection_string)
                    
                    # Generate report
                    result = report_plugin.generate_report_from_conversation(
                        conversation_id=st.session_state.get('conversation_id', str(uuid.uuid4())),
                        session_id=st.session_state.session_id
                    )
                    
                    result_data = json.loads(result)
                    if result_data.get("success"):
                        st.success("Report generated successfully!")
                        st.json({
                            "Filename": result_data["filename"],
                            "Download URL": result_data["blob_url"]
                        })
                    else:
                        st.error(f"Failed to generate report: {result_data.get('error')}")
                except Exception as e:
                    st.error(f"Error generating report: {str(e)}")
        else:
            st.warning("No conversation history to generate report from.")
    
    st.divider()
    
    # View existing reports
    st.subheader("View Reports")
    
    # Filter options
    col1, col2 = st.columns(2)
    with col1:
        filter_session_id = st.text_input("Filter by Session ID (optional)")
    with col2:
        filter_conversation_id = st.text_input("Filter by Conversation ID (optional)")
    
    if st.button("Search Reports"):
        with st.spinner("Fetching reports..."):
            try:
                connection_string = os.getenv("DB_CONNECTION_STRING")
                report_plugin = ReportFilePlugin(connection_string)
                
                # Get reports
                reports_json = report_plugin.get_reports(
                    session_id=filter_session_id if filter_session_id else None,
                    conversation_id=filter_conversation_id if filter_conversation_id else None
                )
                
                reports = json.loads(reports_json)
                
                if isinstance(reports, dict) and "error" in reports:
                    st.error(f"Error retrieving reports: {reports['error']}")
                elif reports:
                    # Display reports in a table
                    st.write(f"Found {len(reports)} reports")
                    
                    # Convert to DataFrame for display
                    df = pd.DataFrame(reports)
                    
                    # Add download buttons for each report
                    for index, row in df.iterrows():
                        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
                        with col1:
                            st.write(f"**{row['filename']}**")
                        with col2:
                            st.write(f"Created: {row['created_date']}")
                        with col3:
                            st.write(f"Type: {row['report_type']}")
                        with col4:
                            st.markdown(f"[Download]({row['blob_url']})")
                    
                    # Show full data table
                    st.subheader("Report Details")
                    st.dataframe(df)
                else:
                    st.info("No reports found")
                    
            except Exception as e:
                st.error(f"Error fetching reports: {str(e)}")
                import traceback
                st.code(traceback.format_exc())

# Footer
st.divider()
st.caption("Equipment Schedule Agent v1.0 | Built with Streamlit and Semantic Kernel")

# Add session cleanup function
def cleanup_resources():
    """Clean up any resources when the app is done."""
    print("Running cleanup_resources...")
    
    if "chatbot_manager" in st.session_state:
        chatbot_manager = st.session_state.chatbot_manager
        
        # For the main thread in Streamlit, we need to use nest_asyncio
        import nest_asyncio
        nest_asyncio.apply()
        
        # Get or create event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            # Get all active session IDs
            if hasattr(chatbot_manager, 'chat_sessions'):
                session_ids = list(chatbot_manager.chat_sessions.keys())
                
                # Run cleanup for each session synchronously
                for session_id in session_ids:
                    print(f"Cleaning up session {session_id}")
                    result = loop.run_until_complete(
                        chatbot_manager.close_session(session_id)
                    )
                    print(f"Session {session_id} cleanup result: {result}")
                    
            # Use the correct method name: cleanup_sessions instead of cleanup_all_sessions
            if hasattr(chatbot_manager, 'cleanup_sessions'):
                print("Running general cleanup_sessions with max_age_minutes=0")
                loop.run_until_complete(chatbot_manager.cleanup_sessions(max_age_minutes=0))
                    
        except Exception as e:
            print(f"Error during cleanup: {e}")
            import traceback
            traceback.print_exc()
                
        print("Resources cleaned up")
    else:
        print("No chatbot_manager in session state to clean up")

# Main entry point
if __name__ == "__main__":
    try:
        # Make sure asyncio is imported
        import asyncio
        
        # Apply nest_asyncio for safety
        import nest_asyncio
        nest_asyncio.apply()
        
        # Register the cleanup function to run when Streamlit is done
        import atexit
        atexit.register(cleanup_resources)
        
        # Only register signal handlers if we're in the main thread
        import threading
        if threading.current_thread() is threading.main_thread():
            import signal
            
            def signal_handler(sig, frame):
                print(f"Received signal {sig}, running cleanup...")
                # Create a new event loop if needed
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                cleanup_resources()
                sys.exit(0)
                
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
        else:
            print("Not in main thread, skipping signal handler registration")
            
    except Exception as e:
        print(f"Error setting up cleanup handlers: {e}")