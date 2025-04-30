-- Sample data for dim_project
INSERT INTO dim_project (project_code, project_name, project_country, project_location)
VALUES ('100000', 'Project A', 'Germany', 'Rathenaustraße 2, 93055 Regensburg, Germany');


-- Sample data for dim_work_package
INSERT INTO dim_work_package (work_package_code, work_package_name, wbs)
VALUES ('F12', 'Low Voltage / Power', 'S-100000-2-67-F12');

-- Sample data for dim_equipment
INSERT INTO dim_equipment (equipment_code, equipment_name, equipment_type, specifications)
VALUES 
('123456', 'LV Switchgear - 400V/5000A Switchboard-1 (3-Sections)', 'Electrical Equipment', 'Low Voltage Switchgear, 400V, 5000A rating, 3-section configuration'),
('123457', 'LV Switchgear - 400V/5000A Switchboard-2 (3-Sections)', 'Electrical Equipment', 'Low Voltage Switchgear, 400V, 5000A rating, 3-section configuration'),
('123458', 'LV Switchgear - 400V/5000A Switchboard-3 (3-Sections)', 'Electrical Equipment', 'Low Voltage Switchgear, 400V, 5000A rating, 3-section configuration');

-- Sample data for dim_milestone
INSERT INTO dim_milestone (milestone_number, milestone_activity, milestone_description)
VALUES 
('1', 'Assembly Start', 'Begin panel structure fabrication, mounting of devices, and wiring.'),
('2', 'Mechanical Completion', 'Physical assembly done: all components mounted, busbars installed, routing complete.'),
('3', 'Internal Testing / Pre-FAT', 'In-house electrical checks: wiring, continuity, insulation, interlocks.'),
('4', 'FAT (Factory Acceptance Test)', 'Customer-witnessed tests to verify build quality and functional performance.'),
('5', 'Packing & Dispatch', 'Item packed and dispatched from factory'),
('6', 'Shipping manifest received', 'Shipping tracking information & manifest generated'),
('7', 'Delivery to Site', 'Needs date'),
('8', 'Engineering drawings finalized', 'Issued For Construction (IFC)');

-- Sample data for dim_supplier
INSERT INTO dim_supplier (supplier_number, supplier_name, contact_name, contact_number, email_address)
VALUES 
('111111', 'Company A', 'Bob', '123456', 'Bob@test.com'),
('111112', 'Company B', 'George', '123456', 'George@test.com'),
('111113', 'Company C', 'Sarah', '789012', 'sarah@test.com');

-- Sample data for dim_equipment_supplier
INSERT INTO dim_equipment_supplier (equipment_id, supplier_id, unit_cost, is_preferred, lead_time_days)
VALUES 
-- Equipment 1 (123456) suppliers
(1, 1, 85000.00, 1, 180),  -- Company A is preferred
(1, 2, 88000.00, 0, 195),  -- Company B alternative
(1, 3, 82000.00, 0, 210),  -- Company C alternative (cheaper but longer lead time)

-- Equipment 2 (123457) suppliers
(2, 1, 85000.00, 1, 180),  -- Company A is preferred
(2, 2, 86500.00, 0, 190),  -- Company B alternative
(2, 3, 83000.00, 0, 205),  -- Company C alternative

-- Equipment 3 (123458) suppliers
(3, 1, 85000.00, 1, 180),  -- Company A is preferred
(3, 2, 87500.00, 0, 185),  -- Company B alternative
(3, 3, 84000.00, 0, 200);  -- Company C alternative

-- Sample data for fact_purchase_order
INSERT INTO fact_purchase_order (purchase_order_number, line_item, project_id, work_package_id, supplier_id, equipment_id, short_text, amount)
VALUES 
('PO0001', '10', 1, 1, 1, 1, 'F12 - LV Switchgear, Interconnecting', 85000.00),
('PO0001', '20', 1, 1, 1, 2, 'F12 - LV Switchgear, Interconnecting', 85000.00),
('PO0001', '30', 1, 1, 1, 3, 'F12 - LV Switchgear, Interconnecting', 85000.00);

