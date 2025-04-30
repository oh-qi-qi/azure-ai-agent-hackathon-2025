from spire.doc import *
from spire.doc.common import *
import os
import time

def format_document(input_file, output_file):
    # Create a Document object
    document = Document()

    # Load the markdown file
    document.LoadFromFile(input_file)

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
                    font_size = 12
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

    # Ensure the output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Make sure the file isn't already open
    if os.path.exists(output_file):
        try:
            # Try to remove the existing file
            os.remove(output_file)
            # Give a moment for the file system to catch up
            time.sleep(0.5)
        except PermissionError:
            # If we can't remove it, it might be open
            # Create a new filename with timestamp
            base, ext = os.path.splitext(output_file)
            new_output_file = f"{base}_{int(time.time())}{ext}"
            output_file = new_output_file

    # Save the document
    try:
        document.SaveToFile(output_file, FileFormat.Docx2019)
    except Exception:
        # Try an alternative save method
        try:
            document.SaveToFile(output_file, FileFormat.Docx)
        except Exception:
            pass

if __name__ == "__main__":
    input_file = "./sample_output.md"
    output_file = "reports/FormattedDocument.docx"
    format_document(input_file, output_file)