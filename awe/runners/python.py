from __future__ import annotations
import importlib
import time
import traceback

from . import RunOutput
from ..suite import Suite, Case


def resolve(target: str):
    mod, _, attr = target.partition(":")
    if not mod or not attr:
        raise ValueError(f"target must be 'module:callable', got {target!r}")
    return getattr(importlib.import_module(mod), attr)


def run_python(suite: Suite, case: Case) -> RunOutput:
    t0 = time.perf_counter()
    try:
        fn = resolve(suite.target)
        out = fn(**case.inputs)
        return RunOutput(output=out, seconds=time.perf_counter() - t0)
    except Exception as e:  # noqa: BLE001 - the harness records, never crashes
        return RunOutput(output=None, seconds=time.perf_counter() - t0, error=f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}")
