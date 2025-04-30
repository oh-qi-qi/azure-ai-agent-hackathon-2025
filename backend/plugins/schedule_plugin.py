"""Equipment schedule plugin for schedule management."""

import json
import uuid
import pyodbc
from semantic_kernel.functions.kernel_function_decorator import kernel_function

class EquipmentSchedulePlugin:
    """A plugin for working with equipment schedule data."""
    
    def __init__(self, connection_string):
        self.connection_string = connection_string
    
    @kernel_function(description="Retrieves equipment schedule comparison data")
    def get_schedule_comparison_data(self) -> str:
        """Retrieves schedule comparison data for analysis"""
        try:
            print(f"Called get_schedule_comparison_data")
            
            # Connect to database
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            
            # Base query
            query = "EXEC sp_GetScheduleComparisonData"
            
            print(f"Executing query: {query}")
            cursor.execute(query)
            
            # Fetch results
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()
            
            # Convert to list of dictionaries
            results = []
            for row in rows:
                results.append(dict(zip(columns, row)))
            
            print(f"Query returned {len(results)} rows")
            print(results)
            
            # Close connection
            cursor.close()
            conn.close()
            
            # Return as JSON string
            return json.dumps(results, default=str)
            
        except Exception as e:
            print(f"Error in get_schedule_comparison_data: {str(e)}")
            return json.dumps({"error": str(e)})