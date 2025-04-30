from spire.doc import *
from spire.doc.common import *

# Create an object of Document class
doc = Document()

# Load a Word document
doc.LoadFromFile("../Sample.docx")

# Loop thorugh the sections of document
for i in range(doc.Sections.Count):
    # Get a section
    section = doc.Sections.get_Item(i)
    # Get the margins of the section
    margins = section.PageSetup.Margins
    print(margins.Top)
    print(margins.Bottom)
    print(margins.Left)
    print(margins.Right)
    # Set the top, bottom, left, and right margins
   
# Save the document
doc.SaveToFile("reports/SetPageMargins.docx", FileFormat.Auto)