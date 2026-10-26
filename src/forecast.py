"""Risk scoring and Monte Carlo delivery forecast.
Method: resample observed stage-transition delays from comparable projects (bootstrap), carry each project
forward from its last confirmed milestone, apply attrition, and count dwellings completed by the deadline.
Invalid values flagged by data quality rules are quarantined, not used.
Run:  python src/forecast.py   (after pipeline.py)
"""
from __future__ import annotations
import json
import sqlite3
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
AS_AT = date(2026, 9, 30)
DEADLINE = date(2029, 6, 30)
MS = ["approval", "contract_close", "financial_close", "construction_start", "practical_completion"]
TARGET_SHARE = 0.90          # illustrative target = 90% of planned dwellings
BASE_ATTRITION = 0.03        # calibrated to the ~2-3% withdrawn share in the synthetic data
BAND_MULT = {"Low": 1.0, "Mid": 1.5, "High": 2.5}
EARLY_STAGE_MULT = {"Pipeline": 1.5, "Approved": 1.5}


def ordv(s: pd.Series) -> np.ndarray:
    out = pd.to_datetime(s, errors="coerce")
    return out.map(lambda x: x.toordinal() if pd.notna(x) else np.nan).to_numpy(dtype=float)


def load() -> pd.DataFrame:
    con = sqlite3.connect(ROOT / "outputs" / "housing.db")
    p = pd.read_sql("SELECT * FROM silver_project WHERE status <> 'Withdrawn'", con)
    dq = pd.read_sql("SELECT project_id, rule_id FROM silver_dq_exception", con)
    snap = pd.read_sql("SELECT project_id, completion_slip_days, max_overdue_days, dq_flags, dq_high FROM fact_project_snapshot", con)
    part = pd.read_sql("SELECT * FROM vw_partner_performance", con)
    con.close()
    p = p.merge(snap, on="project_id", how="left")
    r01 = set(dq[dq.rule_id == "R01"].project_id)
    r05 = set(dq[dq.rule_id == "R05"].project_id)
    # QUARANTINE: do not let known-bad values drive the forecast
    p.loc[p.project_id.isin(r05), "actual_practical_completion"] = None
    p.loc[p.project_id.isin(r01), "forecast_practical_completion"] = None
    p.loc[p.project_id.isin(r05) & (p.status == "Completed"), "status"] = "Active"
    p = p.merge(part[["partner_id", "avg_slip_days"]].rename(columns={"avg_slip_days": "partner_avg_slip"}), on="partner_id", how="left")
    return p


def risk_scores(p: pd.DataFrame) -> pd.DataFrame:
    """Transparent additive score (0-100). Weights are policy choices, documented in docs/."""
    slip = p.completion_slip_days
    s = np.where(slip.isna(), 15, np.clip(slip.fillna(0) / 180, 0, 1) * 35)
    s = s + np.clip(p.max_overdue_days.fillna(0) / 120, 0, 1) * 20
    s = s + np.clip(p.dq_high.fillna(0), 0, 2) / 2 * 10 + np.where(p.days_since_update > 60, 5, 0)
    ps = p.partner_avg_slip.fillna(p.partner_avg_slip.median())
    s = s + (ps.rank(pct=True) * 15)
    s = s + p.stage.map({"Pipeline": 10, "Approved": 8, "Contracted": 6, "Financial close": 5, "Under construction": 3, "Completed": 0}).fillna(0)
    p = p.copy()
    p["risk_score"] = np.clip(s, 0, 100).round(1)
    p["rag"] = pd.cut(p.risk_score, [-1, 30, 45, 101], labels=["Green", "Amber", "Red"]).astype(str)
    p.loc[p.status == "Completed", ["risk_score", "rag"]] = [0, "Complete"]
    return p


def build_pools(p: pd.DataFrame):
    base = np.column_stack([ordv(p[f"baseline_{m}"]) for m in MS])
    act = np.column_stack([ordv(p[f"actual_{m}"]) for m in MS])
    delays = np.full(act.shape, np.nan)
    delays[:, 0] = act[:, 0] - base[:, 0]
    for j in range(1, 5):
        delays[:, j] = (act[:, j] - act[:, j - 1]) - (base[:, j] - base[:, j - 1])
    slip_to_date = np.nanmax(np.where(np.isnan(act), -np.inf, act - base), axis=1)
    band = np.where(slip_to_date > 90, "High", np.where(slip_to_date > 30, "Mid", "Low"))
    band = np.where(np.isinf(slip_to_date), "Mid", band)
    pools = {}
    for j in range(5):
        glob = delays[~np.isnan(delays[:, j]), j]
        for b in ("Low", "Mid", "High"):
            x = delays[(band == b) & ~np.isnan(delays[:, j]), j]
            pools[(b, j)] = x if len(x) >= 15 else glob
    return base, act, band, pools


