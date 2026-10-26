-- GOLD: star schema for the Power BI semantic model.
DROP TABLE IF EXISTS dim_project;
CREATE TABLE dim_project AS
SELECT project_id, round, stream, state, partner_id, housing_type, funding_product,
       dwellings_agreement AS dwellings, funding_amount, stage, status, commentary
FROM silver_project;

DROP TABLE IF EXISTS dim_partner;
CREATE TABLE dim_partner AS
SELECT partner_id, partner_type, size_band FROM bronze_partner;

DROP TABLE IF EXISTS fact_milestone;
CREATE TABLE fact_milestone AS
WITH m AS (
    SELECT project_id, 1 AS milestone_order, 'Approval' AS milestone,
           baseline_approval AS baseline_date, actual_approval AS actual_date, NULL AS forecast_date FROM silver_project
    UNION ALL
    SELECT project_id, 2, 'Contract close', baseline_contract_close, actual_contract_close, NULL FROM silver_project
    UNION ALL
    SELECT project_id, 3, 'Financial close', baseline_financial_close, actual_financial_close, NULL FROM silver_project
    UNION ALL
    SELECT project_id, 4, 'Construction start', baseline_construction_start, actual_construction_start, NULL FROM silver_project
    UNION ALL
    SELECT project_id, 5, 'Practical completion', baseline_practical_completion, actual_practical_completion,
           forecast_practical_completion FROM silver_project
)
SELECT m.project_id, m.milestone_order, m.milestone, m.baseline_date, m.actual_date, m.forecast_date,
       CASE WHEN m.actual_date IS NOT NULL
            THEN CAST(julianday(m.actual_date) - julianday(m.baseline_date) AS INTEGER)
            WHEN m.forecast_date IS NOT NULL
            THEN CAST(julianday(m.forecast_date) - julianday(m.baseline_date) AS INTEGER) END AS variance_days,
       CASE WHEN m.actual_date IS NULL AND m.baseline_date < (SELECT as_at_date FROM ref_as_at)
            THEN CAST(julianday((SELECT as_at_date FROM ref_as_at)) - julianday(m.baseline_date) AS INTEGER) END AS overdue_days
FROM m JOIN silver_project p USING (project_id)
WHERE p.status <> 'Withdrawn';

DROP TABLE IF EXISTS fact_project_snapshot;
CREATE TABLE fact_project_snapshot AS
WITH dq AS (
    SELECT project_id, COUNT(*) AS dq_flags,
           SUM(CASE WHEN severity = 'High' THEN 1 ELSE 0 END) AS dq_high
    FROM silver_dq_exception WHERE rule_id <> 'R06' GROUP BY project_id
),
slip AS (
    SELECT project_id,
           MAX(COALESCE(variance_days, 0)) AS worst_variance_days,
           MAX(COALESCE(overdue_days, 0))  AS max_overdue_days
    FROM fact_milestone GROUP BY project_id
)
SELECT p.project_id, p.round, p.stream, p.state, p.partner_id, p.stage, p.status,
       p.dwellings_agreement AS dwellings, p.funding_amount,
       p.baseline_practical_completion, p.forecast_practical_completion,
       CAST(julianday(p.forecast_practical_completion) - julianday(p.baseline_practical_completion) AS INTEGER)
           AS completion_slip_days,
       s.worst_variance_days, s.max_overdue_days,
       COALESCE(q.dq_flags, 0) AS dq_flags, COALESCE(q.dq_high, 0) AS dq_high,
       p.days_since_update, p.commentary
FROM silver_project p
LEFT JOIN slip s USING (project_id)
LEFT JOIN dq q USING (project_id)
WHERE p.status <> 'Withdrawn';
