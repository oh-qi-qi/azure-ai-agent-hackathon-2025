"""FastAPI server for the equipment schedule agent."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import asyncio
import os
import dotenv
import uuid
from typing import Optional, Dict, List
from datetime import datetime
import pyodbc
import json

# Load environment variables
dotenv.load_dotenv()

# Try to import modules from our application
try:
    from config.settings import get_database_connection_string
    from managers.chatbot_manager import ChatbotManager

    modules_imported = True
except ImportError as e:
    modules_imported = False
    print(f"Import error: {e}")

app = FastAPI(title="Equipment Schedule Agent API")

# Store active chatbot managers
active_managers: Dict[str, ChatbotManager] = {}


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str


class ChatResponse(BaseModel):
    status: str
    response: Optional[str] = None
    error: Optional[str] = None
    session_id: str


class SessionResponse(BaseModel):
    session_id: str
    conversations: List[dict]


class SessionIdResponse(BaseModel):
    session_id: str
    user_query: str
    session_date: str


class ThinkingLogResponse(BaseModel):
    session_id: str
    conversations: List[dict]


class ThinkingLogIdResponse(BaseModel):
    session_id: str
    first_query: Optional[str] = None


class HeatmapResponse(BaseModel):
    datetime_stamp: str
    conversation_id: str
    session_id: str
    country: str
    average_risk: str
    breakdown: str = ""


class ReportResponse(BaseModel):
    session_id: str
    blob_url: str
    filename: str
    report_type: str
    created_date: str


def get_chatbot_manager(session_id: str) -> ChatbotManager:
    """Get or create a ChatbotManager for the session."""
    if session_id not in active_managers:
        if modules_imported:
            connection_string = get_database_connection_string()
        else:
            connection_string = os.getenv("DB_CONNECTION_STRING")
            if not connection_string:
                raise HTTPException(
                    status_code=500, detail="DB_CONNECTION_STRING not set"
                )

        active_managers[session_id] = ChatbotManager(connection_string)

    return active_managers[session_id]


def validate_session(session_id: str) -> bool:
    """Validate if a session exists and is still active."""
    if not session_id:
        return False

    # Check if session exists in active managers
    if session_id not in active_managers:
        return False

    return True


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        session_id = request.session_id or str(uuid.uuid4())

        # Validate existing session
        if request.session_id and not validate_session(session_id):
            # Session expired or invalid, create new session
            session_id = str(uuid.uuid4())

        # Get or create chatbot manager
        chatbot_manager = get_chatbot_manager(session_id)

        # Process the message
        try:
            response = await asyncio.wait_for(
                chatbot_manager.process_message(session_id, request.message),
                timeout=300,
            )

            if response.get("status") == "error":
                raise HTTPException(
                    status_code=500,
                    detail=response.get("error", "Unknown error occurred"),
                )

            return ChatResponse(
                status="success",
                response=response.get("response"),
                session_id=session_id,  # Always return session_id for continuity
            )

        except asyncio.TimeoutError:
            # Clean up the timed-out session
            if session_id in active_managers:
                del active_managers[session_id]

            raise HTTPException(
                status_code=504,
                detail="Request timed out. Please try a simpler request or wait a moment before retrying.",
            )

    except Exception as e:
        # Clean up the session on error
        if session_id in active_managers:
            del active_managers[session_id]

        raise HTTPException(
            status_code=500, detail=f"Error processing chat request: {str(e)}"
        )


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup resources when shutting down."""
    for manager in active_managers.values():
        if hasattr(manager, "cleanup_sessions"):
            await manager.cleanup_sessions(max_age_minutes=0)
    active_managers.clear()


