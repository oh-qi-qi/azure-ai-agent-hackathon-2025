CREATE PROCEDURE sp_GetScheduleComparisonData
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @today DATE = CAST(GETDATE() AS DATE);
    
    -- Return raw comparison data for the agent to analyze
    SELECT 
        p.project_id,
        p.project_name,
        p.project_code,
        eq.equipment_id,
        eq.equipment_code,
        eq.equipment_name,
        eq.equipment_type,
        wp.work_package_id,
        wp.work_package_code,
        wp.work_package_name,
        m.milestone_id,
        m.milestone_number,
        m.milestone_activity,
        ps.p6_schedule_due_date,
        ems.equipment_milestone_due_date,
        DATEDIFF(DAY, ps.p6_schedule_due_date, ems.equipment_milestone_due_date) AS days_variance,
        DATEDIFF(DAY, @today, ps.p6_schedule_due_date) AS days_until_p6_due,
        s.supplier_id,
        s.supplier_name,
        s.supplier_number,
        po.purchase_order_id,
        po.purchase_order_number,
        po.line_item,
        po.amount
    FROM fact_p6_schedule ps
    JOIN fact_equipment_milestone_schedule ems ON 
        ps.equipment_id = ems.equipment_id AND 
        ps.milestone_id = ems.milestone_id AND
        ps.project_id = ems.project_id AND
        ps.work_package_id = ems.work_package_id
    JOIN dim_project p ON ps.project_id = p.project_id
    JOIN dim_equipment eq ON ps.equipment_id = eq.equipment_id
    JOIN dim_work_package wp ON ps.work_package_id = wp.work_package_id
    JOIN dim_milestone m ON ps.milestone_id = m.milestone_id
    JOIN fact_purchase_order po ON ems.purchase_order_id = po.purchase_order_id
    JOIN dim_supplier s ON po.supplier_id = s.supplier_id
    -- Get a separate subquery with alternative suppliers info
    OUTER APPLY (
        SELECT STUFF((
            SELECT ',' + alt_s.supplier_name + ' (Cost: ' + 
                   CAST(es.unit_cost AS VARCHAR) + ', Lead time: ' + 
                   CAST(es.lead_time_days AS VARCHAR) + ' days)'
            FROM dim_equipment_supplier es
            JOIN dim_supplier alt_s ON es.supplier_id = alt_s.supplier_id
            WHERE es.equipment_id = eq.equipment_id AND es.supplier_id != s.supplier_id
            FOR XML PATH('')), 1, 1, '') AS alternatives
    ) AS alt
    WHERE 
        -- Only looking at delivery milestones (7 is "Delivery to Site" in our sample data)
        -- You might want to make this configurable or include all milestones
        m.milestone_id = 7;
END;


CREATE OR ALTER PROCEDURE sp_LogScheduleVariance
    @project_id INT,
    @equipment_id INT,
    @work_package_id INT,
    @milestone_id INT,
    @p6_due_date DATE,
    @equipment_delivery_date DATE,
    @days_variance INT,
    @risk_flag VARCHAR(20),
    @risk_description VARCHAR(500),
    @mitigation_action VARCHAR(500),
    @conversation_id UNIQUEIDENTIFIER,
    @variance_id INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Insert into fact_schedule_variance table
    INSERT INTO fact_schedule_variance (
        project_id, 
        equipment_id, 
        work_package_id, 
        milestone_id,
        p6_due_date, 
        equipment_delivery_date, 
        days_variance,
        risk_flag, 
        risk_description, 
        mitigation_action, 
        conversation_id
    )
    VALUES (
        @project_id,
        @equipment_id,
        @work_package_id,
        @milestone_id,
        @p6_due_date,
        @equipment_delivery_date,
        @days_variance,
        @risk_flag,
        @risk_description,
        @mitigation_action,
        @conversation_id
    );
    
    -- Get the new variance_id
    SET @variance_id = SCOPE_IDENTITY();
    
    RETURN @variance_id;
END;

CREATE OR ALTER PROCEDURE sp_LogAgentEvent
    @agent_name VARCHAR(100),
    @action VARCHAR(100),
    @project_id INT = NULL,
    @result_summary VARCHAR(1000),
    @conversation_id UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Insert into dim_agent_event_log table
    INSERT INTO dim_agent_event_log (
        event_id,
        agent_name,
        event_time,
        action,
        project_id,
        result_summary,
        conversation_id
    )
    VALUES (
        NEWID(),
        @agent_name,
        GETDATE(),
        @action,
        @project_id,
        @result_summary,
        @conversation_id
    );
END;