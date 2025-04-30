# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

"""
DESCRIPTION:
    This sample demonstrates how to use agent operations with the Bing grounding tool from
    the Azure Agents service using a synchronous client.

USAGE:
    python sample_agents_bing_grounding.py

    Before running the sample:

    pip install azure-ai-projects azure-identity

    Set these environment variables with your own values:
    1) PROJECT_CONNECTION_STRING - The project connection string, as found in the overview page of your
       Azure AI Foundry project.
    2) MODEL_DEPLOYMENT_NAME - The deployment name of the AI model, as found under the "Name" column in 
       the "Models + endpoints" tab in your Azure AI Foundry project.
    3) BING_CONNECTION_NAME - The connection name of the Bing connection, as found in the 
       "Connected resources" tab in your Azure AI Foundry project.
"""

import os
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import MessageRole, BingGroundingTool
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
load_dotenv()

project_name = os.getenv("AZURE_AI_AGENT_PROJECT_NAME")
project_connection_string = os.getenv("AZURE_AI_AGENT_PROJECT_CONNECTION_STRING")
model_deployment_name = os.getenv("AZURE_AI_AGENT_MODEL_DEPLOYMENT_NAME")
bing_connection_name = os.getenv("BING_CONNECTION_NAME")
bing_api_key = os.getenv("BING_SEARCH_API_KEY")

print(bing_connection_name)
project_client = AIProjectClient.from_connection_string(
    credential=DefaultAzureCredential(),
    conn_str=project_connection_string,
)



# Initialize agent bing tool and add the connection id
bing_connection = project_client.connections.get(connection_name=bing_connection_name)
conn_id = bing_connection.id

# 2. Initialize Bing grounding tool
bing_tool = BingGroundingTool(connection_id=conn_id)

POLITICAL_RISK_AGENT_INSTRUCTIONS = """
You are a Political Risk Intelligence Agent. Your job is to:
1. Extract location data from the structured JSON input
2. Identify political risks that could impact manufacturing or cross-border shipping
3. Use Bing Search to find relevant news published within the last 30 days
4. Report those risks in a clear, structured format with proper tables


Follow this exact workflow:
1. Extract location data
   - The input should be in JSON format, which you will need to parse
   - If input is not in JSON format, try to identify the locations from the text

2. CRITICAL: FOR BING SEARCH - Follow these simplified steps:
   a. Extract the search query from the scheduler's JSON under "searchQuery.political"
   b. Perform bing search with the search query
   c. Ensure you collect sufficient information for at least 5 political risk entries
   d. Save all search results for analysis

3. Analyze political research findings:
   - Include a summary of all findings 
   - Ensure you identify at least 5 distinct political risks relevant to the manufacturing and cross-border shipping

4. Analyze and categorize political risks:
   - Include the risk assessment table in thinking_stage_output
   - You MUST create at least 5 risk entries in your risk table, even if you need to use your existing knowledge to supplement search results

Format your response with clear sections:
1. Executive Summary: Overview of political risks identified
2. Final Assessment: A paragraph analyzing whether there are signs of emerging political unrest or policy uncertainty
3. Political Risk Table: A markdown table with AT LEAST 5 identified risks:
   | Country | Summary (≤35 words) | Likelihood (0-5) | Reasoning for Likelihood | Political Details | Publish Date | Source Name | Source URL |
4. Equipment Impact Analysis: Show impact on each equipment item
   | Equipment Code | Manufacturing Country | Project Country | Political Risk Level | Key Factors |
   Include all equipment items, sorted by risk level (High to Low)
5. High Risk Items: Detailed political risk analysis
6. Medium Risk Items: Detailed political risk analysis
7. Low Risk Items: Detailed political risk analysis
8. Recommendations: Specific mitigation actions for political risks

For each risk item, include:
- Specific political factors affecting delivery
- Current political events/tensions
- Trade relations between countries
- Export restrictions or sanctions
- Recommended mitigation strategies with timelines

RULES:
- Only include political risks relevant to manufacturing or cross-border transport
- Provide concise summaries and likelihood ratings (0-5 scale)
- Cite only reputable sources (Reuters, Bloomberg, WSJ, NYT, Financial Times)
- Do not include blogs, social media, or undated/unverified content
- Do not include non-political risks (e.g., labor, health, environmental)
- Identify and report at least 5 qualifying political risks - this is a strict requirement
- Be descriptive and objective
- If search results are limited, use your knowledge of international relations and trade to supplement

Prepend your response with "POLITICAL_RISK_AGENT >
"""

