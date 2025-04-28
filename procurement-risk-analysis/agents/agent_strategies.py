"""Agent selection and termination strategies."""

from semantic_kernel.agents.strategies import TerminationStrategy, SequentialSelectionStrategy
from semantic_kernel.contents.utils.author_role import AuthorRole
import asyncio
import time

from .agent_definitions import (
    SCHEDULER_AGENT, REPORTING_AGENT, ASSISTANT_AGENT,
    POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT
)

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

"""Agent selection and termination strategies."""

from semantic_kernel.agents.strategies import TerminationStrategy, SequentialSelectionStrategy
from semantic_kernel.contents.utils.author_role import AuthorRole
import asyncio
import time

from .agent_definitions import (
    SCHEDULER_AGENT, REPORTING_AGENT, ASSISTANT_AGENT,
    POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT
)

# Selection Strategy for interactive chatbot - FIXED VERSION
class ChatbotSelectionStrategy(SequentialSelectionStrategy):
    """Enhanced strategy for chatbot interaction with new risk agents."""
    
    async def select_agent(self, agents, history):
        """Check which agent should take the next turn in the chat."""
        # If the last message is from the user, determine the appropriate first agent
        if history[-1].role == AuthorRole.USER:
            user_message = history[-1].content.lower()
            
            # Case 1: Schedule-only risk questions
            if any(keyword in user_message for keyword in ["schedule risk", "delay risk", "variance risk"]) and \
               not any(keyword in user_message for keyword in ["political", "tariff", "logistics", "all risks", "comprehensive"]):
                agent_name = SCHEDULER_AGENT
                return next((agent for agent in agents if agent.name == agent_name), None)
            
            # Case 2: Specific risk type questions
            if "political risk" in user_message or "political risks" in user_message:
                # Need scheduler first, then political
                agent_name = SCHEDULER_AGENT
                return next((agent for agent in agents if agent.name == agent_name), None)
            
            if any(keyword in user_message for keyword in ["tariff risk", "tariff risks", "trade risk", "custom risk", "customs risk"]):
                # Need scheduler first, then tariff
                agent_name = SCHEDULER_AGENT
                return next((agent for agent in agents if agent.name == agent_name), None)
            
            if any(keyword in user_message for keyword in ["logistics risk", "logistics risks", "shipping risk", "port risk", "transport risk"]):
                # Need scheduler first, then logistics
                agent_name = SCHEDULER_AGENT
                return next((agent for agent in agents if agent.name == agent_name), None)
            
            # Case 3: Comprehensive risk analysis
            if any(keyword in user_message for keyword in ["all risks", "comprehensive", "full analysis", "complete risk", "risk analysis", "what are the risks"]):
                # Start with scheduler for full risk analysis
                agent_name = SCHEDULER_AGENT
                return next((agent for agent in agents if agent.name == agent_name), None)
            
            # Case 4: Report generation from conversation ID
            if "generate report" in user_message and "conversation id" in user_message:
                # Go directly to reporting agent
                agent_name = REPORTING_AGENT
                return next((agent for agent in agents if agent.name == agent_name), None)
            
            # Case 5: General queries about risks or schedules (not specific)
            if any(keyword in user_message for keyword in ["risk", "risks", "schedule", "delay", "variance", "equipment"]) and \
               not any(keyword in user_message for keyword in ["hello", "hi", "help", "what can you do"]):
                # Start with scheduler for general risk/schedule queries
                agent_name = SCHEDULER_AGENT
                return next((agent for agent in agents if agent.name == agent_name), None)
            
            # Default case: For general questions, help requests, or chat, use assistant agent
            assistant_agent = next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            if assistant_agent:
                return assistant_agent
        
        # Handle agent sequence flow
        last_agent = history[-1].name if hasattr(history[-1], 'name') else None
        
        # FIXED: After scheduler, determine next agent based on original query 
        if last_agent == SCHEDULER_AGENT:
            original_query = next((msg.content for msg in history if msg.role == AuthorRole.USER), "").lower()
            
            # If schedule risk analysis only (not specific risk types), go to reporting
            if any(keyword in original_query for keyword in ["schedule risk", "delay risk", "variance risk"]) and \
               not any(keyword in original_query for keyword in ["political", "tariff", "logistics", "all risks"]):
                return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
            
            # If specific risk type requested, route to that agent
            if ("political risk" in original_query or "political risks" in original_query):
                # Check if POLITICAL_RISK_AGENT has already responded
                if not any(msg.name == POLITICAL_RISK_AGENT for msg in history):
                    return next((agent for agent in agents if agent.name == POLITICAL_RISK_AGENT), None)
                else:
                    # If political risk agent has responded, go to reporting
                    return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
            
            if any(keyword in original_query for keyword in ["tariff risk", "tariff risks", "trade risk"]):
                if not any(msg.name == TARIFF_RISK_AGENT for msg in history):
                    return next((agent for agent in agents if agent.name == TARIFF_RISK_AGENT), None)
                else:
                    return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
            
            if any(keyword in original_query for keyword in ["logistics risk", "logistics risks", "shipping risk"]):
                if not any(msg.name == LOGISTICS_RISK_AGENT for msg in history):
                    return next((agent for agent in agents if agent.name == LOGISTICS_RISK_AGENT), None)
                else:
                    return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
            
            # If comprehensive analysis, trigger all risk agents in sequence
            if any(keyword in original_query for keyword in ["all risks", "comprehensive", "what are the risks"]):
                responded_agents = set(msg.name for msg in history if hasattr(msg, 'name'))
                risk_agent_order = [POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT]
                
                for agent_name in risk_agent_order:
                    if agent_name not in responded_agents:
                        return next((agent for agent in agents if agent.name == agent_name), None)
                
                # If all risk agents have responded, go to reporting
                if all(agent_name in responded_agents for agent_name in risk_agent_order):
                    return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
        
        # FIXED: After a specific risk agent, go to reporting
        if last_agent in [POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT]:
            original_query = next((msg.content for msg in history if msg.role == AuthorRole.USER), "").lower()
            
            # If comprehensive analysis, continue to next agent
            if any(keyword in original_query for keyword in ["all risks", "comprehensive", "what are the risks"]):
                responded_agents = set(msg.name for msg in history if hasattr(msg, 'name'))
                risk_agent_order = [POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT]
                
                for agent_name in risk_agent_order:
                    if agent_name not in responded_agents:
                        return next((agent for agent in agents if agent.name == agent_name), None)
                
                # If all risk agents have responded, go to reporting
                if all(agent_name in responded_agents for agent_name in risk_agent_order):
                    return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
            else:
                # For specific risk queries, go to reporting after risk agent responds
                return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
        
        # After reporting agent, terminate
        if last_agent == REPORTING_AGENT:
            return None
        
        # After assistant agent, terminate
        if last_agent == ASSISTANT_AGENT:
            return None
        
        # Default to assistant agent
        return next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)

