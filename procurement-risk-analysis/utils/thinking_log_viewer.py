"""Streamlit component for viewing enhanced agent thinking logs."""

import streamlit as st
import pandas as pd
import json
import plotly.express as px
from datetime import datetime

def render_thinking_log_viewer():
    """Renders the thinking log viewer component in the Streamlit UI."""
    st.header("Agent Thinking Logs Viewer")
    
    # Create tabs for different views
    log_tab, thread_tab, stats_tab = st.tabs(["Thinking Logs", "Thread Analysis", "Stats & Metrics"])
    
    with log_tab:
        render_thinking_logs_tab()
    
    with thread_tab:
        render_thread_analysis_tab()
    
    with stats_tab:
        render_stats_tab()

def render_thinking_logs_tab():
    """Renders the thinking logs tab."""
    st.subheader("Agent Thinking Process")
    
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
    
    # Add a search box for thought content
    search_term = st.text_input("Search in thought content")
    
    # Add a date range filter
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", 
                                  datetime.now().replace(hour=0, minute=0, second=0, microsecond=0))
    with col2:
        end_date = st.date_input("End Date", 
                                datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999))
    
    # Add status filter
    status_filter = st.multiselect("Status", 
                                 ["success", "error", "rate_limited"], 
                                 default=["success", "error", "rate_limited"])
    
    # View logs button
    if st.button("View Logs"):
        try:
            # Use the logging plugin to get logs
            from plugins.logging_plugin import LoggingPlugin
            from config.settings import get_database_connection_string
            
            # Initialize the plugin
            connection_string = get_database_connection_string()
            logging_plugin = LoggingPlugin(connection_string)
            
            # Build query parameters
            agent_name = None if agent_filter == "All" else agent_filter
            
            # Get logs
            logs_json = logging_plugin.get_agent_thinking_logs(
                conversation_id=conversation_id if conversation_id else None,
                session_id=session_id if session_id else None,
                agent_name=agent_name,
                limit=1000  # Adjust as needed
            )
            
            logs = json.loads(logs_json)
            
            if isinstance(logs, dict) and "error" in logs:
                st.error(f"Error retrieving logs: {logs['error']}")
                return
            
            # Convert to DataFrame for easier filtering
            if logs:
                df = pd.DataFrame(logs)
                
                # Apply additional filters
                if not df.empty:
                    # Filter by search term
                    if search_term:
                        df = df[df["thought_content"].str.contains(search_term, case=False, na=False)]
                    
                    # Filter by date
                    if "created_date" in df.columns:
                        df["created_date"] = pd.to_datetime(df["created_date"])
                        start_datetime = pd.to_datetime(start_date)
                        end_datetime = pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
                        df = df[(df["created_date"] >= start_datetime) & (df["created_date"] <= end_datetime)]
                    
                    # Filter by status
                    if "status" in df.columns and status_filter:
                        df = df[df["status"].isin(status_filter)]
                    
                    # Sort by created_date
                    if "created_date" in df.columns:
                        df = df.sort_values("created_date", ascending=False)
                
                # Display the logs
                if df.empty:
                    st.info("No logs found matching the selected filters.")
                    return
                
                st.write(f"Found {len(df)} logs")
                
                # Add a download button
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "Download Logs as CSV",
                    csv,
                    "agent_thinking_logs.csv",
                    "text/csv",
                    key='download-csv'
                )
                
                # Display logs in an expandable format
                for i, row in df.iterrows():
                    with st.expander(f"{row.get('agent_name', 'Unknown')} - {row.get('thinking_stage', 'Unknown')} - {row.get('created_date', 'Unknown date')}"):
                        # Show status indicator
                        status = row.get("status", "unknown")
                        if status == "success":
                            st.success(f"Status: {status}")
                        elif status == "error":
                            st.error(f"Status: {status}")
                        elif status == "rate_limited":
                            st.warning(f"Status: {status}")
                        else:
                            st.info(f"Status: {status}")
                        
                        # Show key metadata
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**Conversation ID:** {row.get('conversation_id', 'N/A')}")
                            st.write(f"**Session ID:** {row.get('session_id', 'N/A')}")
                            st.write(f"**Thread ID:** {row.get('thread_id', 'N/A')}")
                        with col2:
                            st.write(f"**Agent ID:** {row.get('azure_agent_id', 'N/A')}")
                            st.write(f"**Model:** {row.get('model_deployment_name', 'N/A')}")
                            st.write(f"**Created:** {row.get('created_date', 'N/A')}")
                        
                        # Show user query if available
                        if row.get("user_query"):
                            st.write("**User Query:**")
                            st.info(row.get("user_query"))
                        
                        # Show thought content
                        st.write("**Thought Content:**")
                        st.write(row.get("thought_content", "No content"))
                        
                        # Show agent output if available
                        if row.get("agent_output"):
                            st.write("**Agent Output:**")
                            st.code(row.get("agent_output"))
            else:
                st.info("No logs found")
                
        except Exception as e:
            st.error(f"Error retrieving logs: {str(e)}")
            import traceback
            st.code(traceback.format_exc())

