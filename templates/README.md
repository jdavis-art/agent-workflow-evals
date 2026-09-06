# Running the harness from another folder

The harness does not care where suites live. Any folder that contains `suites/` can be a root, and results
land in `<root>/results/<suite>/`. Three steps:

1. **Install the package** into the Python you will run it with. From this repo's folder:

   ```
   pip install -e .
   ```

   The bid-scoring suite also needs the sibling scorer, `pip install -e ../bid-radar`; other suites do not.

2. **Copy the template** to `<root>/suites/<name>/` and edit `suite.yaml`, the prompt, the fixtures and the
   cases. For a vault the root is `<vault>/.claude/evals`, so the copy target is
   `<vault>/.claude/evals/suites/<name>/`. Both `<vault>/.claude/evals/suites/` and
   `<vault>/.claude/evals/results/` exist with a `.gitkeep`; results are gitignored on the vault side.

3. **Run it** with `--root` pointing at the folder that holds `suites/`. Two command forms:

   ```
   awe --root <vault>/.claude/evals run <name> --dry-run          # console script (a venv install puts it on PATH)
   py -m awe.cli --root <vault>/.claude/evals run <name> --dry-run  # module form when Scripts/ is not on PATH
   ```

   The vault uses the system Python (`py`), where the console script is not on PATH, so the module form is
   the one to use there. Drop `--dry-run` to spend tokens; add `--repeat 3` for a pass rate and `--judge` to
   enable the suite's rubric. `awe --root <root> list` names the suites, `awe --root <root> diff <name>` prints
   the latest scoreboard with the change against the previous run.

Real fixtures (a snapshot of a real table, a real collector payload) stay in the vault. They never enter
this repository.
