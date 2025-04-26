-- Create Dimension Tables
CREATE TABLE dim_project (
    project_id INT IDENTITY(1,1) PRIMARY KEY,
    project_code VARCHAR(20) NOT NULL,
    project_name VARCHAR(100) NOT NULL,
    created_date DATETIME DEFAULT GETDATE(),
    modified_date DATETIME DEFAULT GETDATE(),
    CONSTRAINT uq_project_code UNIQUE (project_code)
);

CREATE TABLE dim_work_package (
    work_package_id INT IDENTITY(1,1) PRIMARY KEY,
    work_package_code VARCHAR(20) NOT NULL,
    work_package_name VARCHAR(100) NOT NULL,
    wbs VARCHAR(50),
    created_date DATETIME DEFAULT GETDATE(),
    modified_date DATETIME DEFAULT GETDATE(),
    CONSTRAINT uq_work_package_code UNIQUE (work_package_code)
);

CREATE TABLE dim_equipment (
    equipment_id INT IDENTITY(1,1) PRIMARY KEY,
    equipment_code VARCHAR(20) NOT NULL,
    equipment_name VARCHAR(100) NOT NULL,
    equipment_type VARCHAR(50),
    specifications VARCHAR(500),
    created_date DATETIME DEFAULT GETDATE(),
    modified_date DATETIME DEFAULT GETDATE(),
    CONSTRAINT uq_equipment_code UNIQUE (equipment_code)
);

CREATE TABLE dim_milestone (
    milestone_id INT IDENTITY(1,1) PRIMARY KEY,
    milestone_number VARCHAR(20),
    milestone_activity VARCHAR(100) NOT NULL,
    milestone_description VARCHAR(255),
    created_date DATETIME DEFAULT GETDATE(),
    modified_date DATETIME DEFAULT GETDATE(),
    CONSTRAINT uq_milestone_activity UNIQUE (milestone_activity, milestone_description)
);

CREATE TABLE dim_supplier (
    supplier_id INT IDENTITY(1,1) PRIMARY KEY,
    supplier_number VARCHAR(20) NOT NULL,
    supplier_name VARCHAR(100) NOT NULL,
    contact_name VARCHAR(100),
    contact_number VARCHAR(50),
    email_address VARCHAR(100),
    created_date DATETIME DEFAULT GETDATE(),
    modified_date DATETIME DEFAULT GETDATE(),
    CONSTRAINT uq_supplier_number UNIQUE (supplier_number)
);

-- New table to link equipment with suppliers and costs
CREATE TABLE dim_equipment_supplier (
    equipment_supplier_id INT IDENTITY(1,1) PRIMARY KEY,
    equipment_id INT NOT NULL,
    supplier_id INT NOT NULL,
    unit_cost DECIMAL(18,2) NOT NULL,
    is_preferred BIT DEFAULT 0,
    lead_time_days INT,
    remarks VARCHAR(500),
    created_date DATETIME DEFAULT GETDATE(),
    modified_date DATETIME DEFAULT GETDATE(),
    CONSTRAINT fk_equipment_supplier_equipment FOREIGN KEY (equipment_id) REFERENCES dim_equipment(equipment_id),
    CONSTRAINT fk_equipment_supplier_supplier FOREIGN KEY (supplier_id) REFERENCES dim_supplier(supplier_id),
    CONSTRAINT uq_equipment_supplier UNIQUE (equipment_id, supplier_id)
);

-- Create Fact Tables
CREATE TABLE fact_purchase_order (
    purchase_order_id INT IDENTITY(1,1) PRIMARY KEY,
    purchase_order_number VARCHAR(50) NOT NULL,
    line_item VARCHAR(20),
    project_id INT NOT NULL,
    work_package_id INT NOT NULL,
    supplier_id INT NOT NULL,
    equipment_id INT NOT NULL,  -- Now required field
    short_text VARCHAR(255),
    remarks VARCHAR(500),
    amount DECIMAL(18,2),
    created_date DATETIME DEFAULT GETDATE(),
    modified_date DATETIME DEFAULT GETDATE(),
    CONSTRAINT fk_purchase_order_project FOREIGN KEY (project_id) REFERENCES dim_project(project_id),
    CONSTRAINT fk_purchase_order_work_package FOREIGN KEY (work_package_id) REFERENCES dim_work_package(work_package_id),
    CONSTRAINT fk_purchase_order_supplier FOREIGN KEY (supplier_id) REFERENCES dim_supplier(supplier_id),
    CONSTRAINT fk_purchase_order_equipment FOREIGN KEY (equipment_id) REFERENCES dim_equipment(equipment_id),
    CONSTRAINT uq_purchase_order_number_line UNIQUE (purchase_order_number, line_item)
);

