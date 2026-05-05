from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SpawnRule:
    actor_type: str
    weight: float = 1.0
