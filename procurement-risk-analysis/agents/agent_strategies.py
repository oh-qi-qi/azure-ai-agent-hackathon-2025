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
        # If the last message is from the user, determine the appropriate first agent
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
        
        # We don't need to select ASSISTANT_AGENT after REPORTING_AGENT anymore
        # as we'll terminate after REPORTING_AGENT for schedule-related queries
        
        # Default to assistant agent if none of the above conditions are met
        assistant_agent = next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
        if assistant_agent:
            print("Selecting ASSISTANT_AGENT as default")
            return assistant_agent

# Termination Strategy for interactive chatbot
class ChatbotTerminationStrategy(TerminationStrategy):
    """A strategy for determining when to end the chatbot interaction with better handling of rate limit scenarios."""
    
    async def should_terminate(self, selected_agent, history):
        """Check if the chat should terminate."""
        # If we have fewer than 2 messages, don't terminate
        if len(history) < 2:
            return False
            
        # For schedule-related questions, we want to terminate after REPORTING_AGENT responds
        # or after SCHEDULER_AGENT if REPORTING_AGENT couldn't respond due to rate limits
        
        # Check if the current query is schedule-related
        is_schedule_query = False
        for i, msg in enumerate(history):
            if msg.role == AuthorRole.USER:
                user_message = msg.content.lower()
                if any(keyword in user_message for keyword in ["schedule", "risk", "delay", "variance", "late", "delivery", "milestone"]):
                    is_schedule_query = True
                    break
        
        # For schedule-related queries
        if is_schedule_query:
            # If the last message is from REPORTING_AGENT, terminate 
            if hasattr(history[-1], 'name') and history[-1].name == REPORTING_AGENT:
                print("Terminating after REPORTING_AGENT for schedule-related query")
                return True
                
            # If the last message is from SCHEDULER_AGENT and it's been selected again
            # (which happens during retries), this suggests a rate limit issue
            if (hasattr(history[-1], 'name') and history[-1].name == SCHEDULER_AGENT and 
                selected_agent.name == SCHEDULER_AGENT):
                # Check if we've already had multiple turns from SCHEDULER_AGENT
                scheduler_count = sum(1 for msg in history if hasattr(msg, 'name') and msg.name == SCHEDULER_AGENT)
                if scheduler_count > 1:
                    print("Terminating after multiple SCHEDULER_AGENT turns (possible rate limit issue)")
                    return True
        
        # For non-schedule questions, terminate after the assistant responds
        if selected_agent.name == ASSISTANT_AGENT:
            for i in range(len(history) - 1):
                if (history[i].role == AuthorRole.USER and
                    hasattr(history[i+1], 'name') and history[i+1].name == ASSISTANT_AGENT):
                    print("Terminating after ASSISTANT_AGENT for non-schedule query")
                    return True
        
        # Don't terminate yet - continue the conversation
        return False