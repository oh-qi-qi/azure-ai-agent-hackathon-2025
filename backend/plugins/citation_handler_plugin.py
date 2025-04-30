"""Plugin for retrieving and formatting citations from Bing search."""

import json
from semantic_kernel.functions.kernel_function_decorator import kernel_function

class CitationLoggerPlugin:
    """A plugin for retrieving and formatting citations from Bing search."""
    
    def __init__(self, connection_string=None):
        """Initialize the plugin.
        
        Args:
            connection_string: Not used but kept for compatibility
        """
        self._cached_citations = {}  # Cache citations by thread_id
    
    @kernel_function(description="Get citations from thread and format as markdown")
    def get_formatted_citations(self, thread_id: str) -> str:
        """Retrieve citations from a thread and return as formatted markdown.
        
        Args:
            thread_id: The thread ID to retrieve citations from
            
        Returns:
            str: JSON string with the citations and formatted markdown
        """
        try:
            # Step 1: Retrieve the citations from the thread
            citations = self._get_citations_from_thread(thread_id)
            
            # Step 2: Format the citations as markdown
            markdown = self._format_citations_as_markdown(citations)
            
            # Return the results
            return json.dumps({
                "success": True,
                "citation_count": len(citations),
                "citations": citations,
                "markdown": markdown
            })
                
        except Exception as e:
            print(f"Error in get_formatted_citations: {e}")
            import traceback
            traceback.print_exc()
            return json.dumps({
                "error": str(e),
                "success": False,
                "citation_count": 0,
                "citations": [],
                "markdown": "### References\n\nUnable to retrieve citations."
            })
    
    def _get_citations_from_thread(self, thread_id):
        """Get citations from a thread.
        
        Args:
            thread_id: The thread ID from Azure AI Projects
        
        Returns:
            list: List of citation dictionaries
        """
        # Return cached citations if available
        if thread_id in self._cached_citations:
            return self._cached_citations[thread_id]
            
        try:
            # Get the project client
            from config.settings import get_project_client
            project_client = get_project_client()
            
            if not project_client:
                print("Failed to get project client")
                return []
            
            citations = []
            
            # Get the response message from the thread
            with project_client:
                response_messages = project_client.agents.list_messages(thread_id=thread_id)
                response_message = response_messages.get_last_message_by_role("assistant")
                
                if not response_message:
                    print(f"No response message found in thread {thread_id}")
                    return []
                
                # Extract citations
                if hasattr(response_message, 'url_citation_annotations') and response_message.url_citation_annotations:
                    for annotation in response_message.url_citation_annotations:
                        citation = {
                            "title": annotation.url_citation.title,
                            "url": annotation.url_citation.url,
                            "source": self._extract_source_from_title(annotation.url_citation.title)
                        }
                        citations.append(citation)
                        
                    # Cache the citations
                    self._cached_citations[thread_id] = citations
                    print(f"Retrieved and cached {len(citations)} citations from thread {thread_id}")
                else:
                    print(f"No citation annotations found in thread {thread_id}")
            
            return citations
            
        except Exception as e:
            print(f"Error getting citations from thread: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _extract_source_from_title(self, title):
        """Extract the source name from a citation title.
        
        Args:
            title: The citation title
            
        Returns:
            str: The extracted source name
        """
        # Many citation titles follow the format: "Title - Source, Date"
        if " - " in title:
            parts = title.split(" - ")
            if len(parts) > 1:
                source_part = parts[-1].strip()
                # Further extract if there's a comma with date
                if "," in source_part:
                    return source_part.split(",")[0].strip()
                return source_part
        
        # Default to returning the title itself if no clear source
        return title
    
    def _format_citations_as_markdown(self, citations):
        """Format citations as markdown.
        
        Args:
            citations: List of citation dictionaries
            
        Returns:
            str: Formatted citation section as markdown
        """
        if not citations:
            return "### References\n\nNo citations available."
            
        citation_section = "### References\n\n"
        
        for i, citation in enumerate(citations):
            title = citation.get("title", "Unknown Source")
            url = citation.get("url", "#")
            source = citation.get("source", "Unknown")
            
            citation_section += f"{i+1}. [\"{title}\" - {source}]({url})\n\n"
        
        return citation_section
    
    @kernel_function(description="Enhance political risk output with citations")
    def enhance_political_risk_output(self, agent_output: str, thread_id: str) -> str:
        """Enhances the political risk output by adding proper citations.
        
        Args:
            agent_output: The agent's output content
            thread_id: The thread ID to retrieve citations from
            
        Returns:
            str: Enhanced output with proper citations
        """
        try:
            # Get the citations from the thread
            citations = self._get_citations_from_thread(thread_id)
            
            if not citations:
                print("No citations found, returning original output")
                return agent_output
            
            # Check if the output already has a References section
            if "### References" in agent_output:
                print("Output already has References section, replacing it")
                
                # Replace the existing References section
                import re
                pattern = r'### References.*?(?=###|\Z)'
                references_section = self._format_citations_as_markdown(citations)
                enhanced_output = re.sub(pattern, references_section, agent_output, flags=re.DOTALL)
                
                return enhanced_output
            else:
                # Add the References section at the end
                print("Adding References section to output")
                references_section = self._format_citations_as_markdown(citations)
                
                # Make sure there's a newline before adding references
                if not agent_output.endswith("\n\n"):
                    enhanced_output = agent_output + "\n\n" + references_section
                else:
                    enhanced_output = agent_output + references_section
                
                return enhanced_output
                
        except Exception as e:
            print(f"Error enhancing political risk output: {e}")
            import traceback
            traceback.print_exc()
            return agent_output  # Return original output in case of error