"""Generate a SYNTHETIC, illustrative project portfolio that mimics the *structure* of a
social and affordable housing delivery program (funding rounds, streams, milestones, self-reported
status updates). No real Housing Australia data is used. All names, values and text are invented.
"""
from __future__ import annotations
import json
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

SEED = 2026
AS_AT = date(2026, 9, 30)
OUT = Path(__file__).resolve().parents[1] / "data"
THEMES = ["on_track", "approvals_delay", "planning_delay", "cost_pressure",
          "labour_shortage", "supply_chain", "partner_capacity"]
THEME_P = [0.42, 0.12, 0.10, 0.12, 0.10, 0.06, 0.08]
# mean extra delay (days) added to each of: approval->contract, contract->fin close, fin close->start, construction
DELAY = {
    "on_track":         (0, 0, 0, 0),
    "approvals_delay":  (55, 20, 0, 0),
    "planning_delay":   (0, 15, 70, 0),
    "cost_pressure":    (0, 50, 25, 35),
    "labour_shortage":  (0, 0, 10, 80),
    "supply_chain":     (0, 0, 0, 60),
    "partner_capacity": (30, 55, 20, 20),
}
TEXT = {
    "on_track": ["Project progressing in line with baseline. No material issues to report.",
                 "Works on schedule and next milestone expected as planned.",
                 "No variance to program. Partner reports steady progress.",
                 "Delivery tracking to baseline and contractor engaged."],
    "approvals_delay": ["Awaiting final approval from the delegate and the contracting timeline has moved.",
                        "Contract negotiations extended due to outstanding information requests.",
                        "Approval pathway is taking longer than planned and revised dates are being confirmed."],
    "planning_delay": ["Development application assessment is taking longer than expected.",
                       "Planning conditions are under review with council and start of works is deferred.",
                       "Rezoning and permit conditions have pushed back site establishment."],
    "cost_pressure": ["Tender prices came in above budget and the partner is reviewing the funding gap.",
                      "Construction cost escalation is affecting viability and value engineering is underway.",
                      "Financial close is pending while cost increases and valuation are resolved."],
    "labour_shortage": ["Builder reports trade shortages affecting site progress.",
                        "Skilled labour availability has slowed framing and fit-out works.",
                        "Subcontractor capacity constraints are extending the build program."],
    "supply_chain": ["Material delivery delays for steel and timber are affecting the program.",
                     "Supply chain disruption to fittings and prefabricated components.",
                     "Freight and fuel cost impacts are delaying key deliveries."],
    "partner_capacity": ["Partner resourcing constraints are slowing reporting and contract documentation.",
                         "Limited internal capacity at the delivery partner and support has been requested.",
                         "Staff turnover at the partner has delayed documentation and financial close."],
}
SUFFIX = ["", "", " Next update due next month.", " Site visit scheduled.", " Partner engaged with the investment manager."]
STATES = ["NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"]
STATE_P = [0.29, 0.25, 0.20, 0.10, 0.07, 0.04, 0.03, 0.02]
STREAMS_FR3 = ["S1 First Nations", "S2 Housing Diversity", "S3 States and Territories",
               "S4 Partnerships at Scale", "S5 Release 1"]
STREAM_P = [0.12, 0.45, 0.18, 0.05, 0.20]


def d(x: date) -> str:
    return x.isoformat()


def noisy(text: str, rng) -> str:
    if rng.random() < 0.10:  # light noise: dropped characters, lower-casing
        i = int(rng.integers(5, max(6, len(text) - 5)))
        text = text[:i] + text[i + 1:]
    if rng.random() < 0.08:
        text = text.lower()
    return text


