# Architecture

```
srt_submissions.csv + partners.csv      (synthetic quarterly reporting)
        |  pipeline.py loads as-is
        v
BRONZE  bronze_submission, bronze_partner       raw, duplicates kept
        |  sql/02_silver.sql
        v
SILVER  silver_project (latest per project, stage derived)
        silver_dq_exception (rules R01 to R06)
        |  reconciliation checks, pipeline FAILS on any break
        v
GOLD    dim_project, dim_partner, fact_milestone, fact_project_snapshot, vw_*
        |                      |                         |
        v                      v                         v
   Power BI model       forecast.py                ai_assurance.py
   (dax/measures.dax)   risk score + Monte Carlo   theme tagger, routing, audit log
        \_____________________|_________________________/
                              v
                  Live dashboard + review queue
```

Local SQLite stands in for a Fabric warehouse or SQL endpoint. The SQL is plain ANSI plus a few SQLite date functions (`julianday`), which map to `DATEDIFF` in T-SQL.

## Design decisions

1. Reconciliation is a gate. Row counts and dwelling totals must tie between layers or the run fails, so a broken load never reaches a report.
2. Quarantine, do not delete. Bad forecasts are excluded from simulation but stay visible in the exception table.
3. The risk score is additive and explainable. Every point can be traced to a rule. Weights are policy choices, not fitted values.
4. Score is not exposure. Exposure multiplies dwellings by the chance of missing the deadline, which surfaces large Green projects.
5. Simulation resamples observed stage delays by slippage band rather than assuming a distribution.
6. AI never overwrites data. It proposes a theme and a confidence, and a human decides below the threshold.
