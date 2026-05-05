from __future__ import annotations

from dataclasses import dataclass

from shared.models import Vec2


@dataclass(frozen=True, slots=True)
class SpawnZone:
    id: str
    kind: str
    center: Vec2
    radius: float
