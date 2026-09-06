# Claude Code Operating Context — Agent Workflow Evals (Build Session)

Status: shipped 2026-09-06.

You are the **build session** for `awe`, the agent workflow evals
harness. A separate supervising session reviews your work gate by
gate. Read, in order:

1. `docs/superpowers/plans/2026-09-05-agent-workflow-evals.md` (execute task by task)
2. `docs/superpowers/specs/2026-09-05-agent-workflow-evals-design.md` (the design)

## What this is

A Python harness that runs agent workflows against fixtures through a
headless Claude Code runner or a Python callable, grades them with
assertions and an optional LLM judge, and keeps a scoreboard. Three
suites ship with it. This repo is **public**.

## THE GATE RULE (most important instruction)

Five gates. **At each gate you STOP, print the gate's required output,
and wait** for the green light.

## Locked decisions (do not relitigate)

- Python 3.12+ via `py`; runtime dep `pyyaml` only; `pytest` for tests.
- The claude runner is `claude -p --output-format json` in a sandbox
  copy of the fixtures with read-only allowed tools, a timeout, and a
  cost cap per case. No API keys; the CLI's own auth.
- Assertions are deterministic; the judge is optional and only for
  what assertions cannot express.
- The bid-scoring suite grades the real sibling package
  (`bid-radar`, installed editable). Golden labels are proposals until
  the owner corrects them; say so in output.
- Live suite runs spend real tokens. Run `--dry-run` first, respect
  `max_cost_usd`, and report total cost at every gate.

## Public repo hygiene

- `results/` (except `.gitkeep`), `seed/`, `.env*`, `*.local.*` are
  gitignored. Never `git add -f`.
- Fixtures are fictional or public solicitation data. No company,
  client, or person names. The morning-brief and seed-drift fixtures
  use the invented names in the plan only.
- The vault-side real fixtures never enter this repo.

## Working style

- TDD per the plan; commit after every task with the plan's message.
- When a live case fails on substance (the model fabricated, missed
  drift), that is a finding: report it, do not tune the assertion or
  the prompt to hide it. Tighten prompts only for formatting failures.
- Keep gate output short: `pytest -q`, the scoreboard, cost, `git status`.
