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
    kind: str = "generic"
    intensity: float = 1.0

@dataclass(slots=True)
class ZombieActionResult:
    player_hits: list[tuple[str, int]] = field(default_factory=list)
    soldier_hits: list[tuple[str, int]] = field(default_factory=list)
    poison_spits: list[Any] = field(default_factory=list)


@dataclass(slots=True)
class ZombieContext:
    zombie: ZombieState
    players: tuple[PlayerState, ...]
    targets: tuple[ActorTarget, ...]
    dt: float
    time: float
    rng: random.Random
    difficulty: Any

    can_see: Callable[[ZombieState, ActorTarget], bool]
    can_hear: Callable[[ZombieState], SoundEvent | None]
    line_blocked: Callable[[Vec2, Vec2, int], bool]
    move_toward: Callable[[ZombieState, Vec2, float, bool, random.Random], None]
    random_patrol_pos: Callable[[random.Random], Vec2]
    pick_search_waypoint: Callable[[ZombieState, Vec2, random.Random], Vec2 | None]
    building_entry_target: Callable[[str], Vec2 | None]
    path_next_point: Callable[[ZombieState, Vec2], Vec2]

@dataclass(slots=True)
class ActorTarget:
    id: str
    kind: str  # "player" | "zombie" | "soldier"
    pos: Vec2
    floor: int
    alive: bool
    radius: float
    health: int = 1
    sprinting: bool = False
    inside_building: str | None = None