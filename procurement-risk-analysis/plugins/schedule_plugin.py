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
        """Retrieves schedule comparison data for analysis, with optional filtering by equipment or project"""
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

    @kernel_function(description="Gets a summary of current schedule risks")
    def get_risk_summary(self) -> str:
        """Gets a summary of current schedule risks from the database"""
        try:
            # Connect to database
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            
            # Execute query to get risk summary
            cursor.execute("""
                SELECT risk_flag, COUNT(*) as count
                FROM fact_schedule_variance
                WHERE created_date >= DATEADD(day, -7, GETDATE())
                GROUP BY risk_flag
                ORDER BY 
                    CASE risk_flag 
                        WHEN 'High Risk' THEN 1
                        WHEN 'Medium Risk' THEN 2
                        WHEN 'Low Risk' THEN 3
                        ELSE 4
                    END
            """)
            
            # Fetch results
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()
            
            # Convert to list of dictionaries
            results = []
            for row in rows:
                results.append(dict(zip(columns, row)))
            
            # Get top risks
            cursor.execute("""
                SELECT TOP 5
                    e.equipment_name,
                    e.equipment_code,
                    p.project_name,
                    sv.risk_flag,
                    sv.days_variance,
                    sv.risk_description
                FROM fact_schedule_variance sv
                JOIN dim_equipment e ON sv.equipment_id = e.equipment_id
                JOIN dim_project p ON sv.project_id = p.project_id
                WHERE sv.created_date >= DATEADD(day, -7, GETDATE())
                ORDER BY 
                    CASE sv.risk_flag 
                        WHEN 'High Risk' THEN 1
                        WHEN 'Medium Risk' THEN 2
                        WHEN 'Low Risk' THEN 3
                        ELSE 4
                    END,
                    ABS(sv.days_variance) DESC
            """)
            
            # Fetch top risks
            top_columns = [column[0] for column in cursor.description]
            top_rows = cursor.fetchall()
            
            # Convert to list of dictionaries
            top_risks = []
            for row in top_rows:
                top_risks.append(dict(zip(top_columns, row)))
            
            # Close connection
            cursor.close()
            conn.close()
            
            # Return as JSON string
            return json.dumps({
                "summary": results,
                "top_risks": top_risks
            }, default=str)
            
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    # @kernel_function(description="Logs a schedule variance detected by the agent")
    # def log_schedule_variance(self, project_id: int, equipment_id: int, work_package_id: int, 
    #                         milestone_id: int, p6_due_date: str, equipment_delivery_date: str, 
    #                         days_variance: int, risk_flag: str, risk_description: str, 
    #                         mitigation_action: str, agent_run_id: str) -> str:
    #     """Logs a schedule variance to the database"""
    #     try:
    #         # Connect to database
    #         conn = pyodbc.connect(self.connection_string)
    #         cursor = conn.cursor()
            
    #         # Prepare parameters for stored procedure
    #         params = (project_id, equipment_id, work_package_id, milestone_id, 
    #                 p6_due_date, equipment_delivery_date, days_variance,
    #                 risk_flag, risk_description, mitigation_action, agent_run_id)
            
    #         # Execute stored procedure with output parameter
    #         cursor.execute("""
    #             DECLARE @variance_id INT;
    #             EXEC sp_LogScheduleVariance ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, @variance_id OUTPUT;
    #             SELECT @variance_id AS variance_id;
    #         """, params)
            
    #         # Get the variance_id
    #         result = cursor.fetchone()
    #         variance_id = result.variance_id if result else None
            
    #         # Commit and close connection
    #         conn.commit()
    #         cursor.close()
    #         conn.close()
            
    #         # Return success message with the variance_id
    #         return json.dumps({"success": True, "variance_id": variance_id})
            
    #     except Exception as e:
    #         return json.dumps({"error": str(e)})
    
    @kernel_function(description="Logs multiple schedule variances in a batch")
    def log_schedule_variances_batch(self, variances_json: str) -> str:
        """Logs multiple schedule variances from a JSON array of variance objects
        
        The JSON should be an array of objects, each with:
        - project_id, equipment_id, work_package_id, milestone_id
        - p6_due_date, equipment_delivery_date, days_variance
        - risk_flag, risk_description, mitigation_action
        """
        try:
            # Parse the JSON array
            variances = json.loads(variances_json)
            
            # Generate a run ID for this batch
            agent_run_id = str(uuid.uuid4())
            
            # Track results
            results = []
            
            # Process each variance
            for variance in variances:
                try:
                    # Extract parameters
                    project_id = variance.get('project_id')
                    equipment_id = variance.get('equipment_id')
                    work_package_id = variance.get('work_package_id')
                    milestone_id = variance.get('milestone_id')
                    p6_due_date = variance.get('p6_due_date')
                    equipment_delivery_date = variance.get('equipment_delivery_date')
                    days_variance = variance.get('days_variance')
                    risk_flag = variance.get('risk_flag')
                    risk_description = variance.get('risk_description')
                    mitigation_action = variance.get('mitigation_action')
                    
                    # Log the variance
                    result_json = self.log_schedule_variance(
                        project_id=project_id,
                        equipment_id=equipment_id,
                        work_package_id=work_package_id,
                        milestone_id=milestone_id,
                        p6_due_date=p6_due_date,
                        equipment_delivery_date=equipment_delivery_date,
                        days_variance=days_variance,
                        risk_flag=risk_flag,
                        risk_description=risk_description,
                        mitigation_action=mitigation_action,
                        agent_run_id=agent_run_id
                    )
                    
                    # Parse the result
                    result = json.loads(result_json)
                    results.append({
                        'equipment_id': equipment_id,
                        'success': result.get('success', False),
                        'variance_id': result.get('variance_id'),
                        'error': result.get('error')
                    })
                except Exception as item_error:
                    results.append({
                        'equipment_id': variance.get('equipment_id'),
                        'success': False,
                        'error': str(item_error)
                    })
            
            # Return the batch results
            return json.dumps({
                'agent_run_id': agent_run_id,
                'total_processed': len(variances),
                'results': results
            })
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    @kernel_function(description="Logs an agent event for observability")
    def log_agent_event(self, agent_name: str, action: str, result_summary: str, 
                       project_id: int = None, agent_run_id: str = None) -> str:
        """Logs an agent event to the database"""
        try:
            # Connect to database
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            
            # Use existing agent_run_id or create a new one
            if not agent_run_id:
                agent_run_id = str(uuid.uuid4())
            
            # Prepare parameters for stored procedure
            params = (agent_name, action, project_id, result_summary, agent_run_id)
            
            # Execute stored procedure
            cursor.execute("EXEC sp_LogAgentEvent ?, ?, ?, ?, ?", params)
            
            # Commit and close connection
            conn.commit()
            cursor.close()
            conn.close()
            
            # Return success message with the agent_run_id
            return json.dumps({"success": True, "agent_run_id": agent_run_id})
            
        except Exception as e:
            return json.dumps({"error": str(e)})

    @kernel_function(description="Log the agent's thinking process")
    def log_agent_thinking(self, agent_name: str, thinking_stage: str, thought_content: str, agent_run_id: str = None) -> str:
        """Logs the agent's thinking process to the database"""
        try:
            # Connect to database
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            
            # Use existing agent_run_id or create a new one
            if not agent_run_id:
                agent_run_id = str(uuid.uuid4())
            
            # Execute insert query
            cursor.execute("""
                INSERT INTO dim_agent_thinking_log 
                (agent_name, thinking_stage, thought_content, agent_run_id, created_date)
                VALUES (?, ?, ?, ?, GETDATE())
            """, (agent_name, thinking_stage, thought_content, agent_run_id))
            
            # Commit and close connection
            conn.commit()
            cursor.close()
            conn.close()
            
            return json.dumps({"success": True, "agent_run_id": agent_run_id})
            
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    @kernel_function(description="Retrieve agent thinking logs for an analysis run")
    def get_agent_thinking_logs(self, agent_run_id: str) -> str:
        """Retrieves the agent thinking logs for a specific run"""
        try:
            # Connect to database
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()
            
            # Execute query
            cursor.execute("""
                SELECT thinking_id, agent_name, thinking_stage, thought_content, created_date
                FROM dim_agent_thinking_log
                WHERE agent_run_id = ?
                ORDER BY created_date
            """, (agent_run_id,))
            
            # Fetch results
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()
            
            # Convert to list of dictionaries
            logs = []
            for row in rows:
                logs.append(dict(zip(columns, row)))
            
            # Close connection
            cursor.close()
            conn.close()
            
            # Return as JSON string
            return json.dumps(logs, default=str)
            
        except Exception as e:
            return json.dumps({"error": str(e)})