"""Improved ReportFilePlugin with md2docx_python integration."""

import json
import uuid
import os
import pyodbc
from datetime import datetime
import re
import traceback
import tempfile
from semantic_kernel.functions.kernel_function_decorator import kernel_function

# Import the md2docx_python library
try:
    from md2docx_python.src.md2docx_python import markdown_to_word
    MD2DOCX_AVAILABLE = True
except ImportError:
    print("md2docx_python not available. Install with: pip install md2docx-python")
    MD2DOCX_AVAILABLE = False

# Import Azure storage modules
try:
    from azure.storage.blob import BlobServiceClient, ContentSettings
    from azure.identity import DefaultAzureCredential
    AZURE_STORAGE_AVAILABLE = True
except ImportError:
    print("Azure Storage SDK not available. Uploads to data lake will not work.")
    AZURE_STORAGE_AVAILABLE = False

class ReportFilePlugin:
    """A plugin for creating Word reports and uploading them to data lake."""
    
    def __init__(self, connection_string, storage_connection_string=None):
        """Initialize the plugin with improved error handling.
        
        Args:
            connection_string: Database connection string
            storage_connection_string: Optional storage connection string
        """
        self.connection_string = connection_string
        self.storage_connection_string = storage_connection_string or os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        self.storage_container = os.getenv("AZURE_STORAGE_CONTAINER", "procurement-expediting-risk-reports")
        self.report_directory = os.getenv("REPORT_STORAGE_PATH", "reports")
        
        # Create report directory if it doesn't exist
        try:
            if not os.path.exists(self.report_directory):
                os.makedirs(self.report_directory)
                print(f"Created report directory: {self.report_directory}")
        except Exception as e:
            print(f"Error creating report directory: {e}")
            # Use a default that should always work
            self.report_directory = "."
        
        # Initialize blob service client
        self.blob_service_client = None
        if AZURE_STORAGE_AVAILABLE:
            try:
                if self.storage_connection_string:
                    try:
                        self.blob_service_client = BlobServiceClient.from_connection_string(self.storage_connection_string)
                        print("Initialized blob service client from connection string")
                    except Exception as e:
                        print(f"Error initializing blob service client from connection string: {e}")
                elif os.getenv("AZURE_STORAGE_ACCOUNT_NAME"):
                    try:
                        credential = DefaultAzureCredential()
                        account_url = f"https://{os.getenv('AZURE_STORAGE_ACCOUNT_NAME')}.blob.core.windows.net"
                        self.blob_service_client = BlobServiceClient(account_url, credential=credential)
                        print("Initialized blob service client from Azure credentials")
                    except Exception as e:
                        print(f"Error initializing blob service client from Azure credentials: {e}")
            except Exception as e:
                print(f"Error initializing blob service client: {e}")
    
    @kernel_function(description="Saves a report to Word document and uploads to data lake")
    def save_report_to_file(self, report_content: str, session_id: str, 
                          conversation_id: str, report_title: str = None) -> str:
        """Saves a report to Word document and uploads to data lake with improved error handling.
        
        Args:
            report_content: The report content in markdown format
            session_id: The session ID
            conversation_id: The conversation ID
            report_title: Optional report title
            
        Returns:
            str: JSON string with result information
        """
        try:
            # Check if md2docx is available
            if not MD2DOCX_AVAILABLE:
                print("md2docx_python not available. Cannot generate Word document.")
                return json.dumps({
                    "error": "Word document generation is not available. md2docx_python library is missing.",
                    "success": False,
                    "stage": "initialization"
                })
            
            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_id = str(uuid.uuid4())[:8]
            docx_filename = f"risk_report_{timestamp}_{report_id}.docx"
            docx_filepath = os.path.join(self.report_directory, docx_filename)
            
            # Print debug info
            print(f"Saving report to file: {docx_filepath}")
            print(f"Report content length: {len(report_content)} characters")
            print(f"Report title: {report_title}")
            
            # First create a temporary markdown file
            temp_md_file = None
            try:
                # Create a temporary file to store markdown content
                with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as temp:
                    temp.write(report_content)
                    temp_md_file = temp.name
                    print(f"Created temporary markdown file: {temp_md_file}")
                
                # Generate Word document with detailed error handling
                self._generate_word_document(temp_md_file, docx_filepath, report_title)
                print(f"Successfully generated Word document: {docx_filepath}")
            except Exception as word_error:
                print(f"Error generating Word document: {word_error}")
                traceback.print_exc()
                return json.dumps({
                    "error": f"Word document generation failed: {str(word_error)}",
                    "stage": "word_generation",
                    "success": False
                })
            finally:
                # Clean up temporary markdown file
                if temp_md_file and os.path.exists(temp_md_file):
                    try:
                        os.remove(temp_md_file)
                        print(f"Deleted temporary markdown file: {temp_md_file}")
                    except Exception as e:
                        print(f"Error deleting temporary markdown file: {e}")
            
            # Upload to data lake with detailed error handling
            blob_url = None
            try:
                if self.blob_service_client and AZURE_STORAGE_AVAILABLE:
                    blob_url = self._upload_to_data_lake(docx_filepath, docx_filename)
                    print(f"Successfully uploaded to data lake: {blob_url}")
                else:
                    print("No blob service client available, skipping upload")
                    # Use a local file URL as fallback
                    blob_url = f"file://{os.path.abspath(docx_filepath)}"
                    print(f"Using local file URL: {blob_url}")
            except Exception as upload_error:
                print(f"Error uploading to data lake: {upload_error}")
                traceback.print_exc()
                # Continue anyway with local file path
                blob_url = f"file://{os.path.abspath(docx_filepath)}"
                print(f"Using local file URL as fallback: {blob_url}")
            
            # Log to database with detailed error handling
            try:
                self._log_report_to_database(session_id, conversation_id, docx_filename, blob_url)
                print("Successfully logged report to database")
            except Exception as db_error:
                print(f"Error logging report to database: {db_error}")
                traceback.print_exc()
                # Continue anyway
            
            # Return success information
            return json.dumps({
                "success": True,
                "filename": docx_filename,
                "filepath": docx_filepath,
                "blob_url": blob_url,
                "session_id": session_id,
                "conversation_id": conversation_id,
                "report_id": report_id
            })
            
        except Exception as e:
            print(f"Error in save_report_to_file: {e}")
            traceback.print_exc()
            return json.dumps({
                "error": str(e),
                "success": False,
                "stage": "overall_process"
            })
    
    def _generate_word_document(self, markdown_filepath: str, docx_filepath: str, title: str = None):
        """Generates a Word document from markdown.
        
        Args:
            markdown_filepath: Input markdown filepath
            docx_filepath: Output Word document filepath
            title: Optional report title
        """
        # Check if md2docx_python is available
        if not MD2DOCX_AVAILABLE:
            raise ImportError("md2docx_python is not available. Cannot generate Word document.")
        
        # Print debug info
        print(f"Generating Word document: {docx_filepath}")
        
        try:
            # Convert Markdown to Word document using md2docx_python
            markdown_to_word(markdown_filepath, docx_filepath)
            print(f"Successfully converted markdown to Word document: {docx_filepath}")
            
            # Additional processing or customization can be added here if needed
            
            return True
            
        except Exception as e:
            print(f"Error generating Word document: {e}")
            traceback.print_exc()
            raise
    
    def _upload_to_data_lake(self, filepath: str, filename: str) -> str:
        """Uploads a file to Azure Data Lake Storage with improved error handling.
        
        Args:
            filepath: Local file path
            filename: File name to use in storage
            
        Returns:
            str: URL of the uploaded blob
        """
        try:
            # Check if blob service client is available
            if not self.blob_service_client or not AZURE_STORAGE_AVAILABLE:
                print("Blob service client not available, cannot upload to data lake")
                # Return a local file URL as fallback
                return f"file://{os.path.abspath(filepath)}"
            
            try:
                # Create container if it doesn't exist
                container_client = self.blob_service_client.get_container_client(self.storage_container)
                if not container_client.exists():
                    container_client.create_container()
                    print(f"Created container: {self.storage_container}")
            except Exception as container_error:
                print(f"Error with container: {container_error}")
                # Try to get the container anyway, it might just be a permissions issue
                container_client = self.blob_service_client.get_container_client(self.storage_container)
            
            # Generate blob path with folder structure
            year = datetime.now().strftime("%Y")
            month = datetime.now().strftime("%m")
            blob_path = f"{year}/{month}/{filename}"
            
            # Upload file
            blob_client = container_client.get_blob_client(blob_path)
            
            # Check if file exists
            if not os.path.exists(filepath):
                print(f"File not found: {filepath}")
                return f"file_not_found:{filepath}"
            
            with open(filepath, "rb") as data:
                blob_client.upload_blob(
                    data, 
                    overwrite=True,
                    content_settings=ContentSettings(content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                )
            
            print(f"File uploaded successfully: {blob_client.url}")
            return blob_client.url
            
        except Exception as e:
            print(f"Error in _upload_to_data_lake: {e}")
            traceback.print_exc()
            # Return a local file URL as fallback
            return f"file://{os.path.abspath(filepath)}"
    
    def _log_report_to_database(self, session_id: str, conversation_id: str, 
                              filename: str, blob_url: str):
        """Logs report metadata to database with improved error handling.
        
        Args:
            session_id: The session ID
            conversation_id: The conversation ID
            filename: The report filename
            blob_url: The report URL
        """
        try:
            # Connect to database
            try:
                conn = pyodbc.connect(self.connection_string)
            except Exception as conn_error:
                print(f"Error connecting to database: {conn_error}")
                return False
            
            cursor = conn.cursor()
            
            # Try to execute the stored procedure
            try:
                cursor.execute("""
                    EXEC sp_LogRiskReport 
                        @session_id = ?,
                        @conversation_id = ?,
                        @filename = ?,
                        @blob_url = ?
                """, (session_id, conversation_id, filename, blob_url))
                
                conn.commit()
                print("Successfully logged report to database")
                
            except Exception as sp_error:
                print(f"Error executing stored procedure: {sp_error}")
                
                # Try direct insert as fallback
                try:
                    cursor.execute("""
                        INSERT INTO fact_risk_report (
                            session_id, 
                            conversation_id, 
                            filename,
                            blob_url,
                            report_type,
                            created_date
                        )
                        VALUES (?, ?, ?, ?, 'comprehensive', GETDATE())
                    """, (session_id, conversation_id, filename, blob_url))
                    
                    conn.commit()
                    print("Successfully inserted report using direct SQL")
                    
                except Exception as insert_error:
                    print(f"Error inserting report: {insert_error}")
                    conn.rollback()
                    raise
            
            cursor.close()
            conn.close()
            return True
            
        except Exception as e:
            print(f"Error in _log_report_to_database: {e}")
            traceback.print_exc()
            return False
    
    @kernel_function(description="Generates a report from conversation history")
    def generate_report_from_conversation(self, conversation_id: str, session_id: str, report_type: str = "comprehensive") -> str:
        """Generates a Word report from a conversation history.
        
        Args:
            conversation_id: The conversation ID
            session_id: The session ID
            report_type: The report type (e.g., "comprehensive", "political", "schedule")
            
        Returns:
            str: JSON string with result information
        """
        try:
            # Retrieve the conversation history from the database
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            
            # Query to get the conversation log
            cursor.execute("""
                SELECT 
                    agent_name, 
                    action, 
                    event_time, 
                    user_query, 
                    agent_output,
                    result_summary
                FROM 
                    dim_agent_event_log
                WHERE 
                    conversation_id = ?
                ORDER BY 
                    event_time
            """, (conversation_id,))
            
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            if not rows:
                return json.dumps({
                    "error": "No conversation history found for the provided conversation ID",
                    "success": False
                })
            
            # Extract relevant information and build the report
            report_content += f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            
            # Add executive summary
            report_content += "## Executive Summary\n\n"
            report_content += "This report was automatically generated from a conversation about equipment schedule risks.\n\n"
            
            # Add key findings section
            report_content += "## Key Findings\n\n"
            
            # Extract agent outputs - focus particularly on REPORTING_AGENT and SCHEDULER_AGENT
            report_sections = {
                "user_queries": [],
                "schedule_analysis": [],
                "political_analysis": [],
                "tariff_analysis": [],
                "logistics_analysis": [],
                "report_generation": []
            }
            
            # Sort events by time and type
            for row in rows:
                agent_name = row[0]
                action = row[1]
                user_query = row[3]
                agent_output = row[4]
                
                # Save user queries
                if action == "User Query" and user_query:
                    report_sections["user_queries"].append(user_query)
                
                # Save agent outputs
                if agent_output:
                    if "SCHEDULER_AGENT" in agent_name:
                        report_sections["schedule_analysis"].append(agent_output)
                    elif "POLITICAL_RISK_AGENT" in agent_name:
                        report_sections["political_analysis"].append(agent_output)
                    elif "TARIFF_RISK_AGENT" in agent_name:
                        report_sections["tariff_analysis"].append(agent_output)
                    elif "LOGISTICS_RISK_AGENT" in agent_name:
                        report_sections["logistics_analysis"].append(agent_output)
                    elif "REPORTING_AGENT" in agent_name:
                        report_sections["report_generation"].append(agent_output)
            
            # Add user queries section
            if report_sections["user_queries"]:
                report_content += "### User Questions\n\n"
                for query in report_sections["user_queries"]:
                    report_content += f"- {query}\n"
                report_content += "\n"
            
            # Add relevant content from each agent - prioritize REPORTING_AGENT output
            if report_sections["report_generation"]:
                # Extract the most comprehensive report
                comprehensive_report = max(report_sections["report_generation"], key=len)
                
                # Clean up the report (remove agent prefix and any debugging info)
                comprehensive_report = re.sub(r'REPORTING_AGENT >\s*', '', comprehensive_report)
                comprehensive_report = re.sub(r'```\s*Agent Name:.*?```', '', comprehensive_report, flags=re.DOTALL)
                comprehensive_report = re.sub(r'\*\*Step \d+:.*?Stage\*\*.*?(?=\*\*Step|\*\*Comprehensive|\Z)', '', comprehensive_report, flags=re.DOTALL)
                
                # Use the comprehensive report as the main content
                report_content = comprehensive_report
            else:
                # If no reporting agent output, compile information from other agents
                for section_name, section_items in [
                    ("Schedule Risk Analysis", report_sections["schedule_analysis"]),
                    ("Political Risk Analysis", report_sections["political_analysis"]),
                    ("Tariff Risk Analysis", report_sections["tariff_analysis"]),
                    ("Logistics Risk Analysis", report_sections["logistics_analysis"])
                ]:
                    if section_items:
                        report_content += f"## {section_name}\n\n"
                        # Use the most comprehensive analysis (usually the longest one)
                        best_analysis = max(section_items, key=len)
                        # Clean up the analysis (remove agent prefix)
                        best_analysis = re.sub(r'.*_AGENT >\s*', '', best_analysis)
                        # Extract the most relevant sections
                        analysis_sections = re.split(r'##\s+', best_analysis)
                        for section in analysis_sections[1:]:  # Skip the first split result
                            report_content += f"### {section}\n\n"
            
            # Generate the report file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_id = str(uuid.uuid4())[:8]
            
            # Save the report to a file
            result = self.save_report_to_file(
                report_content=report_content,
                session_id=session_id,
                conversation_id=conversation_id,
                report_title=f"Comprehensive Risk Report - {timestamp}"
            )
            
            return result
            
        except Exception as e:
            print(f"Error generating report from conversation: {e}")
            traceback.print_exc()
            return json.dumps({
                "error": str(e),
                "success": False
            })
    
    @kernel_function(description="Gets all available reports")
    def get_reports(self, session_id: str = None, conversation_id: str = None) -> str:
        """Gets all available reports with optional filtering.
        
        Args:
            session_id: Optional session ID to filter by
            conversation_id: Optional conversation ID to filter by
            
        Returns:
            str: JSON string with the reports
        """
        try:
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            
            # Build query parameters based on filters
            params = []
            where_clauses = []
            
            if session_id:
                where_clauses.append("session_id = ?")
                params.append(session_id)
                
            if conversation_id:
                where_clauses.append("conversation_id = ?")
                params.append(conversation_id)
            
            # Build the query
            query = "SELECT * FROM fact_risk_report"
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
            query += " ORDER BY created_date DESC"
            
            # Execute the query
            cursor.execute(query, params)
            
            # Fetch results
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()
            
            # Convert to list of dictionaries
            reports = []
            for row in rows:
                reports.append(dict(zip(columns, row)))
            
            cursor.close()
            conn.close()
            
            # Return as JSON
            return json.dumps(reports, default=str)
            
        except Exception as e:
            print(f"Error getting reports: {e}")
            traceback.print_exc()
            return json.dumps({
                "error": str(e)
            })