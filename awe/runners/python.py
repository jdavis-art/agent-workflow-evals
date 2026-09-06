from __future__ import annotations
import importlib
import sys
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
    """Import `suite.target` ('module:callable') and call it with the case inputs as keyword arguments.
    The suite folder is put on sys.path for the call so a suite can ship its own target module."""
    t0 = time.perf_counter()
    sys.path.insert(0, str(suite.path))
    try:
        fn = resolve(suite.target)
        out = fn(**case.inputs)
        return RunOutput(output=out, seconds=time.perf_counter() - t0)
    except Exception as e:  # noqa: BLE001 - the harness records, never crashes
        return RunOutput(output=None, seconds=time.perf_counter() - t0, error=f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}")
    finally:
        try:
            sys.path.remove(str(suite.path))
        except ValueError:
            pass
