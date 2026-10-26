# Housing Delivery Risk Intelligence

End-to-end reference project: data pipeline, data quality gate, risk scoring, Monte Carlo delivery forecast, AI-assisted commentary assurance, Power BI measures, CI, and a hosted dashboard. All data is synthetic and illustrative.

## Run it
```
pip install -r requirements.txt
python src/generate_data.py
python src/pipeline.py        # bronze, silver, gold, reconciliation
python src/forecast.py        # risk scores, scenarios, sensitivities
python src/ai_assurance.py    # tagger, routing, audit log
python -m pytest -q tests
```
Outputs land in `outputs/`.

## Layout
- `src/` generator, pipeline, forecast, AI module
- `sql/` silver, gold, views
- `tests/` 15 tests
- `dax/measures.dax` Power BI measures (not tested in Power BI)
- `docs/` case study, architecture, data dictionary, AI adoption plan, deployment runbook
- `.github/workflows/ci.yml` build and test

## Limits
Synthetic data. Risk weights and the 90% target are assumptions. AI metrics are inflated by templated text. Fabric and Power BI deployment are documented, not executed.
