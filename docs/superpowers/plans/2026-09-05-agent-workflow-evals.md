# Agent Workflow Evals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Python harness (`awe`) that runs agent workflows against fixtures through two runners (headless Claude Code and a Python callable), grades outputs with deterministic assertions and an optional LLM judge, and keeps a scoreboard with diffs, plus three working suites.

**Architecture:** `suite.py` loads and validates YAML; runners produce a `RunOutput` (text or value, cost, duration); `assertions.py` grades; `judge.py` asks the CLI for a strict JSON verdict; `results.py` persists runs and renders `latest.md`; `metrics.py` computes precision and recall for label suites. Suites are folders of YAML and fixtures; nothing in the harness knows about any particular workflow.

**Tech Stack:** Python 3.12+ (`py`), `pyyaml`, `pytest`; the Claude Code CLI already installed (`claude -p --output-format json`); the sibling `bid-radar` package installed editable for the scoring suite.

**Spec:** `docs/superpowers/specs/2026-09-05-agent-workflow-evals-design.md`

## Global Constraints

- Python 3.12+ via `py`; venv at `.venv`; runtime deps `pyyaml` only; dev dep `pytest`. The bid-scoring suite adds `bid-radar` (editable install from `C:\Users\jdavi\Documents\Claude\Projects\bid-radar`).
- The claude runner passes `--allowedTools` from the suite and runs with the sandbox as the working directory. Allowed tools in shipped suites are read-only (`Read`, `Glob`, `Grep`).
- Every claude case enforces `max_cost_usd` and `timeout_seconds`; exceeding either fails the case with a reason.
- `results/` is gitignored except `.gitkeep`. Fixtures in the repo are fictional or public solicitation data. No company, client, or person names.
- Commit after every task with the message shown. Git identity is set for this repo.
- **Gate rule:** at Gates 1 to 5 STOP, print the requested output, and wait for the supervising session's green light.

---

## File Structure

```
agent-workflow-evals/
  pyproject.toml
  awe/__init__.py
  awe/suite.py           # load_suite(path) -> Suite; Case; SuiteError
  awe/assertions.py      # check(assertion: dict, output) -> AssertionResult
  awe/runners/__init__.py, python.py, claude.py
  awe/judge.py           # judge(rubric, context, output, cli) -> JudgeResult
  awe/results.py         # save_run, load_latest_two, render_latest_md, diff
  awe/metrics.py         # precision_recall(labels, scores, threshold) -> dict
  awe/cli.py             # awe run | awe diff | awe list
  suites/bid-scoring/{suite.yaml, golden.csv, cases/threshold-3.yaml, cases/exclusions-hold.yaml}
  suites/seed-drift/{suite.yaml, prompt.md, fixtures/..., cases/*.yaml}
  suites/morning-brief/{suite.yaml, prompt.md, rubric.md, fixtures/collectors.json, cases/*.yaml}
  scripts/build_golden.py           # proposes golden.csv from the bid-radar regression fixture
  scripts/fake_claude.py            # stub CLI for tests
  tests/test_suite.py, test_assertions.py, test_python_runner.py, test_results.py, test_metrics.py, test_claude_runner.py, test_judge.py
  results/.gitkeep
  README.md
```

---

### Task 1: Scaffold and suite loader

**Files:**
- Create: `pyproject.toml`, `awe/__init__.py`, `awe/suite.py`, `tests/test_suite.py`, `results/.gitkeep`

**Interfaces:**
- `@dataclass Suite(name, path, runner: str, prompt_file, allowed_tools: list[str], timeout_seconds: int, max_cost_usd: float, judge: dict, target: str|None, pass_threshold: float, cases: list[Case])`
- `@dataclass Case(id, description, fixtures: str|None, inputs: dict, assertions: list[dict], path)`
- `load_suite(path: Path) -> Suite` raising `SuiteError` with a message naming the file and field.

- [ ] **Step 1: pyproject and venv**

```toml
[project]
name = "agent-workflow-evals"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["pyyaml>=6.0"]
[project.optional-dependencies]
dev = ["pytest>=8.2"]
[project.scripts]
awe = "awe.cli:main"
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"
[tool.setuptools.packages.find]
include = ["awe*"]
[tool.pytest.ini_options]
testpaths = ["tests"]
```
Run: `py -m venv .venv && .venv\Scripts\python.exe -m pip install -e .[dev]`. Create `results/.gitkeep` (empty).

- [ ] **Step 2: Failing tests**

`tests/test_suite.py`:
```python
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
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_suite.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'awe.suite'`

- [ ] **Step 4: Implement suite.py**

```python
"""Suite and case loading with validation. A suite is a folder: suite.yaml + cases/*.yaml (+ fixtures, prompt, rubric)."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import yaml

RUNNERS = ("python", "claude")
DEFAULT_TOOLS = ["Read", "Glob", "Grep"]


class SuiteError(ValueError):
    pass


@dataclasses.dataclass
class Case:
    id: str
    description: str
    fixtures: str | None
    inputs: dict
    assertions: list[dict]
    path: Path


@dataclasses.dataclass
class Suite:
    name: str
    path: Path
    runner: str
    prompt_file: str | None
    allowed_tools: list[str]
    timeout_seconds: int
    max_cost_usd: float
    judge: dict
    target: str | None
    pass_threshold: float
    cases: list[Case]

    def prompt(self) -> str:
        if not self.prompt_file:
            raise SuiteError(f"{self.name}: prompt_file is required for the claude runner")
        return (self.path / self.prompt_file).read_text(encoding="utf-8")


def _yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise SuiteError(f"{path}: invalid YAML: {e}") from None
    if not isinstance(data, dict):
        raise SuiteError(f"{path}: top level must be a mapping")
    return data


def load_suite(path: Path | str) -> Suite:
    path = Path(path)
    spec = _yaml(path / "suite.yaml")
    name = spec.get("name") or path.name
    runner = spec.get("runner")
    if runner not in RUNNERS:
        raise SuiteError(f"{path / 'suite.yaml'}: runner must be one of {RUNNERS}, got {runner!r}")
    target = spec.get("target")
    if runner == "python" and not target:
        raise SuiteError(f"{path / 'suite.yaml'}: python runner requires target 'module:callable'")
    judge = spec.get("judge") or {"enabled": False}
    judge.setdefault("enabled", False)
    cases_dir = path / "cases"
    cases = []
    for f in sorted(cases_dir.glob("*.yaml")) if cases_dir.is_dir() else []:
        c = _yaml(f)
        if not c.get("id"):
            raise SuiteError(f"{f}: case needs an id")
        cases.append(Case(id=str(c["id"]), description=c.get("description", ""), fixtures=c.get("fixtures"),
                          inputs=c.get("inputs") or {}, assertions=list(c.get("assert") or []), path=f))
    if not cases:
        raise SuiteError(f"{path}: no cases under cases/")
    return Suite(
        name=name, path=path, runner=runner, prompt_file=spec.get("prompt_file"),
        allowed_tools=list(spec.get("allowed_tools") or DEFAULT_TOOLS),
        timeout_seconds=int(spec.get("timeout_seconds", 300)), max_cost_usd=float(spec.get("max_cost_usd", 0.5)),
        judge=judge, target=target,
        pass_threshold=float(spec.get("pass_threshold", 1.0 if runner == "python" else 0.67)), cases=cases,
    )
```

