"""LLM judge: rubric + fixture context + output -> strict JSON verdict through the same CLI.

The judge has no tools, so anything it must check against goes into the prompt: suite.yaml may list
judge.context_files (paths relative to the case's fixtures folder) and their contents are appended as a
FIXTURE DATA section, capped at CONTEXT_CAP characters. Only a top-level {"pass": bool, "reasons": [str]}
object counts as a verdict (code fences are stripped first). Anything else is a failure with the reason
"non-JSON judge answer"."""
from __future__ import annotations
import json
import re
from pathlib import Path

from .runners.claude import ISOLATION, default_cli, model_args, run_command
from .suite import Suite, Case

CONTEXT_CAP = 20_000

TEMPLATE = """JUDGE. You are grading an agent's output against a rubric. Answer with ONLY a JSON object of the form
{{"pass": true|false, "reasons": ["..."]}} and nothing else.

RUBRIC:
{rubric}
{context}
CASE: {case_id} - {description}

OUTPUT UNDER TEST:
<<<
{output}
>>>"""

_FENCE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*\n?(.*?)\n?\s*```\s*$", re.S)


def build_context(base: Path, names: list[str]) -> str:
    """A FIXTURE DATA section naming each file with its contents; total contents capped at CONTEXT_CAP."""
    if not names:
        return ""
    parts = ["\nFIXTURE DATA (the only source the output may draw from):\n"]
    budget = CONTEXT_CAP
    for name in names:
        body = (Path(base) / name).read_text(encoding="utf-8")
        parts.append(f"\n--- {name} ---\n")
        if len(body) > budget:
            parts.append(body[:budget] + f"\n[truncated: fixture data capped at {CONTEXT_CAP} characters]\n")
            break
        budget -= len(body)
        parts.append(body + "\n")
    return "".join(parts)


def parse_verdict(text: str) -> dict | None:
    """Return {"pass": bool, "reasons": [str]} for a strict verdict, else None."""
    body = text.strip()
    if m := _FENCE.match(body):
        body = m.group(1).strip()
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("pass"), bool):
        return None
    reasons = data.get("reasons", [])
    if not isinstance(reasons, list):
        return None
    return {"pass": data["pass"], "reasons": [str(r) for r in reasons]}


def judge(suite: Suite, case: Case, output, cli: list[str] | None = None) -> dict:
    cli = cli or default_cli()
    rubric = (suite.path / suite.judge.get("rubric_file", "rubric.md")).read_text(encoding="utf-8")
    names = list(suite.judge.get("context_files") or [])
    base = suite.path / (case.fixtures or "")
    missing = [n for n in names if not (base / n).is_file()]
    if missing:
        return {"pass": False, "reasons": [f"context file missing: {n}" for n in missing], "cost_usd": 0.0, "raw": ""}
    prompt = TEMPLATE.format(rubric=rubric, context=build_context(base, names), case_id=case.id, description=case.description,
                             output=output if isinstance(output, str) else json.dumps(output))
    # The judge answers from the prompt alone: no tools at all (--tools "").
    cmd = [*cli, "-p", prompt, "--output-format", "json", *ISOLATION, "--tools", "", "--max-turns", "1",
           "--max-budget-usd", f"{suite.max_cost_usd:.2f}", *model_args(suite)]
    res = run_command(cmd, cwd=None, timeout=suite.timeout_seconds)
    if res.error is not None:
        return {"pass": False, "reasons": ["non-JSON judge answer"], "cost_usd": res.cost_usd, "raw": res.error[-300:]}
    verdict = parse_verdict(res.output)
    if verdict is None:
        return {"pass": False, "reasons": ["non-JSON judge answer"], "cost_usd": res.cost_usd, "raw": res.output[:300]}
    return {**verdict, "cost_usd": res.cost_usd, "raw": res.output[:300]}