CREATE TABLE fact_p6_schedule (
    p6_schedule_id INT IDENTITY(1,1) PRIMARY KEY,
    project_id INT NOT NULL,
    work_package_id INT NOT NULL,
    equipment_id INT NOT NULL,
    milestone_id INT NOT NULL,
    p6_schedule_due_date DATE NOT NULL,
    created_date DATETIME DEFAULT GETDATE(),
    modified_date DATETIME DEFAULT GETDATE(),
    CONSTRAINT fk_p6_schedule_project FOREIGN KEY (project_id) REFERENCES dim_project(project_id),
    CONSTRAINT fk_p6_schedule_work_package FOREIGN KEY (work_package_id) REFERENCES dim_work_package(work_package_id),
    CONSTRAINT fk_p6_schedule_equipment FOREIGN KEY (equipment_id) REFERENCES dim_equipment(equipment_id),
    CONSTRAINT fk_p6_schedule_milestone FOREIGN KEY (milestone_id) REFERENCES dim_milestone(milestone_id)
);

CREATE TABLE fact_equipment_milestone_schedule (
    equipment_milestone_id INT IDENTITY(1,1) PRIMARY KEY,
    equipment_id INT NOT NULL,
    project_id INT NOT NULL,
    work_package_id INT NOT NULL,
    milestone_id INT NOT NULL,
    purchase_order_id INT,
    equipment_milestone_due_date DATE NOT NULL,
    status VARCHAR(20) DEFAULT 'Active',
    created_date DATETIME DEFAULT GETDATE(),
    modified_date DATETIME DEFAULT GETDATE(),
    CONSTRAINT fk_equipment_milestone_equipment FOREIGN KEY (equipment_id) REFERENCES dim_equipment(equipment_id),
    CONSTRAINT fk_equipment_milestone_project FOREIGN KEY (project_id) REFERENCES dim_project(project_id),
    CONSTRAINT fk_equipment_milestone_work_package FOREIGN KEY (work_package_id) REFERENCES dim_work_package(work_package_id),
    CONSTRAINT fk_equipment_milestone_milestone FOREIGN KEY (milestone_id) REFERENCES dim_milestone(milestone_id),
    CONSTRAINT fk_equipment_milestone_purchase_order FOREIGN KEY (purchase_order_id) REFERENCES fact_purchase_order(purchase_order_id)
);

-- Additional tables for manufacturing and logistics information
CREATE TABLE dim_manufacturing_location (
    manufacturing_location_id INT IDENTITY(1,1) PRIMARY KEY,
    equipment_id INT NOT NULL,
    supplier_id INT NOT NULL,
    location_address VARCHAR(255) NOT NULL,
    created_date DATETIME DEFAULT GETDATE(),
    modified_date DATETIME DEFAULT GETDATE(),
    CONSTRAINT fk_manufacturing_location_equipment FOREIGN KEY (equipment_id) REFERENCES dim_equipment(equipment_id),
    CONSTRAINT fk_manufacturing_location_supplier FOREIGN KEY (supplier_id) REFERENCES dim_supplier(supplier_id)
);

CREATE TABLE dim_logistics_info (
    logistics_info_id INT IDENTITY(1,1) PRIMARY KEY,
    equipment_id INT NOT NULL,
    supplier_id INT NOT NULL,
    logistics_method VARCHAR(50) NOT NULL,
    shipping_port VARCHAR(100),
    receiving_port VARCHAR(100),
    created_date DATETIME DEFAULT GETDATE(),
    modified_date DATETIME DEFAULT GETDATE(),
    CONSTRAINT fk_logistics_info_equipment FOREIGN KEY (equipment_id) REFERENCES dim_equipment(equipment_id),
    CONSTRAINT fk_logistics_info_supplier FOREIGN KEY (supplier_id) REFERENCES dim_supplier(supplier_id)
);

