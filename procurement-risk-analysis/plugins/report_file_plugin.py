"""Improved ReportFilePlugin with all necessary imports and robust error handling."""

import json
import uuid
import os
import pyodbc
from datetime import datetime
import re
import traceback
from semantic_kernel.functions.kernel_function_decorator import kernel_function

# Import necessary reportlab modules
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    REPORTLAB_AVAILABLE = True
except ImportError:
    print("ReportLab not available. PDF generation will not work.")
    REPORTLAB_AVAILABLE = False

# Import Azure storage modules
try:
    from azure.storage.blob import BlobServiceClient, ContentSettings
    from azure.identity import DefaultAzureCredential
    AZURE_STORAGE_AVAILABLE = True
except ImportError:
    print("Azure Storage SDK not available. Uploads to data lake will not work.")
    AZURE_STORAGE_AVAILABLE = False

class ReportFilePlugin:
    """A plugin for creating PDF reports and uploading them to data lake."""
    
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
    
    @kernel_function(description="Saves a report to PDF and uploads to data lake")
    def save_report_to_file(self, report_content: str, session_id: str, 
                          conversation_id: str, report_title: str = None) -> str:
        """Saves a report to PDF and uploads to data lake with improved error handling.
        
        Args:
            report_content: The report content in markdown format
            session_id: The session ID
            conversation_id: The conversation ID
            report_title: Optional report title
            
        Returns:
            str: JSON string with result information
        """
        try:
            # Check if PDF generation is available
            if not REPORTLAB_AVAILABLE:
                print("ReportLab not available. Cannot generate PDF.")
                return json.dumps({
                    "error": "PDF generation is not available. ReportLab library is missing.",
                    "success": False,
                    "stage": "initialization"
                })
            
            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_id = str(uuid.uuid4())[:8]
            filename = f"risk_report_{timestamp}_{report_id}.pdf"
            filepath = os.path.join(self.report_directory, filename)
            
            # Print debug info
            print(f"Saving report to file: {filepath}")
            print(f"Report content length: {len(report_content)} characters")
            print(f"Report title: {report_title}")
            
            # Generate PDF with detailed error handling
            try:
                self._generate_pdf(filepath, report_content, report_title)
                print(f"Successfully generated PDF: {filepath}")
            except Exception as pdf_error:
                print(f"Error generating PDF: {pdf_error}")
                traceback.print_exc()
                return json.dumps({
                    "error": f"PDF generation failed: {str(pdf_error)}",
                    "stage": "pdf_generation",
                    "success": False
                })
            
            # Upload to data lake with detailed error handling
            blob_url = None
            try:
                if self.blob_service_client and AZURE_STORAGE_AVAILABLE:
                    blob_url = self._upload_to_data_lake(filepath, filename)
                    print(f"Successfully uploaded to data lake: {blob_url}")
                else:
                    print("No blob service client available, skipping upload")
                    # Use a local file URL as fallback
                    blob_url = f"file://{os.path.abspath(filepath)}"
                    print(f"Using local file URL: {blob_url}")
            except Exception as upload_error:
                print(f"Error uploading to data lake: {upload_error}")
                traceback.print_exc()
                # Continue anyway with local file path
                blob_url = f"file://{os.path.abspath(filepath)}"
                print(f"Using local file URL as fallback: {blob_url}")
            
            # Log to database with detailed error handling
            try:
                self._log_report_to_database(session_id, conversation_id, filename, blob_url)
                print("Successfully logged report to database")
            except Exception as db_error:
                print(f"Error logging report to database: {db_error}")
                traceback.print_exc()
                # Continue anyway
            
            # Return success information
            return json.dumps({
                "success": True,
                "filename": filename,
                "filepath": filepath,
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
    
    def _generate_pdf(self, filepath: str, content: str, title: str = None):
        """Generates a PDF report with improved table handling.
        
        Args:
            filepath: Output filepath
            content: Report content in markdown format
            title: Optional report title
        """
        # Check if PDF generation is available
        if not REPORTLAB_AVAILABLE:
            raise ImportError("ReportLab is not available. Cannot generate PDF.")
        
        # Print debug info
        print(f"Generating PDF: {filepath}")
        print(f"Content length: {len(content)} characters")
        
        try:
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
            
            # Find all tables in the content
            table_matches = re.finditer(r'(?:\n\|.*\|\n\|[-:| ]+\|\n)((?:\|.*\|\n)+)', content, re.MULTILINE)
            table_positions = []
            for match in table_matches:
                start, end = match.span()
                table_content = match.group(0)
                table_positions.append((start, end, table_content))
            
            # Replace content at table positions with placeholders
            if table_positions:
                # Sort by start position in reverse to avoid affecting earlier positions
                table_positions.sort(key=lambda x: x[0], reverse=True)
                
                # Replace tables with placeholders
                content_parts = list(content)
                for idx, (start, end, table_content) in enumerate(table_positions):
                    placeholder = f"\n[TABLE_{idx}]\n"
                    content_parts[start:end] = placeholder
                
                # Reassemble content
                modified_content = ''.join(content_parts)
            else:
                modified_content = content
            
            # Define table rendering function
            def render_table(table_content):
                lines = table_content.strip().split('\n')
                rows = []
                
                for line in lines:
                    if '|' in line:
                        # Skip delimiter rows (with dashes)
                        if re.search(r'\|[\s-:]+\|', line) and '-' in line:
                            continue
                        
                        # Process row cells
                        cells = [cell.strip() for cell in line.split('|')]
                        # Remove empty cells at start and end
                        if cells and cells[0] == '':
                            cells = cells[1:]
                        if cells and cells[-1] == '':
                            cells = cells[:-1]
                        
                        rows.append(cells)
                
                if not rows:
                    return None
                
                # Limit table columns to 5 max for PDF
                max_cols = 5
                for i in range(len(rows)):
                    if len(rows[i]) > max_cols:
                        print(f"Warning: Table has {len(rows[i])} columns, limiting to {max_cols}")
                        rows[i] = rows[i][:max_cols]
                
                # Create even column widths
                col_count = len(rows[0]) if rows else 0
                col_widths = [doc.width / col_count] * col_count
                
                # Create table
                table = Table(rows, colWidths=col_widths)
                
                # Style the table
                style = [
                    ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.darkblue),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),  # Smaller font for tables
                ]
                
                # Add zebra striping
                for i in range(1, len(rows)):
                    if i % 2 == 0:
                        style.append(('BACKGROUND', (0, i), (-1, i), colors.lightgrey))
                
                table.setStyle(TableStyle(style))
                return table
            
            # Split content by headers and create a dictionary
            sections = {}
            lines = modified_content.split('\n')
            current_header = None
            current_content = []
            
            for line in lines:
                # Check for headers (# Header)
                header_match = re.match(r'^(#+)\s+(.*)', line)
                if header_match:
                    # Save previous section if it exists
                    if current_header:
                        sections[current_header] = '\n'.join(current_content)
                    
                    # Start new section
                    level = len(header_match.group(1))
                    header_text = header_match.group(2).strip()
                    current_header = (level, header_text)
                    current_content = []
                else:
                    # Add to current section
                    current_content.append(line)
            
            # Add the last section
            if current_header:
                sections[current_header] = '\n'.join(current_content)
            
            # Handle case where there are no headers
            if not sections and modified_content.strip():
                # Create a default section
                sections[(1, "Content")] = modified_content
            
            # Render sections with table handling
            for section_header, content in sections.items():
                level, header = section_header  # Unpack the tuple
                
                # Add header
                if level == 1:
                    story.append(Paragraph(header, header1_style))
                elif level == 2:
                    story.append(Paragraph(header, header2_style))
                else:
                    story.append(Paragraph(header, header3_style))
                
                story.append(Spacer(1, 5))
                
                # Check for table placeholders
                table_placeholders = re.findall(r'\[TABLE_\d+\]', content)
                if table_placeholders:
                    # Split by table placeholders
                    parts = re.split(r'\[TABLE_\d+\]', content)
                    
                    for i, part in enumerate(parts):
                        # Add text part
                        if part.strip():
                            # Look for bullet points
                            if re.search(r'^[-*]\s', part.strip(), re.MULTILINE):
                                # Process bullet points
                                for line in part.strip().split('\n'):
                                    line = line.strip()
                                    if line.startswith('-') or line.startswith('*'):
                                        bullet_text = line[1:].strip()
                                        story.append(Paragraph('• ' + bullet_text, bullet_style))
                                    else:
                                        story.append(Paragraph(line, normal_style))
                            else:
                                # Regular paragraph
                                for para in part.strip().split('\n\n'):
                                    if para.strip():
                                        story.append(Paragraph(para.strip(), normal_style))
                        
                        # Add table if there is one after this part
                        if i < len(table_placeholders):
                            # Get original table content
                            try:
                                table_idx = int(table_placeholders[i].split('_')[1].rstrip(']'))
                                if table_idx < len(table_positions):
                                    _, _, table_content = table_positions[table_idx]
                                    
                                    # Render table
                                    table = render_table(table_content)
                                    if table:
                                        story.append(table)
                                        story.append(Spacer(1, 5))
                            except (ValueError, IndexError) as e:
                                print(f"Error processing table placeholder: {e}")
                else:
                    # No tables, just process text
                    paragraphs = content.strip().split('\n\n')
                    for para in paragraphs:
                        if not para.strip():
                            continue
                            
                        # Look for bullet points
                        if re.search(r'^[-*]\s', para.strip(), re.MULTILINE):
                            # Process bullet points
                            for line in para.strip().split('\n'):
                                line = line.strip()
                                if line.startswith('-') or line.startswith('*'):
                                    bullet_text = line[1:].strip()
                                    story.append(Paragraph('• ' + bullet_text, bullet_style))
                                else:
                                    story.append(Paragraph(line, normal_style))
                        else:
                            # Regular paragraph
                            story.append(Paragraph(para.strip(), normal_style))
                
                story.append(Spacer(1, 10))
            
            # Add footer with page numbers
            def add_page_number(canvas, doc):
                canvas.saveState()
                canvas.setFont('Helvetica', 8)
                canvas.setFillColor(colors.grey)
                footer_text = "Equipment Schedule Risk Analysis - Page %d" % doc.page
                canvas.drawCentredString(letter[0]/2, 0.5*inch, footer_text)
                canvas.restoreState()
            
            # Build PDF
            doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
            print(f"Successfully built PDF: {filepath}")
            
        except Exception as e:
            print(f"Error generating PDF: {e}")
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
                    content_settings=ContentSettings(content_type="application/pdf")
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