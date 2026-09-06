"""run_suite aggregation: pass rate, totals, and the first-failure summary."""
from awe import cli
from awe.suite import Suite, Case


def _suite():
    case = Case(id="a", description="", fixtures=None, inputs={}, assertions=[], path=None)
    return Suite(name="t", path=None, runner="python", prompt_file=None, allowed_tools=[], timeout_seconds=1,
                 max_cost_usd=1.0, judge={"enabled": True}, target="x:y", pass_threshold=1.0, cases=[case])


def _attempt(passed, error=None, assertions=(), judge=None):
    return {"passed": passed, "error": error, "cost_usd": 0.0, "seconds": 0.0,
            "assertions": list(assertions), "judge": judge, "output_excerpt": ""}


def test_first_failure_summary(monkeypatch):
    s = _suite()
    scripted = iter([
        _attempt(False, error="boom"),
        _attempt(False, assertions=[{"kind": "contains", "passed": False, "detail": "contains 'q'"}]),
        _attempt(False, judge={"pass": False, "reasons": ["invented a meeting"]}),
        _attempt(False, judge={"pass": False, "reasons": []}),
        _attempt(True),
    ])
    monkeypatch.setattr(cli, "_run_case_once", lambda *a, **k: next(scripted))
    firsts = [cli.run_suite(s, judge_on=True)["cases"][0]["first_failure"] for _ in range(5)]
    assert firsts == ["boom", "contains 'q'", "invented a meeting", "judge failed (no reasons)", None]
