-- SILVER: one clean, typed row per project (latest submission wins) plus a data quality exception table.
DROP TABLE IF EXISTS silver_project;
CREATE TABLE silver_project AS
WITH ranked AS (
    SELECT b.*,
           ROW_NUMBER() OVER (PARTITION BY project_id
                              ORDER BY last_updated DESC, submission_id DESC) AS rn
    FROM bronze_srt_submission b
),
latest AS (SELECT * FROM ranked WHERE rn = 1),
asat AS (SELECT as_at_date FROM ref_as_at)
SELECT
    l.project_id, l.round, l.stream, l.state, l.partner_id, l.housing_type, l.funding_product,
    l.funding_amount, l.dwellings_agreement, l.dwellings_reported,
    l.baseline_approval, l.baseline_contract_close, l.baseline_financial_close,
    l.baseline_construction_start, l.baseline_practical_completion,
    NULLIF(l.actual_approval, '')             AS actual_approval,
    NULLIF(l.actual_contract_close, '')       AS actual_contract_close,
    NULLIF(l.actual_financial_close, '')      AS actual_financial_close,
    NULLIF(l.actual_construction_start, '')   AS actual_construction_start,
    NULLIF(l.actual_practical_completion, '') AS actual_practical_completion,
    NULLIF(l.forecast_practical_completion, '') AS forecast_practical_completion,
    l.status, l.last_updated, l.commentary,
    CAST(julianday(a.as_at_date) - julianday(l.last_updated) AS INTEGER) AS days_since_update,
    CASE
        WHEN l.status = 'Withdrawn' THEN 'Withdrawn'
        WHEN l.status = 'Completed' THEN 'Completed'
        WHEN NULLIF(l.actual_construction_start, '') IS NOT NULL THEN 'Under construction'
        WHEN NULLIF(l.actual_financial_close, '')    IS NOT NULL THEN 'Financial close'
        WHEN NULLIF(l.actual_contract_close, '')     IS NOT NULL THEN 'Contracted'
        WHEN NULLIF(l.actual_approval, '')           IS NOT NULL THEN 'Approved'
        ELSE 'Pipeline'
    END AS stage
FROM latest l CROSS JOIN asat a;

-- Data quality rules. Each rule returns the project, the rule and a human-readable detail.
DROP TABLE IF EXISTS silver_dq_exception;
CREATE TABLE silver_dq_exception AS
SELECT project_id, 'R01' AS rule_id, 'Forecast completion precedes construction start' AS rule_name,
       'High' AS severity,
       'Forecast ' || forecast_practical_completion || ' is before start ' ||
       COALESCE(actual_construction_start, baseline_construction_start) AS detail
FROM silver_project
WHERE forecast_practical_completion IS NOT NULL
  AND forecast_practical_completion < COALESCE(actual_construction_start, baseline_construction_start)
UNION ALL
SELECT project_id, 'R02', 'Active project has no forecast completion date', 'High',
       'Stage ' || stage || ' with no forecast'
FROM silver_project WHERE status = 'Active' AND forecast_practical_completion IS NULL
UNION ALL
SELECT project_id, 'R03', 'Update is stale (over 60 days)', 'Medium',
       'Last update ' || days_since_update || ' days ago'
FROM silver_project
WHERE status = 'Active' AND stage <> 'Pipeline' AND days_since_update > 60
UNION ALL
SELECT project_id, 'R04', 'Reported dwellings differ from funding agreement', 'Medium',
       'Reported ' || dwellings_reported || ' vs agreement ' || dwellings_agreement
FROM silver_project WHERE dwellings_reported <> dwellings_agreement
UNION ALL
SELECT project_id, 'R05', 'Completion recorded without a construction start', 'High',
       'Actual completion ' || actual_practical_completion || ' but no start date'
FROM silver_project
WHERE actual_practical_completion IS NOT NULL AND actual_construction_start IS NULL
UNION ALL
SELECT project_id, 'R06', 'Duplicate submissions resolved (latest kept)', 'Info',
       COUNT(*) || ' submissions received'
FROM bronze_srt_submission GROUP BY project_id HAVING COUNT(*) > 1;
