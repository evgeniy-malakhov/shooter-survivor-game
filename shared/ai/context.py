from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Any

from shared.models import PlayerState, Vec2, ZombieState


@dataclass(slots=True)
class SoundEvent:
    pos: Vec2
    floor: int
    radius: float
    timer: float
    source_player_id: str | None = None

@dataclass(slots=True)
class ZombieActionResult:
    player_hits: list[tuple[str, int]] = field(default_factory=list)
    poison_spits: list[Any] = field(default_factory=list)


@dataclass(slots=True)
class ZombieContext:
    zombie: ZombieState
    players: tuple[PlayerState, ...]
    dt: float
    time: float
    rng: random.Random
    difficulty: Any

    can_see: Callable[[ZombieState, PlayerState], bool]
    can_hear: Callable[[ZombieState], SoundEvent | None]
    line_blocked: Callable[[Vec2, Vec2, int], bool]
    move_toward: Callable[[ZombieState, Vec2, float, bool, random.Random], None]
    random_patrol_pos: Callable[[random.Random], Vec2]
    pick_search_waypoint: Callable[[ZombieState, Vec2, random.Random], Vec2 | None]
    building_entry_target: Callable[[str], Vec2 | None]
