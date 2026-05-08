from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class BufferedSnapshot:
    tick: int
    server_time: float
    received_at: float
    data: dict[str, Any]
