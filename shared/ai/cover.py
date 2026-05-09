from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable

from shared.constants import MAP_HEIGHT, MAP_WIDTH
from shared.models import Vec2


@dataclass(slots=True)
class CoverPoint:
    position: Vec2
    direction: Vec2
    floor: int
    protection_score: float
    occupied_by: str | None = None


def choose_cover_position(
    *,
    origin: Vec2,
    threat: Vec2,
    floor: int,
    line_blocked: Callable[[Vec2, Vec2, int], bool],
    rng: random.Random,
    min_distance: float = 180.0,
    max_distance: float = 330.0,
) -> Vec2 | None:
    away = Vec2(origin.x - threat.x, origin.y - threat.y)
    if away.length() <= 0.01:
        away = Vec2(1.0, 0.0)
    base_angle = math.atan2(away.y, away.x)

    best: CoverPoint | None = None
    for index in range(10):
        side = -1.0 if index % 2 else 1.0
        spread = (index // 2) * 0.28 * side
        angle = base_angle + spread + rng.uniform(-0.08, 0.08)
        distance = rng.uniform(min_distance, max_distance)
        candidate = Vec2(
            origin.x + math.cos(angle) * distance,
            origin.y + math.sin(angle) * distance,
        )
        candidate.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)

        blocked = line_blocked(candidate, threat, floor)
        distance_score = min(1.0, candidate.distance_to(threat) / max_distance)
        protection = (0.65 if blocked else 0.0) + distance_score * 0.35
        if not blocked and protection < 0.55:
            continue
        point = CoverPoint(
            position=candidate,
            direction=Vec2(math.cos(angle), math.sin(angle)),
            floor=floor,
            protection_score=protection,
        )
        if best is None or point.protection_score > best.protection_score:
            best = point

    return best.position if best else None