@app.get("/api/sessions", response_model=List[SessionResponse])
async def get_sessions():
    try:
        # Get connection string from environment or chatbot manager
        if modules_imported:
            connection_string = get_database_connection_string()
        else:
            connection_string = os.getenv("DB_CONNECTION_STRING")
            if not connection_string:
                raise HTTPException(
                    status_code=500,
                    detail="DB_CONNECTION_STRING environment variable not set",
                )

        # Test connection first
        try:
            conn = pyodbc.connect(connection_string)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            conn.close()
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Database connection test failed: {str(e)}"
            )

        # Execute the actual query
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()

        query = """
            SELECT
                session_id,
                (
                    SELECT (
                        SELECT
                            conversation_id,
                            MAX(event_time) as last_interaction,
                            (
                                SELECT (
                                    SELECT
                                        CONVERT(varchar(50), event_time, 127) as event_time,
                                        user_query,
                                        agent_output,
                                        action
                                    FROM dim_agent_event_log AS messages
                                    WHERE messages.conversation_id = convs.conversation_id
                                    ORDER BY event_time
                                    FOR JSON PATH
                                )
                            ) as messages
                        FROM dim_agent_event_log AS convs
                        WHERE convs.session_id = sessions.session_id
                        GROUP BY conversation_id
                        FOR JSON PATH
                    )
                ) as conversations
            FROM dim_agent_event_log AS sessions
            GROUP BY session_id
            ORDER BY MAX(created_date) DESC
        """

        cursor.execute(query)
        rows = cursor.fetchall()

        # Format results
        results = []
        for row in rows:
            # Parse the JSON string into a Python list
            conversations = json.loads(row[1]) if row[1] else []

            results.append(
                SessionResponse(session_id=row[0], conversations=conversations)
            )

        cursor.close()
        conn.close()

        return results

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving sessions: {str(e)}"
        )


@app.get("/api/session-ids", response_model=List[SessionIdResponse])
async def get_session_ids():
    try:
        # Get connection string from environment or chatbot manager
        if modules_imported:
            connection_string = get_database_connection_string()
        else:
            connection_string = os.getenv("DB_CONNECTION_STRING")
            if not connection_string:
                raise HTTPException(
                    status_code=500,
                    detail="DB_CONNECTION_STRING environment variable not set",
                )

        # Execute the query
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()

        query = """
            WITH SessionData AS (
                SELECT DISTINCT
                    session_id,
                    FIRST_VALUE(user_query) OVER (PARTITION BY session_id ORDER BY event_time) as first_query,
                    FORMAT(MIN(event_time) OVER (PARTITION BY session_id) AT TIME ZONE 'UTC' AT TIME ZONE 'Singapore Standard Time', 'dd MMM yyyy hh:mm:ss tt') as session_date,
                    MIN(event_time) OVER (PARTITION BY session_id) as order_date
                FROM dim_agent_event_log
                WHERE user_query IS NOT NULL
            )
            SELECT
                session_id,
                first_query,
                session_date
            FROM SessionData
            ORDER BY order_date DESC
        """

        cursor.execute(query)
        rows = cursor.fetchall()

        # Format results
        results = [
            SessionIdResponse(
                session_id=row[0],
                user_query=row[1] if row[1] else "",
                session_date=row[2] if row[2] else "",
            )
            for row in rows
        ]

        cursor.close()
        conn.close()

        return results

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving session IDs: {str(e)}"
        )


@app.get("/api/thinking-logs", response_model=List[ThinkingLogResponse])
async def get_thinking_logs():
    try:
        # Get connection string
        if modules_imported:
            connection_string = get_database_connection_string()
        else:
            connection_string = os.getenv("DB_CONNECTION_STRING")
            if not connection_string:
                raise HTTPException(
                    status_code=500,
                    detail="DB_CONNECTION_STRING environment variable not set",
                )

        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()

        query = """
            WITH OrderedThoughts AS (
                SELECT
                    session_id,
                    conversation_id,
                    user_query,
                    agent_name,
                    thought_content,
                    thinking_stage,
                    thinking_stage_output,
                    created_date,
                    ROW_NUMBER() OVER (PARTITION BY conversation_id, agent_name ORDER BY created_date ASC) as thought_order,
                    FIRST_VALUE(created_date) OVER (PARTITION BY conversation_id, agent_name ORDER BY created_date ASC) as first_appearance
                FROM dim_agent_thinking_log
            )
            SELECT
                session_id,
                (
                    SELECT (
                        SELECT DISTINCT
                            t1.conversation_id,
                            MAX(t1.user_query) as user_query,
                            (
                                SELECT (
                                    SELECT DISTINCT
                                        t2.agent_name,
                                        t2.first_appearance,
                                        (
                                            SELECT (
                                                SELECT
                                                    t3.thought_content,
                                                    t3.thinking_stage,
                                                    t3.thinking_stage_output,
                                                    FORMAT(t3.created_date AT TIME ZONE 'UTC' AT TIME ZONE 'Singapore Standard Time', 'dd MMM yyyy hh:mm:ss tt') as created_date
                                                FROM OrderedThoughts t3
                                                WHERE t3.conversation_id = t1.conversation_id
                                                    AND t3.agent_name = t2.agent_name
                                                ORDER BY t3.thought_order
                                                FOR JSON PATH
                                            )
                                        ) as thoughts
                                    FROM OrderedThoughts t2
                                    WHERE t2.conversation_id = t1.conversation_id
                                    GROUP BY t2.agent_name, t2.first_appearance
                                    ORDER BY t2.first_appearance
                                    FOR JSON PATH
                                )
                            ) as agents
                        FROM OrderedThoughts t1
                        WHERE t1.session_id = sessions.session_id
                        GROUP BY t1.conversation_id
                        FOR JSON PATH
                    )
                ) as conversations
            FROM OrderedThoughts sessions
            WHERE session_id = ?
            GROUP BY session_id
        """

        cursor.execute(query)
        rows = cursor.fetchall()

        results = []
        for row in rows:
            conversations = json.loads(row[1]) if row[1] else []
            results.append(
                ThinkingLogResponse(session_id=row[0], conversations=conversations)
            )

        cursor.close()
        conn.close()

        return results

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving thinking logs: {str(e)}"
        )


