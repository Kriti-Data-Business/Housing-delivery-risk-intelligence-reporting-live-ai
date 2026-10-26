"""AI-assisted assurance of self-reported project commentary (human-in-the-loop).

What it does
1. Tags each partner commentary with a delivery-risk theme (TF-IDF + logistic regression, runs locally).
2. Routes each tag by confidence: auto-accept (with sampled QA), analyst review, or manual.
3. Cross-checks the narrative against structured data and flags 'says on track but the data says otherwise'.
4. Writes a review queue and an immutable-style audit log so every AI suggestion is traceable.

The model is deliberately simple and explainable. In production the tagger could be swapped for an LLM
behind the same routing, evaluation and audit layer (see docs/ai_adoption_plan.md).
Run:  python src/ai_assurance.py   (after pipeline.py and forecast.py)
"""
from __future__ import annotations
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline

ROOT = Path(__file__).resolve().parents[1]
MODEL_VERSION = "assurance-tagger-v1"
AUTO, REVIEW = 0.80, 0.50          # confidence thresholds (policy choices, tuned in shadow mode)
MINUTES_PER_MANUAL_READ = 3        # ASSUMPTION used for the modelled time saving, to be measured in a pilot
QA_SAMPLE = 0.10

KEYWORDS = {  # transparent rule-based baseline
    "approvals_delay": r"approval|contract negotiation|information request|delegate",
    "planning_delay": r"planning|development application|rezoning|permit|council",
    "cost_pressure": r"cost|tender|budget|viability|valuation|funding gap",
    "labour_shortage": r"labour|trade shortage|subcontractor|skilled",
    "supply_chain": r"supply chain|material|freight|fuel|delivery delays",
    "partner_capacity": r"capacity|resourcing|turnover|staff",
}

# Hand-written phrasings the model never saw (a small stress test for generalisation)
STRESS = [
    ("Still waiting on sign-off from the funding body before we can execute the agreement.", "approvals_delay"),
    ("The council has asked for further information on the DA so site works cannot begin.", "planning_delay"),
    ("Quotes have increased materially and we need to close a gap before committing.", "cost_pressure"),
    ("We cannot get enough carpenters and the build is behind as a result.", "labour_shortage"),
    ("Windows and cladding are arriving late from overseas suppliers.", "supply_chain"),
    ("Our small team is stretched and paperwork is lagging.", "partner_capacity"),
    ("Everything is going to plan and the next stage starts on time.", "on_track"),
    ("Contractor mobilised and works are progressing as scheduled.", "on_track"),
    ("Approval from the delegate is outstanding and dates are being revised.", "approvals_delay"),
    ("Tenders were higher than budget and a viability review is underway.", "cost_pressure"),
    ("Not enough skilled tradespeople are available on site this quarter.", "labour_shortage"),
    ("Steel deliveries have slipped by several weeks.", "supply_chain"),
]


def keyword_tag(text: str) -> str:
    t = text.lower()
    for theme, pat in KEYWORDS.items():
        if re.search(pat, t):
            return theme
    return "on_track"


def make_model() -> Pipeline:
    feats = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, lowercase=True, min_df=2)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=3)),  # robust to typos
    ])
    return Pipeline([("tfidf", feats), ("clf", LogisticRegression(C=6, max_iter=3000, class_weight="balanced"))])


def route(conf: float) -> str:
    return "auto_accept" if conf >= AUTO else ("analyst_review" if conf >= REVIEW else "manual_classification")