`awe/__init__.py`: `__version__ = "0.1.0"`.

- [ ] **Step 5: Run**

Run: `.venv\Scripts\python.exe -m pytest tests/test_suite.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml awe/__init__.py awe/suite.py tests/test_suite.py results/.gitkeep
git commit -m "feat: scaffold and suite loader"
```

---

### Task 2: Assertions

**Files:**
- Create: `awe/assertions.py`, `tests/test_assertions.py`

**Interfaces:**
- `@dataclass AssertionResult(kind, passed: bool, detail: str)`
- `check(assertion: dict, output) -> AssertionResult` where `output` is a `str` (claude runner) or any value (python runner).
- Kinds: `contains`, `not_contains`, `regex`, `not_regex`, `length_between: [lo, hi]`, `mentions_all: [..]`, `mentions_none: [..]`, `equals`, `json_path: {path: "a.b[0]", equals: v}` (also `gte`/`lte`), `gte`/`lte` on numeric output.

- [ ] **Step 1: Failing tests**

`tests/test_assertions.py`:
```python
from awe.assertions import check

TXT = "Seed drift: Cedar Row is missing. Northline box count moved from 18 to 20.\nPaste into seed-data.json."


def test_text_assertions():
    assert check({"contains": "Cedar Row"}, TXT).passed
    assert not check({"contains": "matches vault"}, TXT).passed
    assert check({"not_contains": "Seed matches vault"}, TXT).passed
    assert check({"regex": r"seed-data\.json"}, TXT).passed
    assert check({"not_regex": r"TBD|TODO"}, TXT).passed
    assert check({"length_between": [50, 500]}, TXT).passed
    assert not check({"length_between": [500, 900]}, TXT).passed
    r = check({"mentions_all": ["cedar row", "northline", "Pine"]}, TXT)
    assert not r.passed and "Pine" in r.detail
    assert check({"mentions_none": ["Riverbend"]}, TXT).passed


def test_value_assertions():
    assert check({"equals": 4.0}, 4.0).passed
    assert check({"gte": 0.9}, 0.95).passed and not check({"gte": 0.9}, 0.5).passed
    out = {"precision": 0.7, "confusion": [{"title": "x"}]}
    assert check({"json_path": {"path": "precision", "gte": 0.6}}, out).passed
    assert check({"json_path": {"path": "confusion[0].title", "equals": "x"}}, out).passed
    r = check({"json_path": {"path": "nope.deeper", "equals": 1}}, out)
    assert not r.passed and "nope" in r.detail


def test_unknown_kind():
    r = check({"sparkles": True}, "x")
    assert not r.passed and "unknown assertion" in r.detail
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_assertions.py -v`
Expected: FAIL, no module `awe.assertions`

- [ ] **Step 3: Implement**

```python
"""Deterministic checks against a run's output (text or value)."""
from __future__ import annotations

import dataclasses
import json
import re
from typing import Any


@dataclasses.dataclass
class AssertionResult:
    kind: str
    passed: bool
    detail: str = ""


def _text(output: Any) -> str:
    return output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)


def _path(value: Any, path: str) -> Any:
    cur = value
    for part in re.findall(r"[^.\[\]]+|\[\d+\]", path):
        if part.startswith("["):
            cur = cur[int(part[1:-1])]
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(part)
    return cur


def _compare(kind: str, actual: Any, expected: Any) -> AssertionResult:
    ok = {"equals": actual == expected, "gte": actual >= expected, "lte": actual <= expected}[kind]
    return AssertionResult(kind, ok, f"{kind}: actual {actual!r}, expected {expected!r}")


def check(assertion: dict, output: Any) -> AssertionResult:
    if len(assertion) != 1:
        return AssertionResult("?", False, f"assertion must have one key: {assertion}")
    kind, arg = next(iter(assertion.items()))
    text = _text(output)
    low = text.lower()
    if kind == "contains":
        return AssertionResult(kind, arg in text, f"contains {arg!r}")
    if kind == "not_contains":
        return AssertionResult(kind, arg not in text, f"not_contains {arg!r}")
    if kind == "regex":
        return AssertionResult(kind, re.search(arg, text, re.S) is not None, f"regex {arg!r}")
    if kind == "not_regex":
        return AssertionResult(kind, re.search(arg, text, re.S) is None, f"not_regex {arg!r}")
    if kind == "length_between":
        lo, hi = arg
        return AssertionResult(kind, lo <= len(text) <= hi, f"length {len(text)} not in [{lo}, {hi}]" if not (lo <= len(text) <= hi) else f"length {len(text)}")
    if kind == "mentions_all":
        missing = [m for m in arg if m.lower() not in low]
        return AssertionResult(kind, not missing, f"missing: {missing}" if missing else "all mentioned")
    if kind == "mentions_none":
        present = [m for m in arg if m.lower() in low]
        return AssertionResult(kind, not present, f"present: {present}" if present else "none mentioned")
    if kind in ("equals", "gte", "lte"):
        return _compare(kind, output, arg)
    if kind == "json_path":
        try:
            actual = _path(output, arg["path"])
        except (KeyError, IndexError, TypeError) as e:
            return AssertionResult(kind, False, f"path {arg['path']!r} not found ({e})")
        for k in ("equals", "gte", "lte"):
            if k in arg:
                r = _compare(k, actual, arg[k])
                return AssertionResult(kind, r.passed, f"{arg['path']}: {r.detail}")
        return AssertionResult(kind, False, "json_path needs equals/gte/lte")
    return AssertionResult(kind, False, f"unknown assertion kind {kind!r}")
```

