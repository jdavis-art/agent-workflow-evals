# Agent Workflow Evals — Design Spec

Date: 2026-09-05. Status: draft for review. Owner: Jason Davis.
Wave 2 of the Sept 2026 portfolio builds.

## 1. Purpose

A small Python harness that runs an agent workflow against fixtures
and grades the output with deterministic assertions plus an optional
LLM-judge rubric, then writes a scoreboard and a diff against the last
run. It exists so that workflows the owner relies on every week (a
weekly review, a morning brief, a solicitation scorer) are tested the
way code is tested: a fixture with a known answer, a pass or fail, and
a history.

The trigger: a weekly-review workflow was supposed to flag drift
between a dashboard seed and the source of truth. It said "matches"
six reviews in a row while three projects were missing. Nobody noticed
because nothing checked the checker. The same class of failure showed
up in a morning brief that invented action items. Both would have
failed a fixture.

## 2. Scope

### In scope (v1)
- Harness: suites, cases, two runners (`claude` for headless Claude
  Code, `python` for a callable), assertions, an LLM-judge rubric,
  repeat runs with pass rate, a results store, a scoreboard, a diff.
- Three suites with fictional or public fixtures in the repo:
  1. `seed-drift`: a mini vault plus a seed file with planted drift;
     the workflow must name every drifted item and must not say the
     seed matches.
  2. `morning-brief`: collector JSON plus the synthesizer prompt; the
     brief must have the required sections, sit in the length band,
     and every action item must trace to the fixture data.
  3. `bid-scoring`: a hand-labeled golden set of public solicitations;
     the scorer's precision and recall at the digest threshold, with
     the confusion list.
- A cost and time guard per run.
- Vault-side suite configs that point the same harness at real
  fixtures (those stay in the vault, not in this repo).

### Out of scope (v1)
- A UI. The scoreboard is markdown.
- Model comparison across providers. One CLI, one model setting.
- Tracing or token-level analysis.
- Automatically fixing the workflow when a case fails.

## 3. Stack

Python 3.12+ (`py`), `pyyaml`, `pytest` for the harness's own tests,
and the Claude Code CLI already on the machine (`claude -p` with
`--output-format json`). The bid-scoring suite imports the scorer
from the sibling `bid-radar` package (installed in editable mode) so
the golden set grades the real code.

```
agent-workflow-evals/
  pyproject.toml                  # package "awe", console script "awe"
  awe/
    cli.py                        # awe run <suite> [--case ID] [--repeat N] [--judge] [--dry-run]
    suite.py                      # load suite.yaml + cases/*.yaml, validate
    runners/claude.py             # sandbox copy of fixtures, claude -p, capture text + cost
    runners/python.py             # import path:callable, call with case inputs
    assertions.py                 # contains, not_contains, regex, json_path, length_between, mentions_all, mentions_none
    judge.py                      # rubric -> claude -p -> {pass, reasons}, strict JSON
    results.py                    # results/<suite>/<ts>.json, latest.md, diff vs previous
    metrics.py                    # precision/recall/confusion for label suites
  suites/
    seed-drift/suite.yaml, cases/*.yaml, fixtures/vault/*.md, fixtures/seed-data.json
    morning-brief/suite.yaml, cases/*.yaml, fixtures/collectors.json, prompt.md
    bid-scoring/suite.yaml, golden.csv
  tests/                          # harness unit tests
  results/                        # gitignored except .gitkeep
  docs/superpowers/{specs,plans}/
```

## 4. Suite and case format

`suite.yaml`:
```yaml
name: seed-drift
runner: claude            # claude | python
prompt_file: prompt.md    # claude runner: the workflow prompt; {fixtures} is substituted with the sandbox path
allowed_tools: [Read, Glob, Grep]
timeout_seconds: 300
max_cost_usd: 0.50        # per case per run; exceeding fails the case
judge:
  enabled: false
  rubric_file: rubric.md
```

`cases/missing-project.yaml`:
```yaml
id: missing-project
description: seed lacks one project that the line-loading table lists
fixtures: fixtures/            # copied into a fresh sandbox per run
inputs: {}                     # python runner: kwargs for the callable
assert:
  - mentions_all: ["Cedar Row", "Northline"]     # every drifted item named
  - not_contains: "Seed matches vault"
  - regex: "seed-data\\.json"                     # a paste-ready prompt is present
  - length_between: [300, 6000]
```

Assertions are evaluated against the run's final text (claude runner)
or the callable's return value (python runner; `json_path` works on
dicts). `mentions_all` and `mentions_none` are case-insensitive
substring checks. A case passes when every assertion passes and, if
the judge is enabled, the judge returns `pass: true`.

## 5. Runners

