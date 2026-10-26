import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import pipeline, forecast, ai_assurance  # noqa: E402

pipeline.run()
forecast.main()
ai_assurance.main()
F = json.loads((ROOT / "outputs" / "forecast_summary.json").read_text())
A = json.loads((ROOT / "outputs" / "ai_metrics.json").read_text())
risk = pd.read_csv(ROOT / "outputs" / "project_risk.csv")
audit = pd.read_csv(ROOT / "outputs" / "ai_audit_log.csv")


def test_probabilities_are_valid():
    assert risk.p_on_time.between(0, 1).all()
    for s in F["scenarios"].values():
        assert 0 <= s["p_meet_target"] <= 1 and s["p10"] <= s["p50"] <= s["p90"]


def test_scenario_ordering_is_sensible():
    s = F["scenarios"]
    assert s["Accelerated approvals"]["p50"] > s["Base case"]["p50"] > s["Cost shock"]["p50"]


def test_sensitivity_directions():
    d = {x["case"]: x for x in F["sensitivity"]}
    assert d["Attrition halved"]["p50"] > d["Attrition doubled"]["p50"]
    assert d["Delays 20% smaller"]["p50"] > d["Delays 20% larger"]["p50"]


def test_forecast_never_exceeds_planned_dwellings():
    assert all(s["p90"] <= F["total_planned_dwellings"] for s in F["scenarios"].values())


def test_quarantined_values_not_used():
    bad = risk[risk.dq_flags > 0]
    assert len(bad) > 0 and bad.p_on_time.notna().all()


def test_model_beats_keyword_baseline():
    assert A["macro_f1_model"] > A["macro_f1_keyword_baseline"]


def test_every_ai_suggestion_is_audited():
    assert len(audit) == A["n_live_projects"] and audit.project_id.is_unique
    assert set(audit.route) <= {"auto_accept", "analyst_review", "manual_classification"}
    assert (audit[audit.route != "auto_accept"].decision == "pending_review").all()


def test_low_confidence_never_auto_accepted():
    assert (audit[audit.route == "auto_accept"].confidence >= ai_assurance.AUTO).all()
