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

# Isolation: no user/project/local settings, no MCP servers, no skills, file tools confined to the sandbox,
# no session files written. Without these the run inherits the whole user context (MCP tool definitions,
# skills, the user's model choice) and can burn the budget before producing any output. `--bare` is NOT
# used: it disables the CLI's OAuth login and would require an API key.
ISOLATION = ["--restricted", "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"]


def default_cli() -> list[str]:
    env = os.environ.get("AWE_CLAUDE_CLI")
    if env:
        return shlex.split(env)
    return [shutil.which("claude") or "claude"]


def model_args(suite: Suite) -> list[str]:
    return ["--model", suite.model] if suite.model else []


def build_command(suite: Suite, sandbox: str, cli: list[str]) -> list[str]:
    prompt = suite.prompt().replace("{fixtures}", sandbox)
    tools = ",".join(suite.allowed_tools)
    return [*cli, "-p", prompt, "--output-format", "json", *ISOLATION, "--tools", tools, "--allowedTools", tools,
            "--max-turns", MAX_TURNS, "--max-budget-usd", f"{suite.max_cost_usd:.2f}", *model_args(suite)]


def parse_envelope(stdout: str) -> tuple[str, float, str | None]:
    """The last non-empty stdout line is the JSON envelope.
    Returns (result text, total cost in USD, error). error is "cli <subtype>" when the CLI reports
    is_error or a subtype other than "success" (budget stop, max turns, ...), else None."""
    lines = [ln for ln in stdout.strip().splitlines() if ln.strip()]
    data = json.loads(lines[-1])
    if not isinstance(data, dict):
        raise ValueError("envelope is not a JSON object")
    subtype = str(data.get("subtype") or "success")
    error = f"cli {subtype}" if data.get("is_error") or subtype != "success" else None
    return str(data.get("result", "")), float(data.get("total_cost_usd", 0.0)), error


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
        text, cost, error = parse_envelope(proc.stdout)
    except (ValueError, IndexError, TypeError) as e:
        return RunOutput(output=None, seconds=secs, error=f"unparseable CLI output ({e}): {proc.stdout[-300:]}")
    if error:
        return RunOutput(output=None, cost_usd=cost, seconds=secs, error=error)
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