# Termination Strategy for interactive chatbot - FIXED VERSION
class ChatbotTerminationStrategy(TerminationStrategy):
    """Enhanced termination strategy for different query types."""
    
    async def should_terminate(self, selected_agent, history):
        """Check if the chat should terminate."""
        # If we have fewer than 2 messages, don't terminate
        if len(history) < 2:
            return False
        
        # Extract the original user query
        original_query = ""
        for msg in history:
            if msg.role == AuthorRole.USER:
                original_query = msg.content.lower()
                break
        
        # Case 1: Schedule-only risk questions (no specific risk types mentioned)
        if any(keyword in original_query for keyword in ["schedule risk", "delay risk", "variance risk"]) and \
           not any(keyword in original_query for keyword in ["political", "tariff", "logistics", "all risks", "comprehensive"]):
            # Terminate after reporting agent responds
            if any(msg.name == REPORTING_AGENT for msg in history):
                return True
        
        # Case 2: Specific risk type questions
        if ("political risk" in original_query or "political risks" in original_query) and \
           not any(keyword in original_query for keyword in ["all risks", "comprehensive"]):
            # Terminate after reporting agent responds
            if any(msg.name == REPORTING_AGENT for msg in history):
                return True
        
        if any(keyword in original_query for keyword in ["tariff risk", "tariff risks", "trade risk"]) and \
           not any(keyword in original_query for keyword in ["all risks", "comprehensive"]):
            # Terminate after reporting agent responds
            if any(msg.name == REPORTING_AGENT for msg in history):
                return True
        
        if any(keyword in original_query for keyword in ["logistics risk", "logistics risks", "shipping risk"]) and \
           not any(keyword in original_query for keyword in ["all risks", "comprehensive"]):
            # Terminate after reporting agent responds
            if any(msg.name == REPORTING_AGENT for msg in history):
                return True
        
        # Case 3: Comprehensive risk analysis
        if any(keyword in original_query for keyword in ["all risks", "comprehensive", "full analysis", "what are the risks"]):
            # Terminate only after reporting agent responds
            if any(msg.name == REPORTING_AGENT for msg in history):
                return True
        
        # Case 4: Report generation from conversation ID
        if "generate report" in original_query and "conversation id" in original_query:
            # Terminate after reporting agent responds
            if any(msg.name == REPORTING_AGENT for msg in history):
                return True
        
        # Case 5: For general chat or help questions
        if any(keyword in original_query for keyword in ["hello", "hi", "help", "what can you do", "how are you"]):
            # Terminate after assistant responds
            if any(msg.name == ASSISTANT_AGENT for msg in history):
                return True
        
        # Default case: Check for standard termination conditions
        last_agent = history[-1].name if hasattr(history[-1], 'name') else None
        if last_agent == ASSISTANT_AGENT:
            return True
        
        # Don't terminate yet - continue the conversation
        return False
    