- [ ] **Step 4: Run**

Run: `.venv\Scripts\python.exe -m pytest tests/test_assertions.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add awe/assertions.py tests/test_assertions.py
git commit -m "feat: deterministic assertions"
```

---

### Task 3: Python runner, results store, scoreboard, CLI

**Files:**
- Create: `awe/runners/__init__.py`, `awe/runners/python.py`, `awe/results.py`, `awe/cli.py`, `tests/test_python_runner.py`, `tests/test_results.py`

**Interfaces:**
- `@dataclass RunOutput(output: Any, cost_usd: float, seconds: float, error: str|None)`
- `run_python(suite: Suite, case: Case) -> RunOutput` importing `target` and calling it with `**case.inputs`.
- `@dataclass CaseRun(case_id, attempts: list[dict], pass_rate: float, cost_usd: float, first_failure: str|None)`
- `run_suite(suite, case_ids=None, repeat=1, judge=False, runner_override=None) -> dict` (the run record) in `awe/cli.py` helpers.
- `save_run(root, suite_name, record) -> Path`, `latest_two(root, suite_name) -> (cur, prev|None)`, `render_latest_md(cur, prev) -> str`, `write_latest(root, suite_name)`.

- [ ] **Step 1: Failing tests**

`tests/test_python_runner.py`:
```python
import textwrap
from awe.suite import load_suite
from awe.runners.python import run_python


def test_runs_callable(tmp_path):
    d = tmp_path / "s"; (d / "cases").mkdir(parents=True)
    (d / "suite.yaml").write_text("name: m\nrunner: python\ntarget: 'math:pow'\n", encoding="utf-8")
    (d / "cases" / "a.yaml").write_text("id: a\ninputs: {base: 2, exp: 5}\nassert:\n  - equals: 32\n", encoding="utf-8")
    s = load_suite(d)
    out = run_python(s, s.cases[0])
    assert out.output == 32 and out.error is None and out.cost_usd == 0


def test_reports_exception(tmp_path):
    d = tmp_path / "s"; (d / "cases").mkdir(parents=True)
    (d / "suite.yaml").write_text("name: m\nrunner: python\ntarget: 'math:sqrt'\n", encoding="utf-8")
    (d / "cases" / "a.yaml").write_text("id: a\ninputs: {x: -1}\nassert: []\n", encoding="utf-8")
    s = load_suite(d)
    out = run_python(s, s.cases[0])
    assert out.output is None and "math domain error" in out.error
```

`tests/test_results.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_python_runner.py tests/test_results.py -v`
Expected: FAIL, missing modules

- [ ] **Step 3: Implement**

`awe/runners/__init__.py`:
```python
from __future__ import annotations
import dataclasses
from typing import Any


@dataclasses.dataclass
class RunOutput:
    output: Any
    cost_usd: float = 0.0
    seconds: float = 0.0
    error: str | None = None
```

`awe/runners/python.py`:
```python
from __future__ import annotations
import importlib
import time
import traceback

from . import RunOutput
from ..suite import Suite, Case


def resolve(target: str):
    mod, _, attr = target.partition(":")
    if not mod or not attr:
        raise ValueError(f"target must be 'module:callable', got {target!r}")
    return getattr(importlib.import_module(mod), attr)


def run_python(suite: Suite, case: Case) -> RunOutput:
    t0 = time.perf_counter()
    try:
        fn = resolve(suite.target)
        out = fn(**case.inputs)
        return RunOutput(output=out, seconds=time.perf_counter() - t0)
    except Exception as e:  # noqa: BLE001 - the harness records, never crashes
        return RunOutput(output=None, seconds=time.perf_counter() - t0, error=f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}")
```

`awe/results.py`:
```python
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
```

`awe/cli.py` (the claude runner and judge are wired in Task 5; import them lazily so this task runs alone):
```python
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
            "output_excerpt": (out.output if isinstance(out.output, str) else repr(out.output))[:2000]}


def run_suite(suite: Suite, case_ids: list[str] | None = None, repeat: int = 1, judge_on: bool = False, dry_run: bool = False) -> dict:
    cases = [c for c in suite.cases if not case_ids or c.id in case_ids]
    record = {"suite": suite.name, "timestamp": dt.datetime.now().strftime("%Y-%m-%dT%H-%M-%S"), "repeat": repeat, "cases": [], "totals": {}}
    for case in cases:
        attempts = [_run_case_once(suite, case, judge_on, dry_run) for _ in range(repeat)]
        rate = sum(1 for a in attempts if a["passed"]) / len(attempts)
        first_fail = next((a["error"] or next((r["detail"] for r in a["assertions"] if not r["passed"]), (a["judge"] or {}).get("reasons", [""])[0] if a["judge"] else None) for a in attempts if not a["passed"]), None)
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
        print("dry run complete (no CLI calls)"); return 0
    save_run(root, suite.name, record)
    print(write_latest(root, suite.name).read_text(encoding="utf-8"))
    return 0 if record["totals"]["passed"] == record["totals"]["cases"] else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run**

Run: `.venv\Scripts\python.exe -m pytest -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add awe/runners awe/results.py awe/cli.py tests/test_python_runner.py tests/test_results.py
git commit -m "feat: python runner, results store, scoreboard, CLI"
```

- [ ] **GATE 1 — STOP.** Print `pytest -q` and `awe list` (empty is fine). Wait for the green light.

---

### Task 4: Metrics and the bid-scoring suite

**Files:**
- Create: `awe/metrics.py`, `tests/test_metrics.py`, `scripts/build_golden.py`, `suites/bid-scoring/suite.yaml`, `suites/bid-scoring/golden.csv`, `suites/bid-scoring/cases/threshold-3.yaml`, `suites/bid-scoring/cases/exclusions-hold.yaml`, `suites/bid-scoring/score_golden.py`

**Interfaces:**
- `precision_recall(rows: list[dict], threshold: int) -> dict` where each row has `label` (`pursue`|`ignore`) and `score` (int); returns `precision, recall, f1, tp, fp, fn, tn, confusion: [{uid,title,score,label}]` (confusion = fp and fn rows).
- `score_golden(golden_csv: str, threshold: int = 3) -> dict` in `suites/bid-scoring/score_golden.py`: loads the bid-radar config and rules, scores every golden row, returns the metrics dict plus `exclusion_violations: [...]`.

- [ ] **Step 1: Failing metrics test**

`tests/test_metrics.py`:
```python
from awe.metrics import precision_recall

