"""awe run <suite> [--case ID]... [--repeat N] [--judge] [--dry-run] [--root DIR]
   awe diff <suite>            awe list [--root DIR]"""
from __future__ import annotations
import argparse
import datetime as dt
import sys
from pathlib import Path

from .assertions import check
from .results import save_run, write_latest, latest_two, render_latest_md
from .runners.python import run_python
from .suite import load_suite, Suite, Case

EXCERPT_CHARS = 20_000  # a workflow answer ends with a paste-ready prompt; 2,000 cut it off on real fixtures


def _run_case_once(suite: Suite, case: Case, judge_on: bool, dry_run: bool) -> dict:
    if suite.runner == "python":
        out = run_python(suite, case)
    else:
        from .runners.claude import run_claude
        out = run_claude(suite, case, dry_run=dry_run)
    results = [] if out.error else [check(a, out.output) for a in case.assertions]
    passed = out.error is None and all(r.passed for r in results)
    judge_res = None
    if passed and judge_on and suite.judge.get("enabled"):
        from .judge import judge
        judge_res = judge(suite, case, out.output)
        passed = judge_res["pass"]
        out.cost_usd += judge_res.get("cost_usd", 0.0)
    if out.error is None and out.cost_usd > suite.max_cost_usd:
        passed = False
        out.error = f"cost ${out.cost_usd:.3f} exceeded max ${suite.max_cost_usd:.2f}"
    return {"passed": passed, "error": out.error, "cost_usd": out.cost_usd, "seconds": round(out.seconds, 2),
            "assertions": [vars(r) for r in results], "judge": judge_res,
            "output_excerpt": (out.output if isinstance(out.output, str) else repr(out.output))[:EXCERPT_CHARS]}


def _failure_summary(attempt: dict) -> str | None:
    """One line naming why a failed attempt failed: runner error, first failing assertion, or judge reason."""
    if attempt["error"]:
        return attempt["error"]
    for r in attempt["assertions"]:
        if not r["passed"]:
            return r["detail"]
    verdict = attempt.get("judge")
    if verdict and not verdict.get("pass", False):
        reasons = verdict.get("reasons") or []
        return reasons[0] if reasons else "judge failed (no reasons)"
    return None


def run_suite(suite: Suite, case_ids: list[str] | None = None, repeat: int = 1, judge_on: bool = False, dry_run: bool = False) -> dict:
    cases = [c for c in suite.cases if not case_ids or c.id in case_ids]
    record = {"suite": suite.name, "timestamp": dt.datetime.now().strftime("%Y-%m-%dT%H-%M-%S"), "repeat": repeat, "cases": [], "totals": {}}
    for case in cases:
        attempts = [_run_case_once(suite, case, judge_on, dry_run) for _ in range(repeat)]
        rate = sum(1 for a in attempts if a["passed"]) / len(attempts)
        first_fail = next((_failure_summary(a) for a in attempts if not a["passed"]), None)
        record["cases"].append({"case_id": case.id, "pass_rate": rate, "cost_usd": sum(a["cost_usd"] for a in attempts), "first_failure": first_fail, "attempts": attempts})
    record["totals"] = {"cases": len(record["cases"]), "passed": sum(1 for c in record["cases"] if c["pass_rate"] >= suite.pass_threshold),
                        "cost_usd": sum(c["cost_usd"] for c in record["cases"]), "threshold": suite.pass_threshold}
    return record


def main(argv=None) -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    p = argparse.ArgumentParser(prog="awe")
    p.add_argument("--root", default=".", help="folder holding suites/ and results/")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("suite"); r.add_argument("--case", action="append"); r.add_argument("--repeat", type=int, default=1)
    r.add_argument("--judge", action="store_true"); r.add_argument("--dry-run", action="store_true")
    d = sub.add_parser("diff"); d.add_argument("suite")
    sub.add_parser("list")
    a = p.parse_args(argv)
    root = Path(a.root)
    if a.cmd == "list":
        for s in sorted((root / "suites").glob("*/suite.yaml")):
            print(s.parent.name)
        return 0
    if a.cmd == "diff":
        cur, prev = latest_two(root, a.suite)
        if not cur:
            print("no runs"); return 1
        print(render_latest_md(cur, prev)); return 0
    suite = load_suite(root / "suites" / a.suite)
    record = run_suite(suite, a.case, a.repeat, a.judge, a.dry_run)
    if a.dry_run:
        for c in record["cases"]:
            for attempt in c["attempts"]:
                print(f"[{c['case_id']}] {attempt['error'] or attempt['output_excerpt']}")
        print("dry run complete (no CLI calls)"); return 0
    save_run(root, suite.name, record)
    print(write_latest(root, suite.name).read_text(encoding="utf-8"))
    return 0 if record["totals"]["passed"] == record["totals"]["cases"] else 1


if __name__ == "__main__":
    sys.exit(main())
