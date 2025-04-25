"""Context-aware thinking logger plugin."""

from semantic_kernel.functions.kernel_function_decorator import kernel_function
from .thinking_logger_plugin import ThinkingLoggerPlugin

class ContextAwareThinkingLoggerPlugin:
    """A plugin that automatically includes context in logging."""
    
    def __init__(self, connection_string, session_id=None, 
                 azure_agent_id=None, model_deployment_name=None):
        self.connection_string = connection_string
        self.session_id = session_id
        self.azure_agent_id = azure_agent_id
        self.model_deployment_name = model_deployment_name
        self.base_logger = ThinkingLoggerPlugin(connection_string)
    
    @kernel_function(description="Log the agent's thinking process with context")
    def log_agent_thinking(self, agent_name: str, thinking_stage: str, 
                          thought_content: str, agent_run_id: str = None) -> str:
        """Logs the agent's thinking process with context automatically included"""
        # Call the base logger but include the context
        return self.base_logger.log_agent_thinking(
            agent_name=agent_name,
            thinking_stage=thinking_stage,
            thought_content=thought_content,
            agent_run_id=agent_run_id,
            session_id=self.session_id,
            azure_agent_id=self.azure_agent_id,
            model_deployment_name=self.model_deployment_name
        )