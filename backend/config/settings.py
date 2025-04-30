"""Configuration settings for the application."""

import os
from semantic_kernel.agents import AzureAIAgentSettings
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

def initialize_ai_agent_settings():
    """Initializes AI Agent settings from environment variables.
    
    Returns:
        AzureAIAgentSettings: The initialized AI Agent settings
        
    Raises:
        ValueError: If required environment variables are missing
    """
    # Get Azure AI Agent settings from environment variables
    project_name = os.getenv("AZURE_AI_AGENT_PROJECT_NAME")
    project_connection_string = os.getenv("AZURE_AI_AGENT_PROJECT_CONNECTION_STRING")
    model_deployment_name = os.getenv("AZURE_AI_AGENT_MODEL_DEPLOYMENT_NAME")
    
    # Validate required environment variables
    if not all([project_connection_string, model_deployment_name]):
        raise ValueError(
            "Missing required environment variables. Please set "
            "AZURE_AI_AGENT_PROJECT_CONNECTION_STRING and "
            "AZURE_AI_AGENT_MODEL_DEPLOYMENT_NAME."
        )
    
    # Create AI Agent settings
    ai_agent_settings = AzureAIAgentSettings(
        project_name=project_name,
        service_connection_string=project_connection_string,
        model_deployment_name=model_deployment_name
    )
    
    return ai_agent_settings

def get_database_connection_string():
    """Gets the database connection string from environment variables.
    
    Returns:
        str: The database connection string
        
    Raises:
        ValueError: If the connection string is missing
    """
    connection_string = os.getenv("DB_CONNECTION_STRING")
    if not connection_string:
        raise ValueError("Missing required environment variable: DB_CONNECTION_STRING")
    return connection_string

def get_project_client():
    project_connection_string = os.getenv("AZURE_AI_AGENT_PROJECT_CONNECTION_STRING")
    # Connect to the Azure AI Foundry project
    project_client = AIProjectClient.from_connection_string(
        credential=DefaultAzureCredential
            (exclude_environment_credential=True,
            exclude_managed_identity_credential=True),
        conn_str=project_connection_string
    )

    return project_client