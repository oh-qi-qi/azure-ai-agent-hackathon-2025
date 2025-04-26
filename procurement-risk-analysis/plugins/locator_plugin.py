import json
import uuid
import datetime
import pyodbc
from semantic_kernel.functions.kernel_function_decorator import kernel_function

class LocatorPlugin:
    """A plugin for analyzing logistics risks based on shipping and receiving ports and
    analysing poltitcal or tariff risks based on manufacturing or project locations."""
    
    def __init__(self, connection_string):
        self.connection_string = connection_string

    @kernel_function(description="Analyzes political and tariff risks for high-risk equipment")
    def analyze_manufacturing_location_risks(self) -> str:
        """Retrieves high and medium risk equipment data and analyzes political/tariff risks by manufacturing location"""
        try:
            print(f"Called analyze_manufacturing_location_risks")
            
            # Connect to database
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            
            # Query for non-low risk equipment with manufacturing locations
            query = "EXEC sp_GetEquipmentRiskAndLocationInfo @exclude_risk_flag = 'Low'"
            
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
            
            # Group by manufacturing location for risk analysis
            location_risks = {}
            for item in results:
                location = item.get('location_address')
                if not location:
                    continue
                    
                if location not in location_risks:
                    location_risks[location] = {
                        'equipment_count': 0,
                        'items': [],
                        #'political_risk_assessment': self._assess_political_risk(location),
                        #'tariff_risk_assessment': self._assess_tariff_risk(location)
                    }
                
                location_risks[location]['equipment_count'] += 1
                location_risks[location]['items'].append({
                    'project_id': item.get('project_id'),
                    'equipment_id': item.get('equipment_id'),
                    'risk_flag': item.get('risk_flag'),
                    'risk_description': item.get('risk_description')
                })
            
            # Close connection
            cursor.close()
            conn.close()
            
            risk_analysis = {
                'analysis_timestamp': datetime.now().isoformat(),
                'total_equipment_analyzed': len(results),
                'location_risk_assessments': location_risks
            }
            
            # Return as JSON string
            return json.dumps(risk_analysis, default=str)
            
        except Exception as e:
            print(f"Error in analyze_manufacturing_location_risks: {str(e)}")
            return json.dumps({"error": str(e)})
    
    @kernel_function(description="Analyzes logistics risks for high-risk equipment")
    def analyze_port_logistics_risks(self) -> str:
        """Retrieves high and medium risk equipment data and analyzes logistics risks by shipping and receiving ports"""
        try:
            print(f"Called analyze_port_logistics_risks")
            
            # Connect to database
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            
            # Query for non-low risk equipment with port information
            query = "EXEC sp_GetEquipmentRiskAndLocationInfo @exclude_risk_flag = 'Low'"
            
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
            
            # Analyze shipping routes (from shipping_port to receiving_port)
            route_risks = {}
            for item in results:
                shipping_port = item.get('shipping_port')
                receiving_port = item.get('receiving_port')
                
                if not shipping_port or not receiving_port:
                    continue
                    
                route_key = f"{shipping_port} → {receiving_port}"
                
                if route_key not in route_risks:
                    route_risks[route_key] = {
                        'shipping_port': shipping_port,
                        'receiving_port': receiving_port,
                        'equipment_count': 0,
                        'items': [],
                        #'weather_risk': self._assess_weather_risk(shipping_port, receiving_port),
                        #'congestion_risk': self._assess_congestion_risk(shipping_port, receiving_port),
                        #'security_risk': self._assess_security_risk(shipping_port, receiving_port),
                        #'alternative_routes': self._get_alternative_routes(shipping_port, receiving_port)
                    }
                
                route_risks[route_key]['equipment_count'] += 1
                route_risks[route_key]['items'].append({
                    'project_id': item.get('project_id'),
                    'equipment_id': item.get('equipment_id'),
                    'risk_flag': item.get('risk_flag'),
                    'risk_description': item.get('risk_description')
                })
            
            # Close connection
            cursor.close()
            conn.close()
            
            risk_analysis = {
                'analysis_timestamp': datetime.now().isoformat(),
                'total_equipment_analyzed': len(results),
                'route_risk_assessments': route_risks
            }
            
            # Return as JSON string
            return json.dumps(risk_analysis, default=str)
            
        except Exception as e:
            print(f"Error in analyze_port_logistics_risks: {str(e)}")
            return json.dumps({"error": str(e)})