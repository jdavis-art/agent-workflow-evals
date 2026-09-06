from __future__ import annotations
import dataclasses
from typing import Any


@dataclasses.dataclass
class RunOutput:
    output: Any
    cost_usd: float = 0.0
    seconds: float = 0.0
    error: str | None = None
