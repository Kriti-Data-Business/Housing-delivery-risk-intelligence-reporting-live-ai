import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import pipeline  # noqa: E402

log = pipeline.run()
con = sqlite3.connect(pipeline.DB)
injected = json.loads((ROOT / "data" / "injected_issues.json").read_text())


def dq_count(rule):
    return con.execute("SELECT COUNT(DISTINCT project_id) FROM silver_dq_exception WHERE rule_id=?", (rule,)).fetchone()[0]


def test_reconciliation_checks_pass():
    assert all(log["reconciliation"]["checks"].values())


def test_one_row_per_project_in_silver():
    n, d = con.execute("SELECT COUNT(*), COUNT(DISTINCT project_id) FROM silver_project").fetchone()
    assert n == d


def test_latest_submission_wins_for_duplicates():
    row = con.execute("""SELECT b.last_updated, s.last_updated FROM bronze_srt_submission b
                         JOIN silver_project s USING (project_id)
                         WHERE b.project_id IN (SELECT project_id FROM bronze_srt_submission GROUP BY project_id HAVING COUNT(*) > 1)
                         ORDER BY b.last_updated ASC LIMIT 1""").fetchone()
    assert row[0] < row[1]


def test_every_injected_issue_is_detected():
    for rule in ("R01", "R02", "R04", "R05", "R06"):
        assert dq_count(rule) == injected[rule], rule


def test_no_clean_project_is_flagged_for_r01():
    bad = con.execute("""SELECT COUNT(*) FROM silver_project
                         WHERE forecast_practical_completion >= COALESCE(actual_construction_start, baseline_construction_start)
                         AND project_id IN (SELECT project_id FROM silver_dq_exception WHERE rule_id='R01')""").fetchone()[0]
    assert bad == 0


def test_gold_variance_is_actual_minus_baseline():
    r = con.execute("""SELECT variance_days, CAST(julianday(actual_date)-julianday(baseline_date) AS INT)
                       FROM fact_milestone WHERE actual_date IS NOT NULL LIMIT 200""").fetchall()
    assert r and all(a == b for a, b in r)


def test_withdrawn_projects_excluded_from_gold():
    assert con.execute("SELECT COUNT(*) FROM fact_project_snapshot WHERE status='Withdrawn'").fetchone()[0] == 0