def main() -> None:
    rng = np.random.default_rng(SEED)
    OUT.mkdir(exist_ok=True)

    n_partners = 45
    partners = pd.DataFrame({
        "partner_id": [f"P{i:02d}" for i in range(1, n_partners + 1)],
        "partner_type": rng.choice(["Community housing provider", "State or territory agency",
                                     "First Nations housing organisation", "Delivery partner"],
                                    n_partners, p=[0.6, 0.12, 0.13, 0.15]),
        "size_band": rng.choice(["Small", "Medium", "Large"], n_partners, p=[0.4, 0.4, 0.2]),
    })
    capacity = np.clip(rng.beta(5, 2.5, n_partners), 0.25, 1.0)  # hidden driver, never exported

    windows = {"FR01": (date(2024, 6, 1), date(2024, 12, 31), 70),
               "FR02": (date(2025, 3, 1), date(2025, 9, 30), 45),
               "FR03": (date(2026, 1, 15), date(2027, 2, 28), 305)}
    rows, labels = [], []
    pid = 1000
    for rnd, (w0, w1, n) in windows.items():
        for _ in range(n):
            pid += 1
            project_id = f"PRJ-{pid}"
            pidx = int(rng.integers(0, n_partners))
            theme = rng.choice(THEMES, p=THEME_P)
            amp = 1.6 - capacity[pidx]
            stream = "Standard" if rnd != "FR03" else str(rng.choice(STREAMS_FR3, p=STREAM_P))
            dw = int(np.clip(rng.lognormal(3.9, 0.7), 8, 420))
            if stream.startswith("S4"):
                dw = int(rng.integers(500, 700))
            housing = str(rng.choice(["Social", "Affordable"], p=[0.5, 0.5]))
            if stream.startswith("S3"):
                housing = "Social"
            product = str(rng.choice(["Grant", "Concessional loan", "Availability payment"], p=[0.2, 0.35, 0.45]))
            b_app = w0 + timedelta(days=int(rng.integers(0, (w1 - w0).days + 1)))
            d1, d2, d3 = [max(20, int(rng.normal(m, s))) for m, s in ((110, 25), (60, 15), (45, 12))]
            d4 = int(np.clip(330 + dw * 1.5 + rng.normal(0, 60), 300, 900))
            b_con, b_fin = b_app + timedelta(days=d1), b_app + timedelta(days=d1 + d2)
            b_start = b_app + timedelta(days=d1 + d2 + d3)
            d4 = int(min(d4, max(300, (date(2029, 3, 31) - b_start).days)))  # program baselines are designed to land before the 30 Jun 2029 deadline
            b_comp = b_start + timedelta(days=d4)
            mean = DELAY[theme]
            delays = [int(max(0, m * amp * rng.uniform(0.5, 1.5) + rng.exponential(4 if theme == "on_track" else 10)))
                      for m in mean]
            a_app = b_app + timedelta(days=int(max(0, rng.normal(6, 5))))
            a_con = a_app + timedelta(days=d1 + delays[0])
            a_fin = a_con + timedelta(days=d2 + delays[1])
            a_start = a_fin + timedelta(days=d3 + delays[2])
            true_comp = a_start + timedelta(days=d4 + delays[3])
            act = {"approval": a_app, "contract_close": a_con, "financial_close": a_fin,
                   "construction_start": a_start, "practical_completion": true_comp}
            seen, prev_ok = {}, True
            for k, v in act.items():
                prev_ok = prev_ok and v <= AS_AT
                seen[k] = v if prev_ok else None
            status = "Withdrawn" if rng.random() < 0.03 else ("Completed" if seen["practical_completion"] else "Active")
            slip = (true_comp - b_comp).days
            optimism = rng.uniform(0.0, 0.1) if theme == "on_track" else rng.uniform(0.1, 0.7)
            fc = b_comp + timedelta(days=int(max(0, slip * (1 - optimism))))
            forecast = None if status in ("Withdrawn", "Completed") else fc
            # commentary: what the partner *says* (may be over-optimistic vs structured data)
            said = theme
            if theme != "on_track" and slip > 90 and rng.random() < 0.18:
                said = "on_track"
            text = rng.choice(TEXT[said])
            if said != "on_track" and rng.random() < 0.12:
                other = rng.choice([t for t in THEMES if t not in ("on_track", said)])
                text += " " + rng.choice(TEXT[other])
            text = noisy(text + str(rng.choice(SUFFIX)), rng)
            stale = rng.random() < 0.09
            lu = AS_AT - timedelta(days=int(rng.integers(61, 150)) if stale else int(min(55, rng.exponential(22))))
            rows.append(dict(
                project_id=project_id, round=rnd, stream=stream,
                state=str(rng.choice(STATES, p=STATE_P)), partner_id=partners.partner_id[pidx],
                housing_type=housing, funding_product=product,
                funding_amount=int(dw * rng.uniform(250_000, 450_000)),
                dwellings_agreement=dw, dwellings_reported=dw,
                baseline_approval=d(b_app), baseline_contract_close=d(b_con), baseline_financial_close=d(b_fin),
                baseline_construction_start=d(b_start), baseline_practical_completion=d(b_comp),
                actual_approval=d(seen["approval"]) if seen["approval"] else "",
                actual_contract_close=d(seen["contract_close"]) if seen["contract_close"] else "",
                actual_financial_close=d(seen["financial_close"]) if seen["financial_close"] else "",
                actual_construction_start=d(seen["construction_start"]) if seen["construction_start"] else "",
                actual_practical_completion=d(seen["practical_completion"]) if seen["practical_completion"] else "",
                forecast_practical_completion=d(forecast) if forecast else "",
                status=status, last_updated=d(lu), commentary=text))
            labels.append(dict(project_id=project_id, commentary_label=said, driver_theme=theme))

    df = pd.DataFrame(rows)
    lab = pd.DataFrame(labels)
    inj = {k: [] for k in ["R01", "R02", "R03", "R04", "R05", "R06"]}
    active = df.index[(df.status == "Active") & (df.actual_construction_start != "")].tolist()
    for i in rng.choice(active, size=max(6, int(0.08 * len(active))), replace=False):
        df.loc[i, "forecast_practical_completion"] = d(date.fromisoformat(df.loc[i, "actual_construction_start"]) - timedelta(days=30))
        inj["R01"].append(df.loc[i, "project_id"])
    r01_ids = set(inj["R01"])
    act_f = df.index[(df.status == "Active") & (df.forecast_practical_completion != "") & (~df.project_id.isin(r01_ids))].tolist()
    for i in rng.choice(act_f, size=int(0.04 * len(act_f)), replace=False):
        df.loc[i, "forecast_practical_completion"] = ""
        inj["R02"].append(df.loc[i, "project_id"])
    for i in rng.choice(df.index, size=int(0.03 * len(df)), replace=False):
        df.loc[i, "dwellings_reported"] = int(round(df.loc[i, "dwellings_agreement"] * rng.choice([0.88, 0.9, 1.1, 1.12])))
        inj["R04"].append(df.loc[i, "project_id"])
    cand = df.index[(df.status == "Active") & (df.actual_construction_start == "")].tolist()
    for i in rng.choice(cand, size=max(1, int(0.015 * len(df))), replace=False):
        df.loc[i, "actual_practical_completion"] = d(AS_AT - timedelta(days=20))
        inj["R05"].append(df.loc[i, "project_id"])
    dup_idx = rng.choice(df.index, size=int(0.015 * len(df)), replace=False)
    dups = df.loc[dup_idx].copy()
    dups["last_updated"] = (pd.to_datetime(dups["last_updated"]) - pd.Timedelta(days=12)).dt.strftime("%Y-%m-%d")
    inj["R06"] = dups.project_id.tolist()
    df = pd.concat([df, dups], ignore_index=True)
    df.insert(0, "submission_id", [f"SUB-{i:05d}" for i in range(1, len(df) + 1)])

    df.to_csv(OUT / "srt_submissions.csv", index=False)
    partners.to_csv(OUT / "partners.csv", index=False)
    lab.to_csv(OUT / "commentary_labels.csv", index=False)  # evaluation ground truth only
    (OUT / "injected_issues.json").write_text(json.dumps({k: len(set(v)) for k, v in inj.items()}, indent=2))
    print(f"submissions={len(df)} projects={df.project_id.nunique()} injected={ {k: len(set(v)) for k, v in inj.items()} }")


if __name__ == "__main__":
    main()
