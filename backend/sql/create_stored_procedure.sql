-- Script to create all used stored procedures

-- Enhanced stored procedure that returns all data needed for various risk agents
CREATE OR ALTER PROCEDURE sp_GetScheduleComparisonData
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @today DATE = CAST(GETDATE() AS DATE);
    
    SELECT 
        -- Basic project and equipment info
        p.project_id,
        p.project_name,
        p.project_code,
        p.project_country,
        p.project_location,
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
        
        -- Schedule dates
        ps.p6_schedule_due_date,
        ems.equipment_milestone_due_date,
        DATEDIFF(DAY, ps.p6_schedule_due_date, ems.equipment_milestone_due_date) AS days_variance,
        DATEDIFF(DAY, @today, ps.p6_schedule_due_date) AS days_until_p6_due,
        
        -- Supplier info
        s.supplier_id,
        s.supplier_name,
        s.supplier_number,
        po.purchase_order_id,
        po.purchase_order_number,
        po.line_item,
        po.amount,
        es.lead_time_days AS supplier_lead_time,
        
        -- Manufacturing location data (for Political & Tariff risk)
        ml.location_address AS manufacturing_location,
        
        -- Logistics data (for Logistics risk)
        li.shipping_port,
        li.receiving_port,
        li.logistics_method,
        
        -- Alternative suppliers
        alt.alternatives AS alternative_suppliers
        
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
    
    -- Join equipment supplier to get lead time
    LEFT JOIN dim_equipment_supplier es ON 
        es.equipment_id = eq.equipment_id AND 
        es.supplier_id = s.supplier_id
    
    -- Join manufacturing location
    LEFT JOIN dim_manufacturing_location ml ON 
        ml.equipment_id = eq.equipment_id AND 
        ml.supplier_id = s.supplier_id
    
    -- Join logistics info
    LEFT JOIN dim_logistics_info li ON 
        li.equipment_id = eq.equipment_id AND 
        li.supplier_id = s.supplier_id
    
    -- Alternative suppliers info
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
        m.milestone_id = 7; -- Delivery to Site milestone
END;
GO

-- Stored procedure for logging risk reports
CREATE OR ALTER PROCEDURE sp_LogRiskReport
    @session_id VARCHAR(100),
    @conversation_id UNIQUEIDENTIFIER,
    @filename VARCHAR(255),
    @blob_url VARCHAR(1000),
    @report_type VARCHAR(50) = 'comprehensive'
AS
BEGIN
    SET NOCOUNT ON;
    
    INSERT INTO fact_risk_report (
        session_id, 
        conversation_id, 
        filename,
        blob_url,
        report_type
    )
    VALUES (
        @session_id,
        @conversation_id,
        @filename,
        @blob_url,
        @report_type
    );
    
    SELECT SCOPE_IDENTITY() as report_id;
END;
GO

-- Stored procedure for getting reports
CREATE OR ALTER PROCEDURE sp_GetReports
    @session_id VARCHAR(100) = NULL,
    @conversation_id UNIQUEIDENTIFIER = NULL
AS
BEGIN
    SET NOCOUNT ON;
    
    SELECT *
    FROM fact_risk_report
    WHERE (@session_id IS NULL OR session_id = @session_id)
      AND (@conversation_id IS NULL OR conversation_id = @conversation_id)
    ORDER BY created_date DESC;
END;
GO

-- Stored procedure for logging agent events
CREATE OR ALTER PROCEDURE sp_LogAgentEvent
    @agent_name VARCHAR(100),
    @action VARCHAR(100),
    @result_summary VARCHAR(1000) = NULL,
    @conversation_id UNIQUEIDENTIFIER,
    @session_id VARCHAR(100) = NULL,
    @user_query NVARCHAR(MAX) = NULL,
    @agent_output NVARCHAR(MAX) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    
    INSERT INTO dim_agent_event_log (
        event_id,
        agent_name,
        event_time,
        action,
        result_summary,
        user_query,
        agent_output,
        conversation_id,
        session_id
    )
    VALUES (
        NEWID(),
        @agent_name,
        GETDATE(),
        @action,
        @result_summary,
        @user_query,
        @agent_output,
        @conversation_id,
        @session_id
    );
END;
GO