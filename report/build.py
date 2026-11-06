"""Inline the report data into template.html.

Writes docs/index.html, a single standalone page that opens offline in any browser
and is served by GitHub Pages.
"""
import json
from pathlib import Path

import pandas as pd

root = Path(__file__).resolve().parent
d = root / "data"
proj = pd.read_csv(d / "project_risk.csv")
cols = ["project_id", "stream", "state", "stage", "dwellings_agreement", "completion_slip_days", "max_overdue_days",
        "dq_flags", "risk_score", "rag", "p_on_time", "dwellings_at_risk"]
rows = []
for r in proj[cols].itertuples(index=False):
    rows.append([r[0], r[1], r[2], r[3], int(r[4]), None if pd.isna(r[5]) else float(r[5]), int(r[6]), int(r[7]),
                 float(r[8]), r[9], float(r[10]), float(r[11])])
queue = pd.read_csv(d / "ai_review_queue.csv")
data = dict(
    projects=rows,
    queue=json.loads(queue[["project_id", "stream", "state", "stage", "ai_theme", "ai_confidence", "route", "review_reason", "commentary"]].to_json(orient="records")),
    scenarios=json.loads((d / "scenarios.json").read_text()),
    hist=json.loads((d / "hist.json").read_text()),
    sens=json.loads((d / "sensitivity.json").read_text()),
    ai=json.loads((d / "ai_metrics.json").read_text()),
    headline=json.loads((d / "headline.json").read_text()),
    dq=pd.read_csv(d / "vw_dq_summary.csv").to_dict(orient="records"),
)
# tie the live slippage table back to the published view
view = pd.read_csv(d / "vw_slippage_by_stream.csv").set_index("stream")
act = proj[proj.completion_slip_days.notna()]
for s, g in act.groupby("stream"):
    assert len(g) == view.loc[s, "projects"], (s, len(g))
    assert round(g.completion_slip_days.mean(), 1) == view.loc[s, "avg_forecast_slip_days"], s
    assert int((g.completion_slip_days > 90).sum()) == view.loc[s, "projects_over_90d"], s
    assert int((g.max_overdue_days > 0).sum()) == view.loc[s, "projects_with_overdue_milestone"], s
blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
frag = (root / "template.html").read_text().replace("/*__DATA__*/null", blob)
out = root.parent / "docs" / "index.html"
out.write_text("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"></head><body>" + frag + "</body></html>")
print("ok", len(frag) // 1024, "KB; slippage table ties to the published view")
