import sys
import pathlib
from awe.suite import load_suite
from awe.judge import judge, parse_verdict, build_context, CONTEXT_CAP

STUB = [sys.executable, str(pathlib.Path(__file__).resolve().parent.parent / "scripts" / "fake_claude.py")]


def _suite(tmp_path, judge_extra="", case_extra=""):
    d = tmp_path / "s"; (d / "cases").mkdir(parents=True)
    (d / "suite.yaml").write_text(f"name: j\nrunner: claude\nprompt_file: p.md\njudge:\n  enabled: true\n  rubric_file: rubric.md\n{judge_extra}", encoding="utf-8")
    (d / "p.md").write_text("x", encoding="utf-8"); (d / "rubric.md").write_text("Every action item must trace to the fixture.", encoding="utf-8")
    (d / "cases" / "a.yaml").write_text(f"id: a\nassert: []\n{case_extra}", encoding="utf-8")
    return load_suite(d)


def test_judge_context_files_reach_the_prompt(tmp_path):
    s = _suite(tmp_path, judge_extra="  context_files: [collectors.json]\n", case_extra="fixtures: fixtures\n")
    (s.path / "fixtures").mkdir()
    (s.path / "fixtures" / "collectors.json").write_text('{"note": "GOOD OUTPUT"}', encoding="utf-8")
    r = judge(s, s.cases[0], "meh", cli=STUB)  # the stub passes only if the marker from the file is in the prompt
    assert r["pass"] is True


def test_judge_context_file_missing_fails(tmp_path):
    s = _suite(tmp_path, judge_extra="  context_files: [collectors.json]\n", case_extra="fixtures: fixtures\n")
    (s.path / "fixtures").mkdir()
    r = judge(s, s.cases[0], "GOOD OUTPUT", cli=STUB)
    assert r["pass"] is False and r["reasons"] == ["context file missing: collectors.json"] and r["cost_usd"] == 0


def test_build_context_caps_total_size(tmp_path):
    (tmp_path / "big.txt").write_text("x" * (CONTEXT_CAP + 500), encoding="utf-8")
    (tmp_path / "small.txt").write_text("tail", encoding="utf-8")
    text = build_context(tmp_path, ["big.txt", "small.txt"])
    assert "FIXTURE DATA" in text and "big.txt" in text and "[truncated" in text
    assert len(text) <= CONTEXT_CAP + 200  # cap plus headers and the marker


def test_judge_pass_and_fail(tmp_path):
    s = _suite(tmp_path)
    ok = judge(s, s.cases[0], "GOOD OUTPUT", cli=STUB)
    assert ok["pass"] is True and ok["cost_usd"] == 0.001
    bad = judge(s, s.cases[0], "meh", cli=STUB)
    assert bad["pass"] is False and bad["reasons"] == ["stub verdict"]


def test_judge_strips_code_fences(tmp_path):
    s = _suite(tmp_path)
    ok = judge(s, s.cases[0], "GOOD OUTPUT FENCED", cli=STUB)
    assert ok["pass"] is True and ok["reasons"] == ["stub verdict"]


def test_judge_non_json(tmp_path, monkeypatch):
    s = _suite(tmp_path)
    r = judge(s, s.cases[0], "x", cli=[sys.executable, "-c", "print('{\"result\": \"not json at all\", \"total_cost_usd\": 0}')"])
    assert r["pass"] is False and r["reasons"] == ["non-JSON judge answer"]


def test_parse_verdict_shapes():
    assert parse_verdict('{"pass": true, "reasons": ["a", 2]}') == {"pass": True, "reasons": ["a", "2"]}
    assert parse_verdict('```json\n{"pass": false, "reasons": []}\n```') == {"pass": False, "reasons": []}
    assert parse_verdict('Sure! {"pass": true, "reasons": []}') is None  # prose around the object is not a verdict
    assert parse_verdict('{"verdict": "pass"}') is None  # no top-level pass
    assert parse_verdict('{"pass": "yes", "reasons": []}') is None  # pass must be a bool
    assert parse_verdict('[{"pass": true}]') is None  # not a top-level object