def main() -> None:
    con = sqlite3.connect(ROOT / "outputs" / "housing.db")
    snap = pd.read_sql("SELECT * FROM fact_project_snapshot", con)
    con.close()
    lab = pd.read_csv(ROOT / "data" / "commentary_labels.csv")
    df = snap.merge(lab, on="project_id")
    df = df[df.status != "Completed"].reset_index(drop=True)   # review applies to live projects
    X, y = df.commentary.fillna(""), df.commentary_label

    # 1. Evaluation on a held-out split
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, stratify=y, random_state=11)
    model = make_model().fit(Xtr, ytr)
    pred, proba = model.predict(Xte), model.predict_proba(Xte)
    conf = proba.max(axis=1)
    base_pred = Xte.map(keyword_tag)
    res = {
        "model_version": MODEL_VERSION, "n_live_projects": int(len(df)), "n_test": int(len(Xte)),
        "macro_f1_model": round(f1_score(yte, pred, average="macro"), 3),
        "macro_f1_keyword_baseline": round(f1_score(yte, base_pred, average="macro"), 3),
        "accuracy_model": round(accuracy_score(yte, pred), 3),
    }
    routes = pd.Series([route(c) for c in conf])
    res["routing_share_test"] = routes.value_counts(normalize=True).round(3).to_dict()
    res["accuracy_by_route_test"] = {r: round(float((pred[routes.values == r] == yte.values[routes.values == r]).mean()), 3)
                                     for r in routes.unique()}
    res["per_class_f1"] = {k: round(v["f1-score"], 2) for k, v in classification_report(yte, pred, output_dict=True).items()
                            if k in set(y)}
    stress_pred = model.predict([s for s, _ in STRESS])
    res["stress_test_accuracy"] = round(float(np.mean([a == b for a, (_, b) in zip(stress_pred, STRESS)])), 3)
    res["stress_test_n"] = len(STRESS)

    # 2. Out-of-fold predictions for every live project, so no project is scored by a model that trained on it
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=11)
    oof = cross_val_predict(make_model(), X, y, cv=skf, method="predict_proba")
    classes = sorted(y.unique())
    df["ai_theme"] = [classes[i] for i in oof.argmax(axis=1)]
    df["ai_confidence"] = oof.max(axis=1).round(3)
    df["route"] = [route(c) for c in df.ai_confidence]

    # 3. Narrative vs data consistency check
    df["mismatch_flag"] = (df.ai_theme == "on_track") & ((df.completion_slip_days.fillna(0) >= 60) | (df.max_overdue_days.fillna(0) >= 30))
    truth = (df.commentary_label == "on_track") & (df.driver_theme != "on_track")   # synthetic ground truth
    tp = int((df.mismatch_flag & truth).sum())
    res["consistency_check"] = {"flagged": int(df.mismatch_flag.sum()), "true_optimistic_narratives": int(truth.sum()),
                                "precision": round(tp / max(1, int(df.mismatch_flag.sum())), 3),
                                "recall": round(tp / max(1, int(truth.sum())), 3)}

    # 4. Review queue, prioritised by exposure (dwellings) and reason
    reasons = []
    for _, r in df.iterrows():
        rs = []
        if r.mismatch_flag:
            rs.append("Narrative says on track but data shows slippage or an overdue milestone")
        if r.route != "auto_accept":
            rs.append(f"Low-confidence tag ({r.route.replace('_', ' ')})")
        if r.dq_high > 0:
            rs.append("High-severity data quality issue")
        reasons.append("; ".join(rs))
    df["review_reason"] = reasons
    df["priority"] = (df.mismatch_flag * 3 + (df.route != "auto_accept") * 1 + (df.dq_high > 0) * 2) * np.log1p(df.dwellings)
    q = df[df.review_reason != ""].sort_values("priority", ascending=False)
    q[["project_id", "stream", "state", "stage", "dwellings", "ai_theme", "ai_confidence", "route", "mismatch_flag",
       "completion_slip_days", "max_overdue_days", "review_reason", "commentary"]].to_csv(ROOT / "outputs" / "ai_review_queue.csv", index=False)

    # 5. Audit log: every suggestion is recorded with model version, input hash, confidence and routing
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    audit = pd.DataFrame({
        "timestamp_utc": now, "model_version": MODEL_VERSION, "project_id": df.project_id,
        "input_sha256": df.commentary.map(lambda t: hashlib.sha256(str(t).encode()).hexdigest()[:16]),
        "ai_theme": df.ai_theme, "confidence": df.ai_confidence, "route": df.route,
        "reviewer": "", "decision": np.where(df.route == "auto_accept", "auto_accepted_sampled_qa", "pending_review"),
    })
    audit.to_csv(ROOT / "outputs" / "ai_audit_log.csv", index=False)

    # 6. Modelled analyst time (assumption-driven, to be measured in a shadow pilot)
    n = len(df)
    shares = df.route.value_counts(normalize=True)
    reads = n * (shares.get("analyst_review", 0) + shares.get("manual_classification", 0) + QA_SAMPLE * shares.get("auto_accept", 0))
    res["modelled_time"] = {"assumption_minutes_per_read": MINUTES_PER_MANUAL_READ,
                            "hours_manual_all": round(n * MINUTES_PER_MANUAL_READ / 60, 1),
                            "hours_with_routing": round(reads * MINUTES_PER_MANUAL_READ / 60, 1)}
    res["route_share_all_live"] = shares.round(3).to_dict()
    res["queue_size"] = int(len(q))
    (ROOT / "outputs" / "ai_metrics.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