-- Sample data for fact_p6_schedule
INSERT INTO fact_p6_schedule (project_id, work_package_id, equipment_id, milestone_id, p6_schedule_due_date)
VALUES 
-- Engineering milestone
(1, 1, 1, 7, '2026-02-21'),
(1, 1, 2, 7, '2026-02-25'),
(1, 1, 3, 7, '2026-02-27');

-- Sample data for fact_equipment_milestone_schedule
INSERT INTO fact_equipment_milestone_schedule (equipment_id, project_id, work_package_id, milestone_id, purchase_order_id, equipment_milestone_due_date)
VALUES 
-- Equipment 123456 milestones
(1, 1, 1, 1, 1, '2025-04-11'),  -- Assembly Start
(1, 1, 1, 2, 1, '2025-09-08'),  -- Mechanical Completion
(1, 1, 1, 3, 1, '2025-11-07'),  -- Internal Testing
(1, 1, 1, 4, 1, '2025-11-27'),  -- FAT
(1, 1, 1, 5, 1, '2025-12-07'),  -- Packing & Dispatch
(1, 1, 1, 6, 1, '2026-01-06'),  -- Shipping manifest
(1, 1, 1, 7, 1, '2026-01-21'),  -- Delivery to Site (earlier than P6 needed date of 2026-02-21)

-- Equipment 123457 milestones
(2, 1, 1, 1, 2, '2025-05-11'),  -- Assembly Start
(2, 1, 1, 2, 2, '2025-10-08'),  -- Mechanical Completion
(2, 1, 1, 3, 2, '2025-12-07'),  -- Internal Testing
(2, 1, 1, 4, 2, '2025-12-27'),  -- FAT
(2, 1, 1, 5, 2, '2026-01-06'),  -- Packing & Dispatch
(2, 1, 1, 6, 2, '2026-02-05'),  -- Shipping manifest
(2, 1, 1, 7, 2, '2026-02-20'),  -- Delivery to Site (earlier than P6 needed date of 2026-02-25)

-- Equipment 123458 milestones
(3, 1, 1, 1, 3, '2025-05-26'),  -- Assembly Start
(3, 1, 1, 2, 3, '2025-10-23'),  -- Mechanical Completion
(3, 1, 1, 3, 3, '2025-12-22'),  -- Internal Testing
(3, 1, 1, 4, 3, '2026-01-11'),  -- FAT
(3, 1, 1, 5, 3, '2026-01-21'),  -- Packing & Dispatch
(3, 1, 1, 6, 3, '2026-02-20'),  -- Shipping manifest
(3, 1, 1, 7, 3, '2026-03-07');  -- Delivery to Site (later than P6 needed date - THIS SHOULD TRIGGER A RISK)


INSERT INTO dim_manufacturing_location (equipment_id, supplier_id, location_address)
VALUES 
(1, 1, '20 Cooper Square, New York, NY 10003, USA'),
(2, 1, '200 Wangfujing Ave, Dongcheng, Beijing, China, 100836'),
(3, 1, 'Adriatico St, Ermita, Manila, 1000 Metro Manila, Philippines'),
(1, 1, 'Palika Bazar, Connaught Place, New Delhi, Delhi 110001, India'),
(2, 1, '43 Charing Cross Rd, London WC2H 0AP, United Kingdom'),
(3, 1, 'alan Seladang, Taman Abad, 80250 Johor Bahru, Johor, Malaysia');

-- Sample data for Logistics Information
INSERT INTO dim_logistics_info (equipment_id, supplier_id, logistics_method, shipping_port, receiving_port)
VALUES 
(1, 1, 'Shipping', 'Hamburg, Germany', 'Penang Port'),
(2, 1, 'Shipping', 'Hamburg, Germany', 'Singapore'),
(3, 1, 'Shipping', 'Wilhelmshaven, Germany', 'Singapore');