ROWS = [
    {"uid": "1", "title": "a", "score": 5, "label": "pursue"},
    {"uid": "2", "title": "b", "score": 3, "label": "ignore"},
    {"uid": "3", "title": "c", "score": 1, "label": "pursue"},
    {"uid": "4", "title": "d", "score": 0, "label": "ignore"},
]


def test_precision_recall():
    m = precision_recall(ROWS, 3)
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (1, 1, 1, 1)
    assert m["precision"] == 0.5 and m["recall"] == 0.5 and m["f1"] == 0.5
    assert [r["uid"] for r in m["confusion"]] == ["2", "3"]


def test_empty():
    m = precision_recall([], 3)
    assert m["precision"] == 0 and m["recall"] == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_metrics.py -v`
Expected: FAIL, missing module

- [ ] **Step 3: Implement metrics.py**

```python
from __future__ import annotations


def precision_recall(rows: list[dict], threshold: int) -> dict:
    tp = fp = fn = tn = 0
    confusion = []
    for r in rows:
        pred = int(r["score"]) >= threshold
        truth = r["label"] == "pursue"
        if pred and truth: tp += 1
        elif pred and not truth: fp += 1; confusion.append(r)
        elif not pred and truth: fn += 1; confusion.append(r)
        else: tn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "confusion": [{"uid": r.get("uid"), "title": r.get("title"), "score": r["score"], "label": r["label"]} for r in confusion]}
```

- [ ] **Step 4: Golden set builder**

Install the sibling package: `.venv\Scripts\python.exe -m pip install -e C:\Users\jdavi\Documents\Claude\Projects\bid-radar`.

`scripts/build_golden.py`:
```python
"""Propose suites/bid-scoring/golden.csv from bid-radar's public regression fixture.
Takes every row scored 3+ and a fixed sample of 60 rows scored 0-2, proposes label = pursue if score >= 3 else ignore,
and writes the CSV for hand correction. Rerun with --keep-labels to preserve labels already edited."""
import argparse
import csv
import json
import pathlib
import random

FIX = pathlib.Path(r"C:\Users\jdavi\Documents\Claude\Projects\bid-radar\tests\fixtures\sweep-2026-09-04-scored.jsonl")
OUT = pathlib.Path(__file__).resolve().parent.parent / "suites" / "bid-scoring" / "golden.csv"
COLS = ["uid", "title", "agency", "location", "bid_type", "blurb", "legacy_score", "label", "note"]

ap = argparse.ArgumentParser(); ap.add_argument("--keep-labels", action="store_true"); a = ap.parse_args()
rows = [json.loads(l) for l in FIX.read_text(encoding="utf-8").splitlines()]
hi = [r for r in rows if r["legacy_score"] >= 3]
lo = [r for r in rows if r["legacy_score"] < 3]
random.Random(20260904).shuffle(lo)
pick = hi + lo[:60]
existing = {}
if a.keep_labels and OUT.exists():
    existing = {r["uid"]: r for r in csv.DictReader(open(OUT, encoding="utf-8", newline=""))}
with open(OUT, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=COLS); w.writeheader()
    for r in pick:
        uid = f"bidnet:{r['id']}"
        prev = existing.get(uid, {})
        w.writerow({"uid": uid, "title": r["title"], "agency": r["agency"], "location": r["location"], "bid_type": r["bid_type"],
                    "blurb": r["blurb"], "legacy_score": r["legacy_score"],
                    "label": prev.get("label") or ("pursue" if r["legacy_score"] >= 3 else "ignore"), "note": prev.get("note", "")})
print(f"wrote {len(pick)} rows to {OUT}; labels are PROPOSALS until reviewed by hand")
```
Run it once. The supervisor hands the CSV to the owner for correction; until then the suite runs on proposed labels and its floors are provisional.

- [ ] **Step 5: The suite**

`suites/bid-scoring/score_golden.py`:
```python
"""Scores golden.csv with the real bid-radar rules. Target for the python runner."""
import csv
import pathlib

from bid_radar.config import load_config
from bid_radar.model import Solicitation
from bid_radar.scoring import Rules, score
from awe.metrics import precision_recall

HERE = pathlib.Path(__file__).resolve().parent


def score_golden(golden_csv: str = "golden.csv", threshold: int = 3) -> dict:
    rules = Rules.from_config(load_config()["scoring"])
    rows, violations = [], []
    for r in csv.DictReader(open(HERE / golden_csv, encoding="utf-8", newline="")):
        sol = Solicitation(uid=r["uid"], source="bidnet", source_id=r["uid"].split(":")[1], title=r["title"], agency=r["agency"],
                           location=r["location"], bid_type=r["bid_type"], blurb=r["blurb"])
        s, note = score(sol, rules)
        rows.append({**r, "score": s, "note": note})
        if r["label"] == "ignore" and note.startswith("excluded:") and s != 0:
            violations.append({"uid": r["uid"], "title": r["title"], "score": s})
    out = precision_recall(rows, threshold)
    out["exclusion_violations"] = violations
    out["n"] = len(rows)
    return out
