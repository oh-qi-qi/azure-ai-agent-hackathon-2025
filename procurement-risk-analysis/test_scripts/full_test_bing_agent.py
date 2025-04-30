#!/usr/bin/env python
"""Stronger test script to verify Bing search integration with explicit requirements."""

import os
import time
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import MessageRole, BingGroundingTool
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get configuration
project_connection_string = os.getenv("AZURE_AI_AGENT_PROJECT_CONNECTION_STRING")
model_deployment_name = os.getenv("AZURE_AI_AGENT_MODEL_DEPLOYMENT_NAME")
bing_connection_name = os.getenv("BING_CONNECTION_NAME")
bing_api_key = os.getenv("BING_SEARCH_API_KEY")

# Print configuration for debugging
print("=== Configuration ===")
print(f"Project Connection String: {'Set (masked)' if project_connection_string else 'NOT SET'}")
print(f"Model Deployment Name: {model_deployment_name}")
print(f"Bing Connection Name: {bing_connection_name}")
print(f"Bing API Key: {'Set (masked)' if bing_api_key else 'NOT SET'}")
print("====================\n")

# Test JSON data from scheduler agent
TEST_JSON_DATA = """
SCHEDULER_AGENT > json { "projectInfo": [ { "name": "Project A", "location": "Tuas South Avenue 14, Singapore 637312" } ], "manufacturingLocations": [ "Regensburg, Germany" ], "shippingPorts": [ "Hamburg, Germany", "Wilhelmshaven, Germany" ], "receivingPorts": [ "Singapore", "Penang Port" ], "equipmentItems": [ { "code": "123456", "name": "LV Switchgear - 400V/5000A Switchboard-1 (3-Sections)", "origin": "Germany", "destination": "Singapore", "status": "Ahead", "p6DueDate": "2026-02-21", "deliveryDate": "2026-01-21", "variance": -31 }, { "code": "123457", "name": "LV Switchgear - 400V/5000A Switchboard-2 (3-Sections)", "origin": "Germany", "destination": "Singapore", "status": "On-Track / Slightly Ahead", "p6DueDate": "2026-02-25", "deliveryDate": "2026-02-20", "variance": -5 }, { "code": "123458", "name": "LV Switchgear - 400V/5000A Switchboard-3 (3-Sections)", "origin": "Germany", "destination": "Singapore", "status": "Late", "p6DueDate": "2026-02-27", "deliveryDate": "2026-03-07", "variance": 8 } ], "searchQuery": { "political": "Political risks manufacturing exports Germany to Singapore Electrical Equipment current issues", "tariff": "Germany Singapore tariffs Electrical Equipment trade agreements", "logistics": "Hamburg to Singapore shipping route issues logistics current delays" } } 
"""

# Stronger test instructions with more explicit requirements
TEST_INSTRUCTIONS = """
You are a Political Risk Intelligence Agent specifically tasked with finding POLITICAL RISKS using Bing Search.

CRITICAL MISSION: You MUST identify at least 5 distinct political risks from Bing Search results.
- Cite only reputable sources with dates
- Do not include blogs, social media, or undated/unverified content
- Do not include non-political risks (e.g., labor, health, environmental)

CRITICAL REQUIREMENTS:
- You MUST include at least 5 political risks with citations
- Each risk MUST have a specific source from your search results
- You MUST focus only on POLITICAL risks (government policy, regulations, sanctions, trade relations, tariff)
- DO NOT use risks you already know - ONLY use what you find in the search
- Be specific about dates, countries, and risk factors

Follow these specific steps:
1. Extract the exact search query from "searchQuery.political" in the JSON
2. Perform a SINGLE Bing search using the EXACT query string from the JSON and ensure all countries identified are covered
3. THOROUGHLY analyze the search results to identify AT LEAST 5 distinct political risks
4. For each risk identified, include a direct source citation
5. DO NOT hallucinate or make up risks - base your analysis EXCLUSIVELY on search results
6. Rate each risk on a 0-5 scale with specific reasoning

Your final response MUST contain:

1. Brief overview of how you used Bing Search
   - Include the exact query used
   - Number of search results analyzed

2. A analysis description of all the risks in a paragraph with 3 to 4 sentences

3. Political Risk Table with EXACTLY 5 OR MORE rows:
   | Country | Risk Information  | Likelihood (0-5) | Reasoning | Publication Date | Citation Title | Citation Name | Citation URL |
   - List each source as a row
   - Only one country per row
   - Publication Date format should be "Month Year" (e.g., "April 2025")

4. Equipment Impact Analysis:
   - based on politcal risk how it can affect the schedule of the equipment.

5. Mitigation Recommendations
   - Focus on actions the project team can directly implement
   - Include schedule adjustments, contingency plans, and contract protections
   - Avoid suggesting government-level policy changes or diplomatic solutions

If you cannot find 5 political risks, explicitly say "I could not find 5 political risks from the search results" and provide what you did find.

Prepend your response with "POLITICAL_RISK_AGENT > "
"""

