from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Any

from shared.ai.context import ActorTarget
from shared.models import SoldierState, Vec2, WeaponSpec


@dataclass(slots=True)
class SoldierActionResult:
    projectiles: list[dict[str, Any]] = field(default_factory=list)
    sounds: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class SoldierContext:
    soldier: SoldierState
    targets: tuple[ActorTarget, ...]
    dt: float
    time: float
    rng: random.Random
    spec: Any
    weapon: WeaponSpec

    line_blocked: Callable[[Vec2, Vec2, int], bool]
    move_toward: Callable[[SoldierState, Vec2, float, random.Random], None]
    random_guard_pos: Callable[[SoldierState, random.Random], Vec2]
    projectile_life: Callable[[float], float]