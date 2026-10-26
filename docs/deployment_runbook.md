# Deployment runbook

Status: this describes how the project would be promoted in Microsoft Fabric and Power BI. Only the CI build and the hosted dashboard were run for this reference implementation.

## Environments
| Env | Purpose | Data | Refresh |
|---|---|---|---|
| Dev | Build and unit test | Synthetic or masked | On demand |
| Test | UAT with business users | Masked production copy | Daily |
| Prod | Published reporting | Production | Per reporting cycle, plus daily |

## Promotion
1. Merge to main. CI runs generate, pipeline, forecast, AI, pytest. Any failure blocks the merge.
2. Deploy the warehouse objects (SQL files in order) to Test.
3. Use a Fabric deployment pipeline to move the semantic model and report from Dev to Test to Prod, with deployment rules that swap the data source per stage.
4. Run reconciliation checks in each stage. Compare row counts and dwelling totals to the previous cycle.
5. Business owner signs off in Test before Prod.

## Security
- Row level security by state for state delivery teams, tested with View as role.
- Workspace roles: Admin and Member for the data team, Viewer for stakeholders via an app.
- Sensitivity labels on the semantic model.

## Monitoring
- Refresh failure alerts to the data team.
- DQ rule counts tracked per cycle. A jump in R01, R02 or R05 triggers a call to the submitting program.
- Model drift report on theme mix and confidence distribution.

## Rollback
Redeploy the previous pipeline stage content. Warehouse changes are versioned SQL, so revert the commit and rerun.

## Handover
Data dictionary, measure definitions, this runbook, support contacts, and a list of known limitations.