```
`load_config()` with no root reads bid-radar's own `config.yaml` (its `project_root()` is package-relative), so the suite grades the shipped public config.

`suites/bid-scoring/suite.yaml`:
```yaml
name: bid-scoring
runner: python
target: "suites.bid-scoring.score_golden:score_golden"
```
Because the folder name has a hyphen, importing by dotted path fails. Instead set `target: "score_golden:score_golden"` and have the python runner add the suite folder to `sys.path` before importing. Add to `run_python` at the top of the `try`: `sys.path.insert(0, str(suite.path))` (import `sys`), and remove it in a `finally`. Update the test in Task 3 only if it breaks (it will not; `math` is on the path already).

`cases/threshold-3.yaml`:
```yaml
id: threshold-3
description: precision and recall of the shipped config at the digest threshold
inputs: {golden_csv: golden.csv, threshold: 3}
assert:
  - json_path: {path: recall, gte: 0.90}
  - json_path: {path: precision, gte: 0.60}
```
`cases/exclusions-hold.yaml`:
```yaml
id: exclusions-hold
description: every row excluded by an exclusion word still scores 0
inputs: {golden_csv: golden.csv, threshold: 3}
assert:
  - json_path: {path: exclusion_violations, equals: []}
```

- [ ] **Step 6: Run**

Run: `.venv\Scripts\python.exe -m pytest -q` then `.venv\Scripts\awe.exe run bid-scoring`. With proposed labels the recall is 1.0 and precision 1.0 by construction; that is expected until the labels are corrected.

- [ ] **Step 7: Commit**

```bash
git add awe/metrics.py tests/test_metrics.py scripts/build_golden.py suites/bid-scoring awe/runners/python.py
git commit -m "feat: metrics and the bid-scoring golden suite"
```

- [ ] **GATE 2 — STOP.** Print the scoreboard and the first ten confusion rows (there will be none until labels are corrected; say so). Hand `suites/bid-scoring/golden.csv` to the supervisor for labeling. Wait for the green light.

---

### Task 5: Claude runner and judge

**Files:**
- Create: `awe/runners/claude.py`, `awe/judge.py`, `scripts/fake_claude.py`, `tests/test_claude_runner.py`, `tests/test_judge.py`

**Interfaces:**
- `run_claude(suite, case, dry_run=False, cli: list[str]|None=None) -> RunOutput`; `cli` defaults to `["claude"]` and tests pass `[sys.executable, "scripts/fake_claude.py"]`.
- `judge(suite, case, output, cli=None) -> {"pass": bool, "reasons": [str], "cost_usd": float, "raw": str}`.
- Env `AWE_CLAUDE_CLI` overrides the CLI command (space-separated) for both.

- [ ] **Step 1: The stub CLI**

`scripts/fake_claude.py`:
```python
"""Stub for tests: echoes a canned JSON envelope like `claude -p --output-format json`.
Reads the prompt from argv (after -p) and answers based on markers in it."""
import json
import sys

args = sys.argv[1:]
prompt = args[args.index("-p") + 1] if "-p" in args else ""
if "JUDGE" in prompt:
    verdict = {"pass": "GOOD OUTPUT" in prompt, "reasons": ["stub verdict"]}
    print(json.dumps({"result": json.dumps(verdict), "total_cost_usd": 0.001}))
elif "EXPENSIVE" in prompt:
    print(json.dumps({"result": "ok", "total_cost_usd": 9.0}))
else:
    print(json.dumps({"result": "Seed drift: Cedar Row is missing. See seed-data.json.", "total_cost_usd": 0.02}))
```

- [ ] **Step 2: Failing tests**

`tests/test_claude_runner.py`:
```python
import sys
import pathlib
from awe.suite import load_suite
from awe.runners.claude import run_claude, build_command

STUB = [sys.executable, str(pathlib.Path(__file__).resolve().parent.parent / "scripts" / "fake_claude.py")]


def _suite(tmp_path, prompt="Find drift in {fixtures}", extra=""):
    d = tmp_path / "s"; (d / "cases").mkdir(parents=True); (d / "fixtures").mkdir()
    (d / "fixtures" / "a.md").write_text("x", encoding="utf-8")
    (d / "suite.yaml").write_text(f"name: c\nrunner: claude\nprompt_file: prompt.md\nmax_cost_usd: 0.5\n{extra}", encoding="utf-8")
    (d / "prompt.md").write_text(prompt, encoding="utf-8")
    (d / "cases" / "a.yaml").write_text("id: a\nfixtures: fixtures\nassert:\n  - contains: Cedar Row\n", encoding="utf-8")
    return load_suite(d)


def test_build_command_and_dry_run(tmp_path):
    s = _suite(tmp_path)
    cmd = build_command(s, "/sandbox", ["claude"])
    assert cmd[:3] == ["claude", "-p", "Find drift in /sandbox"]
    assert "--output-format" in cmd and "json" in cmd and "--allowedTools" in cmd and "Read,Glob,Grep" in cmd
    out = run_claude(s, s.cases[0], dry_run=True, cli=["claude"])
    assert out.output.startswith("DRY RUN:") and out.cost_usd == 0


def test_runs_stub_in_sandbox(tmp_path):
    s = _suite(tmp_path)
    out = run_claude(s, s.cases[0], cli=STUB)
    assert "Cedar Row" in out.output and out.cost_usd == 0.02 and out.error is None


def test_cost_cap_is_reported(tmp_path):
    s = _suite(tmp_path, prompt="EXPENSIVE {fixtures}")
    out = run_claude(s, s.cases[0], cli=STUB)
    assert out.cost_usd == 9.0  # the CLI layer decides pass/fail against max_cost_usd
```

`tests/test_judge.py`:
```python
import sys
import pathlib
from awe.suite import load_suite
from awe.judge import judge