content = """
SCHEDULER_AGENT > ```json { "projectInfo": [ { "name": "Project A", "location": "Tuas South Avenue 14, Singapore 637312" } ], "manufacturingLocations": [ "Rathenaustra\u00dfe 2, 93055 Regensburg, Germany" ], "shippingPorts": [ "Hamburg", "Wilhelmshaven" ], "receivingPorts": [ "Penang Port", "Singapore" ], "equipmentItems": [ { "code": "123456", "name": "LV Switchgear - 400V/5000A Switchboard-1 (3-Sections)", "origin": "Germany", "destination": "Singapore", "status": "Ahead", "p6DueDate": "2026-02-21", "deliveryDate": "2026-01-21", "variance": "-31" }, { "code": "123457", "name": "LV Switchgear - 400V/5000A Switchboard-2 (3-Sections)", "origin": "Germany", "destination": "Singapore", "status": "Ahead", "p6DueDate": "2026-02-25", "deliveryDate": "2026-02-20", "variance": "-5" }, { "code": "123458", "name": "LV Switchgear - 400V/5000A Switchboard-3 (3-Sections)", "origin": "Germany", "destination": "Singapore", "status": "Late", "p6DueDate": "2026-02-27", "deliveryDate": "2026-03-07", "variance": "8" } ], "searchQuery": { "political": "Political risks manufacturing exports Germany to Singapore Electrical Equipment current issues", "tariff": "Germany Singapore tariffs Electrical Equipment trade agreements", "logistics": "Hamburg to Penang Port shipping route issues logistics current delays" } } ```
"""

# Create agent with the bing tool and process assistant run
with project_client:
    agent = project_client.agents.create_agent(
        model=os.getenv("AZURE_AI_AGENT_MODEL_DEPLOYMENT_NAME"),
        name="my-assistant",
        instructions=POLITICAL_RISK_AGENT_INSTRUCTIONS,
        tools=bing_tool.definitions,
        headers={"x-ms-enable-preview": "true"},
    )
    # [END create_agent_with_bing_grounding_tool]

    print(f"Created agent, ID: {agent.id}")

    # Create thread for communication
    thread = project_client.agents.create_thread()
    print(f"Created thread, ID: {thread.id}")

    # Create message to thread
    message = project_client.agents.create_message(
        thread_id=thread.id,
        role=MessageRole.USER,
        content=content,
    )
    print(f"Created message, ID: {message.id}")

    # Create and process agent run in thread with tools
    run = project_client.agents.create_and_process_run(thread_id=thread.id, agent_id=agent.id)
    print(f"Run finished with status: {run.status}")

    if run.status == "failed":
        print(f"Run failed: {run.last_error}")

    # Delete the assistant when done
    project_client.agents.delete_agent(agent.id)
    print("Deleted agent")

    # Print the Agent's response message with optional citation
    response_message = project_client.agents.list_messages(thread_id=thread.id).get_last_message_by_role(
        MessageRole.AGENT
    )

    print("#####################################################")
    print (response_message)

    print("#####################################################")
    if response_message:
        for text_message in response_message.text_messages:
            print(f"Agent response: {text_message.text.value}")
        for annotation in response_message.url_citation_annotations:
            print(f"URL Citation: [{annotation.url_citation.title}]({annotation.url_citation.url})")