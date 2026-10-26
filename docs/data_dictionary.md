# Data dictionary (synthetic)

| Layer | Object | Grain | Purpose |
|---|---|---|---|
| Bronze | bronze_submission | One row per project submission, duplicates kept | Raw quarterly reporting file as received |
| Bronze | bronze_partner | One row per delivery partner | Partner reference data |
| Silver | silver_project | One row per project | Latest submission only, stage derived, types cleaned |
| Silver | silver_dq_exception | One row per rule hit | Rules R01 to R06 with severity |
| Gold | dim_project, dim_partner | Project, partner | Descriptive attributes |
| Gold | fact_milestone | Project x milestone | Baseline, actual, forecast, variance and overdue days |
| Gold | fact_project_snapshot | One row per non-withdrawn project | Reporting grain for Power BI |
| Gold | vw_* | Aggregates | Portfolio by stage, slippage by stream, partner performance, DQ summary |

## Data quality rules

| Rule | Severity | Test |
|---|---|---|
| R01 | High | Forecast completion earlier than construction start |
| R02 | High | Active project with no forecast completion |
| R03 | Medium | Last update more than 60 days before the as-at date |
| R04 | Medium | Reported dwellings differ from the funding agreement |
| R05 | High | Completion recorded with no construction start |
| R06 | Info | Duplicate submission, latest kept |

Quarantine: R01 forecasts and R05 completions are removed before simulation so bad dates cannot distort delivery odds.
