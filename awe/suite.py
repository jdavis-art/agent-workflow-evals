"""Suite and case loading with validation. A suite is a folder: suite.yaml + cases/*.yaml (+ fixtures, prompt, rubric)."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import yaml

RUNNERS = ("python", "claude")
DEFAULT_TOOLS = ["Read", "Glob", "Grep"]


class SuiteError(ValueError):
    pass


@dataclasses.dataclass
class Case:
    id: str
    description: str
    fixtures: str | None
    inputs: dict
    assertions: list[dict]
    path: Path


@dataclasses.dataclass
class Suite:
    name: str
    path: Path
    runner: str
    prompt_file: str | None
    allowed_tools: list[str]
    timeout_seconds: int
    max_cost_usd: float
    judge: dict
    target: str | None
    pass_threshold: float
    cases: list[Case]

    def prompt(self) -> str:
        if not self.prompt_file:
            raise SuiteError(f"{self.name}: prompt_file is required for the claude runner")
        return (self.path / self.prompt_file).read_text(encoding="utf-8")


def _yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise SuiteError(f"{path}: invalid YAML: {e}") from None
    if not isinstance(data, dict):
        raise SuiteError(f"{path}: top level must be a mapping")
    return data


def load_suite(path: Path | str) -> Suite:
    path = Path(path)
    spec = _yaml(path / "suite.yaml")
    name = spec.get("name") or path.name
    runner = spec.get("runner")
    if runner not in RUNNERS:
        raise SuiteError(f"{path / 'suite.yaml'}: runner must be one of {RUNNERS}, got {runner!r}")
    target = spec.get("target")
    if runner == "python" and not target:
        raise SuiteError(f"{path / 'suite.yaml'}: python runner requires target 'module:callable'")
    judge = spec.get("judge") or {"enabled": False}
    judge.setdefault("enabled", False)
    cases_dir = path / "cases"
    cases = []
    for f in sorted(cases_dir.glob("*.yaml")) if cases_dir.is_dir() else []:
        c = _yaml(f)
        if not c.get("id"):
            raise SuiteError(f"{f}: case needs an id")
        cases.append(Case(id=str(c["id"]), description=c.get("description", ""), fixtures=c.get("fixtures"),
                          inputs=c.get("inputs") or {}, assertions=list(c.get("assert") or []), path=f))
    if not cases:
        raise SuiteError(f"{path}: no cases under cases/")
    return Suite(
        name=name, path=path, runner=runner, prompt_file=spec.get("prompt_file"),
        allowed_tools=list(spec.get("allowed_tools") or DEFAULT_TOOLS),
        timeout_seconds=int(spec.get("timeout_seconds", 300)), max_cost_usd=float(spec.get("max_cost_usd", 0.5)),
        judge=judge, target=target,
        pass_threshold=float(spec.get("pass_threshold", 1.0 if runner == "python" else 0.67)), cases=cases,
    )