STUB = [sys.executable, str(pathlib.Path(__file__).resolve().parent.parent / "scripts" / "fake_claude.py")]


def _suite(tmp_path):
    d = tmp_path / "s"; (d / "cases").mkdir(parents=True)
    (d / "suite.yaml").write_text("name: j\nrunner: claude\nprompt_file: p.md\njudge:\n  enabled: true\n  rubric_file: rubric.md\n", encoding="utf-8")
    (d / "p.md").write_text("x", encoding="utf-8"); (d / "rubric.md").write_text("Every action item must trace to the fixture.", encoding="utf-8")
    (d / "cases" / "a.yaml").write_text("id: a\nassert: []\n", encoding="utf-8")
    return load_suite(d)


def test_judge_pass_and_fail(tmp_path):
    s = _suite(tmp_path)
    ok = judge(s, s.cases[0], "GOOD OUTPUT", cli=STUB)
    assert ok["pass"] is True and ok["cost_usd"] == 0.001
    bad = judge(s, s.cases[0], "meh", cli=STUB)
    assert bad["pass"] is False and bad["reasons"] == ["stub verdict"]


def test_judge_non_json(tmp_path, monkeypatch):
    s = _suite(tmp_path)
    r = judge(s, s.cases[0], "x", cli=[sys.executable, "-c", "print('{\"result\": \"not json at all\", \"total_cost_usd\": 0}')"])
    assert r["pass"] is False and r["reasons"] == ["non-JSON judge answer"]
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_claude_runner.py tests/test_judge.py -v`
Expected: FAIL, missing modules

- [ ] **Step 4: Implement**

`awe/runners/claude.py`:
```python
"""Headless Claude Code runner: sandbox copy of the fixtures, `claude -p --output-format json`, cost + timeout."""
from __future__ import annotations
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time

from . import RunOutput
from ..suite import Suite, Case


def default_cli() -> list[str]:
    env = os.environ.get("AWE_CLAUDE_CLI")
    return shlex.split(env) if env else ["claude"]


def build_command(suite: Suite, sandbox: str, cli: list[str]) -> list[str]:
    prompt = suite.prompt().replace("{fixtures}", sandbox)
    return [*cli, "-p", prompt, "--output-format", "json", "--allowedTools", ",".join(suite.allowed_tools), "--max-turns", "25"]


def parse_envelope(stdout: str) -> tuple[str, float]:
    data = json.loads(stdout.strip().splitlines()[-1])
    return str(data.get("result", "")), float(data.get("total_cost_usd", 0.0))


def run_claude(suite: Suite, case: Case, dry_run: bool = False, cli: list[str] | None = None) -> RunOutput:
    cli = cli or default_cli()
    sandbox = tempfile.mkdtemp(prefix="awe-")
    try:
        if case.fixtures:
            shutil.copytree(suite.path / case.fixtures, sandbox, dirs_exist_ok=True)
        cmd = build_command(suite, sandbox, cli)
        if dry_run:
            return RunOutput(output="DRY RUN: " + " ".join(shlex.quote(c) for c in cmd))
        t0 = time.perf_counter()
        try:
            proc = subprocess.run(cmd, cwd=sandbox, capture_output=True, text=True, encoding="utf-8", timeout=suite.timeout_seconds, shell=(cli[0] == "claude" and os.name == "nt"))
        except subprocess.TimeoutExpired:
            return RunOutput(output=None, seconds=suite.timeout_seconds, error=f"timeout after {suite.timeout_seconds}s")
        secs = time.perf_counter() - t0
        if proc.returncode != 0 and not proc.stdout.strip():
            return RunOutput(output=None, seconds=secs, error=f"cli exit {proc.returncode}: {proc.stderr[-500:]}")
        try:
            text, cost = parse_envelope(proc.stdout)
        except (ValueError, IndexError) as e:
            return RunOutput(output=None, seconds=secs, error=f"unparseable CLI output ({e}): {proc.stdout[-300:]}")
        return RunOutput(output=text, cost_usd=cost, seconds=secs)
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
```
Note the `shell=` flag: on Windows the `claude` entry point is a `.cmd` shim, which `subprocess` cannot spawn without a shell. The stub (a Python file) and any explicit CLI path run without a shell.

`awe/judge.py`:
```python
"""LLM judge: rubric + output -> strict JSON verdict through the same CLI."""
from __future__ import annotations
import json
import os
import re
import subprocess

from .runners.claude import default_cli, parse_envelope
from .suite import Suite, Case

TEMPLATE = """JUDGE. You are grading an agent's output against a rubric. Answer with ONLY a JSON object of the form
{{"pass": true|false, "reasons": ["..."]}} and nothing else.

RUBRIC:
{rubric}

CASE: {case_id} - {description}

OUTPUT UNDER TEST:
<<<
{output}
>>>"""


def judge(suite: Suite, case: Case, output, cli: list[str] | None = None) -> dict:
    cli = cli or default_cli()
    rubric = (suite.path / suite.judge.get("rubric_file", "rubric.md")).read_text(encoding="utf-8")
    prompt = TEMPLATE.format(rubric=rubric, case_id=case.id, description=case.description, output=output if isinstance(output, str) else json.dumps(output))
    cmd = [*cli, "-p", prompt, "--output-format", "json", "--max-turns", "1"]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=suite.timeout_seconds, shell=(cli[0] == "claude" and os.name == "nt"))
    try:
        text, cost = parse_envelope(proc.stdout)
    except (ValueError, IndexError):
        return {"pass": False, "reasons": ["non-JSON judge answer"], "cost_usd": 0.0, "raw": proc.stdout[-300:]}
    m = re.search(r"\{.*\}", text, re.S)
    try:
        verdict = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        verdict = None
    if not isinstance(verdict, dict) or "pass" not in verdict:
        return {"pass": False, "reasons": ["non-JSON judge answer"], "cost_usd": cost, "raw": text[:300]}
    return {"pass": bool(verdict["pass"]), "reasons": [str(r) for r in verdict.get("reasons", [])], "cost_usd": cost, "raw": text[:300]}
