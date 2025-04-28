"""Simple report plugin for PDF generation and data lake upload."""

import json
import uuid
import os
import pyodbc
from datetime import datetime
from semantic_kernel.functions.kernel_function_decorator import kernel_function
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.identity import DefaultAzureCredential
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

class ReportFilePlugin:
    """A plugin for creating PDF reports and uploading them to data lake."""
    
    def __init__(self, connection_string, storage_connection_string=None):
        self.connection_string = connection_string
        self.storage_connection_string = storage_connection_string or os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        self.storage_container = os.getenv("AZURE_STORAGE_CONTAINER", "procurement-expediting-risk-reports")
        self.report_directory = os.getenv("REPORT_STORAGE_PATH", "reports")
        
        # Create report directory if it doesn't exist
        if not os.path.exists(self.report_directory):
            os.makedirs(self.report_directory)
        
        # Initialize blob service client
        self.blob_service_client = None
        if self.storage_connection_string:
            self.blob_service_client = BlobServiceClient.from_connection_string(self.storage_connection_string)
        elif os.getenv("AZURE_STORAGE_ACCOUNT_NAME"):
            credential = DefaultAzureCredential()
            account_url = f"https://{os.getenv('AZURE_STORAGE_ACCOUNT_NAME')}.blob.core.windows.net"
            self.blob_service_client = BlobServiceClient(account_url, credential=credential)
    
    @kernel_function(description="Saves a report to PDF and uploads to data lake")
    def save_report_to_file(self, report_content: str, session_id: str, 
                          conversation_id: str, report_title: str = None) -> str:
        """Saves a report to PDF and uploads to data lake."""
        try:
            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_id = str(uuid.uuid4())[:8]
            filename = f"risk_report_{timestamp}_{report_id}.pdf"
            filepath = os.path.join(self.report_directory, filename)
            
            # Generate PDF
            self._generate_pdf(filepath, report_content, report_title)
            
            # Upload to data lake
            blob_url = self._upload_to_data_lake(filepath, filename)
            
            # Log to database
            self._log_report_to_database(session_id, conversation_id, filename, blob_url)
            
            return json.dumps({
                "success": True,
                "filename": filename,
                "filepath": filepath,
                "blob_url": blob_url,
                "session_id": session_id,
                "conversation_id": conversation_id
            })
            
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    def _generate_pdf(self, filepath: str, content: str, title: str = None):
        """Generates a PDF report."""
        doc = SimpleDocTemplate(filepath, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        
        # Add title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30
        )
        story.append(Paragraph(title or "Equipment Schedule Risk Analysis Report", title_style))
        story.append(Spacer(1, 12))
        
        # Add generation date
        story.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        story.append(Spacer(1, 20))
        
        # Process content - split by sections and format appropriately
        sections = content.split('\n\n')
        
        for section in sections:
            if section.strip():
                # Handle headers
                if section.startswith('#'):
                    header_level = section.count('#', 0, 6)
                    text = section.replace('#', '').strip()
                    
                    if header_level == 1:
                        style = styles['Heading1']
                    elif header_level == 2:
                        style = styles['Heading2']
                    else:
                        style = styles['Heading3']
                    
                    story.append(Paragraph(text, style))
                    story.append(Spacer(1, 12))
                
                # Handle tables (simple markdown tables)
                elif '|' in section and section.count('\n') > 1:
                    table_data = []
                    for line in section.split('\n'):
                        if line.strip() and '---' not in line:
                            cells = [cell.strip() for cell in line.split('|') if cell.strip()]
                            table_data.append(cells)
                    
                    if table_data:
                        t = Table(table_data)
                        t.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, 0), 14),
                            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                            ('FONTSIZE', (0, 1), (-1, -1), 12),
                            ('GRID', (0, 0), (-1, -1), 1, colors.black)
                        ]))
                        story.append(t)
                        story.append(Spacer(1, 12))
                
                # Handle regular paragraphs
                else:
                    story.append(Paragraph(section, styles['Normal']))
                    story.append(Spacer(1, 12))
        
        # Build PDF
        doc.build(story)
    
    def _upload_to_data_lake(self, filepath: str, filename: str) -> str:
        """Uploads a file to Azure Data Lake Storage."""
        try:
            # Create container if it doesn't exist
            container_client = self.blob_service_client.get_container_client(self.storage_container)
            if not container_client.exists():
                container_client.create_container()
            
            # Generate blob path with folder structure
            year = datetime.now().strftime("%Y")
            month = datetime.now().strftime("%m")
            blob_path = f"{year}/{month}/{filename}"
            
            # Upload file
            blob_client = container_client.get_blob_client(blob_path)
            with open(filepath, "rb") as data:
                blob_client.upload_blob(
                    data, 
                    overwrite=True,
                    content_settings=ContentSettings(content_type="application/pdf")
                )
            
            return blob_client.url
            
        except Exception as e:
            print(f"Error uploading to data lake: {e}")
            raise
    
    def _log_report_to_database(self, session_id: str, conversation_id: str, 
                              filename: str, blob_url: str):
        """Logs report metadata to database."""
        try:
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            
            cursor.execute("""
                EXEC sp_LogRiskReport 
                    @session_id = ?,
                    @conversation_id = ?,
                    @filename = ?,
                    @blob_url = ?
            """, (session_id, conversation_id, filename, blob_url))
            
            conn.commit()
            cursor.close()
            conn.close()
            
        except Exception as e:
            print(f"Error logging report to database: {e}")
            raise
    
    @kernel_function(description="Generate report from conversation history")
    def generate_report_from_conversation(self, conversation_id: str, session_id: str) -> str:
        """Generates a report from conversation history."""
        try:
            # Get conversation history from database
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT agent_name, event_time, action, user_query, agent_output
                FROM dim_agent_event_log
                WHERE conversation_id = ?
                ORDER BY event_time
            """, (conversation_id,))
            
            rows = cursor.fetchall()
            
            # Process conversation history into report format
            report_content = ""
            for row in rows:
                agent_name, event_time, action, user_query, agent_output = row
                
                if agent_output and len(agent_output) > 100:  # Only include substantial outputs
                    report_content += f"## {agent_name} - {action}\n\n"
                    report_content += agent_output
                    report_content += "\n\n---\n\n"
            
            cursor.close()
            conn.close()
            
            # Save report
            return self.save_report_to_file(
                report_content=report_content,
                session_id=session_id,
                conversation_id=conversation_id,
                report_title="Conversation History Report"
            )
            
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    @kernel_function(description="Get reports for a session")
    def get_reports(self, session_id: str = None, conversation_id: str = None) -> str:
        """Gets reports for a session or conversation."""
        try:
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            
            cursor.execute("""
                EXEC sp_GetReports 
                    @session_id = ?,
                    @conversation_id = ?
            """, (session_id, conversation_id))
            
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                results.append(dict(zip(columns, row)))
            
            cursor.close()
            conn.close()
            
            return json.dumps(results, default=str)
            
        except Exception as e:
            return json.dumps({"error": str(e)})