def simulate(p, base, act, band, pools, S=4000, seed=7, accel=False, cost_shock=False, attr_mult=1.0, delay_scale=1.0):
    rng = np.random.default_rng(seed)
    N = len(p)
    asat, dead = AS_AT.toordinal(), DEADLINE.toordinal()
    achieved = ~np.isnan(act)
    first_missing = np.where(achieved.all(axis=1), 5, np.argmax(~achieved, axis=1))
    T = np.empty((S, N))
    for i in range(N):
        T[:, i] = act[i, first_missing[i] - 1] if first_missing[i] > 0 else base[i, 0]
        if first_missing[i] == 5:
            T[:, i] = act[i, 4]
    for j in range(5):
        active = first_missing <= j
        if not active.any():
            continue
        basedur = np.zeros(N) if j == 0 else (base[:, j] - base[:, j - 1])
        for i in np.where(active)[0]:
            d = rng.choice(pools[(band[i], j)], size=S) * delay_scale
            if cost_shock and j >= 3:
                d = np.where(d > 0, d * 1.3, d)
            dur = basedur[i] + d
            if accel and j in (1, 2):
                dur = np.maximum(20, dur - 21) if j == 1 else dur
                dur = np.where(d > 0, dur - 0.3 * d, dur)
            newT = T[:, i] + np.maximum(dur, 1)
            if j == first_missing[i]:  # milestone has not happened by as-at date, so it cannot be in the past
                newT = np.where(newT <= asat, asat + rng.integers(7, 60, size=S), newT)
            T[:, i] = newT
    mult = np.array([BAND_MULT[b] * EARLY_STAGE_MULT.get(s, 1.0) for b, s in zip(band, p.stage)])
    p_attr = np.clip(BASE_ATTRITION * mult * attr_mult, 0, 0.5)
    p_attr[first_missing == 5] = 0
    attrited = rng.random((S, N)) < p_attr
    on_time = (T <= dead) & ~attrited
    dw = p.dwellings_agreement.to_numpy(dtype=float)
    delivered = (on_time * dw).sum(axis=1)
    return delivered, on_time.mean(axis=0), T


def summarise(delivered, target):
    return {"p10": float(np.percentile(delivered, 10)), "p50": float(np.percentile(delivered, 50)),
            "p90": float(np.percentile(delivered, 90)), "mean": float(delivered.mean()),
            "p_meet_target": float((delivered >= target).mean()),
            "expected_shortfall": float(np.maximum(0, target - delivered).mean())}


def main():
    p = risk_scores(load())
    base, act, band, pools = build_pools(p)
    total = float(p.dwellings_agreement.sum())
    target = TARGET_SHARE * total
    scen = {"Base case": {}, "Accelerated approvals": {"accel": True}, "Cost shock": {"cost_shock": True}}
    out = {"as_at": AS_AT.isoformat(), "deadline": DEADLINE.isoformat(), "total_planned_dwellings": total,
           "illustrative_target": target, "simulations": 4000, "scenarios": {}}
    base_probs = None
    for name, kw in scen.items():
        delivered, probs, _ = simulate(p, base, act, band, pools, **kw)
        out["scenarios"][name] = summarise(delivered, target)
        counts, edges = np.histogram(delivered, bins=24)
        out["scenarios"][name]["hist"] = {"counts": counts.tolist(), "edges": edges.round(0).tolist()}
        if name == "Base case":
            base_probs = probs
    sens = []
    for label, kw in [("Attrition halved", {"attr_mult": 0.5}), ("Attrition doubled", {"attr_mult": 2.0}),
                      ("Delays 20% smaller", {"delay_scale": 0.8}), ("Delays 20% larger", {"delay_scale": 1.2})]:
        delivered, _, _ = simulate(p, base, act, band, pools, S=2000, **kw)
        sens.append({"case": label, **{k: v for k, v in summarise(delivered, target).items() if k in ("p50", "p_meet_target")}})
    out["sensitivity"] = sens
    p["p_on_time"] = base_probs.round(3)
    p["dwellings_at_risk"] = (p.dwellings_agreement * (1 - p.p_on_time)).round(1)
    out["rag_counts"] = p.rag.value_counts().to_dict()
    out["dwellings_at_risk_total"] = float(p.dwellings_at_risk.sum())
    (ROOT / "outputs" / "forecast_summary.json").write_text(json.dumps(out, indent=2))
    cols = ["project_id", "round", "stream", "state", "partner_id", "stage", "dwellings_agreement", "completion_slip_days",
            "max_overdue_days", "dq_flags", "risk_score", "rag", "p_on_time", "dwellings_at_risk"]
    p[cols].sort_values("dwellings_at_risk", ascending=False).to_csv(ROOT / "outputs" / "project_risk.csv", index=False)
    assump = pd.DataFrame([
        ("Deadline", DEADLINE.isoformat()), ("Illustrative target", f"{int(TARGET_SHARE*100)}% of planned dwellings"),
        ("Base attrition", f"{BASE_ATTRITION:.0%} per project, x{BAND_MULT}, early-stage x1.5"),
        ("Delay model", "Bootstrap of observed stage-transition delays, grouped by slippage band"),
        ("Accelerated approvals", "Contract-stage duration -21 days, approval-stage delays -30%"),
        ("Cost shock", "Construction-stage delays +30%, attrition x2"), ("Simulations", "4,000 per scenario")],
        columns=["assumption", "value"])
    assump.to_csv(ROOT / "outputs" / "assumptions.csv", index=False)
    print(json.dumps({k: out[k] for k in ("total_planned_dwellings", "illustrative_target", "rag_counts", "dwellings_at_risk_total")}, indent=2))
    for k, v in out["scenarios"].items():
        print(k, {a: round(b, 3) for a, b in v.items() if a != "hist"})
    print(json.dumps(sens, indent=1))


if __name__ == "__main__":
    main()