def render_thread_analysis_tab():
    """Renders the thread analysis tab."""
    st.subheader("Thread Analysis")
    
    # Add filters
    col1, col2 = st.columns(2)
    with col1:
        conversation_id = st.text_input("Conversation ID (optional)", key="thread_conversation_id")
    with col2:
        session_id = st.text_input("Session ID (optional)", 
                                  value=st.session_state.get("session_id", ""),
                                  key="thread_session_id")
    
    # Add a button to analyze threads
    if st.button("Analyze Threads"):
        try:
            # Import necessary modules
            from plugins.logging_plugin import LoggingPlugin
            from config.settings import get_database_connection_string
            
            # Initialize the plugin
            connection_string = get_database_connection_string()
            logging_plugin = LoggingPlugin(connection_string)
            
            # Get logs for analysis
            logs_json = logging_plugin.get_agent_thinking_logs(
                conversation_id=conversation_id if conversation_id else None,
                session_id=session_id if session_id else None,
                limit=5000
            )
            
            logs = json.loads(logs_json)
            
            if isinstance(logs, dict) and "error" in logs:
                st.error(f"Error retrieving logs: {logs['error']}")
                return
            
            if logs:
                df = pd.DataFrame(logs)
                
                # Analyze threads
                if "thread_id" in df.columns:
                    thread_stats = df.groupby("thread_id").agg({
                        "thinking_id": "count",
                        "agent_name": lambda x: list(x.unique()),
                        "created_date": ["min", "max"],
                        "status": lambda x: dict(x.value_counts()),
                        "conversation_id": lambda x: list(x.unique())
                    }).reset_index()
                    
                    st.write(f"Found {len(thread_stats)} unique threads")
                    
                    # Display thread information
                    for i, thread in thread_stats.iterrows():
                        with st.expander(f"Thread: {thread['thread_id']}"):
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write(f"**First seen:** {thread['created_date']['min']}")
                                st.write(f"**Thinking steps:** {thread['thinking_id']['count']}")
                                
                                status_counts = thread['status']['<lambda>']
                                errors = status_counts.get('error', 0)
                                st.write(f"**Errors:** {errors}")
                            with col2:
                                st.write(f"**Last seen:** {thread['created_date']['max']}")
                                st.write(f"**Conversations:** {len(thread['conversation_id']['<lambda>'])}")
                                st.write(f"**Agents:** {', '.join(thread['agent_name']['<lambda>'])}")
                            
                            # Display status breakdown
                            st.write("**Status breakdown:**")
                            status_df = pd.DataFrame.from_dict(status_counts, orient='index', columns=['Count'])
                            st.dataframe(status_df)
                            
                            # Display conversation IDs
                            st.write("**Conversation IDs:**")
                            for conv_id in thread['conversation_id']['<lambda>']:
                                st.code(conv_id)
                else:
                    st.info("No thread information available in the logs")
            else:
                st.info("No logs found")
        except Exception as e:
            st.error(f"Error analyzing threads: {str(e)}")
            import traceback
            st.code(traceback.format_exc())

