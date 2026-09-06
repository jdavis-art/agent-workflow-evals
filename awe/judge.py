"""LLM judge: rubric + output -> strict JSON verdict through the same CLI.

Only a top-level {"pass": bool, "reasons": [str]} object counts as a verdict (code fences are stripped
first). Anything else is a failure with the reason "non-JSON judge answer"."""
from __future__ import annotations
import json
import re

from .runners.claude import default_cli, run_command
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

_FENCE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*\n?(.*?)\n?\s*```\s*$", re.S)


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
    prompt = TEMPLATE.format(rubric=rubric, case_id=case.id, description=case.description,
                             output=output if isinstance(output, str) else json.dumps(output))
    cmd = [*cli, "-p", prompt, "--output-format", "json", "--max-turns", "1", "--max-budget-usd", f"{suite.max_cost_usd:.2f}"]
    res = run_command(cmd, cwd=None, timeout=suite.timeout_seconds)
    if res.error is not None:
        return {"pass": False, "reasons": ["non-JSON judge answer"], "cost_usd": res.cost_usd, "raw": res.error[-300:]}
    verdict = parse_verdict(res.output)
    if verdict is None:
        return {"pass": False, "reasons": ["non-JSON judge answer"], "cost_usd": res.cost_usd, "raw": res.output[:300]}
    return {**verdict, "cost_usd": res.cost_usd, "raw": res.output[:300]}
