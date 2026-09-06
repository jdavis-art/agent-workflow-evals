import os
import pathlib
import sys

from awe.runners import claude as claude_runner
from awe.runners.claude import run_claude, build_command, default_cli
from awe.suite import load_suite

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
    assert cmd[cmd.index("--max-budget-usd") + 1] == "0.50"
    assert cmd[cmd.index("--tools") + 1] == "Read,Glob,Grep"
    for flag in ("--restricted", "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"):
        assert flag in cmd
    assert "--bare" not in cmd  # --bare turns off OAuth and would need an API key
    assert "--model" not in cmd
    out = run_claude(s, s.cases[0], dry_run=True, cli=["claude"])
    assert out.output.startswith("DRY RUN:") and out.cost_usd == 0


def test_model_passthrough(tmp_path):
    s = _suite(tmp_path, extra="model: sonnet\n")
    cmd = build_command(s, "/sandbox", ["claude"])
    assert cmd[cmd.index("--model") + 1] == "sonnet"


def test_default_cli_resolves_or_overrides(monkeypatch):
    monkeypatch.setenv("AWE_CLAUDE_CLI", "py -3 stub.py")
    assert default_cli() == ["py", "-3", "stub.py"]
    monkeypatch.delenv("AWE_CLAUDE_CLI")
    monkeypatch.setattr(claude_runner.shutil, "which", lambda name: r"C:\somewhere\claude.exe")
    assert default_cli() == [r"C:\somewhere\claude.exe"]


def test_runs_stub_in_sandbox(tmp_path):
    s = _suite(tmp_path)
    out = run_claude(s, s.cases[0], cli=STUB)
    assert "Cedar Row" in out.output and out.cost_usd == 0.02 and out.error is None


def test_cost_cap_is_reported(tmp_path):
    s = _suite(tmp_path, prompt="EXPENSIVE {fixtures}")
    out = run_claude(s, s.cases[0], cli=STUB)
    assert out.cost_usd == 9.0  # the CLI layer decides pass/fail against max_cost_usd


def test_timeout_fails_and_cleans_sandbox(tmp_path, monkeypatch):
    s = _suite(tmp_path, extra="timeout_seconds: 1\n")
    made = []
    real = claude_runner.tempfile.mkdtemp
    monkeypatch.setattr(claude_runner.tempfile, "mkdtemp", lambda **kw: made.append(real(**kw)) or made[-1])
    out = run_claude(s, s.cases[0], cli=[sys.executable, "-c", "import time; time.sleep(10)"])
    assert out.output is None and out.error.startswith("timeout")
    assert made and not os.path.exists(made[0])