-- Tables for risk management and agent logging
CREATE TABLE fact_schedule_variance (
    variance_id INT IDENTITY(1,1) PRIMARY KEY,
    project_id INT NOT NULL,
    equipment_id INT NOT NULL,
    work_package_id INT NOT NULL,
    milestone_id INT NOT NULL,
    p6_due_date DATE NOT NULL,
    equipment_delivery_date DATE NOT NULL,
    days_variance INT,              -- Positive if late, negative if early
    risk_flag VARCHAR(20),          -- 'High Risk', 'Medium Risk', 'Low Risk', 'On Track'
    risk_description VARCHAR(500),  -- Detailed description of the risk
    mitigation_action VARCHAR(500), -- Suggested actions to mitigate the risk
    conversation_id UNIQUEIDENTIFIER,  -- Reference to agent event
    created_date DATETIME DEFAULT GETDATE(),
    modified_date DATETIME DEFAULT GETDATE(),
    CONSTRAINT fk_schedule_variance_project FOREIGN KEY (project_id) REFERENCES dim_project(project_id),
    CONSTRAINT fk_schedule_variance_equipment FOREIGN KEY (equipment_id) REFERENCES dim_equipment(equipment_id),
    CONSTRAINT fk_schedule_variance_work_package FOREIGN KEY (work_package_id) REFERENCES dim_work_package(work_package_id),
    CONSTRAINT fk_schedule_variance_milestone FOREIGN KEY (milestone_id) REFERENCES dim_milestone(milestone_id)
);

-- New table for tracking notification history
CREATE TABLE fact_risk_notification (
    notification_id INT IDENTITY(1,1) PRIMARY KEY,
    variance_id INT NOT NULL,
    notification_time DATETIME NOT NULL,
    notification_type VARCHAR(50) NOT NULL, -- 'Email', 'SMS', 'Dashboard', etc.
    recipient VARCHAR(255) NOT NULL,
    message_content VARCHAR(1000),
    status VARCHAR(20) DEFAULT 'Sent', -- 'Sent', 'Delivered', 'Read', 'Failed'
    conversation_id UNIQUEIDENTIFIER,
    created_date DATETIME DEFAULT GETDATE(),
    CONSTRAINT fk_risk_notification_variance FOREIGN KEY (variance_id) REFERENCES fact_schedule_variance(variance_id)
);

-- New table for tracking action items and resolutions
CREATE TABLE fact_risk_action_item (
    action_item_id INT IDENTITY(1,1) PRIMARY KEY,
    variance_id INT NOT NULL,
    action_description VARCHAR(500) NOT NULL,
    assigned_to VARCHAR(100),
    due_date DATE,
    status VARCHAR(50) DEFAULT 'Open', -- 'Open', 'In Progress', 'Resolved', 'Closed'
    resolution_notes VARCHAR(1000),
    created_date DATETIME DEFAULT GETDATE(),
    modified_date DATETIME DEFAULT GETDATE(),
    CONSTRAINT fk_risk_action_item_variance FOREIGN KEY (variance_id) REFERENCES fact_schedule_variance(variance_id)
);
CREATE TABLE dim_agent_event_log (
    log_id INT IDENTITY(1,1) PRIMARY KEY,
    event_id UNIQUEIDENTIFIER NOT NULL,
    agent_name VARCHAR(100) NOT NULL,
    event_time DATETIME NOT NULL,
    action VARCHAR(100) NOT NULL,
    result_summary VARCHAR(1000) NULL,
    user_query NVARCHAR(MAX) NULL,
    agent_output NVARCHAR(MAX) NULL,
    conversation_id UNIQUEIDENTIFIER NOT NULL,
    created_date DATETIME DEFAULT GETDATE()
);

-- Create the table with all the fields we want
CREATE TABLE dim_agent_thinking_log (
    thinking_id INT IDENTITY(1,1) PRIMARY KEY,
    agent_name VARCHAR(100) NOT NULL,
    thinking_stage VARCHAR(50) NOT NULL,
    thought_content NVARCHAR(MAX) NOT NULL,
    conversation_id VARCHAR(100) NOT NULL,
    session_id VARCHAR(100) NULL,
    azure_agent_id VARCHAR(100) NULL,
    model_deployment_name VARCHAR(100) NULL,
    created_date DATETIME DEFAULT GETDATE()
);

CREATE TABLE dim_agent_thinking_log_enhanced (
    thinking_id INT IDENTITY(1,1) PRIMARY KEY,
    agent_name VARCHAR(100) NOT NULL,
    thinking_stage VARCHAR(50) NOT NULL,
    thought_content NVARCHAR(MAX) NOT NULL,
    agent_output NVARCHAR(MAX) NULL,  -- New column for agent output
    conversation_id VARCHAR(100) NOT NULL,
    session_id VARCHAR(100) NULL,
    azure_agent_id VARCHAR(100) NULL,
    model_deployment_name VARCHAR(100) NULL,
    thread_id VARCHAR(100) NULL,
    user_query NVARCHAR(MAX) NULL,
    status VARCHAR(50) DEFAULT 'unknown',
    created_date DATETIME DEFAULT GETDATE()
);