- **claude:** copy `fixtures/` into a temp sandbox, run
  `claude -p "<prompt>" --output-format json --allowedTools <list>
  --max-turns 25` with the sandbox as the working directory, parse
  the JSON envelope for `result` (text) and `total_cost_usd`, enforce
  the timeout and the cost cap, delete the sandbox. `--dry-run` prints
  the command without running it.
- **python:** `target: "bid_radar.scoring:score_rows"` style import;
  the callable receives the case inputs and returns a value.
- **repeat:** `--repeat N` runs each case N times; the case's pass rate
  is N-pass over N; the suite pass threshold is configurable
  (default 1.0 for python suites, 0.67 for claude suites, since
  sampling varies).

## 6. Judge

Optional per suite. `judge.py` sends the rubric, the fixture summary
the suite declares, and the output to `claude -p` with a system
instruction to answer only with `{"pass": bool, "reasons": [str]}`.
Non-JSON answers count as judge failure with reason "non-JSON". The
judge is for questions assertions cannot express, such as "every
action item traces to a line in collectors.json." Judge cost counts
toward the case cap.

## 7. The three suites

### seed-drift
Fixtures: a fictional mini vault (`factory-operations.md` with a Line
Loading table of five projects, five project files) and a
`seed-data.json` in the production-plan dashboard's shape with planted
drift: one project missing, one box count moved, one price per box
changed, one status stale. Four cases, one per drift type, plus a
`no-drift` case where the seed matches and the output must contain
"Seed matches vault" and must not name any project as drifted.

### morning-brief
Fixtures: `collectors.json` (calendar, inbox, tasks, meetings arrays
with fictional content) and the synthesizer prompt (a genericized copy
of the pipeline's Phase 2 prompt). Cases: `sections-present` (regex
for each required header), `length-band` (800 to 8000 characters),
`no-fabrication` (judge: every action item maps to an entry in
collectors.json), `empty-calendar` (the brief must say the calendar is
clear rather than invent a meeting).

### bid-scoring
`golden.csv`: uid, title, agency, location, bid_type, blurb, label in
(`pursue`, `ignore`). Built from the 9/4 public sweep: all 85 rows at
score 3 or higher plus 60 sampled rows at 0 to 2, labels proposed from
the current score and corrected by hand before the suite is trusted.
Runner: python, target `bid_radar.scoring:score` over the config
loaded from the sibling repo. Metrics: precision, recall, F1 at
threshold 3, and the confusion list (title, score, label) written to
the scoreboard. Cases: `threshold-3` asserts recall at or above 0.90
and precision at or above 0.60 (initial floors; raise as the config
improves), and `exclusions-hold` asserts that every row labeled ignore
because of an exclusion word still scores 0.

## 8. Results and scoreboard

`results/<suite>/<timestamp>.json` holds every case's assertions,
judge output, cost, duration, and pass rate. `results/<suite>/latest.md`
is regenerated each run: a table of cases with pass rate, cost, and
the first failing assertion; a "changed since last run" section that
lists cases that flipped; totals. `awe diff <suite>` prints the same
against any two timestamps.

## 9. Vault-side use

The vault keeps real suite configs under `.claude/evals/<suite>/`
that reuse the harness with real fixtures (a snapshot of the real
Line Loading table and seed, a real collectors payload). Those files
never enter this repo. The harness is installed in the vault's Python
environment and run as `awe run --root .claude/evals seed-drift`.

## 10. Security and public boundary

- The repo's fixtures are fictional or public solicitation data.
- `results/` is gitignored; a `.gitkeep` holds the folder.
- The claude runner passes only the sandbox path and the prompt; it
  never reads outside the sandbox (allowed tools are read-only and the
  working directory is the sandbox).
- No API keys. The CLI's own auth is used.

## 11. Testing

- Harness unit tests: suite loading and validation errors, every
  assertion type, the judge JSON parser, results and diff, metrics on
  a tiny labeled list. The claude runner is tested with `--dry-run`
  and with a fake CLI stub that returns a canned JSON envelope.
- The three suites are the integration tests; gate 3 and 4 run them
  live.

## 12. Gates (build session stops at each)

1. Harness core: suite loader, assertions, python runner, results and
   scoreboard, unit tests green. Print `pytest -q`.
2. bid-scoring suite live against the sibling repo's scorer; print
   precision, recall, and the confusion list.
3. seed-drift suite live through the claude runner, five cases, pass
   rate with `--repeat 3`. Print the scoreboard.
4. morning-brief suite live with the judge enabled. Print the
   scoreboard and one judge reasons list.
5. README, vault-side config template, `awe` installed in the vault
   environment. Print `awe run --dry-run` from the vault root.

## 13. Later (not v1)

More suites (the CAR pull, the ROM quote drafting), a nightly run
with a delta email, model or prompt A/B on the same suite.
