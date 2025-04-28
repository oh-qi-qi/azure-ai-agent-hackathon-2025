"""Agent creation and management functions."""

from azure.ai.projects.models import BingGroundingTool

async def create_or_reuse_agent(client, agent_name, model_deployment_name, instructions, plugins=None, 
                              connections=None, project_client=None, bing_connection_name=None):
    """Creates a new agent or reuses an existing one with the same name.
    
    Args:
        client: The Azure AI Agent client
        agent_name: The name of the agent to create or reuse
        model_deployment_name: The name of the model deployment to use
        instructions: The instructions for the agent
        plugins: The plugins to attach to the agent
        connections: Optional connections for the agent (legacy, not used)
        project_client: Optional AIProjectClient for creating agents with Bing grounding
        bing_connection_name: Optional Bing connection name for grounding
        
    Returns:
        The created or reused agent
    """
    # Check if agent already exists
    found_agent = None
    try:
        # List all agents and find if one with the same name exists
        response = await client.agents.list_agents()
        
        # Print debug information
        print(f"Agent list response type: {type(response)}")
        
        # Handle the response correctly based on its structure
        if hasattr(response, 'data'):
            # If response has a data attribute (list of agents)
            all_agents = response.data
            print(f"Found {len(all_agents)} agents")
            
            for agent in all_agents:
                if hasattr(agent, 'name') and agent.name == agent_name:
                    found_agent = agent
                    print(f"Found existing agent: {agent_name}")
                    break
        elif isinstance(response, dict) and 'data' in response:
            # If response is a dict with a 'data' key
            all_agents = response['data']
            print(f"Found {len(all_agents)} agents")
            
            for agent in all_agents:
                if isinstance(agent, dict) and agent.get('name') == agent_name:
                    found_agent = agent
                    print(f"Found existing agent: {agent_name}")
                    break
        else:
            # If we don't recognize the structure, just log it and continue
            print(f"Unexpected response structure: {response}")
                
        if found_agent:
            # Create agent instance from existing definition
            from semantic_kernel.agents import AzureAIAgent
            agent = AzureAIAgent(
                client=client,
                definition=found_agent,
                plugins=plugins
            )
            return agent
    except Exception as e:
        print(f"Error checking for existing agent: {e}")
        import traceback
        traceback.print_exc()
    
    # If no existing agent found or error occurred, create a new one
    print(f"Creating new agent: {agent_name}")
    try:
        # Check if we can create agent with Bing grounding
        if project_client and bing_connection_name and agent_name in ["POLITICAL_RISK_AGENT", "TARIFF_RISK_AGENT", "LOGISTICS_RISK_AGENT"]:
            try:
                print(f"Attempting to create {agent_name} with Bing grounding...")
                # Get Bing connection
                bing_connection = project_client.connections.get(
                    connection_name=bing_connection_name
                )
                conn_id = bing_connection.id
                print(f"Found Bing connection with ID: {conn_id}")
                
                # Initialize agent bing tool and add the connection id
                bing = BingGroundingTool(connection_id=conn_id)
                
                # Create agent with the bing tool
                with project_client:
                    azure_agent = project_client.agents.create_agent(
                        model=model_deployment_name,
                        name=agent_name,
                        instructions=instructions,
                        tools=bing.definitions,
                        headers={"x-ms-enable-preview": "true"}
                    )
                    print(f"Created agent with Bing grounding, ID: {azure_agent.id}")
                    
                    # Create SK Agent using the created agent definition
                    from semantic_kernel.agents import AzureAIAgent
                    agent = AzureAIAgent(
                        client=client,
                        definition=azure_agent,
                        plugins=plugins
                    )
                    return agent
            except Exception as bing_error:
                print(f"Could not create agent with Bing grounding: {bing_error}")
                print("Falling back to basic agent creation...")
        
        # If we can't create with Bing grounding or it's not a risk agent, use basic agent creation
        agent_definition = await client.agents.create_agent(
            model=model_deployment_name,
            name=agent_name,
            instructions=instructions
        )
        
        from semantic_kernel.agents import AzureAIAgent
        agent = AzureAIAgent(
            client=client,
            definition=agent_definition,
            plugins=plugins
        )
        
        return agent
    except Exception as e:
        print(f"Error creating new agent: {e}")
        import traceback
        traceback.print_exc()
        raise