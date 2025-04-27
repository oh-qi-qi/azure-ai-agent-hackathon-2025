CREATE PROCEDURE sp_GetEquipmentRiskAndLocationInfo
    @project_id INT = NULL,
    @exclude_risk_flag VARCHAR(20) = NULL,
    @agent_run_id UNIQUEIDENTIFIER = NULL
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Return equipment risk and location information
    SELECT 
        sv.project_id,
        sv.equipment_id,
        sv.risk_flag,
        sv.risk_description,
        sv.mitigation_action,
        sv.agent_run_id,
        ml.location_address,
        li.receiving_port,
        li.shipping_port
    FROM 
        fact_schedule_variance sv
    LEFT JOIN 
        dim_manufacturing_location ml ON sv.equipment_id = ml.equipment_id
    LEFT JOIN 
        dim_logistics_info li ON sv.equipment_id = li.equipment_id
    WHERE
        (@project_id IS NULL OR sv.project_id = @project_id)
        AND (@exclude_risk_flag IS NULL OR sv.risk_flag <> @exclude_risk_flag)
        AND (@agent_run_id IS NULL OR sv.agent_run_id = @agent_run_id);
    
    RETURN 0;
END;

#######


/* 
Query to get medium risks and above

EXEC sp_GetEquipmentRiskAndLocationInfo @exclude_risk_flag = 'Low'

*/