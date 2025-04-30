# RiskWise Backend - Project Structure

The RiskWise backend is built on a modular, maintainable architecture that enables specialized AI agents to collaborate through a well-defined system. Here's a comprehensive overview of the project structure:

```
backend/
│
├── agents/                         # Agent-related code
│   ├── __init__.py                 # Re-exports key classes and functions
│   ├── agent_definitions.py        # Agent instructions and constants
│   ├── agent_strategies.py         # Selection and termination strategies
│   ├── agent_manager.py            # Agent creation and management
│
├── plugins/                        # Semantic Kernel plugins
│   ├── __init__.py
│   ├── schedule_plugin.py          # Equipment schedule data plugin
│   ├── risk_plugin.py              # Risk calculation plugin
│   ├── logging_plugin.py           # Agent thinking and event logging
│   ├── report_file_plugin.py       # Report generation and storage
│   ├── political_risk_json_plugin.py # Political risk data processing
│   ├── citation_handler_plugin.py  # Citation tracking from Bing Search
│
├── managers/                       # High-level managers
│   ├── __init__.py
│   ├── chatbot_manager.py          # Handles chat interactions
│   ├── workflow_manager.py         # Automates schedule analysis workflow
│   ├── scheduler.py                # Handles scheduled runs
│
├── api/                            # API layer
│   ├── __init__.py
│   ├── app.py                      # FastAPI application
│   ├── endpoints.py                # API endpoint definitions
│   ├── api_server.py               # Standalone API server
│
├── config/                         # Configuration
│   ├── __init__.py
│   ├── settings.py                 # Application settings and env vars
│
├── utils/                          # Utilities
│   ├── __init__.py
│   ├── database_utils.py           # Database connection management
│   ├── thinking_log_viewer.py      # Streamlit component for viewing agent thinking
│
├── test_scripts/                   # Testing utilities
│   ├── test_azure_storage.py       # Azure Storage connection tests
│   ├── test_bing_agent.py          # Bing Search integration tests
│   ├── full_test_bing_agent.py     # Comprehensive Bing testing
│   ├── test_create_doc.py          # Document generation testing
│
├── main.py                         # Main entry point
├── streamlit_app.py                # Streamlit UI
├── requirements.txt                # Project dependencies
└── README.md                       # Project documentation
```

## Core Components

### Specialized Agents

The system employs multiple specialized AI agents, each designed for specific tasks:

1. **Scheduler Agent** (`SCHEDULER_AGENT`)
   - Analyzes equipment schedule data
   - Calculates risk percentages and schedule variances
   - Determines initial risk levels for equipment items
   - Prepares data for specialized risk agents

2. **Political Risk Agent** (`POLITICAL_RISK_AGENT`)
   - Monitors global political events via Bing Search
   - Assesses geopolitical risks affecting supply chains
   - Provides sourced insights with proper citations
   - Generates structured political risk assessments

3. **Reporting Agent** (`REPORTING_AGENT`)
   - Consolidates findings from all agents
   - Creates comprehensive risk reports
   - Generates formatted Word documents
   - Stores reports in Azure Blob Storage

4. **Assistant Agent** (`ASSISTANT_AGENT`)
   - Manages conversational interactions
   - Provides general information and guidance
   - Routes specialized queries to appropriate agents
   - Ensures natural, helpful responses

### Plugin System

The system uses Semantic Kernel plugins to extend functionality:

1. **EquipmentSchedulePlugin**
   - Retrieves and processes equipment schedule data
   - Connects to schedule database
   - Provides schedule comparison analytics
   - Calculates variance metrics

2. **RiskCalculationPlugin**
   - Performs risk percentage calculations
   - Categorizes risks based on percentage thresholds
   - Provides standardized risk scoring
   - Ensures consistent risk evaluation

3. **LoggingPlugin**
   - Tracks agent thinking processes
   - Logs user queries and agent responses
   - Provides detailed audit trails
   - Enables transparent AI operations

4. **ReportFilePlugin**
   - Generates formatted Word documents
   - Uploads reports to Azure Storage
   - Tracks report metadata
   - Manages document versioning

5. **PoliticalRiskJsonPlugin**
   - Converts political risk analysis to structured JSON
   - Extracts risk data from agent responses
   - Standardizes political risk information
   - Enables database storage of risk insights

### Management Layer

High-level managers coordinate system operations:

1. **ChatbotManager**
   - Orchestrates agent interaction for chat sessions
   - Routes user queries to appropriate agents
   - Manages conversation state
   - Handles error recovery and rate limiting

## Running Options

 **Streamlit Developer Interface**
   ```bash
   streamlit run streamlit_app.py
   ```
   Launches the Streamlit interface with chat, visualization, and developer tools

## Agent Interaction Patterns

The system supports multiple interaction patterns:

### Interactive Chat Flow
For schedule/risk related questions in chat:
```
User Query → SCHEDULER_AGENT → REPORTING_AGENT → Response
```

### Specialized Risk Analysis
For political risk analysis:
```
User Query → SCHEDULER_AGENT → POLITICAL_RISK_AGENT → REPORTING_AGENT → Response
```

## Required Environment Variables

The application requires these environment variables:

```
AZURE_AI_AGENT_PROJECT_NAME=your_project_name
AZURE_AI_AGENT_PROJECT_CONNECTION_STRING=your_connection_string
AZURE_AI_AGENT_MODEL_DEPLOYMENT_NAME=your_model_deployment
DB_CONNECTION_STRING=your_db_connection_string
AZURE_STORAGE_CONNECTION_STRING=your_storage_connection_string
BING_SEARCH_API_KEY=your_bing_api_key
```