```

- [ ] **Step 5: Run**

Run: `.venv\Scripts\python.exe -m pytest -v`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add awe/runners/claude.py awe/judge.py scripts/fake_claude.py tests/test_claude_runner.py tests/test_judge.py
git commit -m "feat: headless Claude runner with sandbox and cost, LLM judge"
```

---

### Task 6: The seed-drift suite

**Files:**
- Create: `suites/seed-drift/suite.yaml`, `prompt.md`, `fixtures/factory-operations.md`, `fixtures/projects/*.md` (five), `fixtures/seed-data.json`, `fixtures-nodrift/` (same with a matching seed), `cases/missing-project.yaml`, `moved-boxes.yaml`, `changed-price.yaml`, `stale-status.yaml`, `no-drift.yaml`

- [ ] **Step 1: Fixtures**

`fixtures/factory-operations.md`:
```markdown
# Factory Operations (fixture)

## Line Loading

| Project | Boxes | Status | $/box (contract) | Start |
| --- | --- | --- | --- | --- |
| Cedar Row | 24 | contracted | 71,000 | 2026-10-05 |
| Northline | 20 | contracted | 68,500 | 2026-11-02 |
| Pine Ridge | 36 | prospect | 74,000 | 2027-01-11 |
| Wasatch Workforce | 30 | on hold | 69,900 | 2026-12-07 |
| Riverbend | 54 | active | 72,250 | 2026-08-10 |
```
`fixtures/projects/<slug>.md` for each of the five: frontmatter `status:` matching the table and a one-line body with boxes and price. `fixtures/seed-data.json` in the dashboard's shape with `projects: [...]` holding **Northline at 18 boxes**, **Pine Ridge at 70,000 per box**, **Wasatch Workforce status "active"**, Riverbend correct, and **Cedar Row absent**. `fixtures-nodrift/` is a copy where the seed matches the table exactly.

- [ ] **Step 2: Prompt and suite**

`prompt.md`:
```
You are running the seed-drift check of a weekly operations review. In the folder {fixtures} read
factory-operations.md (the Line Loading table is the source of truth), the project files under projects/,
and seed-data.json (a dashboard seed). Compare the seed against the table and project files. Report drift:
projects missing from the seed, box counts that differ, $/box that differ from the contract value, statuses
that differ. Name every drifted project explicitly with what differs. If drift exists, end with a
ready-to-paste build-session prompt that says exactly which fields in seed-data.json to change and to what.
If there is no drift, say exactly: Seed matches vault.
```
`suite.yaml`:
```yaml
name: seed-drift
runner: claude
prompt_file: prompt.md
allowed_tools: [Read, Glob, Grep]
timeout_seconds: 300
max_cost_usd: 0.60
pass_threshold: 0.67
```
Cases:
```yaml
# missing-project.yaml
id: missing-project
description: Cedar Row is in the table but not in the seed
fixtures: fixtures
assert:
  - mentions_all: ["Cedar Row"]
  - not_contains: "Seed matches vault"
  - regex: "seed-data\\.json"
```
```yaml
# moved-boxes.yaml
id: moved-boxes
description: Northline boxes 20 in the table, 18 in the seed
fixtures: fixtures
assert:
  - mentions_all: ["Northline", "18", "20"]
  - not_contains: "Seed matches vault"
```
```yaml
# changed-price.yaml
id: changed-price
description: Pine Ridge $/box 74,000 in the table, 70,000 in the seed
fixtures: fixtures
assert:
  - mentions_all: ["Pine Ridge"]
  - regex: "74[,.]?000"
  - regex: "70[,.]?000"
```
```yaml
# stale-status.yaml
id: stale-status
description: Wasatch Workforce is on hold in the table, active in the seed
fixtures: fixtures
assert:
  - mentions_all: ["Wasatch Workforce", "on hold"]
```
```yaml
# no-drift.yaml
id: no-drift
description: seed matches the table exactly
fixtures: fixtures-nodrift
assert:
  - contains: "Seed matches vault"
  - mentions_none: ["missing", "differs", "changed"]
```

- [ ] **Step 3: Run**

`awe run seed-drift --dry-run` prints five commands. Then `awe run seed-drift --repeat 3` (live; roughly 15 CLI calls, under $5 total at the cap). Read the scoreboard. If a case fails on wording rather than substance (the model said "matches the vault" instead of the exact phrase), tighten the prompt, not the assertion, and rerun.

- [ ] **Step 4: Commit**

```bash
git add suites/seed-drift
git commit -m "feat: seed-drift suite with planted drift fixtures"
```

- [ ] **GATE 3 — STOP.** Print the scoreboard from the `--repeat 3` run and the total cost. Wait for the green light.

---

### Task 7: The morning-brief suite

**Files:**
- Create: `suites/morning-brief/suite.yaml`, `prompt.md`, `rubric.md`, `fixtures/collectors.json`, `fixtures-empty/collectors.json`, `cases/sections-present.yaml`, `length-band.yaml`, `no-fabrication.yaml`, `empty-calendar.yaml`

- [ ] **Step 1: Fixtures**

`fixtures/collectors.json` (fictional):
```json
{
  "date": "2026-09-08",
  "calendar": [
    {"start": "09:00", "end": "09:30", "title": "Reviewer round 2 check-in", "with": ["Studio A"]},
    {"start": "13:00", "end": "14:00", "title": "Riverbend site coordination", "with": ["GC"]}
  ],
  "inbox": [
    {"from": "arch@example.com", "subject": "Sill height revision", "summary": "Revised A-201 attached; needs your ok before resubmittal.", "action_needed": true},
    {"from": "vendor@example.com", "subject": "Window lead time", "summary": "Lead time moved to 6 weeks.", "action_needed": false}
  ],
  "tasks": [
    {"title": "Send Northline ROM", "due": "2026-09-08", "priority": "high"},
    {"title": "Approve payroll", "due": "2026-09-09", "priority": "high"}
  ],
  "meetings_yesterday": [
    {"title": "Ops stand-up", "notes": "Cedar Row start slips one week to 2026-10-12."}
  ]
}
```
`fixtures-empty/collectors.json`: same with `"calendar": []`.

