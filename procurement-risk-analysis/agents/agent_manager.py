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
                print("Warning: AzureAIAgent doesn't support connections parameter. Creating without connections.")
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
        # Prepare agent creation arguments
        creation_args = {
            "model": model_deployment_name,
            "name": agent_name,
            "instructions": instructions,
        }
        
        # Initialize Bing tool if connections is provided with the right format
        bing_tool = None
        
        # Add connections if provided
        if connections:
            # Check if connections is a dictionary with Bing information
            if isinstance(connections, dict) and "type" in connections and connections["type"] == "BingGrounding":
                from azure.ai.projects.models import BingGroundingTool
                
                # Method 1: Using connection_id
                if "connection_id" in connections:
                    print(f"Using connection ID: {connections['connection_id']}")
                    try:
                        bing_tool = BingGroundingTool(connection_id=connections["connection_id"])
                    except Exception as e:
                        print(f"Error creating BingGroundingTool with connection_id: {e}")
                
                # Method 2: Using connection_name - need to get the connection first
                elif "connection_name" in connections:
                    connection_name = connections["connection_name"]
                    print(f"Using named connection: {connection_name}")
                    try:
                        # Get the connection synchronously or asynchronously based on what's supported
                        try:
                            # Try async method first (this is the most likely scenario)
                            bing_connection = await client.connections.get(connection_name=connection_name)
                            print(f"Retrieved Bing connection with ID: {bing_connection.id}")
                        except (TypeError, AttributeError):
                            # Fall back to sync method if async isn't working
                            import inspect
                            if not inspect.iscoroutinefunction(client.connections.get):
                                bing_connection = client.connections.get(connection_name=connection_name)
                                print(f"Retrieved Bing connection with ID: {bing_connection.id} (sync method)")
                            else:
                                # If we get here, something else is wrong
                                raise ValueError("Could not call client.connections.get properly")
                        
                        # Create tool with connection ID
                        bing_tool = BingGroundingTool(connection_id=bing_connection.id)
                    except Exception as e:
                        print(f"Error getting named connection: {e}")
                
                # Method 3: Try API key method
                elif "api_key" in connections:
                    api_key = connections["api_key"]
                    print("Using API key method")
                    try:
                        bing_tool = BingGroundingTool(api_key=api_key)
                    except TypeError as e:
                        print(f"TypeError creating BingGroundingTool with api_key: {e}")
                        print("Your version of azure-ai-projects doesn't support the api_key parameter")
                        
                        # Try to get connection name from environment as fallback
                        import os
                        bing_connection_name = os.getenv("BING_CONNECTION_NAME")
                        if bing_connection_name:
                            try:
                                print(f"Falling back to named connection: {bing_connection_name}")
                                # Try async method first
                                try:
                                    bing_connection = await client.connections.get(connection_name=bing_connection_name)
                                except (TypeError, AttributeError):
                                    # Fall back to sync method if async isn't working
                                    if not inspect.iscoroutinefunction(client.connections.get):
                                        bing_connection = client.connections.get(connection_name=bing_connection_name)
                                    else:
                                        # If we get here, something else is wrong
                                        raise ValueError("Could not call client.connections.get properly")
                                        
                                bing_tool = BingGroundingTool(connection_id=bing_connection.id)
                                print(f"Created BingGroundingTool with connection ID: {bing_connection.id}")
                            except Exception as fallback_e:
                                print(f"Error using fallback named connection: {fallback_e}")
                    except Exception as e:
                        print(f"Other error creating BingGroundingTool: {e}")
                        
            # If connections is already a tool object with definitions
            elif hasattr(connections, "definitions"):
                bing_tool = connections
        
        # Add Bing tool to creation args if successfully created
        if bing_tool and hasattr(bing_tool, "definitions"):
            creation_args["tools"] = bing_tool.definitions
            print(f"Added Bing tool with {len(bing_tool.definitions)} definitions")
            
        # Create the agent with appropriate arguments
        agent_definition = await client.agents.create_agent(**creation_args)
        
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
            print("Warning: AzureAIAgent doesn't support connections parameter. Creating without connections.")
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
