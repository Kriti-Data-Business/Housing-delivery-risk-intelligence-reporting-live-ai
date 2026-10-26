-- Reporting views (also the basis for the Power BI measures in /dax).
DROP VIEW IF EXISTS vw_portfolio_by_stage;
CREATE VIEW vw_portfolio_by_stage AS
SELECT stage, COUNT(*) AS projects, SUM(dwellings) AS dwellings, SUM(funding_amount) AS funding
FROM fact_project_snapshot GROUP BY stage;

DROP VIEW IF EXISTS vw_slippage_by_stream;
CREATE VIEW vw_slippage_by_stream AS
SELECT stream, COUNT(*) AS projects, SUM(dwellings) AS dwellings,
       ROUND(AVG(completion_slip_days), 1) AS avg_forecast_slip_days,
       SUM(CASE WHEN completion_slip_days > 90 THEN 1 ELSE 0 END) AS projects_over_90d,
       SUM(CASE WHEN max_overdue_days > 0 THEN 1 ELSE 0 END) AS projects_with_overdue_milestone
FROM fact_project_snapshot WHERE completion_slip_days IS NOT NULL GROUP BY stream;

DROP VIEW IF EXISTS vw_partner_performance;
CREATE VIEW vw_partner_performance AS
SELECT partner_id, COUNT(*) AS projects, ROUND(AVG(completion_slip_days), 1) AS avg_slip_days,
       RANK() OVER (ORDER BY AVG(completion_slip_days) DESC) AS slip_rank
FROM fact_project_snapshot WHERE completion_slip_days IS NOT NULL
GROUP BY partner_id HAVING COUNT(*) >= 4;

DROP VIEW IF EXISTS vw_dq_summary;
CREATE VIEW vw_dq_summary AS
SELECT rule_id, rule_name, severity, COUNT(DISTINCT project_id) AS projects
FROM silver_dq_exception GROUP BY rule_id, rule_name, severity ORDER BY rule_id;
