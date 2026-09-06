"""results/<suite>/<timestamp>.json + latest.md with a diff against the previous run."""
from __future__ import annotations
import json
from pathlib import Path


def results_dir(root: Path, suite: str) -> Path:
    d = Path(root) / "results" / suite
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_run(root: Path, suite: str, record: dict) -> Path:
    p = results_dir(root, suite) / f"{record['timestamp']}.json"
    p.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    return p


def latest_two(root: Path, suite: str):
    files = sorted(results_dir(root, suite).glob("*.json"))
    recs = [json.loads(f.read_text(encoding="utf-8")) for f in files[-2:]]
    if not recs:
        return None, None
    return (recs[-1], recs[-2] if len(recs) > 1 else None)


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def render_latest_md(cur: dict, prev: dict | None) -> str:
    lines = [f"# {cur['suite']} · {cur['timestamp']}", "",
             f"Cases {cur['totals']['cases']} · passed {cur['totals']['passed']} · cost ${cur['totals']['cost_usd']:.3f}", "",
             "| Case | Pass rate | Cost | First failure |", "| --- | --- | --- | --- |"]
    for c in cur["cases"]:
        lines.append(f"| {c['case_id']} | {_pct(c['pass_rate'])} | ${c.get('cost_usd', 0):.3f} | {c.get('first_failure') or ''} |")
    lines += ["", "## Changed since last run"]
    if prev:
        prev_by = {c["case_id"]: c for c in prev["cases"]}
        changed = [f"- {c['case_id']}: {_pct(prev_by[c['case_id']]['pass_rate'])} -> {_pct(c['pass_rate'])}"
                   for c in cur["cases"] if c["case_id"] in prev_by and prev_by[c["case_id"]]["pass_rate"] != c["pass_rate"]]
        new = [f"- {c['case_id']}: new case" for c in cur["cases"] if c["case_id"] not in prev_by]
        lines += (changed + new) or ["- no change"]
    else:
        lines.append("- first run")
    return "\n".join(lines) + "\n"


def write_latest(root: Path, suite: str) -> Path:
    cur, prev = latest_two(root, suite)
    p = results_dir(root, suite) / "latest.md"
    p.write_text(render_latest_md(cur, prev), encoding="utf-8")
    return p
