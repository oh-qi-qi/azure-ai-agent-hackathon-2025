## Project Structure
```
project/
│
├── agents/
│   ├── __init__.py
│   ├── agent_definitions.py      # Contains agent instructions and definitions
│   ├── agent_strategies.py       # Contains selection and termination strategies
│   ├── agent_manager.py          # Contains agent creation and management functions
│
├── plugins/
│   ├── __init__.py
│   ├── schedule_plugin.py        # Contains EquipmentSchedulePlugin
│   ├── risk_plugin.py            # Contains RiskCalculationPlugin
│
├── managers/
│   ├── __init__.py
│   ├── chatbot_manager.py        # ChatbotManager class
│   ├── workflow_manager.py       # AutomatedWorkflowManager class
│   ├── scheduler.py              # WorkflowScheduler class
│
├── api/
│   ├── __init__.py
│   ├── app.py                    # FastAPI application
│   ├── endpoints.py              # API endpoints
│
├── config/
│   ├── __init__.py
│   ├── settings.py               # Configuration settings
│
├── utils/
│   ├── __init__.py
│   ├── database.py               # Database utilities
│   ├── azure_helpers.py          # Azure-related helper functions
│
├── main.py                       # Main entry point for the application
├── streamlit_app.py              # Streamlit application
├── requirements.txt
└── README.md
```

## How to Run or Use the Code
xxxx

### Starting backend server
1. Install project dependencies  
    `npm install`
1. Start the server  
    `npm start`
1. Access from browser   
    http://localhost:3000  
    
    If port `3000` is not free, environment variable `PORT` can be used set to another free port. For example to use port `3001` in bash
    ```sh
    PORT=3001 npm start
    ```
1. Sample Login Details  
    `admin@hta.gov.sg`  
    `p@s$w0rd`

### Resetting Application Data
This is a development and demo feature to reset to the application state to a default starting point. In any page, press:  

`SHIFT + Q`