@app.get("/api/thinking-log-ids", response_model=List[ThinkingLogIdResponse])
async def get_thinking_log_ids():
    try:
        # Get connection string
        if modules_imported:
            connection_string = get_database_connection_string()
        else:
            connection_string = os.getenv("DB_CONNECTION_STRING")
            if not connection_string:
                raise HTTPException(
                    status_code=500,
                    detail="DB_CONNECTION_STRING environment variable not set",
                )

        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()

        query = """
            WITH FirstQueries AS (
                SELECT
                    session_id,
                    FIRST_VALUE(user_query) OVER (PARTITION BY session_id ORDER BY created_date) as first_query
                FROM dim_agent_thinking_log
                WHERE user_query IS NOT NULL
            )
            SELECT DISTINCT t.session_id, fq.first_query
            FROM dim_agent_thinking_log t
            LEFT JOIN FirstQueries fq ON t.session_id = fq.session_id
            ORDER BY t.session_id DESC
        """

        cursor.execute(query)
        rows = cursor.fetchall()

        results = [
            ThinkingLogIdResponse(
                session_id=row[0], first_query=row[1] if row[1] else None
            )
            for row in rows
        ]

        cursor.close()
        conn.close()

        return results

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving thinking log IDs: {str(e)}"
        )


@app.get(
    "/api/thinking-logs-by-session-id/{session_id}", response_model=ThinkingLogResponse
)
async def get_thinking_log_by_session(session_id: str):
    try:
        # Get connection string
        if modules_imported:
            connection_string = get_database_connection_string()
        else:
            connection_string = os.getenv("DB_CONNECTION_STRING")
            if not connection_string:
                raise HTTPException(
                    status_code=500,
                    detail="DB_CONNECTION_STRING environment variable not set",
                )

        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()

        query = """
            WITH OrderedThoughts AS (
                SELECT
                    session_id,
                    conversation_id,
                    user_query,
                    agent_name,
                    thought_content,
                    thinking_stage,
                    thinking_stage_output,
                    created_date,
                    ROW_NUMBER() OVER (PARTITION BY conversation_id, agent_name ORDER BY created_date ASC) as thought_order,
                    FIRST_VALUE(created_date) OVER (PARTITION BY conversation_id, agent_name ORDER BY created_date ASC) as first_appearance
                FROM dim_agent_thinking_log
            )
            SELECT
                session_id,
                (
                    SELECT (
                        SELECT DISTINCT
                            t1.conversation_id,
                            MAX(t1.user_query) as user_query,
                            (
                                SELECT (
                                    SELECT DISTINCT
                                        t2.agent_name,
                                        t2.first_appearance,
                                        (
                                            SELECT (
                                                SELECT
                                                    t3.thought_content,
                                                    t3.thinking_stage,
                                                    t3.thinking_stage_output,
                                                    FORMAT(t3.created_date AT TIME ZONE 'UTC' AT TIME ZONE 'Singapore Standard Time', 'dd MMM yyyy hh:mm:ss tt') as created_date
                                                FROM OrderedThoughts t3
                                                WHERE t3.conversation_id = t1.conversation_id
                                                    AND t3.agent_name = t2.agent_name
                                                ORDER BY t3.thought_order
                                                FOR JSON PATH
                                            )
                                        ) as thoughts
                                    FROM OrderedThoughts t2
                                    WHERE t2.conversation_id = t1.conversation_id
                                    GROUP BY t2.agent_name, t2.first_appearance
                                    ORDER BY t2.first_appearance
                                    FOR JSON PATH
                                )
                            ) as agents
                        FROM OrderedThoughts t1
                        WHERE t1.session_id = sessions.session_id
                        GROUP BY t1.conversation_id
                        FOR JSON PATH
                    )
                ) as conversations
            FROM OrderedThoughts sessions
            WHERE session_id = ?
            GROUP BY session_id
        """

        cursor.execute(query, session_id)
        row = cursor.fetchone()

        if not row:
            # Return empty conversations array instead of 404
            return ThinkingLogResponse(session_id=session_id, conversations=[])

        conversations = json.loads(row[1]) if row[1] else []
        result = ThinkingLogResponse(session_id=row[0], conversations=conversations)

        cursor.close()
        conn.close()

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving thinking log: {str(e)}"
        )


