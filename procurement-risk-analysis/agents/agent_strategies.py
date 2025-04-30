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

# Selection Strategy for interactive chatbot 
class ChatbotSelectionStrategy(SequentialSelectionStrategy):
    """Enhanced strategy for chatbot interaction with risk agents."""
    
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
            print(f"Processing user message: {user_message[:50]}...")
            
            # Case 1: Schedule-only risk questions
            if any(keyword in user_message for keyword in ["schedule risk", "delay risk", "variance risk"]) and \
               not any(keyword in user_message for keyword in ["political", "tariff", "logistics", "all risks", "comprehensive"]):
                agent_name = SCHEDULER_AGENT
                selected_agent = next((agent for agent in agents if agent.name == agent_name), None)
                if selected_agent:
                    print(f"Schedule-only risk query detected, selecting {agent_name}")
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
                    print(f"Political risk query detected, starting with {agent_name}")
                    return selected_agent
                else:
                    print(f"WARNING: Could not find {agent_name} in agents list")
                    return next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            
            if any(keyword in user_message for keyword in ["tariff risk", "tariff risks", "trade risk", "custom risk", "customs risk"]):
                # Need scheduler first, then tariff
                agent_name = SCHEDULER_AGENT
                selected_agent = next((agent for agent in agents if agent.name == agent_name), None)
                if selected_agent:
                    print(f"Tariff risk query detected, starting with {agent_name}")
                    return selected_agent
                else:
                    print(f"WARNING: Could not find {agent_name} in agents list")
                    return next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            
            if any(keyword in user_message for keyword in ["logistics risk", "logistics risks", "shipping risk", "port risk", "transport risk"]):
                # Need scheduler first, then logistics
                agent_name = SCHEDULER_AGENT
                selected_agent = next((agent for agent in agents if agent.name == agent_name), None)
                if selected_agent:
                    print(f"Logistics risk query detected, starting with {agent_name}")
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
                    print(f"Comprehensive risk query detected, starting with {agent_name}")
                    return selected_agent
                else:
                    print(f"WARNING: Could not find {agent_name} in agents list")
                    return next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            
            # Default case: For general questions, help requests, or chat, use assistant agent
            print("Using assistant agent by default")
            assistant_agent = next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
            if assistant_agent:
                return assistant_agent
            else:
                print("WARNING: Could not find ASSISTANT_AGENT in agents list")
                # If no assistant agent, return the first agent in the list
                return agents[0] if agents else None
        
        # Handle agent sequence flow
        last_agent = history[-1].name if hasattr(history[-1], 'name') else None
        print(f"Last agent: {last_agent}")
        
        # After scheduler, determine next agent based on original query 
        if last_agent == SCHEDULER_AGENT:
            print("Selecting next agent after scheduler")
            
            # Find the original user query
            original_query = ""
            for msg in history:
                if msg.role == AuthorRole.USER:
                    original_query = msg.content.lower()
                    break
            
            # Political risk flow
            if "political risk" in original_query or "political risks" in original_query:
                # Check if political agent has already responded
                political_responded = any(msg.name == POLITICAL_RISK_AGENT for msg in history if hasattr(msg, 'name'))
                
                if not political_responded:
                    # Select political risk agent
                    political_agent = next((agent for agent in agents if agent.name == POLITICAL_RISK_AGENT), None)
                    if political_agent:
                        print("Selecting political risk agent after scheduler")
                        return political_agent
                    else:
                        print("WARNING: Political risk agent not found, selecting reporting agent")
                        return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
                else:
                    # Political agent already responded, go to reporting agent
                    print("Political risk agent already responded, selecting reporting agent")
                    return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
            
            # Tariff risk flow
            if any(keyword in original_query for keyword in ["tariff risk", "tariff risks", "trade risk"]):
                # Check if tariff agent has already responded
                tariff_responded = any(msg.name == TARIFF_RISK_AGENT for msg in history if hasattr(msg, 'name'))
                
                if not tariff_responded:
                    # Select tariff risk agent
                    tariff_agent = next((agent for agent in agents if agent.name == TARIFF_RISK_AGENT), None)
                    if tariff_agent:
                        print("Selecting tariff risk agent after scheduler")
                        return tariff_agent
                    else:
                        print("WARNING: Tariff risk agent not found, selecting reporting agent")
                        return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
                else:
                    # Tariff agent already responded, go to reporting agent
                    print("Tariff risk agent already responded, selecting reporting agent")
                    return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
            
            # Logistics risk flow
            if any(keyword in original_query for keyword in ["logistics risk", "logistics risks", "shipping risk"]):
                # Check if logistics agent has already responded
                logistics_responded = any(msg.name == LOGISTICS_RISK_AGENT for msg in history if hasattr(msg, 'name'))
                
                if not logistics_responded:
                    # Select logistics risk agent
                    logistics_agent = next((agent for agent in agents if agent.name == LOGISTICS_RISK_AGENT), None)
                    if logistics_agent:
                        print("Selecting logistics risk agent after scheduler")
                        return logistics_agent
                    else:
                        print("WARNING: Logistics risk agent not found, selecting reporting agent")
                        return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
                else:
                    # Logistics agent already responded, go to reporting agent
                    print("Logistics risk agent already responded, selecting reporting agent")
                    return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
            
            # For comprehensive risk analysis
            if any(keyword in original_query for keyword in ["all risks", "comprehensive", "full analysis", "risk analysis", "what are the risks"]):
                # Check which risk agents have already responded
                political_responded = any(msg.name == POLITICAL_RISK_AGENT for msg in history if hasattr(msg, 'name'))
                tariff_responded = any(msg.name == TARIFF_RISK_AGENT for msg in history if hasattr(msg, 'name'))
                logistics_responded = any(msg.name == LOGISTICS_RISK_AGENT for msg in history if hasattr(msg, 'name'))
                
                # If no risk agents have responded yet, start with political
                if not political_responded and not tariff_responded and not logistics_responded:
                    political_agent = next((agent for agent in agents if agent.name == POLITICAL_RISK_AGENT), None)
                    if political_agent:
                        print("Comprehensive analysis: selecting political risk agent first")
                        return political_agent
                # If political responded but not tariff, select tariff
                elif political_responded and not tariff_responded:
                    tariff_agent = next((agent for agent in agents if agent.name == TARIFF_RISK_AGENT), None)
                    if tariff_agent:
                        print("Comprehensive analysis: selecting tariff risk agent")
                        return tariff_agent
                # If political and tariff responded but not logistics, select logistics
                elif political_responded and tariff_responded and not logistics_responded:
                    logistics_agent = next((agent for agent in agents if agent.name == LOGISTICS_RISK_AGENT), None)
                    if logistics_agent:
                        print("Comprehensive analysis: selecting logistics risk agent")
                        return logistics_agent
                # If all risk agents have responded, select reporting
                else:
                    print("All risk agents have responded or not found, selecting reporting agent")
                    return next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
            
            # For schedule-only queries or unrecognized queries, go to reporting agent
            print("Schedule-only or unrecognized query, selecting reporting agent")
            reporting_agent = next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
            if reporting_agent:
                return reporting_agent
            else:
                print("WARNING: Reporting agent not found, terminating")
                return None
        
        # After a specific risk agent, ALWAYS go to reporting agent
        if last_agent in [POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT]:
            print(f"{last_agent} has responded, selecting reporting agent next")
            
            # Wait briefly to ensure the risk agent has fully completed
            await asyncio.sleep(5)
            
            # Try to get the reporting agent
            reporting_agent = next((agent for agent in agents if agent.name == REPORTING_AGENT), None)
            if reporting_agent:
                print(f"Successfully found reporting agent after {last_agent}")
                return reporting_agent
            else:
                print(f"WARNING: Could not find REPORTING_AGENT after {last_agent}, returning None to terminate")
                return None
        
        # After reporting agent, terminate
        if last_agent == REPORTING_AGENT:
            print("Reporting agent finished, terminating")
            return None
        
        # After assistant agent, terminate
        if last_agent == ASSISTANT_AGENT:
            print("Assistant agent finished, terminating")
            return None
        
        # Default to assistant agent for any other case
        print("No specific condition matched, defaulting to assistant agent")
        assistant_agent = next((agent for agent in agents if agent.name == ASSISTANT_AGENT), None)
        if assistant_agent:
            return assistant_agent
        else:
            print("WARNING: Could not find ASSISTANT_AGENT for default return")
            return None
        
