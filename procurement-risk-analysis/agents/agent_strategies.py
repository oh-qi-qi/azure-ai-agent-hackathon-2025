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
        # Add safety check for empty agents or history
        if not agents or len(agents) == 0:
            print("WARNING: No agents available to select")
            return None
        
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

# Selection Strategy for interactive chatbot - FIXED VERSION
class ChatbotSelectionStrategy(SequentialSelectionStrategy):
    """Enhanced strategy for chatbot interaction with new risk agents."""
    
    async def select_agent(self, agents, history):
        """Check which agent should take the next turn in the chat."""
        # Add safety check for empty agents or history
        if not agents or len(agents) == 0:
            print("WARNING: No agents available to select")
            return None
            
        if not history or len(history) == 0:
            print("WARNING: No history available, defaulting to assistant")
            return next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
        
        # If the last message is from the user, determine the appropriate first agent
        if history[-1].role == AuthorRole.USER:
            user_message = history[-1].content.lower()
            
            # Case 1: Schedule-only risk questions
            if any(keyword in user_message for keyword in ["schedule risk", "delay risk", "variance risk"]) and \
               not any(keyword in user_message for keyword in ["political", "tariff", "logistics", "all risks", "comprehensive"]):
                agent_name = SCHEDULER_AGENT
                selected_agent = next((agent for agent in agents if agent.name == agent_name), None)
                if selected_agent:
                    return selected_agent
                else:
                    print(f"WARNING: Could not find {agent_name} in agents list")
                    return next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            
            # Case 2: Specific risk type questions
            if "political risk" in user_message or "political risks" in user_message:
                # Need scheduler first, then political
                agent_name = SCHEDULER_AGENT
                selected_agent = next((agent for agent in agents if agent.name == agent_name), None)
                if selected_agent:
                    return selected_agent
                else:
                    print(f"WARNING: Could not find {agent_name} in agents list")
                    return next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            
            if any(keyword in user_message for keyword in ["tariff risk", "tariff risks", "trade risk", "custom risk", "customs risk"]):
                # Need scheduler first, then tariff
                agent_name = SCHEDULER_AGENT
                selected_agent = next((agent for agent in agents if agent.name == agent_name), None)
                if selected_agent:
                    return selected_agent
                else:
                    print(f"WARNING: Could not find {agent_name} in agents list")
                    return next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            
            if any(keyword in user_message for keyword in ["logistics risk", "logistics risks", "shipping risk", "port risk", "transport risk"]):
                # Need scheduler first, then logistics
                agent_name = SCHEDULER_AGENT
                selected_agent = next((agent for agent in agents if agent.name == agent_name), None)
                if selected_agent:
                    return selected_agent
                else:
                    print(f"WARNING: Could not find {agent_name} in agents list")
                    return next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            
            # Case 3: Comprehensive risk analysis
            if any(keyword in user_message for keyword in ["all risks", "comprehensive", "full analysis", "complete risk", "risk analysis", "what are the risks"]):
                # Start with scheduler for full risk analysis
                agent_name = SCHEDULER_AGENT
                selected_agent = next((agent for agent in agents if agent.name == agent_name), None)
                if selected_agent:
                    return selected_agent
                else:
                    print(f"WARNING: Could not find {agent_name} in agents list")
                    return next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            
            # Case 4: Report generation from conversation ID
            if "generate report" in user_message and "conversation id" in user_message:
                # Go directly to reporting agent
                agent_name = REPORTING_AGENT
                selected_agent = next((agent for agent in agents if agent.name == agent_name), None)
                if selected_agent:
                    return selected_agent
                else:
                    print(f"WARNING: Could not find {agent_name} in agents list")
                    return next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            
            # Case 5: General queries about risks or schedules (not specific)
            if any(keyword in user_message for keyword in ["risk", "risks", "schedule", "delay", "variance", "equipment"]) and \
               not any(keyword in user_message for keyword in ["hello", "hi", "help", "what can you do"]):
                # Start with scheduler for general risk/schedule queries
                agent_name = SCHEDULER_AGENT
                selected_agent = next((agent for agent in agents if agent.name == agent_name), None)
                if selected_agent:
                    return selected_agent
                else:
                    print(f"WARNING: Could not find {agent_name} in agents list")
                    return next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            
            # Default case: For general questions, help requests, or chat, use assistant agent
            assistant_agent = next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            if assistant_agent:
                return assistant_agent
            else:
                print("WARNING: Could not find ASSISTANT_AGENT in agents list")
                # If no assistant agent, return the first agent in the list
                return agents[0] if agents else None
        
        # Handle agent sequence flow
        last_agent = history[-1].name if hasattr(history[-1], 'name') else None
        
        # After scheduler, determine next agent based on original query 
        if last_agent == SCHEDULER_AGENT:
            original_query = next((msg.content for msg in history if msg.role == AuthorRole.USER), "").lower()
            
            # If schedule risk analysis only (not specific risk types), go to reporting
            if any(keyword in original_query for keyword in ["schedule risk", "delay risk", "variance risk"]) and \
               not any(keyword in original_query for keyword in ["political", "tariff", "logistics", "all risks"]):
                reporting_agent = next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
                if reporting_agent:
                    return reporting_agent
                else:
                    print("WARNING: Could not find REPORTING_AGENT in agents list")
                    return None
            
            # If specific risk type requested, route to that agent
            if ("political risk" in original_query or "political risks" in original_query):
                # Check if POLITICAL_RISK_AGENT has already responded
                if not any(msg.name == POLITICAL_RISK_AGENT for msg in history):
                    political_agent = next((agent for agent in agents if agent.name == POLITICAL_RISK_AGENT), None)
                    if political_agent:
                        return political_agent
                    else:
                        print("WARNING: Could not find POLITICAL_RISK_AGENT in agents list")
                        return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
                else:
                    # If political risk agent has responded, go to reporting
                    return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
            
            if any(keyword in original_query for keyword in ["tariff risk", "tariff risks", "trade risk"]):
                if not any(msg.name == TARIFF_RISK_AGENT for msg in history):
                    tariff_agent = next((agent for agent in agents if agent.name == TARIFF_RISK_AGENT), None)
                    if tariff_agent:
                        return tariff_agent
                    else:
                        print("WARNING: Could not find TARIFF_RISK_AGENT in agents list")
                        return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
                else:
                    return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
            
            if any(keyword in original_query for keyword in ["logistics risk", "logistics risks", "shipping risk"]):
                if not any(msg.name == LOGISTICS_RISK_AGENT for msg in history):
                    logistics_agent = next((agent for agent in agents if agent.name == LOGISTICS_RISK_AGENT), None)
                    if logistics_agent:
                        return logistics_agent
                    else:
                        print("WARNING: Could not find LOGISTICS_RISK_AGENT in agents list")
                        return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
                else:
                    return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
            
            # If comprehensive analysis, trigger all risk agents in sequence
            if any(keyword in original_query for keyword in ["all risks", "comprehensive", "what are the risks"]):
                responded_agents = set(msg.name for msg in history if hasattr(msg, 'name'))
                risk_agent_order = [POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT]
                
                for agent_name in risk_agent_order:
                    if agent_name not in responded_agents:
                        agent = next((agent for agent in agents if agent.name == agent_name), None)
                        if agent:
                            return agent
                        else:
                            print(f"WARNING: Could not find {agent_name} in agents list")
                            continue
                
                # If all risk agents have responded, go to reporting
                if all(agent_name in responded_agents for agent_name in risk_agent_order):
                    return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
                
                # If some risk agents are missing but we didn't find them, go to reporting
                return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
        
        # FIXED: After a specific risk agent, go to reporting
        if last_agent in [POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT]:
            # Always return the reporting agent after a risk agent responds
            reporting_agent = next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
            if reporting_agent:
                return reporting_agent
            else:
                print("WARNING: Could not find REPORTING_AGENT in agents list")
                return None
        
        # After reporting agent, terminate
        if last_agent == REPORTING_AGENT:
            return None
        
        # After assistant agent, terminate
        if last_agent == ASSISTANT_AGENT:
            return None
        
        # Default to assistant agent
        assistant_agent = next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
        if assistant_agent:
            return assistant_agent
        else:
            print("WARNING: Could not find ASSISTANT_AGENT for default return")
            return None

