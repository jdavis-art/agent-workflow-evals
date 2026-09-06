# agent-workflow-evals (`awe`)

A small Python harness that runs an agent workflow against fixtures with a known answer, grades the output
with deterministic assertions and an optional LLM judge, and keeps a scoreboard with a diff against the
last run. It exists so the workflows an operator relies on every week are tested the way code is tested.

Two failures motivated it. A weekly review was supposed to flag drift between a dashboard seed and the
source of truth; it said "matches" six weeks in a row while three projects were missing, and nothing checked
the checker. A morning brief invented action items that were in none of its inputs. Both fail a fixture here.

## Install

Python 3.12 or newer. The only runtime dependency is `pyyaml`; the only dev dependency is `pytest`.

```
py -m venv .venv
.venv\Scripts\python.exe -m pip install -e .[dev]
.venv\Scripts\python.exe -m pytest -q
```

The claude runner uses the Claude Code CLI already on the machine (`claude -p --output-format json`) with
the CLI's own login. No API key is read or stored.

The bid-scoring suite is the one suite with an extra, suite-level dependency: the sibling `bid-radar`
package, installed editable from a checkout next to this one (`pip install -e ../bid-radar`). It is not a
dependency of the harness and is not in `pyproject.toml`.

## Suites and cases

A suite is a folder under `suites/` with a `suite.yaml`, a `cases/` folder of one YAML per case, and whatever
the prompt needs (fixtures, a prompt file, a rubric). Nothing in the harness knows about any particular
workflow.

`suite.yaml`:

```yaml
name: seed-drift
runner: claude            # claude | python
prompt_file: prompt.md    # claude runner: the workflow prompt; {fixtures} is substituted with the sandbox path
allowed_tools: [Read, Glob, Grep]
timeout_seconds: 300
max_cost_usd: 0.50        # per case per attempt; exceeding fails the attempt
pass_threshold: 0.67      # pass rate over --repeat N attempts needed for the case to count as passed
# model: sonnet           # optional; the CLI default otherwise
judge:
  enabled: false
  rubric_file: rubric.md
  context_files: []       # files from the case's fixtures pasted into the judge prompt
```

`cases/missing-project.yaml`:

```yaml
id: missing-project
description: seed lacks one project that the line-loading table lists
fixtures: fixtures/            # copied into a fresh sandbox per attempt
inputs: {}                     # python runner: kwargs for the callable
assert:
  - mentions_all: ["Cedar Row", "Northline"]     # every drifted item named
  - not_contains: "Seed matches vault"
  - regex: 'seed-data\.json'                     # a paste-ready prompt is present
  - length_between: [300, 6000]
```

A case passes when every assertion passes and, if the judge is on, the judge returns `pass: true`. With
`--repeat N` each case runs N times and its pass rate is compared with the suite's `pass_threshold`.
`templates/vault-suite/` holds a fully commented suite and a case showing every assertion kind.

## Assertions

Text kinds run against the run's final text (claude runner) or the JSON dump of the return value (python
runner). Value kinds run against the return value itself.

| Kind | Argument | Passes when |
| --- | --- | --- |
| `contains` | string | the substring is present (case-sensitive) |
| `not_contains` | string | the substring is absent |
| `regex` | pattern | the pattern matches (DOTALL) |
| `not_regex` | pattern | the pattern does not match |
| `length_between` | `[lo, hi]` | the character count is within the bounds, inclusive |
| `mentions_all` | list | every item is present, case-insensitive |
| `mentions_none` | list | no item is present, case-insensitive |
| `equals` | value | the return value equals it |
| `gte`, `lte` | number | the return value compares |
| `json_path` | `{path, equals\|gte\|lte}` | the field at `a.b[0].c` in the return value compares |

The first failing assertion's detail is what the scoreboard shows for the case.

## Runners and the cost and time guard

**claude.** The case's fixtures are copied into a fresh temporary sandbox, and the CLI runs there with the
prompt (its `{fixtures}` placeholder replaced by the sandbox path), `--output-format json`, the suite's tools
as both `--tools` and `--allowedTools`, `--max-turns 25`, and `--max-budget-usd` set to `max_cost_usd`. The
sandbox is deleted afterwards, also on a timeout. The run is isolated from the user's Claude Code setup with
`--restricted --strict-mcp-config --disable-slash-commands --no-session-persistence`: no user or project
settings, no MCP servers, no skills, file tools confined to the sandbox, no session files. Without that the
first live run inherited hundreds of MCP tool definitions and exhausted its budget before writing a word.