# NEW: Strategy for managing parallel execution of risk analysis agents
class ParallelRiskAnalysisStrategy(SequentialSelectionStrategy):
    """A strategy for managing parallel execution of risk analysis agents."""
    
    def __init__(self):
        super().__init__()
        # Store all state in a separate dictionary to avoid Pydantic validation issues
        self._state = {
            'agents_completed': set(),
            'risk_agents': {POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT},
            'agent_queue': [],
            'last_execution_time': {},
            'min_interval': 1.0  # Minimum 1 second between agent executions
        }
        
    async def select_agent(self, agents, history):
        """Select the next agent with rate limit handling."""
        # First execution - start with scheduler
        if not history:
            return next((agent for agent in agents if agent.name == SCHEDULER_AGENT), None)
        
        # Check if scheduler has completed
        scheduler_completed = any(msg.name == SCHEDULER_AGENT and len(msg.content) > 100 
                                for msg in history)
        
        # If scheduler completed but risk agents haven't run yet
        if scheduler_completed and not self._state['agents_completed']:
            # Initialize queue for risk agents if empty
            if not self._state['agent_queue']:
                self._state['agent_queue'] = list(self._state['risk_agents'])
            
            # Rate limiting logic
            current_time = time.time()
            
            # Check if we can execute the next agent
            for agent_name in self._state['agent_queue']:
                last_exec = self._state['last_execution_time'].get(agent_name, 0)
                if current_time - last_exec >= self._state['min_interval']:
                    # Update execution time
                    self._state['last_execution_time'][agent_name] = current_time
                    
                    # Find and return the agent
                    agent = next((a for a in agents if a.name == agent_name), None)
                    if agent:
                        self._state['agent_queue'].remove(agent_name)
                        self._state['agents_completed'].add(agent_name)
                        return agent
            
            # If no agent can execute due to rate limits, wait
            await asyncio.sleep(self._state['min_interval'])
            return await self.select_agent(agents, history)
        
        # If all risk agents have completed, select reporting agent
        if self._state['agents_completed'] == self._state['risk_agents']:
            return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
        
        return None

# NEW: Helper class to manage rate-limited execution
class RateLimitedExecutor:
    """Helper class to manage rate-limited execution of agents."""
    
    def __init__(self, max_concurrent=2, requests_per_minute=20):
        self.max_concurrent = max_concurrent
        self.requests_per_minute = requests_per_minute
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.request_times = []
        
    async def execute_with_limit(self, func, *args, **kwargs):
        """Execute a function with rate limiting."""
        async with self.semaphore:
            # Clean up old request times
            current_time = time.time()
            self.request_times = [t for t in self.request_times if current_time - t < 60]
            
            # Check if we need to wait
            if len(self.request_times) >= self.requests_per_minute:
                wait_time = 60 - (current_time - self.request_times[0])
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
            
            # Execute the function
            self.request_times.append(time.time())
            return await func(*args, **kwargs)