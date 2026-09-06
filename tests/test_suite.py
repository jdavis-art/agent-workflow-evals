import textwrap
import pytest
from awe.suite import load_suite, SuiteError


def _write(tmp_path, suite_yaml, cases):
    d = tmp_path / "s"; (d / "cases").mkdir(parents=True)
    (d / "suite.yaml").write_text(textwrap.dedent(suite_yaml), encoding="utf-8")
    for name, body in cases.items():
        (d / "cases" / name).write_text(textwrap.dedent(body), encoding="utf-8")
    return d


def test_loads_python_suite(tmp_path):
    d = _write(tmp_path, """
        name: demo
        runner: python
        target: "math:sqrt"
    """, {"a.yaml": """
        id: four
        description: sqrt of 16
        inputs: {x: 16}
        assert:
          - equals: 4.0
    """})
    s = load_suite(d)
    assert s.name == "demo" and s.runner == "python" and s.target == "math:sqrt"
    assert s.pass_threshold == 1.0
    assert [c.id for c in s.cases] == ["four"]
    assert s.cases[0].assertions == [{"equals": 4.0}]


def test_claude_suite_defaults(tmp_path):
    d = _write(tmp_path, """
        name: c
        runner: claude
        prompt_file: prompt.md
    """, {"a.yaml": "id: a\nassert: []\n"})
    (d / "prompt.md").write_text("hello {fixtures}", encoding="utf-8")
    s = load_suite(d)
    assert s.allowed_tools == ["Read", "Glob", "Grep"]
    assert s.timeout_seconds == 300 and s.max_cost_usd == 0.5 and s.pass_threshold == 0.67
    assert s.judge == {"enabled": False}


def test_errors_name_the_problem(tmp_path):
    d = _write(tmp_path, "name: bad\nrunner: rocket\n", {"a.yaml": "id: a\nassert: []\n"})
    with pytest.raises(SuiteError, match="runner"):
        load_suite(d)
    d2 = _write(tmp_path / "two", "name: p\nrunner: python\n", {"a.yaml": "id: a\nassert: []\n"})
    with pytest.raises(SuiteError, match="target"):
        load_suite(d2)
    d3 = _write(tmp_path / "three", "name: p\nrunner: python\ntarget: 'a:b'\n", {"a.yaml": "description: no id\nassert: []\n"})
    with pytest.raises(SuiteError, match="id"):
        load_suite(d3)
