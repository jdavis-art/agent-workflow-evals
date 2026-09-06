"""Headless Claude Code runner: sandbox copy of the fixtures, `claude -p --output-format json`, cost + timeout.

The CLI is resolved with shutil.which (so the Windows .exe shim runs without a shell) or taken from the
AWE_CLAUDE_CLI environment variable (space-separated command). The budget cap is passed to the CLI with
--max-budget-usd and checked again against the returned envelope by the CLI layer."""
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

MAX_TURNS = "25"


def default_cli() -> list[str]:
    env = os.environ.get("AWE_CLAUDE_CLI")
    if env:
        return shlex.split(env)
    return [shutil.which("claude") or "claude"]


def build_command(suite: Suite, sandbox: str, cli: list[str]) -> list[str]:
    prompt = suite.prompt().replace("{fixtures}", sandbox)
    return [*cli, "-p", prompt, "--output-format", "json", "--allowedTools", ",".join(suite.allowed_tools),
            "--max-turns", MAX_TURNS, "--max-budget-usd", f"{suite.max_cost_usd:.2f}"]


def parse_envelope(stdout: str) -> tuple[str, float]:
    """The last non-empty stdout line is the JSON envelope; returns (result text, total cost in USD)."""
    lines = [ln for ln in stdout.strip().splitlines() if ln.strip()]
    data = json.loads(lines[-1])
    if not isinstance(data, dict):
        raise ValueError("envelope is not a JSON object")
    return str(data.get("result", "")), float(data.get("total_cost_usd", 0.0))


def run_command(cmd: list[str], cwd: str | None, timeout: int) -> RunOutput:
    """Run a CLI command and turn its JSON envelope into a RunOutput. Shared with the judge."""
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return RunOutput(output=None, seconds=timeout, error=f"timeout after {timeout}s")
    except OSError as e:
        return RunOutput(output=None, seconds=time.perf_counter() - t0, error=f"could not start CLI {cmd[0]!r}: {e}")
    secs = time.perf_counter() - t0
    if proc.returncode != 0 and not proc.stdout.strip():
        return RunOutput(output=None, seconds=secs, error=f"cli exit {proc.returncode}: {proc.stderr[-500:]}")
    try:
        text, cost = parse_envelope(proc.stdout)
    except (ValueError, IndexError, TypeError) as e:
        return RunOutput(output=None, seconds=secs, error=f"unparseable CLI output ({e}): {proc.stdout[-300:]}")
    return RunOutput(output=text, cost_usd=cost, seconds=secs)


def run_claude(suite: Suite, case: Case, dry_run: bool = False, cli: list[str] | None = None) -> RunOutput:
    cli = cli or default_cli()
    sandbox = tempfile.mkdtemp(prefix="awe-")
    try:
        if case.fixtures:
            shutil.copytree(suite.path / case.fixtures, sandbox, dirs_exist_ok=True)
        cmd = build_command(suite, sandbox, cli)
        if dry_run:
            return RunOutput(output="DRY RUN: " + " ".join(shlex.quote(c) for c in cmd))
        return run_command(cmd, cwd=sandbox, timeout=suite.timeout_seconds)
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