@app.get("/api/sessions/{session_id}", response_model=SessionResponse)
async def get_session_by_id(session_id: str):
    try:
        # Get connection string from environment or chatbot manager
        if modules_imported:
            connection_string = get_database_connection_string()
        else:
            connection_string = os.getenv("DB_CONNECTION_STRING")
            if not connection_string:
                raise HTTPException(
                    status_code=500,
                    detail="DB_CONNECTION_STRING environment variable not set",
                )

        # Execute the query
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()

        query = """
            SELECT
                session_id,
                (
                    SELECT (
                        SELECT
                            conversation_id,
                            MAX(event_time) as last_interaction,
                            (
                                SELECT (
                                    SELECT
                                        CONVERT(varchar(50), event_time, 127) as event_time,
                                        user_query,
                                        agent_output,
                                        agent_name,
                                        action
                                    FROM dim_agent_event_log AS messages
                                    WHERE messages.conversation_id = convs.conversation_id
                                    ORDER BY event_time
                                    FOR JSON PATH
                                )
                            ) as messages
                        FROM dim_agent_event_log AS convs
                        WHERE convs.session_id = sessions.session_id
                        GROUP BY conversation_id
                        FOR JSON PATH
                    )
                ) as conversations
            FROM dim_agent_event_log AS sessions
            WHERE session_id = ?
            GROUP BY session_id
        """

        cursor.execute(query, session_id)
        row = cursor.fetchone()

        if not row:
            raise HTTPException(
                status_code=404, detail=f"Session not found with ID: {session_id}"
            )

        # Parse the JSON string into a Python list
        conversations = json.loads(row[1]) if row[1] else []
        result = SessionResponse(session_id=row[0], conversations=conversations)

        cursor.close()
        conn.close()

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving session: {str(e)}"
        )


@app.get("/api/heatmap", response_model=List[HeatmapResponse])
async def get_heatmap_data(conversation_id: str, session_id: str):
    try:
        # Get connection string
        if modules_imported:
            connection_string = get_database_connection_string()
        else:
            connection_string = os.getenv("DB_CONNECTION_STRING")
            if not connection_string:
                raise HTTPException(
                    status_code=500,
                    detail="DB_CONNECTION_STRING environment variable not set",
                )

        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()

        # Execute the stored procedure
        cursor.execute(
            "EXEC [dbo].[GetCountryRiskHeatmapData] @ConversationId = ?, @SessionId = ?",
            conversation_id,
            session_id,
        )

        rows = cursor.fetchall()

        # Format results with snake_case structure
        results = [
            HeatmapResponse(
                datetime_stamp=datetime.now().isoformat(),
                conversation_id=conversation_id,
                session_id=session_id,
                country=row.Country,
                average_risk=str(round(float(row.Average_Risk))),
                breakdown=row.Breakdown,
            )
            for row in rows
        ]

        cursor.close()
        conn.close()

        return results

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving heatmap data: {str(e)}"
        )


@app.get("/api/reports", response_model=List[ReportResponse])
async def get_reports():
    try:
        # Get connection string
        if modules_imported:
            connection_string = get_database_connection_string()
        else:
            connection_string = os.getenv("DB_CONNECTION_STRING")
            if not connection_string:
                raise HTTPException(
                    status_code=500,
                    detail="DB_CONNECTION_STRING environment variable not set",
                )

        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()

        query = """
            SELECT
                session_id,
                blob_url,
                filename,
                report_type,
                FORMAT(created_date AT TIME ZONE 'UTC' AT TIME ZONE 'Singapore Standard Time', 'dd MMM yyyy hh:mm:ss tt') as created_date
            FROM fact_risk_report
            ORDER BY created_date DESC
        """

        cursor.execute(query)
        rows = cursor.fetchall()

        results = [
            ReportResponse(
                session_id=row[0],
                blob_url=row[1],
                filename=row[2],
                report_type=row[3],
                created_date=row[4],
            )
            for row in rows
        ]

        cursor.close()
        conn.close()

        return results

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving reports: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
