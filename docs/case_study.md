# Housing Delivery Risk Intelligence: from raw reporting to a live, AI-assisted assurance product

Technical case study. Reference implementation on synthetic data. Not Housing Australia data.

## 1. Context and decision supported
A national housing program funds hundreds of projects across several streams. Partners report quarterly milestones, forecasts and free-text commentary. Leadership needs one answer: will the portfolio deliver its dwelling target by the deadline, and where should attention go first?

The case study uses 420 synthetic projects across five funding streams plus a standard stream, 45 partners, and an illustrative target of 90% of planned dwellings (28,616 of 31,796) by 30 June 2029, as at 30 September 2026.

## 2. Approach in one page
| Layer | What was built | Why |
|---|---|---|
| Ingest and model | Bronze, silver, gold in SQL, star schema | Auditable lineage and a clean Power BI model |
| Trust | Six DQ rules, five reconciliation checks that fail the run | Stakeholders can rely on the numbers |
| Risk | Transparent 0 to 100 score with RAG | Explainable to program managers |
| Forecast | 4,000-run Monte Carlo, three scenarios, sensitivities | Turns slippage into delivery odds |
| AI | Commentary theme tagger with confidence routing and audit log | Removes reading load, keeps humans in control |
| Delivery | CI, tests, DAX measures, runbook, hosted dashboard | Build to live |

## 3. Data engineering
Raw submissions arrive with duplicates and errors. Bronze keeps them as received (426 rows). Silver keeps the latest submission per project (420 rows, 6 duplicates resolved), derives delivery stage and flags rule breaches. Gold publishes dim_project, dim_partner, fact_milestone and fact_project_snapshot plus reporting views.

Reconciliation checks run after every build: silver rows equal distinct bronze projects, no duplicate keys, dwellings tie out, gold excludes only withdrawn projects, every milestone belongs to a project. Any failure raises and stops the pipeline.

Data quality results: R01 forecast before construction start 6, R02 active with no forecast 14, R03 stale update 13, R04 dwellings mismatch 12, R05 completion without start 6, R06 duplicates 6. R01 forecasts and R05 completions are quarantined before simulation.

## 4. Risk scoring and forecasting
The score adds points for forecast slippage, overdue milestones, stale reporting, data quality flags, partner capacity and stage. Cutoffs are Green up to 30, Amber 30 to 45, Red above 45. These weights are policy choices and are documented, not fitted.

Result: Green 230, Amber 111, Red 24, Complete 45, with 3,415 dwellings at risk.

The simulation resamples the stage-transition delays actually observed in the data, grouped by slippage band, then applies attrition by project size and stage. It outputs the distribution of dwellings delivered by the deadline.

| Scenario | P50 dwellings | Chance of meeting target |
|---|---|---|
| Base | 28,412 | 41% |
| Accelerated approvals | 29,458 | 85% |
| Cost shock | 27,956 | 22% |

Sensitivity: halving attrition lifts odds to 73%, doubling cuts them to 4%. Delays 20% smaller give 74%, 20% larger give 15%.

Key insight: risk score is not exposure. The largest exposures are big Partnerships at Scale projects in early stages, some rated Green, because a modest chance of slipping across a very large dwelling count outweighs a high chance on a small project. Ranking by dwellings at risk puts them at the top of the attention list.

## 5. AI adoption use case
Analysts read every commentary to tag the delay cause and catch contradictions. The tagger automates the first pass and keeps people for judgement.

Design: TF-IDF on words and character n-grams with logistic regression, chosen because it is fast, explainable and easy to audit. Confidence drives routing: 0.80 or above is auto-accepted with a 10% QA sample, 0.50 to 0.80 goes to an analyst, below 0.50 is classified manually. A consistency check compares the narrative with milestone data, so "on track" against a 96-day slip lands in the queue whatever the confidence.

Results on held-out synthetic data (110 rows): macro F1 0.967 against 0.803 for a keyword baseline, accuracy 0.982, 95.5% auto-accepted. The consistency check flagged 23 narratives with precision 0.96 and recall 0.71. Live queue size is 70. Modelled analyst time falls from 18.2 to 2.9 hours per cycle, on a stated assumption of 3 minutes per read.

Honest limits. The text is templated, so these scores overstate real performance. A stress test on 12 unseen phrasings scored 83%, which is the more realistic signal. Recall of the consistency check is 71%, so it supports review and does not replace it. The model has not seen real partner language, so adoption starts in shadow mode (see ai_adoption_plan.md).

## 6. Engineering quality
15 automated tests cover reconciliation, rule behaviour, forecast properties and AI routing. GitHub Actions runs generate, pipeline, forecast, AI and tests on every push. Pipeline outputs are deterministic through seeded generation.

## 7. Build to live
1. Develop locally, run tests, open pull request.
2. CI builds from scratch and must pass.
3. The dashboard is published as a hosted page driven from the gold outputs and AI outputs.
4. In an enterprise setting the same gold tables sit in a Fabric warehouse, the semantic model uses dax/measures.dax, and a deployment pipeline promotes Dev to Test to Prod with row level security, refresh alerts and DQ monitoring (deployment_runbook.md).

What was actually executed: the pipeline, forecast, AI module, tests and the hosted dashboard. What is documented but not executed: Fabric deployment, the Power BI model (the DAX is untested in Power BI), and any LLM variant.

## 8. Stakeholder takeaways
- For executives: base-case odds of 41% against the illustrative target, with approvals speed and partner attrition as the two levers that matter.
- For program managers: a ranked list by dwellings at risk, not only by score.
- For data owners: six DQ rules that show which programs need to fix their submissions.
- For the assurance team: a review queue of 70 projects instead of 365 commentaries, with an audit trail.

## 9. What I would do next with real data
Replace synthetic inputs with the real reporting extract, calibrate risk weights against past outcomes, run the tagger in shadow mode on real commentary, add partner-level trend views, and schedule monthly refresh with alerting.