`prompt.md`:
```
You write a short morning brief for an operations executive. Read {fixtures}/collectors.json. Produce a brief with
exactly these section headers, each on its own line: "📅 CALENDAR", "📬 INBOX", "✅ TASKS", "📝 YESTERDAY", "🎯 FOCUS".
Under each, bullets drawn only from the JSON. Never invent a meeting, email, task, or fact that is not in the file.
If the calendar is empty, say "No meetings today." under CALENDAR. Keep the whole brief between 800 and 3000 characters.
```
`rubric.md`:
```
Pass only if EVERY bullet under 📅 CALENDAR, 📬 INBOX, ✅ TASKS, and 📝 YESTERDAY corresponds to an entry in the
collectors.json data described in the case, with no invented meetings, emails, tasks, people, or dates. Bullets under
🎯 FOCUS may synthesize but must not introduce new facts. Fail and list each invented item otherwise.
```
`suite.yaml`:
```yaml
name: morning-brief
runner: claude
prompt_file: prompt.md
allowed_tools: [Read]
timeout_seconds: 240
max_cost_usd: 0.60
pass_threshold: 0.67
judge:
  enabled: true
  rubric_file: rubric.md
```
Cases:
```yaml
# sections-present.yaml
id: sections-present
fixtures: fixtures
assert:
  - regex: "📅 CALENDAR[\\s\\S]*📬 INBOX[\\s\\S]*✅ TASKS[\\s\\S]*📝 YESTERDAY[\\s\\S]*🎯 FOCUS"
```
```yaml
# length-band.yaml
id: length-band
fixtures: fixtures
assert:
  - length_between: [800, 8000]
```
```yaml
# no-fabrication.yaml
id: no-fabrication
description: every bullet traces to collectors.json (judge)
fixtures: fixtures
assert:
  - mentions_all: ["Sill height", "Northline ROM", "Cedar Row"]
  - not_regex: "TBD|TODO|placeholder"
```
```yaml
# empty-calendar.yaml
id: empty-calendar
fixtures: fixtures-empty
assert:
  - contains: "No meetings today."
  - mentions_none: ["09:00", "13:00", "check-in"]
```
The judge only runs when `--judge` is passed and the suite has it enabled; `no-fabrication` is the case it matters for, but it applies to all cases in the suite when on.

- [ ] **Step 2: Run**

`awe run morning-brief --judge --repeat 2`. Read the judge reasons on any failure; if the model fabricates, that is the finding, not a prompt bug. Only tighten the prompt when the failure is formatting.

- [ ] **Step 3: Commit**

```bash
git add suites/morning-brief
git commit -m "feat: morning-brief suite with fabrication judge"
```

- [ ] **GATE 4 — STOP.** Print the scoreboard and one judge `reasons` list verbatim. Wait for the green light.

---

### Task 8: README, vault-side template, install

**Files:**
- Create: `README.md`, `templates/vault-suite/suite.yaml`, `templates/vault-suite/cases/example.yaml`, `templates/README.md`

- [ ] **Step 1: Vault template**

`templates/vault-suite/suite.yaml`: the seed-drift suite header with a comment on each field. `templates/vault-suite/cases/example.yaml`: one case with every assertion kind shown once, commented. `templates/README.md`: three steps to run the harness from another folder: `pip install -e <this repo>`, copy `templates/vault-suite` to `<vault>/.claude/evals/<name>`, run `awe --root <vault>/.claude/evals run <name>` (the `--root` folder must contain `suites/`; so the copy target is `<vault>/.claude/evals/suites/<name>` and results land in `<vault>/.claude/evals/results/`).

- [ ] **Step 2: README**

Sections in order: purpose (three sentences and the two failures that motivated it, without names), install, suite and case format (copy from the spec section 4), assertion kinds table, runners and the cost/timeout guard, judge, results and diff, the three shipped suites with how to correct the golden labels, vault-side use, what is public and what is not.

- [ ] **Step 3: Install into the vault environment**

From the vault root: `py -m pip install -e C:\Users\jdavi\Documents\Claude\Projects\agent-workflow-evals` (the vault uses the system `py`, no venv). Create `<vault>/.claude/evals/suites/` and `<vault>/.claude/evals/results/` with a `.gitkeep` each; do not copy any real fixture in this task, the supervisor does that in the vault session. Run `awe --root <vault>/.claude/evals list` (empty).

- [ ] **Step 4: Commit**

```bash
git add README.md templates
git commit -m "docs: README and vault-side suite template"
```

- [ ] **GATE 5 — STOP.** Print `pytest -q`, `awe list`, the vault-side `awe list`, and `git status` (clean; nothing under `results/` except `.gitkeep`). Wait for the green light.

---

## Self-review

- **Spec coverage:** suite/case format and validation (Task 1), assertions incl. json_path (Task 2), python runner, results, scoreboard, diff, CLI, repeat and threshold (Task 3), metrics and bid-scoring with the golden builder (Task 4), claude runner with sandbox, cost, timeout, dry-run, stub (Task 5), judge with strict JSON (Task 5), seed-drift five cases (Task 6), morning-brief four cases with judge (Task 7), README, template, vault install (Task 8). Cost guard is enforced in `_run_case_once`. `AWE_CLAUDE_CLI` override in `default_cli`.
- **Placeholders:** the seed-drift project fixture files are described, not printed, because their content is five two-line markdown files whose values are given in the table; write them by hand from that table in Task 6 Step 1. README and template contents are ordered section lists by design.
- **Type consistency:** `RunOutput` (Task 3) used by Task 5; `check` (Task 2) used by the CLI (Task 3); `parse_envelope`/`default_cli` (Task 5) shared by the judge; `precision_recall` (Task 4) used by `score_golden`; `Suite.prompt()` (Task 1) used by `build_command` (Task 5); the python runner's `sys.path` insertion is added in Task 4 and noted.