# Termination Strategy for interactive chatbot - UPDATED VERSION
class ChatbotTerminationStrategy(TerminationStrategy):
    """Fixed termination strategy to ensure proper flow between agents."""
    
    def __init__(self):
        """Initialize the termination strategy."""
        super().__init__()
        # Store all state in local instance variables to avoid Pydantic validation
        self._start_time = time.time()
        self._max_turns = 50
        self._timeout_seconds = 480  # 6 minutes total timeout
        self._agent_timeouts = {
            POLITICAL_RISK_AGENT: 300,  # 5 minutes for political risk agent
            TARIFF_RISK_AGENT: 300,     # 5 minutes for tariff risk agent
            LOGISTICS_RISK_AGENT: 300,  # 5 minutes for logistics risk agent
            REPORTING_AGENT: 300        # 5 minutes for reporting agent
        }
        self._agent_start_times = {}
        self._agent_responses = set()  # Track which agents have responded
        self._reporting_attempted = False
        self._already_terminated = False
        
    def reset(self):
        """Reset the termination strategy."""
        print("Termination strategy has been reset")
        self._start_time = time.time()
        self._agent_start_times = {}
        self._agent_responses = set()
        self._reporting_attempted = False
        self._already_terminated = False
    
    async def should_terminate(self, selected_agent, history):
        """Check if the chat should terminate with improved logic for risk agent flow."""
        # If we've already decided to terminate, stick with that decision
        if self._already_terminated:
            print("Already decided to terminate")
            return True
            
        # If we have fewer than 2 messages, don't terminate
        if len(history) < 2:
            print("History too short, not terminating")
            return False
        
        # Track agent start times
        if selected_agent and selected_agent.name:
            if selected_agent.name not in self._agent_start_times:
                self._agent_start_times[selected_agent.name] = time.time()
        
        # Check for overall timeout
        if time.time() - self._start_time > self._timeout_seconds:
            print(f"Chat terminated due to overall timeout after {self._timeout_seconds} seconds")
            self._already_terminated = True
            return True
        
        # Check for individual agent timeouts
        for agent_name, start_time in self._agent_start_times.items():
            if agent_name in self._agent_timeouts:
                max_time = self._agent_timeouts[agent_name]
                elapsed = time.time() - start_time
                if elapsed > max_time:
                    print(f"Chat terminated due to {agent_name} timeout after {elapsed:.2f} seconds (max: {max_time})")
                    self._already_terminated = True
                    return True
        
        # Check for maximum turns
        if len(history) > self._max_turns * 2:  # *2 because each turn is user + assistant
            print(f"Chat terminated due to exceeding maximum turns: {self._max_turns}")
            self._already_terminated = True
            return True
        
        # Get the last message agent
        last_agent = history[-1].name if hasattr(history[-1], 'name') else None
        
        # Add the last agent to our tracking set if it's an assistant message
        if last_agent and history[-1].role == AuthorRole.ASSISTANT:
            self._agent_responses.add(last_agent)
            print(f"Added {last_agent} to responded agents. Current: {self._agent_responses}")
        
        # Special case for reporting agent (allow it to finish)
        if last_agent == REPORTING_AGENT:
            print("Reporting agent has responded - wait for completion")
            
            # Check if the message indicates a completed report
            message_content = history[-1].content if hasattr(history[-1], 'content') else ""
            
            # Set reporting agent as attempted if we've seen a response
            self._reporting_attempted = True
            
            # Look for indicators of a complete report
            report_completed = False
            
            # Check if the response is substantial enough
            if len(message_content) > 1000:  # Simple check for substantial content
                report_completed = True
            
            # Check for file information section
            if "Report Generated Successfully" in message_content:
                report_completed = True
                
            # Check for executive summary and recommendations sections
            if "Executive Summary" in message_content and "Recommendations" in message_content:
                report_completed = True
                
            if report_completed:
                print("REPORTING_AGENT response is complete, FORCING TERMINATION")
                self._already_terminated = True
                return True
            
            return False
        
        # CRITICAL: After a specific risk agent, check if reporting agent has been attempted
        if last_agent in [POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT]:
            if self._reporting_attempted:
                print(f"Risk agent {last_agent} has responded and reporting has been attempted, terminating")
                self._already_terminated = True
                return True
            return False
        
        # Standard cases for termination
        if last_agent == ASSISTANT_AGENT:
            print("ASSISTANT_AGENT responded - terminating")
            self._already_terminated = True
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
        self._lock = asyncio.Lock()
        
    async def execute_with_limit(self, func, *args, **kwargs):
        """Execute a function with rate limiting."""
        async with self.semaphore:
            async with self._lock:
                # Clean up old request times
                current_time = time.time()
                self.request_times = [t for t in self.request_times if current_time - t < 60]
                
                # Check if we need to wait
                if len(self.request_times) >= self.requests_per_minute:
                    wait_time = 60 - (current_time - self.request_times[0])
                    if wait_time > 0:
                        print(f"Rate limit wait: {wait_time:.2f} seconds")
                        await asyncio.sleep(wait_time)
                
                # Record this request
                self.request_times.append(time.time())
            
            # Execute the function
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                print(f"Error in rate-limited function: {e}")
                import traceback
                traceback.print_exc()
                raise