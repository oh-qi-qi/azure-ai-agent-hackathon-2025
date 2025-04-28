"""Agent creation and management functions."""

async def create_or_reuse_agent(client, agent_name, model_deployment_name, instructions, plugins=None, connections=None):
    """Creates a new agent or reuses an existing one with the same name.
    
    Args:
        client: The Azure AI Agent client
        agent_name: The name of the agent to create or reuse
        model_deployment_name: The name of the model deployment to use
        instructions: The instructions for the agent
        plugins: The plugins to attach to the agent
        connections: Optional connections for the agent (e.g., Bing search)
        
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
            # When reusing an existing agent, we need to check if AzureAIAgent supports connections
            try:
                agent = AzureAIAgent(
                    client=client,
                    definition=found_agent,
                    plugins=plugins,
                    connections=connections
                )
            except TypeError:
                # If connections parameter is not supported, try without it
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
        # Check if create_agent method supports connections parameter
        if connections:
            try:
                agent_definition = await client.agents.create_agent(
                    model=model_deployment_name,
                    name=agent_name,
                    instructions=instructions,
                    connections=connections
                )
            except TypeError:
                # If connections parameter is not supported, create without it
                agent_definition = await client.agents.create_agent(
                    model=model_deployment_name,
                    name=agent_name,
                    instructions=instructions
                )
        else:
            agent_definition = await client.agents.create_agent(
                model=model_deployment_name,
                name=agent_name,
                instructions=instructions
            )
        
        from semantic_kernel.agents import AzureAIAgent
        # When creating a new agent instance, check if AzureAIAgent supports connections
        try:
            agent = AzureAIAgent(
                client=client,
                definition=agent_definition,
                plugins=plugins,
                connections=connections
            )
        except TypeError:
            # If connections parameter is not supported, create without it
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