def main():
    """Run the stronger Bing search test."""
    print("Starting stronger Bing search test...")
    start_time = time.time()
    
    try:
        # Create project client
        print("Creating project client...")
        project_client = AIProjectClient.from_connection_string(
            credential=DefaultAzureCredential(
                exclude_environment_credential=True,
                exclude_managed_identity_credential=True
            ),
            conn_str=project_connection_string
        )
        
        with project_client:
            print("\nCreating test agent with Bing tool...")
            
            # Initialize Bing tool
            bing_tool = None
            
            # Method 1: Using named connection
            if bing_connection_name:
                print(f"Using named connection: {bing_connection_name}")
                try:
                    bing_connection = project_client.connections.get(connection_name=bing_connection_name)
                    print(f"Retrieved Bing connection ID: {bing_connection.id}")
                    bing_tool = BingGroundingTool(connection_id=bing_connection.id)
                except Exception as e:
                    print(f"Error getting named connection: {e}")
                    if bing_api_key:
                        # Fall back to API key method
                        print("Falling back to API key method")
                        bing_tool = BingGroundingTool(api_key=bing_api_key)
            
            # Method 2: Direct API key
            elif bing_api_key:
                print("Using direct API key method")
                bing_tool = BingGroundingTool(api_key=bing_api_key)
            
            if not bing_tool:
                raise ValueError("Could not initialize Bing tool. Please set BING_CONNECTION_NAME or BING_SEARCH_API_KEY.")
            
            # Create test agent
            agent = None
            try:
                print("Creating agent with stronger Bing test instructions...")
                agent = project_client.agents.create_agent(
                    model=model_deployment_name,
                    name="bing-test-agent",
                    instructions=TEST_INSTRUCTIONS,
                    tools=bing_tool.definitions,
                    headers={"x-ms-enable-preview": "true"}
                )
                print(f"Created agent with ID: {agent.id}")
            except Exception as e:
                print(f"ERROR: Failed to create agent: {str(e)}")
                return
            
            # Create thread
            thread = None
            try:
                thread = project_client.agents.create_thread()
                print(f"Created thread with ID: {thread.id}")
            except Exception as e:
                print(f"ERROR: Failed to create thread: {str(e)}")
                if agent:
                    project_client.agents.delete_agent(agent.id)
                    print("Cleaned up agent")
                return
            
            # Create message
            message = None
            try:
                message = project_client.agents.create_message(
                    thread_id=thread.id,
                    role=MessageRole.USER,
                    content=TEST_JSON_DATA
                )
                print(f"Created message with ID: {message.id}")
            except Exception as e:
                print(f"ERROR: Failed to create message: {str(e)}")
                if agent:
                    project_client.agents.delete_agent(agent.id)
                    print("Cleaned up agent")
                return
            
            # Process the run
            run = None
            try:
                print("\nProcessing run...")
                print("This may take a few minutes. Please wait...")
                run = project_client.agents.create_and_process_run(
                    thread_id=thread.id,
                    agent_id=agent.id
                )
                print(f"Run finished with status: {run.status}")
                
                if run.status == "failed":
                    print(f"Run failed: {run.last_error}")
            except Exception as e:
                print(f"ERROR: Failed to process run: {str(e)}")
                if agent:
                    project_client.agents.delete_agent(agent.id)
                    print("Cleaned up agent")
                return
            
            # Print response
            response_message = None
            try:
                response_message = project_client.agents.list_messages(thread_id=thread.id).get_last_message_by_role(
                    MessageRole.AGENT
                )
            except Exception as e:
                print(f"ERROR: Failed to retrieve response message: {str(e)}")

            print("###############################")

            print(response_message)

            print("###############################")
            if response_message:
                print("\n=== AGENT RESPONSE ===")
                for text_message in response_message.text_messages:
                    print(text_message.text.value)
                
                print("\n=== CITATIONS ===")
                citations = []
                try:
                    citations = getattr(response_message, 'url_citation_annotations', [])
                    for annotation in citations:
                        print(f"URL Citation: [{annotation.url_citation.title}]({annotation.url_citation.url})")
                except Exception as e:
                    print(f"Error accessing citations: {e}")
                
                # Check if Bing search was successfully used
                has_citations = len(citations) > 0
                print(f"\n=== RESULT ===")
                print(f"Bing search {'WAS' if has_citations else 'was NOT'} successfully used")
                print(f"Found {len(citations)} citations")
                
                # Check if there are at least 5 risks
                import re
                response_text = ""
                for text_message in response_message.text_messages:
                    response_text += text_message.text.value
                
                # Count table rows (rough estimate)
                risk_table_rows = len(re.findall(r'\|\s*[A-Za-z]+\s*\|', response_text)) - 1  # Subtract header
                
                print(f"Approximately {risk_table_rows} risks identified in table")
                if risk_table_rows < 5:
                    print("WARNING: Less than 5 risks were identified")
                
                # Additional test recommendation
                if not has_citations:
                    print("\nTROUBLESHOOTING TIPS:")
                    print("1. Check that your Bing API key is valid")
                    print("2. Check that your Bing connection is properly configured")
                    print("3. Try using the direct API key method if using a named connection")
                    print("4. Check that the model deployment supports Bing search")
            else:
                print("No response received")
            
            # Clean up
            # try:
            #     if agent:
            #         project_client.agents.delete_agent(agent.id)
            #         print("Test agent deleted")
            # except Exception as e:
            #     print(f"Warning: Failed to clean up agent: {e}")

    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()
    
    # Print execution time
    elapsed_time = time.time() - start_time
    print(f"\nTest completed in {elapsed_time:.2f} seconds")

if __name__ == "__main__":
    main()