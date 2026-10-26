# AI adoption plan: assisted commentary assurance

## Problem
Delivery partners write free-text commentary each quarter. Analysts read all of it to classify delay causes and spot narratives that contradict the milestone data. It is slow, inconsistent between readers, and the first thing dropped under time pressure.

## Use case
A model reads each commentary, proposes one of seven themes with a confidence score, and checks the narrative against the data (for example "on track" against a 96-day slip). Analysts keep the decision.

## Routing
| Confidence | Route | Human role |
|---|---|---|
| 0.80 or above | Auto-accept | 10% random QA sample |
| 0.50 to 0.80 | Analyst review | Confirms or corrects |
| Below 0.50 | Manual classification | Classifies from scratch |

Narrative and data mismatches always go to the review queue, whatever the confidence.

## Rollout
1. Shadow mode (one quarter). Model runs, analysts work as usual, compare agreement.
2. Assisted mode. Analysts see proposals and the queue. Auto-accept stays off.
3. Monitored mode. Auto-accept on for high confidence. Weekly drift report, quarterly relabel of a sample.

Exit criteria for each step: agreement with analysts at or above an agreed threshold, no unexplained drop in any theme, and sign-off from the data owner.

## Governance
- Every decision is written to an audit log with model version, confidence, route and timestamp.
- Humans can override any tag. Overrides feed the next training set.
- No personal data is used. Only project commentary and milestone fields.
- The model is a classifier with a transparent baseline. An LLM could replace it behind the same interface, but that is described here and not tested.
- Model changes need a regression run on the stress set before release.

## Risks
| Risk | Mitigation |
|---|---|
| Templated training text overstates accuracy | Stress test on novel phrasings, shadow mode on real text before trusting any score |
| Partners learn to game keywords | Consistency check against milestone data, periodic relabel |
| Over-reliance on auto-accept | QA sample, drift monitoring, threshold review |
| Theme drift as programs change | Quarterly review of class balance and confusion matrix |

## Measures of success
Analyst hours per cycle, agreement rate, override rate, share of mismatches caught, time from submission to published report.
