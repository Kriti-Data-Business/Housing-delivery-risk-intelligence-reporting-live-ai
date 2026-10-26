"""Bronze -> silver -> gold pipeline (SQLite stands in for a warehouse or Fabric SQL endpoint).
Run:  python src/pipeline.py
"""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "outputs" / "housing.db"
AS_AT = "2026-09-30"
SQL_FILES = ["02_silver.sql", "03_gold.sql", "04_views.sql"]


def run_sql_file(con: sqlite3.Connection, name: str) -> None:
    con.executescript((ROOT / "sql" / name).read_text())


def scalar(con, q):
    return con.execute(q).fetchone()[0]


def run() -> dict:
    DB.parent.mkdir(exist_ok=True)
    DB.unlink(missing_ok=True)
    con = sqlite3.connect(DB)
    log: dict = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "as_at": AS_AT, "steps": []}

    # BRONZE: land raw files untouched (everything as text)
    sub = pd.read_csv(ROOT / "data" / "srt_submissions.csv", dtype=str, keep_default_na=False)
    prt = pd.read_csv(ROOT / "data" / "partners.csv", dtype=str, keep_default_na=False)
    for c in ("funding_amount", "dwellings_agreement", "dwellings_reported"):
        sub[c] = pd.to_numeric(sub[c])
    sub.to_sql("bronze_srt_submission", con, index=False)
    prt.to_sql("bronze_partner", con, index=False)
    con.execute("CREATE TABLE ref_as_at AS SELECT ? AS as_at_date", (AS_AT,))
    log["steps"].append({"layer": "bronze", "rows": len(sub)})

    for f in SQL_FILES:
        run_sql_file(con, f)

    # RECONCILIATION CHECKS: the pipeline fails loudly rather than publishing numbers that do not tie out.
    bronze_rows = scalar(con, "SELECT COUNT(*) FROM bronze_srt_submission")
    bronze_projects = scalar(con, "SELECT COUNT(DISTINCT project_id) FROM bronze_srt_submission")
    silver_rows = scalar(con, "SELECT COUNT(*) FROM silver_project")
    dup_dropped = bronze_rows - silver_rows
    checks = {
        "silver rows equal distinct bronze projects": silver_rows == bronze_projects,
        "no duplicate project_id in silver": scalar(con, "SELECT COUNT(*) - COUNT(DISTINCT project_id) FROM silver_project") == 0,
        "dwellings tie out (bronze latest vs silver)": scalar(con, "SELECT SUM(dwellings_agreement) FROM silver_project") ==
            scalar(con, "SELECT SUM(dwellings_agreement) FROM (SELECT project_id, dwellings_agreement FROM bronze_srt_submission GROUP BY project_id)"),
        "gold snapshot excludes only withdrawn": scalar(con, "SELECT COUNT(*) FROM fact_project_snapshot") ==
            scalar(con, "SELECT COUNT(*) FROM silver_project WHERE status <> 'Withdrawn'"),
        "every milestone row has a project": scalar(con, "SELECT COUNT(*) FROM fact_milestone WHERE project_id NOT IN (SELECT project_id FROM dim_project)") == 0,
    }
    log["reconciliation"] = {"bronze_rows": bronze_rows, "silver_rows": silver_rows, "duplicates_resolved": dup_dropped, "checks": checks}
    failed = [k for k, v in checks.items() if not v]
    if failed:
        raise RuntimeError(f"Reconciliation failed: {failed}")

    gold_dir = ROOT / "outputs" / "gold"
    gold_dir.mkdir(exist_ok=True)
    for t in ["dim_project", "dim_partner", "fact_milestone", "fact_project_snapshot", "silver_dq_exception",
              "vw_portfolio_by_stage", "vw_slippage_by_stream", "vw_partner_performance", "vw_dq_summary"]:
        pd.read_sql(f"SELECT * FROM {t}", con).to_csv(gold_dir / f"{t}.csv", index=False)
    log["dq_summary"] = pd.read_sql("SELECT * FROM vw_dq_summary", con).to_dict("records")
    (ROOT / "outputs" / "pipeline_run.json").write_text(json.dumps(log, indent=2))
    con.commit()
    con.close()
    return log


if __name__ == "__main__":
    out = run()
    print(json.dumps({k: out[k] for k in ("reconciliation", "dq_summary")}, indent=2))
