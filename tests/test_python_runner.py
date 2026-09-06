import textwrap
from awe.suite import load_suite
from awe.runners.python import run_python

# statistics.mean is pure Python and accepts keyword arguments; math.pow/math.sqrt are
# positional-only C functions, so they cannot be called with **inputs.


def test_runs_callable(tmp_path):
    d = tmp_path / "s"; (d / "cases").mkdir(parents=True)
    (d / "suite.yaml").write_text("name: m\nrunner: python\ntarget: 'statistics:mean'\n", encoding="utf-8")
    (d / "cases" / "a.yaml").write_text("id: a\ninputs: {data: [30, 34]}\nassert:\n  - equals: 32\n", encoding="utf-8")
    s = load_suite(d)
    out = run_python(s, s.cases[0])
    assert out.output == 32 and out.error is None and out.cost_usd == 0


def test_reports_exception(tmp_path):
    d = tmp_path / "s"; (d / "cases").mkdir(parents=True)
    (d / "suite.yaml").write_text("name: m\nrunner: python\ntarget: 'statistics:mean'\n", encoding="utf-8")
    (d / "cases" / "a.yaml").write_text("id: a\ninputs: {data: []}\nassert: []\n", encoding="utf-8")
    s = load_suite(d)
    out = run_python(s, s.cases[0])
    assert out.output is None and "StatisticsError" in out.error and "at least one data point" in out.error