Every attempt is guarded twice. `timeout_seconds` fails it with the reason `timeout`, and the cost reported
in the CLI's envelope is checked against `max_cost_usd` even though the CLI was already told the cap. An
envelope with `is_error` or a subtype other than `success` (a budget stop, a turn limit) fails the attempt
with `cli <subtype>` and keeps the cost, so an empty result is never graded as a pass.

**python.** `target: "module:callable"` is imported with the suite folder on `sys.path` and called with the
case's `inputs` as keyword arguments. Exceptions are recorded as the attempt's error. Cost is zero.

`AWE_CLAUDE_CLI` (a space-separated command) overrides the CLI for both the runner and the judge; the tests
point it at `scripts/fake_claude.py`, a stub that answers with canned envelopes.

## Judge

With `--judge`, and only for suites that enable it, each attempt that passed its assertions is sent to the
same CLI with the rubric, the case, the output, and the contents of `judge.context_files` (capped at 20,000
characters). The judge has no tools. Its answer must be exactly a JSON object `{"pass": bool, "reasons":
[...]}`, code fences allowed; anything else fails the attempt with the reason `non-JSON judge answer`. The
judge's cost is added to the attempt's cost and counts against `max_cost_usd`.

Assertions are for everything that can be expressed deterministically. The judge is only for what they
cannot express, such as "every bullet traces to an entry in the input".

## Results and diff

`awe run <suite>` writes `results/<suite>/<timestamp>.json` with every attempt's assertions, judge verdict,
cost, duration and output excerpt, then regenerates `results/<suite>/latest.md`: a table of cases with pass
rate, cost and first failure, a "changed since last run" section listing cases that flipped, and totals.
The exit code is 0 only when every case passed. `awe diff <suite>` prints the same for the latest two runs.
`awe run <suite> --dry-run` prints the exact CLI command per case and calls nothing. `awe list` names the
suites under the root. `--root DIR` points all commands at another folder holding `suites/` and `results/`.

## Shipped suites

All three ran live on 2026-09-05 with the CLI's default model.

**seed-drift** (claude runner). A fictional mini vault: a Line Loading table of five projects, five project
files, and a dashboard seed with planted drift (one project missing, one box count moved, one price per box
changed, one status stale). Five cases, one per drift type plus a no-drift case whose seed matches and whose
answer must be exactly "Seed matches vault." Measured: 15 of 15 attempts passed with `--repeat 3`, at about
$0.08 per attempt. The only change during bring-up was a wording tightening of the prompt for the no-drift
case; no assertion was changed.

**morning-brief** (claude runner, judge enabled). A fictional collector payload (calendar, inbox, tasks,
yesterday's meetings) and a synthesizer prompt. Cases check the five section headers, the length band, that
named inputs appear, and that an empty calendar is reported as "No meetings today." rather than filled with
an invented meeting. The judge grades every bullet against the payload, which reaches it through
`context_files`. Measured: 8 of 8 attempts passed assertions and judge with `--judge --repeat 2`, at about
$0.09 per attempt including the judge call.

**bid-scoring** (python runner). `golden.csv` holds 145 public solicitations from a 2026-09-04 sweep, hand
labeled `pursue` or `ignore` (20 pursue, 125 ignore). `score_golden.py` scores every row with the real
scorer from the sibling `bid-radar` package and reports precision, recall, F1 and the confusion list at the
digest threshold of 3. Measured on the hand-corrected labels: recall 1.0, precision 0.2353. The case's
precision floor is 0.20, a regression guard at the measured baseline; the target is 0.60 once the scoring
config adds exclusion terms for services, program administration, property management, vouchers and trades
work. A second case checks that every row excluded by an exclusion word still scores 0.

To correct labels, edit the `label` column of `suites/bid-scoring/golden.csv` by hand (`note` is free text).
`scripts/build_golden.py --keep-labels` rebuilds the row set from the sweep fixture while preserving the
labels already in the file; without the flag it proposes labels from the legacy score, which is only useful
for a first draft.

## Vault-side use

The same harness runs against real fixtures kept outside this repository. See `templates/README.md` for
the three steps: install the package, copy `templates/vault-suite/` to `<vault>/.claude/evals/suites/<name>/`,
and run `awe --root <vault>/.claude/evals run <name>` (or `py -m awe.cli ...` when the console script is not
on PATH).

## What is public and what is not

- This repository is public. Its fixtures are fictional or public solicitation data, and carry no company,
  client or person names.
- `results/` is gitignored except for `.gitkeep`; so are `seed/`, `.env*` and `*.local.*`.
- The vault-side suites and their real fixtures never enter this repository.
- No API keys. The claude runner uses the CLI's own login, and the sandbox run cannot read outside its
  temporary folder.
