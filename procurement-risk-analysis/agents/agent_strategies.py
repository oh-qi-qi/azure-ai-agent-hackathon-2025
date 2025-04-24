"""Agent selection and termination strategies."""

from semantic_kernel.agents.strategies import TerminationStrategy, SequentialSelectionStrategy
from semantic_kernel.contents.utils.author_role import AuthorRole

from .agent_definitions import SCHEDULER_AGENT, REPORTING_AGENT, ASSISTANT_AGENT

# Selection Strategy for automated workflow
class AutomatedWorkflowSelectionStrategy(SequentialSelectionStrategy):
    """A strategy for determining which agent should take the next turn in the automated workflow."""
    
    async def select_agent(self, agents, history):
        """Check which agent should take the next turn in the chat."""
        if not history:
            # First turn goes to the scheduler agent
            agent_name = SCHEDULER_AGENT
            return next((agent for agent in agents if agent.name == agent_name), None)
            
        # If the last message was from the scheduler agent, reporting agent goes next
        if history[-1].name == SCHEDULER_AGENT:
            agent_name = REPORTING_AGENT
            return next((agent for agent in agents if agent.name == agent_name), None)
            
        # Otherwise start over with the scheduler agent
        agent_name = SCHEDULER_AGENT
        return next((agent for agent in agents if agent.name == agent_name), None)


# Termination Strategy for automated workflow
class AutomatedWorkflowTerminationStrategy(TerminationStrategy):
    """A strategy for determining when to end the automated workflow."""
    
    async def should_terminate(self, selected_agent, history):
        """Check if the chat should terminate."""
        # End after the reporting agent has responded
        if len(history) >= 2 and history[-1].name == REPORTING_AGENT:
            return True
        return False


# Selection Strategy for interactive chatbot
class ChatbotSelectionStrategy(SequentialSelectionStrategy):
    """A strategy for determining which agent should take the next turn in the chatbot."""
    
    async def select_agent(self, agents, history):
        """Check which agent should take the next turn in the chat."""
        # If the last message is from the user, start with scheduler for schedule questions
        if history[-1].role == AuthorRole.USER:
            user_message = history[-1].content.lower()
            
            # Check for schedule analysis or risk related queries
            if any(keyword in user_message for keyword in ["schedule", "risk", "delay", "variance", "late", "delivery", "milestone"]):
                # For schedule/risk questions, start with the scheduler agent
                agent_name = SCHEDULER_AGENT
                scheduler_agent = next((agent for agent in agents if agent.name == agent_name), None)
                if scheduler_agent:
                    print("Selecting SCHEDULER_AGENT after user message")
                    return scheduler_agent
            
            # For non-schedule questions, use the assistant agent
            assistant_agent = next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            if assistant_agent:
                print("Selecting ASSISTANT_AGENT after user message (non-schedule topic)")
                return assistant_agent
        
        # If the last message is from the scheduler agent, the reporting agent goes next
        elif hasattr(history[-1], 'name') and history[-1].name == SCHEDULER_AGENT:
            reporting_agent = next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
            if reporting_agent:
                print("Selecting REPORTING_AGENT after SCHEDULER_AGENT message")
                return reporting_agent
        
        # If the last message is from the reporting agent, the assistant goes next
        elif hasattr(history[-1], 'name') and history[-1].name == REPORTING_AGENT:
            assistant_agent = next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            if assistant_agent:
                print("Selecting ASSISTANT_AGENT after REPORTING_AGENT message")
                return assistant_agent
        
        # Default to assistant agent if none of the above conditions are met
        assistant_agent = next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
        if assistant_agent:
            print("Selecting ASSISTANT_AGENT as default")
            return assistant_agent


# Termination Strategy for interactive chatbot
class ChatbotTerminationStrategy(TerminationStrategy):
    """A strategy for determining when to end the chatbot interaction."""
    
    async def should_terminate(self, selected_agent, history):
        """Check if the chat should terminate."""
        # For schedule-related questions, we want to go through:
        # USER → SCHEDULER → REPORTING → ASSISTANT → terminate
        
        # Track the sequence of the last few messages
        if len(history) >= 3:
            recent_agents = []
            for msg in history[-3:]:
                if hasattr(msg, 'name') and msg.name:
                    recent_agents.append(msg.name)
            
            # If we've just completed a full cycle, terminate after the assistant responds
            if (SCHEDULER_AGENT in recent_agents and 
                REPORTING_AGENT in recent_agents and 
                selected_agent.name == ASSISTANT_AGENT):
                return True
        
        # Don't terminate yet - continue the conversation
        return False
