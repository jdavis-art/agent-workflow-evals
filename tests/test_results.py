import json
from awe.results import save_run, latest_two, render_latest_md, write_latest


def _rec(ts, cases):
    return {"suite": "demo", "timestamp": ts, "cases": cases, "totals": {"cases": len(cases), "passed": sum(1 for c in cases if c["pass_rate"] >= 1), "cost_usd": 0.0}}


def test_save_latest_and_diff(tmp_path):
    a = _rec("2026-09-05T10-00-00", [{"case_id": "x", "pass_rate": 1.0, "cost_usd": 0, "first_failure": None}, {"case_id": "y", "pass_rate": 0.0, "cost_usd": 0, "first_failure": "contains 'q'"}])
    b = _rec("2026-09-05T11-00-00", [{"case_id": "x", "pass_rate": 0.33, "cost_usd": 0.1, "first_failure": "regex"}, {"case_id": "y", "pass_rate": 1.0, "cost_usd": 0, "first_failure": None}])
    save_run(tmp_path, "demo", a); save_run(tmp_path, "demo", b)
    cur, prev = latest_two(tmp_path, "demo")
    assert cur["timestamp"] == b["timestamp"] and prev["timestamp"] == a["timestamp"]
    md = render_latest_md(cur, prev)
    assert "| x | 33% |" in md and "regex" in md
    assert "x: 100% -> 33%" in md and "y: 0% -> 100%" in md
    p = write_latest(tmp_path, "demo")
    assert p.name == "latest.md" and p.read_text(encoding="utf-8") == md
