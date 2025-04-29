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
        """Generates a PDF report with improved table formatting.
        
        Args:
            filepath: Output filepath
            content: Report content in markdown format
            title: Optional report title
        """
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import PageBreak
        from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
        from datetime import datetime
        
        # Create the document with appropriate margins
        doc = SimpleDocTemplate(
            filepath, 
            pagesize=letter,
            leftMargin=0.5*inch,
            rightMargin=0.5*inch,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch
        )
        
        # Create custom styles
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=10,
            textColor=colors.darkblue,
            alignment=TA_CENTER
        )
        
        subtitle_style = ParagraphStyle(
            'Subtitle',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.darkgrey,
            alignment=TA_CENTER
        )
        
        header1_style = ParagraphStyle(
            'Header1',
            parent=styles['Heading1'],
            fontSize=14,
            spaceBefore=10,
            spaceAfter=6,
            textColor=colors.darkblue
        )
        
        header2_style = ParagraphStyle(
            'Header2',
            parent=styles['Heading2'],
            fontSize=12,
            spaceBefore=8,
            spaceAfter=4,
            textColor=colors.darkblue
        )
        
        header3_style = ParagraphStyle(
            'Header3',
            parent=styles['Heading3'],
            fontSize=11,
            spaceBefore=6,
            spaceAfter=3,
            textColor=colors.darkblue
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=10,
            spaceAfter=5
        )
        
        bullet_style = ParagraphStyle(
            'BulletStyle',
            parent=styles['Normal'],
            fontSize=10,
            leftIndent=20,
            spaceAfter=3
        )
        
        # Story is the list of flowables that will be added to the document
        story = []
        
        # Add title
        story.append(Paragraph(title or "Comprehensive Risk Report", title_style))
        
        # Add generation date
        story.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", subtitle_style))
        story.append(Spacer(1, 12))
        
        # Table style for all tables
        table_style_base = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.darkblue),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ]
        
        # Process content - split by sections
        import re
        
        # Process content - handle markdown headers and tables specially 
        sections = []
        current_section = None
        current_content = []
        
        for line in content.split('\n'):
            # Check for headers
            header_match = re.match(r'^(#+)\s+(.*)', line)
            if header_match:
                # Save the previous section
                if current_section and current_content:
                    sections.append((current_section, '\n'.join(current_content)))
                    current_content = []
                    
                # Start a new section
                header_level = len(header_match.group(1))
                header_text = header_match.group(2)
                current_section = (header_level, header_text)
            else:
                # Add to current content
                if current_section:
                    current_content.append(line)
        
        # Add the last section
        if current_section and current_content:
            sections.append((current_section, '\n'.join(current_content)))
        
        # Process each section
        for section in sections:
            header_level, header_text = section[0]
            content_text = section[1]
            
            # Add header
            if header_level == 1:
                story.append(Paragraph(header_text, header1_style))
            elif header_level == 2:
                story.append(Paragraph(header_text, header2_style))
            else:
                story.append(Paragraph(header_text, header3_style))
            
            story.append(Spacer(1, 4))
            
            # Check for tables in the content
            if '|' in content_text and '\n' in content_text:
                # This might be a table
                lines = content_text.split('\n')
                table_lines = []
                
                for line in lines:
                    if '|' in line:
                        table_lines.append(line)
                    elif table_lines and (line.strip() == '' or '---' in line):
                        # Skip empty lines and separator lines within tables
                        continue
                    else:
                        # Process non-table content
                        if table_lines:
                            # We've found a table previously, process it now
                            table_data = []
                            
                            for table_line in table_lines:
                                # Split by | but remove the first and last empty cells
                                row = [cell.strip() for cell in table_line.split('|')]
                                if row and row[0] == '':
                                    row = row[1:]
                                if row and row[-1] == '':
                                    row = row[:-1]
                                    
                                if row:
                                    table_data.append(row)
                            
                            # Skip delimiter rows
                            filtered_table_data = []
                            for i, row in enumerate(table_data):
                                if not any('---' in cell for cell in row) and not any('===' in cell for cell in row):
                                    filtered_table_data.append(row)
                            
                            if filtered_table_data:
                                # Determine appropriate column widths
                                if len(filtered_table_data) > 0 and len(filtered_table_data[0]) > 0:
                                    # Get total width of the page
                                    available_width = doc.width
                                    
                                    # Default width for columns
                                    num_cols = len(filtered_table_data[0])
                                    col_widths = [available_width / num_cols] * num_cols
                                    
                                    # Optimize column widths based on content, limit to max 3 inches
                                    for col_idx in range(num_cols):
                                        max_width = max(
                                            min(0.1*inch * len(row[col_idx]) if col_idx < len(row) else 0, 2*inch)
                                            for row in filtered_table_data if col_idx < len(row)
                                        )
                                        col_widths[col_idx] = max(0.5*inch, max_width)
                                    
                                    # Ensure total width doesn't exceed page width
                                    total_width = sum(col_widths)
                                    if total_width > available_width:
                                        scale_factor = available_width / total_width
                                        col_widths = [w * scale_factor for w in col_widths]
                                
                                    # Create ReportLab table
                                    table = Table(filtered_table_data, colWidths=col_widths)
                                    
                                    # Apply styles
                                    table_style = list(table_style_base)
                                    
                                    # Add zebra striping for better readability
                                    for row in range(1, len(filtered_table_data)):
                                        if row % 2 == 0:
                                            table_style.append(('BACKGROUND', (0, row), (-1, row), colors.lightgrey))
                                    
                                    table.setStyle(TableStyle(table_style))
                                    story.append(table)
                                    story.append(Spacer(1, 6))
                            
                            # Reset table lines
                            table_lines = []
                        
                        # Process this non-table line
                        if line.strip():
                            # Handle bullet points
                            if line.strip().startswith('- ') or line.strip().startswith('* '):
                                bullet_text = line.strip()[2:].strip()
                                story.append(Paragraph('• ' + bullet_text, bullet_style))
                            else:
                                # Regular paragraph
                                story.append(Paragraph(line.strip(), normal_style))
                                story.append(Spacer(1, 3))
                
                # Process any remaining table at the end
                if table_lines:
                    # Same table processing as above (duplicated for simplicity)
                    table_data = []
                    
                    for table_line in table_lines:
                        # Split by | but remove the first and last empty cells
                        row = [cell.strip() for cell in table_line.split('|')]
                        if row and row[0] == '':
                            row = row[1:]
                        if row and row[-1] == '':
                            row = row[:-1]
                            
                        if row:
                            table_data.append(row)
                    
                    # Skip delimiter rows
                    filtered_table_data = []
                    for i, row in enumerate(table_data):
                        if not any('---' in cell for cell in row) and not any('===' in cell for cell in row):
                            filtered_table_data.append(row)
                    
                    if filtered_table_data:
                        # Determine appropriate column widths
                        if len(filtered_table_data) > 0 and len(filtered_table_data[0]) > 0:
                            # Get total width of the page
                            available_width = doc.width
                            
                            # Default width for columns
                            num_cols = len(filtered_table_data[0])
                            col_widths = [available_width / num_cols] * num_cols
                            
                            # Optimize column widths based on content, limit to max 3 inches
                            for col_idx in range(num_cols):
                                max_width = max(
                                    min(0.1*inch * len(row[col_idx]) if col_idx < len(row) else 0, 2*inch)
                                    for row in filtered_table_data if col_idx < len(row)
                                )
                                col_widths[col_idx] = max(0.5*inch, max_width)
                            
                            # Ensure total width doesn't exceed page width
                            total_width = sum(col_widths)
                            if total_width > available_width:
                                scale_factor = available_width / total_width
                                col_widths = [w * scale_factor for w in col_widths]
                        
                            # Create ReportLab table
                            table = Table(filtered_table_data, colWidths=col_widths)
                            
                            # Apply styles
                            table_style = list(table_style_base)
                            
                            # Add zebra striping for better readability
                            for row in range(1, len(filtered_table_data)):
                                if row % 2 == 0:
                                    table_style.append(('BACKGROUND', (0, row), (-1, row), colors.lightgrey))
                            
                            table.setStyle(TableStyle(table_style))
                            story.append(table)
                            story.append(Spacer(1, 6))
            else:
                # No tables, just paragraphs
                paragraphs = content_text.split('\n\n')
                
                for paragraph in paragraphs:
                    if not paragraph.strip():
                        continue
                        
                    lines = paragraph.split('\n')
                    
                    for line in lines:
                        if not line.strip():
                            continue
                            
                        # Handle bullet points
                        if line.strip().startswith('- ') or line.strip().startswith('* '):
                            bullet_text = line.strip()[2:].strip()
                            story.append(Paragraph('• ' + bullet_text, bullet_style))
                        else:
                            # Regular paragraph
                            story.append(Paragraph(line.strip(), normal_style))
                    
                    story.append(Spacer(1, 3))
        
        # Add a footer
        def add_page_number(canvas, doc):
            canvas.saveState()
            canvas.setFont('Helvetica', 8)
            canvas.setFillColor(colors.grey)
            footer_text = "Equipment Schedule Risk Analysis - Page %d" % doc.page
            canvas.drawCentredString(letter[0]/2, 0.5*inch, footer_text)
            canvas.restoreState()
        
        # Build PDF with page numbers
        doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)

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