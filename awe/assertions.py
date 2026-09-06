"""Deterministic checks against a run's output (text or value)."""
from __future__ import annotations

import dataclasses
import json
import re
from typing import Any


@dataclasses.dataclass
class AssertionResult:
    kind: str
    passed: bool
    detail: str = ""


def _text(output: Any) -> str:
    return output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)


def _path(value: Any, path: str) -> Any:
    cur = value
    for part in re.findall(r"[^.\[\]]+|\[\d+\]", path):
        if part.startswith("["):
            cur = cur[int(part[1:-1])]
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(part)
    return cur


def _compare(kind: str, actual: Any, expected: Any) -> AssertionResult:
    ok = {"equals": actual == expected, "gte": actual >= expected, "lte": actual <= expected}[kind]
    return AssertionResult(kind, ok, f"{kind}: actual {actual!r}, expected {expected!r}")


def check(assertion: dict, output: Any) -> AssertionResult:
    if len(assertion) != 1:
        return AssertionResult("?", False, f"assertion must have one key: {assertion}")
    kind, arg = next(iter(assertion.items()))
    text = _text(output)
    low = text.lower()
    if kind == "contains":
        return AssertionResult(kind, arg in text, f"contains {arg!r}")
    if kind == "not_contains":
        return AssertionResult(kind, arg not in text, f"not_contains {arg!r}")
    if kind == "regex":
        return AssertionResult(kind, re.search(arg, text, re.S) is not None, f"regex {arg!r}")
    if kind == "not_regex":
        return AssertionResult(kind, re.search(arg, text, re.S) is None, f"not_regex {arg!r}")
    if kind == "length_between":
        lo, hi = arg
        return AssertionResult(kind, lo <= len(text) <= hi, f"length {len(text)} not in [{lo}, {hi}]" if not (lo <= len(text) <= hi) else f"length {len(text)}")
    if kind == "mentions_all":
        missing = [m for m in arg if m.lower() not in low]
        return AssertionResult(kind, not missing, f"missing: {missing}" if missing else "all mentioned")
    if kind == "mentions_none":
        present = [m for m in arg if m.lower() in low]
        return AssertionResult(kind, not present, f"present: {present}" if present else "none mentioned")
    if kind in ("equals", "gte", "lte"):
        return _compare(kind, output, arg)
    if kind == "json_path":
        try:
            actual = _path(output, arg["path"])
        except (KeyError, IndexError, TypeError) as e:
            return AssertionResult(kind, False, f"path {arg['path']!r} not found ({e})")
        for k in ("equals", "gte", "lte"):
            if k in arg:
                r = _compare(k, actual, arg[k])
                return AssertionResult(kind, r.passed, f"{arg['path']}: {r.detail}")
        return AssertionResult(kind, False, "json_path needs equals/gte/lte")
    return AssertionResult(kind, False, f"unknown assertion kind {kind!r}")
