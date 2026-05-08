from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PendingInputRecord:
    seq: int
    command: dict[str, Any]
    dt: float