def render_stats_tab():
    """Renders the stats and metrics tab."""
    st.subheader("Statistics & Metrics")
    
    try:
        # Query logs for statistics
        from plugins.logging_plugin import LoggingPlugin
        from config.settings import get_database_connection_string
        
        # Initialize the plugin
        connection_string = get_database_connection_string()
        logging_plugin = LoggingPlugin(connection_string)
        
        # Get all logs
        logs_json = logging_plugin.get_agent_thinking_logs(limit=5000)  # Adjust limit as needed
        logs = json.loads(logs_json)
        
        if isinstance(logs, dict) and "error" in logs:
            st.error(f"Error retrieving logs: {logs['error']}")
            return
            
        if not logs:
            st.info("No logs found")
            return
        
        # Convert to DataFrame
        df = pd.DataFrame(logs)
        
        # Convert created_date to datetime
        if "created_date" in df.columns:
            df["created_date"] = pd.to_datetime(df["created_date"])
        
        # Display key metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Thinking Steps", len(df))
        with col2:
            st.metric("Unique Conversations", df["conversation_id"].nunique())
        with col3:
            st.metric("Unique Sessions", df["session_id"].nunique())
        with col4:
            error_count = len(df[df["status"] == "error"]) if "status" in df.columns else 0
            st.metric("Errors", error_count)
        
        # Create visualizations
        
        # 1. Thinking steps by agent
        if "agent_name" in df.columns:
            agent_counts = df["agent_name"].value_counts().reset_index()
            agent_counts.columns = ["Agent", "Count"]
            
            fig1 = px.bar(agent_counts, x="Agent", y="Count", 
                         title="Thinking Steps by Agent",
                         color="Agent")
            st.plotly_chart(fig1)
        
        # 2. Thinking stages distribution
        if "thinking_stage" in df.columns:
            stage_counts = df["thinking_stage"].value_counts().reset_index()
            stage_counts.columns = ["Stage", "Count"]
            
            fig2 = px.pie(stage_counts, names="Stage", values="Count", 
                         title="Thinking Stages Distribution")
            st.plotly_chart(fig2)
        
        # 3. Status distribution
        if "status" in df.columns:
            status_counts = df["status"].value_counts().reset_index()
            status_counts.columns = ["Status", "Count"]
            
            fig3 = px.pie(status_counts, names="Status", values="Count", 
                         title="Status Distribution",
                         color="Status",
                         color_discrete_map={"success": "green", "error": "red", "rate_limited": "orange"})
            st.plotly_chart(fig3)
        
        # 4. Timeline of thinking steps
        if "created_date" in df.columns:
            # Resample by hour
            df.loc[:, "hour"] = df["created_date"].dt.floor("h")
            timeline = df.groupby("hour").size().reset_index()
            timeline.columns = ["Timestamp", "Count"]
            
            fig4 = px.line(timeline, x="Timestamp", y="Count", 
                          title="Timeline of Thinking Steps")
            st.plotly_chart(fig4)
        
        # 5. Errors over time
        if "created_date" in df.columns and "status" in df.columns:
            error_df = df[df["status"] == "error"]
            if not error_df.empty:
                error_df.loc[:, "hour"] = error_df["created_date"].dt.floor("h")
                error_timeline = error_df.groupby("hour").size().reset_index()
                error_timeline.columns = ["Timestamp", "Count"]
                
                fig5 = px.line(error_timeline, x="Timestamp", y="Count", 
                              title="Errors Over Time")
                st.plotly_chart(fig5)
            else:
                st.info("No errors recorded")
        
    except Exception as e:
        st.error(f"Error generating statistics: {str(e)}")
        import traceback
        st.code(traceback.format_exc())