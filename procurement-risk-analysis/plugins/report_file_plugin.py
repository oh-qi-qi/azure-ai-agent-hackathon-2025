"""Report file plugin for handling report file creation and data lake upload."""

import json
import uuid
import os
import hashlib
from datetime import datetime
from semantic_kernel.functions.kernel_function_decorator import kernel_function
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.identity import DefaultAzureCredential

class ReportFilePlugin:
    """A plugin for creating report files and uploading them to data lake."""
    
    def __init__(self, connection_string, storage_connection_string=None):
        self.connection_string = connection_string
        self.storage_connection_string = storage_connection_string or os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        self.storage_container = os.getenv("AZURE_STORAGE_CONTAINER", "risk-reports")
        self.report_directory = os.getenv("REPORT_STORAGE_PATH", "reports")
        
        # Create report directory if it doesn't exist
        if not os.path.exists(self.report_directory):
            os.makedirs(self.report_directory)
        
        # Initialize blob service client if connection string is provided
        self.blob_service_client = None
        if self.storage_connection_string:
            self.blob_service_client = BlobServiceClient.from_connection_string(self.storage_connection_string)
        elif os.getenv("AZURE_STORAGE_ACCOUNT_NAME"):
            # Use DefaultAzureCredential if no connection string but account name is provided
            credential = DefaultAzureCredential()
            account_url = f"https://{os.getenv('AZURE_STORAGE_ACCOUNT_NAME')}.blob.core.windows.net"
            self.blob_service_client = BlobServiceClient(account_url, credential=credential)
    
    @kernel_function(description="Saves a report to a file and uploads to data lake")
    def save_report_to_file(self, report_content: str, report_title: str = None, 
                          conversation_id: str = None, report_type: str = "comprehensive") -> str:
        """Saves a report to a file and optionally uploads to data lake.
        
        Args:
            report_content: The full content of the report
            report_title: Optional title for the report
            conversation_id: ID to link the report to a conversation
            report_type: Type of report (comprehensive, schedule, political, etc.)
            
        Returns:
            JSON string with file path and upload details
        """
        try:
            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_id = str(uuid.uuid4())[:8]
            filename = f"risk_report_{report_type}_{timestamp}_{report_id}.md"
            filepath = os.path.join(self.report_directory, filename)
            
            # Add metadata header to report
            metadata_header = f"""---
                report_id: {report_id}
                report_type: {report_type}
                conversation_id: {conversation_id}
                created_at: {datetime.now().isoformat()}
                title: {report_title or 'Equipment Schedule Risk Analysis Report'}
                ---

                """
            
            # Combine metadata and content
            full_content = metadata_header + report_content
            
            # Write to local file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(full_content)
            
            # Calculate file hash
            file_hash = self._calculate_file_hash(filepath)
            
            # Upload to data lake if configured
            blob_url = None
            if self.blob_service_client:
                blob_url = self._upload_to_data_lake(filepath, filename, report_type)
            
            # Return success response
            return json.dumps({
                "success": True,
                "report_id": report_id,
                "filepath": filepath,
                "filename": filename,
                "file_hash": file_hash,
                "blob_url": blob_url,
                "report_type": report_type,
                "conversation_id": conversation_id,
                "created_at": datetime.now().isoformat()
            })
            
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    def _calculate_file_hash(self, filepath: str) -> str:
        """Calculates SHA-256 hash of a file."""
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def _upload_to_data_lake(self, filepath: str, filename: str, report_type: str) -> str:
        """Uploads a file to Azure Data Lake Storage."""
        try:
            # Create container if it doesn't exist
            container_client = self.blob_service_client.get_container_client(self.storage_container)
            if not container_client.exists():
                container_client.create_container()
            
            # Generate blob path with folder structure
            year = datetime.now().strftime("%Y")
            month = datetime.now().strftime("%m")
            blob_path = f"{report_type}/{year}/{month}/{filename}"
            
            # Upload file
            blob_client = container_client.get_blob_client(blob_path)
            with open(filepath, "rb") as data:
                blob_client.upload_blob(
                    data, 
                    overwrite=True,
                    content_settings=ContentSettings(content_type="text/markdown")
                )
            
            # Return blob URL
            return blob_client.url
            
        except Exception as e:
            print(f"Error uploading to data lake: {e}")
            return None
    
    @kernel_function(description="Gets report metadata from database")
    def get_report_metadata(self, report_id: str = None, conversation_id: str = None) -> str:
        """Gets report metadata from database.
        
        Args:
            report_id: Optional report ID to search for
            conversation_id: Optional conversation ID to search for
            
        Returns:
            JSON string with report metadata
        """
        try:
            import pyodbc
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            
            # Build query based on parameters
            query = "SELECT * FROM fact_risk_report WHERE 1=1"
            params = []
            
            if report_id:
                query += " AND report_id = ?"
                params.append(report_id)
            
            if conversation_id:
                query += " AND conversation_id = ?"
                params.append(conversation_id)
            
            query += " ORDER BY created_date DESC"
            
            # Execute query
            cursor.execute(query, params)
            
            # Fetch results
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()
            
            # Convert to list of dictionaries
            results = []
            for row in rows:
                results.append(dict(zip(columns, row)))
            
            # Close connection
            cursor.close()
            conn.close()
            
            return json.dumps(results, default=str)
            
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    @kernel_function(description="Downloads a report file from data lake")
    def download_report_from_data_lake(self, blob_url: str) -> str:
        """Downloads a report file from data lake.
        
        Args:
            blob_url: The URL of the blob to download
            
        Returns:
            JSON string with file content or error
        """
        try:
            if not self.blob_service_client:
                return json.dumps({"error": "Blob service client not configured"})
            
            # Parse blob URL to get container and blob name
            import urllib.parse
            parsed_url = urllib.parse.urlparse(blob_url)
            path_parts = parsed_url.path.split('/')
            container_name = path_parts[1]
            blob_name = '/'.join(path_parts[2:])
            
            # Get blob client
            container_client = self.blob_service_client.get_container_client(container_name)
            blob_client = container_client.get_blob_client(blob_name)
            
            # Download blob
            blob_data = blob_client.download_blob()
            content = blob_data.readall().decode('utf-8')
            
            return json.dumps({
                "success": True,
                "content": content,
                "blob_url": blob_url
            })
            
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    @kernel_function(description="Creates a consolidated report from multiple agent outputs")
    def create_consolidated_report(self, scheduler_output: str, political_output: str = None,
                                 tariff_output: str = None, logistics_output: str = None,
                                 report_title: str = None) -> str:
        """Creates a consolidated report from multiple agent outputs.
        
        Args:
            scheduler_output: Output from the scheduler agent
            political_output: Output from the political risk agent
            tariff_output: Output from the tariff risk agent
            logistics_output: Output from the logistics risk agent
            report_title: Optional title for the report
            
        Returns:
            JSON string with consolidated report content
        """
        try:
            # Create report header
            report_content = f"""# {report_title or 'Comprehensive Equipment Schedule Risk Analysis Report'}

                Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

                ## Executive Summary

                This comprehensive report analyzes equipment schedule risks across multiple dimensions including schedule variance, political risks, tariff risks, and logistics risks. The following sections provide detailed analysis and recommendations for risk mitigation.

                ---

                """
            
            # Add scheduler section
            report_content += """## 1. Schedule Risk Analysis"""
            report_content += self._clean_agent_output(scheduler_output, "SCHEDULER_AGENT")
            report_content += "\n\n---\n\n"
            
            # Add political risk section if available
            if political_output:
                report_content += """## 2. Political Risk Analysis"""
                report_content += self._clean_agent_output(political_output, "POLITICAL_RISK_AGENT")
                report_content += "\n\n---\n\n"
            
            # Add tariff risk section if available
            if tariff_output:
                report_content += """## 3. Tariff Risk Analysis"""
                report_content += self._clean_agent_output(tariff_output, "TARIFF_RISK_AGENT")
                report_content += "\n\n---\n\n"
            
            # Add logistics risk section if available
            if logistics_output:
                report_content += """## 4. Logistics Risk Analysis"""
                report_content += self._clean_agent_output(logistics_output, "LOGISTICS_RISK_AGENT")
                report_content += "\n\n---\n\n"
            
            # Add consolidated recommendations
            report_content += """## 5. Consolidated Recommendations

                Based on the comprehensive analysis above, the following actions are recommended:

                1. **Immediate Actions**
                - Address all high-risk items identified across all risk categories
                - Initiate mitigation strategies for critical path equipment
                - Engage with key stakeholders for risk resolution

                2. **Short-term Actions (1-3 months)**
                - Monitor medium-risk items closely
                - Implement recommended mitigation strategies
                - Establish regular risk review meetings

                3. **Long-term Actions (3+ months)**
                - Review and update risk assessment methodologies
                - Enhance supply chain resilience
                - Develop contingency plans for future risks

                ---

                *This report was generated automatically. For questions or clarifications, please contact the project management team.*
                """
            
            return json.dumps({
                "success": True,
                "content": report_content,
                "generated_at": datetime.now().isoformat()
            })
            
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    def _clean_agent_output(self, output: str, agent_name: str) -> str:
        """Cleans agent output by removing agent prefixes."""
        if output.startswith(f"{agent_name} > "):
            return output[len(f"{agent_name} > "):].strip()
        return output.strip()
