# Procurement Risk Analysis System

A Python-based system for analyzing procurement risks using Azure AI Agents. The system processes equipment schedules and analyzes various risk factors such as political risks.

## Features

- **Multi-Agent Risk Analysis**: Utilizes specialized AI agents for different types of analysis:
  - Assistant Agent
  - Schedule Risk Analysis Agent
  - Political Risk Analysis Agent
  - Comprehensive Risk Reporting Agent

- **REST API**: FastAPI-based endpoints for integration
- **Data Lake Integration**: Automatic report storage in Azure Data Lake
- **Structured Logging**: Comprehensive logging system for agent interactions
- **Dual Interface Mode**:
  - User Mode: Production-ready Next.js frontend for end users
  - Dev Mode: Streamlit-based interface for testing APIs and agent behaviors

## Backend

## Project Structure

```
project/
├── agents/ # Agent-related code
│ ├── agent_definitions.py # Agent instructions and definitions
│ ├── agent_strategies.py # Selection and termination strategies
│ └── agent_manager.py # Agent creation and management
├── plugins/ # Semantic Kernel plugins
│ ├── schedule_plugin.py # Equipment schedule analysis
│ ├── risk_plugin.py # Risk calculations
│ ├── logging_plugin.py # Consolidated logging
│ └── report_file_plugin.py # Report generation
├── managers/ # System managers
│ ├── chatbot_manager.py # Chat interaction handling
│ ├── workflow_manager.py # Automated workflow management
│ └── scheduler.py # Workflow scheduling
├── api/ # API layer
│ └── api_server.py # API endpoints
├── config/ # Configuration
│ └── settings.py # Application settings
└── main.py # Application entry point
```

## Prerequisites

- Python 3.8+
- Azure AI Projects account
- Azure Storage account (for report storage)
- SQL Server database

## Installation

1. Clone the repository:

```bash
git clone [repository-url]
cd procurement-risk-analysis
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set up environment variables:

```bash
# Create .env file
python -m venv .venv
```

```bash
source .venv/bin/activate
```

#### Required variables

```
AZURE_AI_AGENT_PROJECT_CONNECTION_STRING=your_connection_string
AZURE_AI_AGENT_MODEL_DEPLOYMENT_NAME=your_model_deployment
DB_CONNECTION_STRING=your_db_connection_string
AZURE_STORAGE_CONNECTION_STRING=your_storage_connection_string
```

## Usage

### Running the Application

1. Start the API server:

```bash
python api/api_server.py
```

### API Endpoints

- `POST /api/chat`: Process chat messages with session management

- `GET /api/sessions`: Retrieve all chat sessions with conversation history

- `GET /api/session-ids`: Get a list of session IDs with their first queries

- `GET /api/sessions/{session_id}`: Get conversation history for a specific session

- `GET /api/thinking-logs`: Get detailed agent thinking logs for all sessions

- `GET /api/thinking-log-ids`: Get a simplified list of thinking log sessions

- `GET /api/thinking-logs-by-session-id/{session_id}`: Get thinking logs for a specific session

- `GET /api/heatmap`: Get risk heatmap in a choropleth data

- `GET /api/reports`: Get a list of generated risk reports

## Development

### Adding New Agents

1. Define agent instructions in `agents/agent_definitions.py`
2. Create selection/termination strategies in `agents/agent_strategies.py`
3. Register the agent in `managers/chatbot_manager.py`

### Creating Plugins

1. Create a new plugin class in the `plugins` directory
2. Decorate methods with `@kernel_function`
3. Register the plugin in relevant agent initialization

## Error Handling

The system includes comprehensive error handling and logging:

- Agent interaction logs
- Error tracking
- Rate limiting protection
- Automatic resource cleanup

## Frontend

### User Mode (Production Interface)

The Next.js frontend provides a polished, production-ready interface for end users to interact with the procurement risk analysis system.

## Tech Stack

- **Framework**: Next.js with TypeScript
- **Styling**: Tailwind CSS
- **Package Manager**: npm
- **Code Quality**: ESLint
- **Development Tools**:
  - PostCSS
  - TypeScript configuration
  - Next.js configuration

## Project Structure

```
frontend/
├── app/ # Next.js app directory (pages and routing)
├── components/ # Reusable React components
├── hooks/ # Custom React hooks
├── lib/ # Utility functions and shared logic
├── public/ # Static assets
├── .next/ # Next.js build output
├── node_modules/ # Dependencies
├── tailwind.config.js # Tailwind CSS configuration
├── tsconfig.json # TypeScript configuration
├── next.config.ts # Next.js configuration
├── postcss.config.mjs # PostCSS configuration
├── package.json # Project dependencies and scripts
└── eslint.config.mjs # ESLint configuration
```

## Prerequisites

- Node.js 18.x or higher
- npm 9.x or higher

## Installation

1. Clone the repository:

```bash
git clone [repository-url]
cd frontend
```

2. Install dependencies:

```bash
npm install
```

## Development

To start the development server:

```bash
npm run dev
```

The application will be available at `http://localhost:3000`

## Code Style and Quality

This project uses:

- ESLint for code quality
- TypeScript for type safety
- Prettier for code formatting (configured via ESLint)

## Browser Support

This application supports modern browsers including:

- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)

## Compatibility Notes

- **Mac OS Compatibility**: For Mac OS systems with ARM architecture (Apple Silicon), Spire.Doc currently does not support direct installation. For non-ARM Mac OS systems, please download `Spire.Doc-12.7.1-py3-none-macosx_10_7_universal.whl` before proceeding with pip installation.

## Dev Mode (Testing Interface)

A Streamlit-based interface is available for developers to test APIs and agent behaviors during development.

#### Installation (Dev Mode)

Run the Streamlit interface:

```bash
streamlit run streamlit_app.py
```

The development interface will be available at `http://localhost:8501`

## License

[Your License Here]
