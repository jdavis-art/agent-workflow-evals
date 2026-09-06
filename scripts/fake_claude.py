"""Stub for tests: echoes a canned JSON envelope like `claude -p --output-format json`.
Accepts the same flags the real CLI gets (-p PROMPT, --output-format, --allowedTools, --max-turns,
--max-budget-usd) and answers based on markers in the prompt."""
import json
import sys

args = sys.argv[1:]
prompt = args[args.index("-p") + 1] if "-p" in args else ""
if "JUDGE" in prompt:
    verdict = {"pass": "GOOD OUTPUT" in prompt, "reasons": ["stub verdict"]}
    body = json.dumps(verdict)
    if "FENCED" in prompt:
        body = "```json\n" + body + "\n```"
    print(json.dumps({"result": body, "total_cost_usd": 0.001}))
elif "EXPENSIVE" in prompt:
    print(json.dumps({"result": "ok", "total_cost_usd": 9.0}))
else:
    print(json.dumps({"result": "Seed drift: Cedar Row is missing. See seed-data.json.", "total_cost_usd": 0.02}))
