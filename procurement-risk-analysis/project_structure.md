# Equipment Schedule Agent - Project Structure

I've reorganized your codebase into a modular structure that's easier to maintain and understand. Here's an overview of the new project structure:

```
project/
│
├── agents/                        # Agent-related code
│   ├── __init__.py                # Re-exports key classes and functions
│   ├── agent_definitions.py       # Agent instructions and constants
│   ├── agent_strategies.py        # Selection and termination strategies
│   ├── agent_manager.py           # Agent creation and management
│
├── plugins/                       # Semantic Kernel plugins
│   ├── __init__.py
│   ├── schedule_plugin.py         # Equipment schedule data plugin
│   ├── risk_plugin.py             # Risk calculation plugin
│
├── managers/                      # High-level managers
│   ├── __init__.py
│   ├── chatbot_manager.py         # Handles chat interactions
│   ├── workflow_manager.py        # Automates schedule analysis workflow
│   ├── scheduler.py               # Handles scheduled runs
│
├── api/                           # API layer
│   ├── __init__.py
│   ├── app.py                     # FastAPI application
│   ├── endpoints.py               # API endpoint definitions
│
├── config/                        # Configuration
│   ├── __init__.py
│   ├── settings.py                # Application settings and env vars
│
├── utils/                         # Utilities
│   ├── __init__.py
│   ├── database.py                # Database utilities
│
├── main.py                        # Main entry point
├── streamlit_app.py               # Streamlit UI
├── requirements.txt               # Project dependencies
└── README.md                      # Project documentation
```

## How to Use This Structure

### Running the Application

1. **Direct module import** (recommended)
   ```bash
   python main.py
   ```

2. **Run the Streamlit UI**
   ```bash
   streamlit run streamlit_app.py
   ```

3. **Run just the workflow**
   ```bash
   python main.py --workflow-only
   ```

4. **Run just the scheduler**
   ```bash
   python main.py --scheduler-only
   ```

### Key Components

1. **Agents**
   - `SCHEDULER_AGENT` - Analyzes equipment schedule data
   - `REPORTING_AGENT` - Creates reports from schedule analysis
   - `ASSISTANT_AGENT` - Handles user interaction

2. **Plugins**
   - `EquipmentSchedulePlugin` - Methods for working with schedule data
   - `RiskCalculationPlugin` - Methods for risk analysis

3. **Managers**
   - `ChatbotManager` - Manages chat interactions
   - `AutomatedWorkflowManager` - Runs automatic schedule analysis
   - `WorkflowScheduler` - Schedules automated workflows

4. **Configuration**
   - Environment variables are managed in `config/settings.py`
   - Required env vars: 
     - `DB_CONNECTION_STRING`
     - `AZURE_AI_AGENT_PROJECT_CONNECTION_STRING`
     - `AZURE_AI_AGENT_MODEL_DEPLOYMENT_NAME`

## Understanding Agent Interaction

The key change in this refactored code is how agents interact with each other:

1. For schedule/risk related questions in chat:
   - User query → SCHEDULER_AGENT → REPORTING_AGENT → ASSISTANT_AGENT

2. For automated analysis:
   - Scheduled trigger → SCHEDULER_AGENT → REPORTING_AGENT

This structure supports collaborative multi-agent processing where each agent has a specialized role, and their outputs are combined to provide comprehensive responses to users.

## Database Schema

The database schema remains unchanged. The application connects to your existing database using the connection string provided in the environment variables.
