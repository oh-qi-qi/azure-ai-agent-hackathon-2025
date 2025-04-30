"""Plugin for converting political risk output to standardized JSON."""

import json
import uuid
import re
import pyodbc
from datetime import datetime
from semantic_kernel.functions.kernel_function_decorator import kernel_function

class PoliticalRiskJsonPlugin:
    """Plugin for converting political risk agent output to JSON and storing in event log."""
    
    def __init__(self, connection_string=None):
        """Initialize the plugin.
        
        Args:
            connection_string: Database connection string for event log storage
        """
        self.connection_string = connection_string
    
    @kernel_function(description="Convert political risk analysis to JSON format")
    def convert_to_json(self, risk_analysis: str) -> str:
        """Convert political risk analysis to standardized JSON format.
        
        Args:
            risk_analysis: The complete risk analysis text from the political risk agent
            
        Returns:
            str: A JSON string containing the structured risk data
        """
        try:
            # Initialize the structure
            result = {
                "political_risks": [],
                "timestamp": datetime.now().isoformat()
            }
            
            # Extract from markdown table format (using the format from your example)
            # Pattern to match table rows (not the header row)
            table_pattern = r"\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*(\d+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|"
            
            # Find all matches
            matches = re.findall(table_pattern, risk_analysis)
            
            # Process each match
            for match in matches:
                if len(match) >= 9:  # Ensure we have enough columns
                    # Extract the risk information
                    country = match[0].strip()
                    political_type = match[1].strip()
                    risk_info = match[2].strip()
                    likelihood = match[3].strip()
                    likelihood_reasoning = match[4].strip()
                    pub_date = match[5].strip()
                    citation_title = match[6].strip()
                    source_name = match[7].strip()
                    url = match[8].strip()
                    
                    # Skip header row if it was matched
                    if country.lower() == "country" and "political type" in political_type.lower():
                        continue
                    
                    # Add to political_risks list
                    risk_entry = {
                        "country": country,
                        "political_type": political_type,
                        "risk_information": risk_info,
                        "likelihood": int(likelihood) if likelihood.isdigit() else 0,
                        "likelihood_reasoning": likelihood_reasoning,
                        "publication_date": pub_date,
                        "citation_title": citation_title,
                        "citation_name": source_name,
                        "citation_url": url
                    }
                    result["political_risks"].append(risk_entry)
            
            # Extract query information if available
            query_match = re.search(r'query:\s*"([^"]+)"', risk_analysis, re.IGNORECASE)
            if query_match:
                result["search_query"] = query_match.group(1)
            else:
                # Try another pattern
                query_match = re.search(r'using the query:?\s*"([^"]+)"', risk_analysis, re.IGNORECASE)
                if query_match:
                    result["search_query"] = query_match.group(1)
            
            # Extract the number of search results analyzed
            results_match = re.search(r'A total of (\d+) search results', risk_analysis)
            if results_match:
                result["search_results_count"] = int(results_match.group(1))
            
            # Extract equipment impact analysis
            impact_match = re.search(r'Equipment Impact Analysis.*?([\s\S]*?)(?=###|\Z)', risk_analysis, re.DOTALL)
            if impact_match:
                result["equipment_impact"] = impact_match.group(1).strip()
            
            # Extract mitigation recommendations
            recommendations_match = re.search(r'Mitigation Recommendations.*?([\s\S]*?)(?=###|\Z)', risk_analysis, re.DOTALL)
            if recommendations_match:
                result["mitigation_recommendations"] = recommendations_match.group(1).strip()
            
            # Extract analysis description
            analysis_match = re.search(r'Analysis Description.*?([\s\S]*?)(?=###|\Z)', risk_analysis, re.DOTALL)
            if analysis_match:
                result["analysis_description"] = analysis_match.group(1).strip()
            
            # Return as JSON string
            return json.dumps(result, indent=2)
            
        except Exception as e:
            print(f"Error converting political risk analysis to JSON: {e}")
            import traceback
            traceback.print_exc()
            return json.dumps({
                "error": str(e),
                "political_risks": [],
                "timestamp": datetime.now().isoformat()
            })
    

    @kernel_function(description="Store political risk JSON in agent event log")
    def store_political_json_output_agent_event(self, risk_analysis: str, 
                                            agent_name: str, 
                                            conversation_id: str, 
                                            session_id: str) -> str:
        """Store political risk JSON in agent event log."""
        try:
            if not self.connection_string:
                return json.dumps({"error": "No database connection string provided"})
            
            # First convert to JSON
            json_data = self.convert_to_json(risk_analysis)
            
            # Connect to database
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            
            # Generate a unique event ID
            event_id = str(uuid.uuid4())
            
            # Insert into agent event log
            cursor.execute("""
                INSERT INTO dim_agent_event_log 
                (event_id, agent_name, event_time, action, result_summary, 
                user_query, agent_output, conversation_id, session_id)
                VALUES
                (?, ?, GETDATE(), ?, ?, NULL, ?, ?, ?)
            """, (
                event_id,
                agent_name, 
                "Political Risk JSON Data",
                f"Structured JSON data with {len(json.loads(json_data).get('political_risks', []))} political risks",
                json_data,
                conversation_id,
                session_id
            ))
            
            # Commit and close
            conn.commit()
            cursor.close()
            conn.close()
            
            return json.dumps({
                "success": True,
                "message": "Political risk JSON data stored in agent event log",
                "event_id": event_id,
                "json_data": json.loads(json_data)
            })
            
        except Exception as e:
            print(f"Error storing political risk JSON: {e}")
            import traceback
            traceback.print_exc()
            return json.dumps({
                "error": str(e),
                "message": "Failed to store political risk JSON in event log"
            })

    @kernel_function(description="Extract citations from political risk analysis")
    def extract_citations(self, risk_analysis: str) -> str:
        """Extract citations from political risk analysis.
        
        Args:
            risk_analysis: The complete risk analysis text from the political risk agent
            
        Returns:
            str: JSON string with the extracted citations
        """
        try:
            citations = []
            
            # Extract from markdown table format
            table_pattern = r"\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*(\d+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|"
            matches = re.findall(table_pattern, risk_analysis)
            
            for match in matches:
                if len(match) >= 9:
                    country = match[0].strip()
                    political_type = match[1].strip()
                    risk_info = match[2].strip()
                    pub_date = match[5].strip()
                    citation_title = match[6].strip()
                    source_name = match[7].strip()
                    url = match[8].strip()
                    
                    # Skip header row
                    if country.lower() == "country" and "political type" in political_type.lower():
                        continue
                    
                    # Create citation entry
                    citation = {
                        "title": citation_title,
                        "source": source_name,
                        "url": url,
                        "publication_date": pub_date,
                        "country": country,
                        "risk_type": political_type,
                        "risk_info": risk_info
                    }
                    
                    # Add to list if not already present
                    if not any(c.get("url") == url and c.get("title") == citation_title for c in citations):
                        citations.append(citation)
            
            # Return as JSON string
            return json.dumps({
                "citations": citations,
                "count": len(citations),
                "timestamp": datetime.now().isoformat()
            }, indent=2)
            
        except Exception as e:
            print(f"Error extracting citations: {e}")
            return json.dumps({
                "error": str(e),
                "citations": [],
                "count": 0
            })