# Termination Strategy for interactive chatbot - UPDATED VERSION
class ChatbotTerminationStrategy(TerminationStrategy):
    """Enhanced termination strategy for different query types with improved timing handling."""
    
    def __init__(self):
        """Initialize the termination strategy."""
        super().__init__()
        # Store all state in local instance variables to avoid Pydantic validation
        self._start_time = time.time()
        self._max_turns = 50
        self._timeout_seconds = 600  # Increased from 360
        self._agent_timeouts = {
            POLITICAL_RISK_AGENT: 300,  # 5 minutes for political risk agent
            TARIFF_RISK_AGENT: 300,     # 5 minutes for tariff risk agent
            LOGISTICS_RISK_AGENT: 300,  # 5 minutes for logistics risk agent
            REPORTING_AGENT: 300        # 5 minutes for reporting agent
        }
        self._agent_start_times = {}
    
    async def should_terminate(self, selected_agent, history):
        """Check if the chat should terminate with improved timing logic."""
        # If we have fewer than 2 messages, don't terminate
        if len(history) < 2:
            return False
        
        # Track agent start times
        if selected_agent and selected_agent.name not in self._agent_start_times:
            self._agent_start_times[selected_agent.name] = time.time()
        
        # Check for overall timeout
        if time.time() - self._start_time > self._timeout_seconds:
            print(f"Chat terminated due to overall timeout after {self._timeout_seconds} seconds")
            return True
        
        # Check for individual agent timeouts
        for agent_name, start_time in self._agent_start_times.items():
            if agent_name in self._agent_timeouts:
                max_time = self._agent_timeouts[agent_name]
                elapsed = time.time() - start_time
                if elapsed > max_time:
                    print(f"Chat terminated due to {agent_name} timeout after {elapsed:.2f} seconds (max: {max_time})")
                    return True
        
        # Check for maximum turns
        if len(history) > self._max_turns * 2:  # *2 because each turn is user + assistant
            print(f"Chat terminated due to exceeding maximum turns: {self._max_turns}")
            return True
        
        # Extract the original user query
        original_query = ""
        for msg in history:
            if msg.role == AuthorRole.USER:
                original_query = msg.content.lower()
                break
        
        # Check if reporting agent has responded, which always allows termination
        reporting_agent_responded = any(msg.name == REPORTING_AGENT for msg in history)
        if reporting_agent_responded:
            print("Reporting agent has responded - allowing termination")
            return True
        
        # For political risk queries
        if ("political risk" in original_query or "political risks" in original_query):
            political_agent_responded = any(msg.name == POLITICAL_RISK_AGENT for msg in history)
            
            # If political risk agent has responded but reporting agent hasn't, check time
            if political_agent_responded:
                # Use our tracked start times instead of message attributes
                if POLITICAL_RISK_AGENT in self._agent_start_times:
                    political_resp_time = self._agent_start_times[POLITICAL_RISK_AGENT]
                    # If it's been more than 2 minutes since political agent started and no reporting agent response
                    if time.time() - political_resp_time > 120:
                        print("Forcing termination: waited too long after political agent response")
                        return True
            
            # Check if we've been waiting for political agent response too long (5 minutes)
            if not political_agent_responded and POLITICAL_RISK_AGENT in self._agent_start_times:
                if time.time() - self._agent_start_times[POLITICAL_RISK_AGENT] > 300:
                    print("Forcing termination: political agent taking too long to respond")
                    return True
                    
            # Only terminate if still waiting for responses and not timed out
            return False
        
        # Similar logic for other specific risk queries with the same timeout improvements
        if any(keyword in original_query for keyword in ["tariff risk", "tariff risks", "trade risk"]):
            tariff_agent_responded = any(msg.name == TARIFF_RISK_AGENT for msg in history)
            
            # If tariff agent has responded but reporting agent hasn't, check time
            if tariff_agent_responded:
                if TARIFF_RISK_AGENT in self._agent_start_times:
                    tariff_resp_time = self._agent_start_times[TARIFF_RISK_AGENT]
                    if time.time() - tariff_resp_time > 120:
                        print("Forcing termination: waited too long after tariff agent response")
                        return True
            
            # Check if we've been waiting for tariff agent response too long
            if not tariff_agent_responded and TARIFF_RISK_AGENT in self._agent_start_times:
                if time.time() - self._agent_start_times[TARIFF_RISK_AGENT] > 300:
                    print("Forcing termination: tariff agent taking too long to respond")
                    return True
            
            return False
        
        # Similar timeout handling for logistics risk
        if any(keyword in original_query for keyword in ["logistics risk", "logistics risks", "shipping risk"]):
            logistics_agent_responded = any(msg.name == LOGISTICS_RISK_AGENT for msg in history)
            
            # If logistics agent has responded but reporting agent hasn't, check time
            if logistics_agent_responded:
                if LOGISTICS_RISK_AGENT in self._agent_start_times:
                    logistics_resp_time = self._agent_start_times[LOGISTICS_RISK_AGENT]
                    if time.time() - logistics_resp_time > 120:
                        print("Forcing termination: waited too long after logistics agent response")
                        return True
            
            # Check if we've been waiting for logistics agent response too long
            if not logistics_agent_responded and LOGISTICS_RISK_AGENT in self._agent_start_times:
                if time.time() - self._agent_start_times[LOGISTICS_RISK_AGENT] > 300:
                    print("Forcing termination: logistics agent taking too long to respond")
                    return True
            
            return False
        
        # For schedule-only risk questions, only check for reporting agent
        if any(keyword in original_query for keyword in ["schedule risk", "delay risk", "variance risk"]) and \
        not any(keyword in original_query for keyword in ["political", "tariff", "logistics", "all risks", "comprehensive"]):
            return reporting_agent_responded
        
        # Case 3: Comprehensive risk analysis
        if any(keyword in original_query for keyword in ["all risks", "comprehensive", "full analysis", "what are the risks"]):
            # Check if we've waited more than 10 minutes for the full analysis
            if time.time() - self._start_time > 600:
                print("Forcing termination: comprehensive analysis taking too long")
                return True
            
            # Only terminate if reporting agent has responded
            return reporting_agent_responded
        
        # Case 4: Report generation from conversation ID
        if "generate report" in original_query and "conversation id" in original_query:
            # Check if we've waited more than 5 minutes for report generation
            if REPORTING_AGENT in self._agent_start_times and time.time() - self._agent_start_times[REPORTING_AGENT] > 300:
                print("Forcing termination: report generation taking too long")
                return True
            
            # Only terminate if reporting agent has responded
            return reporting_agent_responded
        
        # Case 5: For general chat or help questions
        if any(keyword in original_query for keyword in ["hello", "hi", "help", "what can you do", "how are you"]):
            # Terminate after assistant responds
            return any(msg.name == ASSISTANT_AGENT for msg in history)
        
        # Default case: Check for standard termination conditions
        last_agent = history[-1].name if hasattr(history[-1], 'name') else None
        
        # If the last agent is the reporting agent, terminate
        if last_agent == REPORTING_AGENT:
            return True
        
        # If the last agent is the assistant agent, terminate
        if last_agent == ASSISTANT_AGENT:
            return True
        
        # If a risk agent has responded and we've waited too long for reporting agent, terminate
        if last_agent in [POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT]:
            # Use our timing data instead of message attributes
            if last_agent in self._agent_start_times:
                if time.time() - self._agent_start_times[last_agent] > 120:
                    print(f"Forcing termination: waited too long after {last_agent} response")
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
        """Check which agent should take the next turn in the chat with improved timing handling."""
        # Add safety check for empty agents or history
        if not agents or len(agents) == 0:
            print("WARNING: No agents available to select")
            return None
            
        if not history or len(history) == 0:
            print("WARNING: No history available, defaulting to assistant")
            return next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
        
        # Debug current state
        last_agent = history[-1].name if hasattr(history[-1], 'name') else None
        print(f"DEBUG - select_agent: last_agent={last_agent}, history_len={len(history)}")
        
        # If the last message is from the user, determine the appropriate first agent
        if history[-1].role == AuthorRole.USER:
            user_message = history[-1].content.lower()
            print(f"DEBUG - User message: {user_message[:50]}...")
            
            # Case 1: Schedule-only risk questions
            if any(keyword in user_message for keyword in ["schedule risk", "delay risk", "variance risk"]) and \
                not any(keyword in user_message for keyword in ["political", "tariff", "logistics", "all risks", "comprehensive"]):
                agent_name = SCHEDULER_AGENT
                selected_agent = next((agent for agent in agents if agent.name == agent_name), None)
                if selected_agent:
                    print(f"DEBUG - User asked about schedule risk, selecting {agent_name}")
                    return selected_agent
                else:
                    print(f"WARNING: Could not find {agent_name} in agents list")
                    return next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            
            # Case 2: Specific risk type questions
            if "political risk" in user_message or "political risks" in user_message:
                # Need scheduler first, then political
                agent_name = SCHEDULER_AGENT
                selected_agent = next((agent for agent in agents if agent.name == agent_name), None)
                if selected_agent:
                    print(f"DEBUG - User asked about political risk, selecting {agent_name}")
                    return selected_agent
                else:
                    print(f"WARNING: Could not find {agent_name} in agents list")
                    return next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            
            if any(keyword in user_message for keyword in ["tariff risk", "tariff risks", "trade risk", "custom risk", "customs risk"]):
                # Need scheduler first, then tariff
                agent_name = SCHEDULER_AGENT
                selected_agent = next((agent for agent in agents if agent.name == agent_name), None)
                if selected_agent:
                    print(f"DEBUG - User asked about tariff risk, selecting {agent_name}")
                    return selected_agent
                else:
                    print(f"WARNING: Could not find {agent_name} in agents list")
                    return next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            
            if any(keyword in user_message for keyword in ["logistics risk", "logistics risks", "shipping risk", "port risk", "transport risk"]):
                # Need scheduler first, then logistics
                agent_name = SCHEDULER_AGENT
                selected_agent = next((agent for agent in agents if agent.name == agent_name), None)
                if selected_agent:
                    print(f"DEBUG - User asked about logistics risk, selecting {agent_name}")
                    return selected_agent
                else:
                    print(f"WARNING: Could not find {agent_name} in agents list")
                    return next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            
            # Case 3: Comprehensive risk analysis
            if any(keyword in user_message for keyword in ["all risks", "comprehensive", "full analysis", "complete risk", "risk analysis", "what are the risks"]):
                # Start with scheduler for full risk analysis
                agent_name = SCHEDULER_AGENT
                selected_agent = next((agent for agent in agents if agent.name == agent_name), None)
                if selected_agent:
                    print(f"DEBUG - User asked about comprehensive risks, selecting {agent_name}")
                    return selected_agent
                else:
                    print(f"WARNING: Could not find {agent_name} in agents list")
                    return next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            
            # Case 4: Report generation from conversation ID
            if "generate report" in user_message and "conversation id" in user_message:
                # Go directly to reporting agent
                agent_name = REPORTING_AGENT
                selected_agent = next((agent for agent in agents if agent.name == agent_name), None)
                if selected_agent:
                    print(f"DEBUG - User asked to generate report, selecting {agent_name}")
                    return selected_agent
                else:
                    print(f"WARNING: Could not find {agent_name} in agents list")
                    return next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            
            # Case 5: General queries about risks or schedules (not specific)
            if any(keyword in user_message for keyword in ["risk", "risks", "schedule", "delay", "variance", "equipment"]) and \
                not any(keyword in user_message for keyword in ["hello", "hi", "help", "what can you do"]):
                # Start with scheduler for general risk/schedule queries
                agent_name = SCHEDULER_AGENT
                selected_agent = next((agent for agent in agents if agent.name == agent_name), None)
                if selected_agent:
                    print(f"DEBUG - User asked about general risks, selecting {agent_name}")
                    return selected_agent
                else:
                    print(f"WARNING: Could not find {agent_name} in agents list")
                    return next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            
            # Default case: For general questions, help requests, or chat, use assistant agent
            print("DEBUG - Default case: selecting ASSISTANT_AGENT")
            assistant_agent = next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            if assistant_agent:
                return assistant_agent
            else:
                print("WARNING: Could not find ASSISTANT_AGENT in agents list")
                # If no assistant agent, return the first agent in the list
                return agents[0] if agents else None
        
        # Handle agent sequence flow
        # After scheduler, determine next agent based on original query 
        if last_agent == SCHEDULER_AGENT:
            original_query = next((msg.content for msg in history if msg.role == AuthorRole.USER), "").lower()
            print(f"DEBUG - After scheduler, original query: {original_query[:50]}...")
            
            # If schedule risk analysis only (not specific risk types), go to reporting
            if any(keyword in original_query for keyword in ["schedule risk", "delay risk", "variance risk"]) and \
                not any(keyword in original_query for keyword in ["political", "tariff", "logistics", "all risks"]):
                reporting_agent = next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
                if reporting_agent:
                    print("DEBUG - Schedule risk only query, going to REPORTING_AGENT")
                    return reporting_agent
                else:
                    print("WARNING: Could not find REPORTING_AGENT in agents list")
                    return None
            
            # If political risk query
            if ("political risk" in original_query or "political risks" in original_query):
                # Add a delay to ensure scheduler processing is complete
                await asyncio.sleep(2)
                
                # Check if POLITICAL_RISK_AGENT has already responded
                if not any(msg.name == POLITICAL_RISK_AGENT for msg in history):
                    print("DEBUG - Selecting POLITICAL_RISK_AGENT after scheduler")
                    political_agent = next((agent for agent in agents if agent.name == POLITICAL_RISK_AGENT), None)
                    if political_agent:
                        return political_agent
                    else:
                        print("WARNING: Could not find POLITICAL_RISK_AGENT in agents list")
                        # Fall back to reporting agent if political agent not found
                        print("DEBUG - Falling back to REPORTING_AGENT")
                        return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
                else:
                    # If political risk agent has responded, go to reporting
                    print("DEBUG - Political agent already responded, going to REPORTING_AGENT")
                    return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
            
            # If tariff risk query
            if any(keyword in original_query for keyword in ["tariff risk", "tariff risks", "trade risk"]):
                # Add a delay to ensure scheduler processing is complete
                await asyncio.sleep(2)
                
                if not any(msg.name == TARIFF_RISK_AGENT for msg in history):
                    print("DEBUG - Selecting TARIFF_RISK_AGENT after scheduler")
                    tariff_agent = next((agent for agent in agents if agent.name == TARIFF_RISK_AGENT), None)
                    if tariff_agent:
                        return tariff_agent
                    else:
                        print("WARNING: Could not find TARIFF_RISK_AGENT in agents list")
                        # Fall back to reporting agent if tariff agent not found
                        print("DEBUG - Falling back to REPORTING_AGENT")
                        return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
                else:
                    print("DEBUG - Tariff agent already responded, going to REPORTING_AGENT")
                    return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
            
            # If logistics risk query
            if any(keyword in original_query for keyword in ["logistics risk", "logistics risks", "shipping risk"]):
                # Add a delay to ensure scheduler processing is complete
                await asyncio.sleep(2)
                
                if not any(msg.name == LOGISTICS_RISK_AGENT for msg in history):
                    print("DEBUG - Selecting LOGISTICS_RISK_AGENT after scheduler")
                    logistics_agent = next((agent for agent in agents if agent.name == LOGISTICS_RISK_AGENT), None)
                    if logistics_agent:
                        return logistics_agent
                    else:
                        print("WARNING: Could not find LOGISTICS_RISK_AGENT in agents list")
                        # Fall back to reporting agent if logistics agent not found
                        print("DEBUG - Falling back to REPORTING_AGENT")
                        return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
                else:
                    print("DEBUG - Logistics agent already responded, going to REPORTING_AGENT")
                    return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
            
            # If comprehensive analysis, trigger all risk agents in sequence
            if any(keyword in original_query for keyword in ["all risks", "comprehensive", "what are the risks"]):
                # Add a delay to ensure scheduler processing is complete
                await asyncio.sleep(2)
                
                responded_agents = set(msg.name for msg in history if hasattr(msg, 'name'))
                risk_agent_order = [POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT]
                
                for agent_name in risk_agent_order:
                    if agent_name not in responded_agents:
                        print(f"DEBUG - Comprehensive analysis: selecting {agent_name}")
                        agent = next((agent for agent in agents if agent.name == agent_name), None)
                        if agent:
                            return agent
                        else:
                            print(f"WARNING: Could not find {agent_name} in agents list")
                            continue
                
                # If all risk agents have responded, go to reporting
                if all(agent_name in responded_agents for agent_name in risk_agent_order):
                    print("DEBUG - All risk agents have responded, going to REPORTING_AGENT")
                    return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
                
                # If some risk agents are missing but we didn't find them, go to reporting
                print("DEBUG - Some risk agents not found, going to REPORTING_AGENT")
                return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
        
        # CRITICAL FIX: After a specific risk agent, ALWAYS go to reporting with delay
        if last_agent in [POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT]:
            print(f"DEBUG - {last_agent} has responded, waiting 2 seconds before going to REPORTING_AGENT")
            # Add a delay to ensure risk agent processing is complete
            await asyncio.sleep(2)
            
            # Always return the reporting agent after a risk agent responds
            reporting_agent = next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
            if reporting_agent:
                print(f"DEBUG - Selecting REPORTING_AGENT after {last_agent}")
                return reporting_agent
            else:
                print("WARNING: Could not find REPORTING_AGENT in agents list")
                return None
        
        # After reporting agent, terminate
        if last_agent == REPORTING_AGENT:
            print("DEBUG - REPORTING_AGENT has responded, terminating")
            return None
        
        # After assistant agent, terminate
        if last_agent == ASSISTANT_AGENT:
            print("DEBUG - ASSISTANT_AGENT has responded, terminating")
            return None
        
        # Default to assistant agent
        print("DEBUG - No specific path matched, defaulting to ASSISTANT_AGENT")
        assistant_agent = next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
        if assistant_agent:
            return assistant_agent
        else:
            print("WARNING: Could not find ASSISTANT_AGENT for default return")
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