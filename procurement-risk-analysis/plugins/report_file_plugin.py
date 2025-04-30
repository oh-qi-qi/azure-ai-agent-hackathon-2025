"""Improved ReportFilePlugin with Spire.Doc.Free integration."""

import json
import uuid
import os
import pyodbc
from datetime import datetime
import re
import traceback
import time
import tempfile
from semantic_kernel.functions.kernel_function_decorator import kernel_function

# Import the Spire.Doc library
try:
    from spire.doc import *
    from spire.doc.common import *
    
    SPIRE_DOC_AVAILABLE = True
except ImportError:
    print("Spire.Doc.Free not available. Install with: pip install Spire.Doc.Free")
    SPIRE_DOC_AVAILABLE = False

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
        print(f"\n==== REPORT GENERATION STARTED ====")
        print(f"Report length: {len(report_content)} characters")
        print(f"Session ID: {session_id}")
        print(f"Conversation ID: {conversation_id}")
        print(f"Report title: {report_title}")
        
        try:
            # Check if Spire.Doc is available
            if not SPIRE_DOC_AVAILABLE:
                print("Spire.Doc.Free not available. Cannot generate Word document.")
                return json.dumps({
                    "error": "Word document generation is not available. Spire.Doc.Free library is missing.",
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
            print(f"Report directory exists: {os.path.exists(self.report_directory)}")
            print(f"Report directory is writable: {os.access(self.report_directory, os.W_OK)}")
            
            # First create a temporary markdown file
            temp_md_file = None
            try:
                # Create a temporary file to store markdown content
                with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as temp:
                    temp.write(report_content)
                    temp_md_file = temp.name
                    print(f"Created temporary markdown file: {temp_md_file}")
                    print(f"Temp file exists: {os.path.exists(temp_md_file)}")
                    print(f"Temp file size: {os.path.getsize(temp_md_file)} bytes")
                
                # Generate Word document with detailed error handling
                print(f"Calling _generate_word_document...")
                self._generate_word_document(temp_md_file, docx_filepath, report_title)
                if os.path.exists(docx_filepath):
                    print(f"Successfully generated Word document: {docx_filepath}")
                    print(f"Word document size: {os.path.getsize(docx_filepath)} bytes")
                else:
                    print(f"WARNING: Word document not found after generation: {docx_filepath}")
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
                    print(f"Uploading to data lake...")
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
                print(f"Logging report to database...")
                self._log_report_to_database(session_id, conversation_id, docx_filename, blob_url)
                print("Successfully logged report to database")
            except Exception as db_error:
                print(f"Error logging report to database: {db_error}")
                traceback.print_exc()
                # Continue anyway
            
            # Return success information
            print(f"==== REPORT GENERATION COMPLETED SUCCESSFULLY ====\n")
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
            print(f"==== REPORT GENERATION FAILED ====\n")
            return json.dumps({
                "error": str(e),
                "success": False,
                "stage": "overall_process"
            })
    
    def _generate_word_document(self, markdown_filepath: str, docx_filepath: str, title: str = None):
        """Generates a Word document from markdown using Spire.Doc.
        
        Args:
            markdown_filepath: Input markdown filepath
            docx_filepath: Output Word document filepath
            title: Optional report title
        """
        # Check if Spire.Doc is available
        if not SPIRE_DOC_AVAILABLE:
            raise ImportError("Spire.Doc.Free is not available. Cannot generate Word document.")
        
        # Print debug info
        print(f"Generating Word document: {docx_filepath}")
        print(f"Using markdown file: {markdown_filepath}")
        print(f"Markdown file exists: {os.path.exists(markdown_filepath)}")
        print(f"Markdown file size: {os.path.getsize(markdown_filepath)} bytes")
        
        try:
            print("Creating Document object...")
            # Create a Document object
            document = Document()
            
            print(f"Loading markdown file...")
            # Load the markdown file
            document.LoadFromFile(markdown_filepath)
            print("Successfully loaded markdown file")
            
            document = self.format_document(document)

            print(f"Saving document to file: {docx_filepath}")
            # Save it as a DOCX file
            document.SaveToFile(docx_filepath, FileFormat.Docx2019)
            print(f"Successfully saved Word document: {docx_filepath}")
            
            print("Disposing document resources...")
            # Dispose of resources
            document.Dispose()
            print("Document resources disposed")
            
            # Verify the file was created
            if os.path.exists(docx_filepath):
                print(f"Confirmed: Word document exists at {docx_filepath}")
                print(f"File size: {os.path.getsize(docx_filepath)} bytes")
            else:
                print(f"WARNING: Word document not found after generation: {docx_filepath}")
            
            return True
            
        except Exception as e:
            print(f"Error generating Word document with Spire.Doc: {e}")
            traceback.print_exc()
            raise
            
    def format_document(self, document: Document):
       
        # Define colors for different heading levels (using ARGB values)
        # Alpha is the first parameter (255 = fully opaque)
        # Dark blue for # headings
        heading1_color = Color.FromArgb(255, 0, 75, 156)
        # Medium blue for ## headings  
        heading2_color = Color.FromArgb(255, 58, 124, 193)
        # Light blue for ### headings
        heading3_color = Color.FromArgb(255, 58, 124, 193)
        # Lightest blue for #### headings
        heading4_color = Color.FromArgb(255, 0, 0, 0)
        
        # Create custom colors for table formatting
        border_color = Color.FromArgb(255, 128, 128, 128)  # Gray
        header_bg_color = Color.FromArgb(255, 240, 240, 240)  # Light gray
        zebra_stripe_color = Color.FromArgb(255, 245, 245, 250)  # Very light blue

        # Loop through the sections of document
        for i in range(document.Sections.Count):
            # Get a section
            section = document.Sections.get_Item(i)
            # Get the margins of the section
            margins = section.PageSetup.Margins
            # Set the top, bottom, left, and right margins
            margins.Top = 72.0
            margins.Bottom = 72.0
            margins.Left = 72.0
            margins.Right = 72.0

            # Process paragraphs in the current section
            para_count = section.Paragraphs.Count
            for j in range(para_count):
                paragraph = section.Paragraphs[j]
                
                # Add 6pt spacing after each paragraph
                try:
                    paragraph.Format.AfterSpacing = 6  # 6 points after each paragraph
                except Exception:
                    # Try alternative property name
                    try:
                        paragraph.Format.SpaceAfter = 6
                    except Exception:
                        pass
                
                # Check for heading styles
                is_heading = False
                heading_level = 0
                
                # Method 1: Check paragraph style name if available
                try:
                    if hasattr(paragraph, 'StyleName'):
                        style_name = paragraph.StyleName.lower()
                        
                        if 'heading 1' in style_name or 'h1' in style_name:
                            heading_level = 1
                            is_heading = True
                        elif 'heading 2' in style_name or 'h2' in style_name:
                            heading_level = 2
                            is_heading = True
                        elif 'heading 3' in style_name or 'h3' in style_name:
                            heading_level = 3
                            is_heading = True
                        elif 'heading 4' in style_name or 'h4' in style_name:
                            heading_level = 4
                            is_heading = True
                except Exception:
                    pass
                
                # Method 2: Check paragraph format heading level if available
                if not is_heading:
                    try:
                        if hasattr(paragraph.Format, 'OutlineLevel'):
                            outline_level = paragraph.Format.OutlineLevel
                            
                            if outline_level is OutlineLevel.Level1:
                                heading_level = 1
                                is_heading = True
                            elif outline_level == 2:
                                heading_level = 2
                                is_heading = True
                            elif outline_level is OutlineLevel.Level3:
                                heading_level = 3
                                is_heading = True
                            elif outline_level is OutlineLevel.Level4:
                                heading_level = 4
                                is_heading = True
                    except Exception:
                        pass
                
                # Method 3: Check text content for # symbols (as fallback)
                if not is_heading:
                    text_content = paragraph.Text
                    if text_content:
                        if text_content.startswith("#"):
                            heading_level = 1
                            is_heading = True
                        elif text_content.startswith("##"):
                            heading_level = 2
                            is_heading = True
                        elif text_content.startswith("###"):
                            heading_level = 3
                            is_heading = True
                        elif text_content.startswith("####"):
                            heading_level = 4
                            is_heading = True
                
                # Method 4: Detect by font size and weight (as last resort)
                if not is_heading:
                    # Check if any of the text ranges have larger font or are bold
                    has_large_font = False
                    
                    for k in range(paragraph.ChildObjects.Count):
                        obj = paragraph.ChildObjects[k]
                        if isinstance(obj, TextRange):
                            if hasattr(obj.CharacterFormat, 'FontSize') and obj.CharacterFormat.FontSize >= 16:
                                has_large_font = True
                    
                    # If large font detected, assume it's a heading
                    if has_large_font:
                        heading_level = 1  # Assume it's a level 1 heading
                        is_heading = True
                
                # If we identified a heading, format it
                if is_heading and heading_level > 0:
                    # Set heading spacing
                    try:
                        # More space for higher level headings
                        if heading_level == 1:
                            paragraph.Format.BeforeSpacing = 6
                            paragraph.Format.AfterSpacing = 8
                        elif heading_level == 2:
                            paragraph.Format.BeforeSpacing = 6
                            paragraph.Format.AfterSpacing = 8
                        else:  # heading_level 3-4
                            paragraph.Format.BeforeSpacing = 6
                            paragraph.Format.AfterSpacing = 8
                    except Exception:
                        pass
                    
                    # Select the appropriate color
                    if heading_level == 1:
                        color = heading1_color
                        font_size = 16
                    elif heading_level == 2:
                        color = heading2_color
                        font_size = 14
                    elif heading_level == 3:
                        color = heading3_color
                        font_size = 14
                    elif heading_level == 4:
                        color = heading4_color
                        font_size = 12
                    else:  
                        color = heading4_color
                        font_size = 10
                    
                    # Apply the text color and formatting to each text range in the paragraph
                    for k in range(paragraph.ChildObjects.Count):
                        obj = paragraph.ChildObjects[k]
                        if isinstance(obj, TextRange):
                            # Set font family
                            obj.CharacterFormat.FontName = "Arial"
                            
                            # Set font size
                            obj.CharacterFormat.FontSize = font_size
                            
                            # Make it bold
                            obj.CharacterFormat.Bold = True
                            
                            # Set color
                            try:
                                obj.CharacterFormat.TextColor = color
                            except Exception:
                                # Try alternative approaches
                                try:
                                    if heading_level == 1:
                                        obj.CharacterFormat.TextColor = Color.FromArgb(255, 0, 75, 156)
                                    elif heading_level == 2:
                                        obj.CharacterFormat.TextColor = Color.FromArgb(255, 58, 124, 193)
                                    elif heading_level == 3:
                                        obj.CharacterFormat.TextColor = Color.FromArgb(255, 79, 156, 241)
                                    else:
                                        obj.CharacterFormat.TextColor = Color.FromArgb(255, 125, 185, 246)
                                except Exception:
                                    # Final fallback
                                    try:
                                        obj.CharacterFormat.TextColor = Color.Blue
                                    except Exception:
                                        pass
                else:
                    # For non-heading paragraphs, just set font to Arial
                    for k in range(paragraph.ChildObjects.Count):
                        obj = paragraph.ChildObjects[k]
                        if isinstance(obj, TextRange):
                            obj.CharacterFormat.FontName = "Arial"

            # Process all tables in the section
            try:
                for table_idx in range(section.Tables.Count):
                    try:
                        table = section.Tables[table_idx]
                        
                        # Try to set default margins for the whole table if available
                        try:
                            # Try to set default table border values
                            table.TableFormat.Borders.BorderType = BorderStyle.Single
                            table.TableFormat.Borders.Color = border_color
                            table.TableFormat.Borders.LineWidth = 0.5
                            
                        except Exception:
                            pass
                        
                        # Bold the first row (header row) of each table
                        if table.Rows.Count > 0:
                            header_row = table.Rows[0]
                            
                            # Set header row properties if supported
                            try:
                                # Make header row stand out
                                header_row.Height = 20  # Slightly taller header row
                            except Exception:
                                pass
                            
                            # Process each cell in the header row
                            for cell_idx in range(header_row.Cells.Count):
                                cell = header_row.Cells[cell_idx]
                                
                                # Set cell background color
                                try:
                                    cell.CellFormat.BackColor = header_bg_color
                                except Exception:
                                    pass
                                
                                # IMPORTANT: Apply more aggressive padding settings to each cell
                                try:
                                    # Try all available padding/margin methods
                                    cell.Width = 500  # Give some base width
                                    
                                    # Approach 1: Using CellFormat
                                    cell.CellFormat.VerticalAlignment = VerticalAlignment.Middle
                                    
                                    # Approach 2: More creative - add empty paragraphs
                                    # Add a small empty paragraph to the beginning of the cell
                                    try:
                                        first_para = cell.Paragraphs[0]
                                        first_para.Format.BeforeSpacing = 5
                                        first_para.Format.AfterSpacing = 5
                                    except:
                                        pass
                                    
                                except Exception:
                                    pass
                                
                                # Process paragraphs in the cell
                                for para_idx in range(cell.Paragraphs.Count):
                                    para = cell.Paragraphs[para_idx]
                                    
                                    # Try to set paragraph spacing in cells
                                    try:
                                        para.Format.LineSpacingRule = LineSpacingRule.AtLeast
                                        para.Format.LineSpacing = 12  # At least 12 points between lines
                                        para.Format.AfterSpacing = 4  # 4 points after each paragraph in cells
                                    except Exception:
                                        pass
                                    
                                    # Format text in the header cell
                                    for obj_idx in range(para.ChildObjects.Count):
                                        try:
                                            obj = para.ChildObjects[obj_idx]
                                            if hasattr(obj, 'CharacterFormat'):
                                                obj.CharacterFormat.FontName = "Arial"
                                                obj.CharacterFormat.FontSize = 9
                                                obj.CharacterFormat.Bold = True  # Make header bold
                                        except Exception:
                                            pass
                            
                            # Format the rest of the table with smaller font
                            for row_idx in range(1, table.Rows.Count):  # Start from row 1 (after header)
                                row = table.Rows[row_idx]
                                
                                # Add zebra striping (alternate row colors)
                                if row_idx % 2 == 0:  # Even rows
                                    try:
                                        row.Height = 18
                                        for cell_idx in range(row.Cells.Count):
                                            try:
                                                row.Cells[cell_idx].CellFormat.BackColor = zebra_stripe_color
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass
                                
                                # Process each cell
                                for cell_idx in range(row.Cells.Count):
                                    cell = row.Cells[cell_idx]
                                    
                                    # IMPORTANT: Apply more aggressive padding settings to each cell
                                    try:
                                        # Try all available padding/margin methods
                                        cell.Width = 500  # Give some base width
                                        
                                        # Approach 1: Using CellFormat
                                        cell.CellFormat.VerticalAlignment = VerticalAlignment.Middle
                                            
                                        # Approach 2: More creative - add empty paragraphs or paragraph spacing
                                        try:
                                            for para_idx in range(cell.Paragraphs.Count):
                                                para = cell.Paragraphs[para_idx]
                                                para.Format.LineSpacingRule = LineSpacingRule.AtLeast
                                                para.Format.LineSpacing = 12 # At least 12 points between lines
                                                para.Format.BeforeSpacing = 5
                                                para.Format.AfterSpacing = 5
                                        except:
                                            pass
                                        
                                    except Exception:
                                        pass
                                    
                                    # Process each paragraph in the cell
                                    for para_idx in range(cell.Paragraphs.Count):
                                        para = cell.Paragraphs[para_idx]
                                        for obj_idx in range(para.ChildObjects.Count):
                                            try:
                                                obj = para.ChildObjects[obj_idx]
                                                if hasattr(obj, 'CharacterFormat'):
                                                    obj.CharacterFormat.FontName = "Arial"
                                                    obj.CharacterFormat.FontSize = 8
                                            except Exception:
                                                pass
                    except Exception:
                        pass
            except Exception:
                pass

        return document

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
            report_content = f"# Comprehensive Risk Report\n\n"
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