-- Script to drop all tables in the correct order (due to foreign key constraints)

-- Drop Fact Tables first
IF OBJECT_ID('fact_risk_action_item', 'U') IS NOT NULL
    DROP TABLE fact_risk_action_item;

IF OBJECT_ID('fact_risk_notification', 'U') IS NOT NULL
    DROP TABLE fact_risk_notification;

IF OBJECT_ID('fact_schedule_variance', 'U') IS NOT NULL
    DROP TABLE fact_schedule_variance;

IF OBJECT_ID('fact_risk_report', 'U') IS NOT NULL
    DROP TABLE fact_risk_report;

IF OBJECT_ID('fact_equipment_milestone_schedule', 'U') IS NOT NULL
    DROP TABLE fact_equipment_milestone_schedule;

IF OBJECT_ID('fact_p6_schedule', 'U') IS NOT NULL
    DROP TABLE fact_p6_schedule;

IF OBJECT_ID('fact_purchase_order', 'U') IS NOT NULL
    DROP TABLE fact_purchase_order;

-- Drop Dimension Tables with dependencies
IF OBJECT_ID('dim_logistics_info', 'U') IS NOT NULL
    DROP TABLE dim_logistics_info;

IF OBJECT_ID('dim_manufacturing_location', 'U') IS NOT NULL
    DROP TABLE dim_manufacturing_location;

IF OBJECT_ID('dim_equipment_supplier', 'U') IS NOT NULL
    DROP TABLE dim_equipment_supplier;

-- Drop main Dimension Tables
IF OBJECT_ID('dim_supplier', 'U') IS NOT NULL
    DROP TABLE dim_supplier;

IF OBJECT_ID('dim_milestone', 'U') IS NOT NULL
    DROP TABLE dim_milestone;

IF OBJECT_ID('dim_equipment', 'U') IS NOT NULL
    DROP TABLE dim_equipment;

IF OBJECT_ID('dim_work_package', 'U') IS NOT NULL
    DROP TABLE dim_work_package;

IF OBJECT_ID('dim_project', 'U') IS NOT NULL
    DROP TABLE dim_project;

-- Drop Logging Tables
IF OBJECT_ID('dim_agent_thinking_log_enhanced', 'U') IS NOT NULL
    DROP TABLE dim_agent_thinking_log_enhanced;

IF OBJECT_ID('dim_agent_thinking_log', 'U') IS NOT NULL
    DROP TABLE dim_agent_thinking_log;

IF OBJECT_ID('dim_agent_event_log', 'U') IS NOT NULL
    DROP TABLE dim_agent_event_log;

-- Drop Stored Procedures
IF OBJECT_ID('sp_GetReports', 'P') IS NOT NULL
    DROP PROCEDURE sp_GetReports;

IF OBJECT_ID('sp_GetScheduleComparisonData', 'P') IS NOT NULL
    DROP PROCEDURE sp_GetScheduleComparisonData;

IF OBJECT_ID('sp_LogAgentEvent', 'P') IS NOT NULL
    DROP PROCEDURE sp_LogAgentEvent;

IF OBJECT_ID('sp_LogRiskReport', 'P') IS NOT NULL
    DROP PROCEDURE sp_LogRiskReport;