from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque

from shared.models import (
    BuildingState,
    GrenadeState,
    InputCommand,
    LootState,
    MineState,
    PlayerState,
    PoisonPoolState,
    PoisonProjectileState,
    ProjectileState,
    RectState,
    SoldierState,
    ZombieState,
)
from shared.ai.context import SoundEvent


@dataclass(slots=True)
class WorldState:
    time: float = 0.0

    players: dict[str, PlayerState] = field(default_factory=dict)
    zombies: dict[str, ZombieState] = field(default_factory=dict)
    soldiers: dict[str, SoldierState] = field(default_factory=dict)

    projectiles: dict[str, ProjectileState] = field(default_factory=dict)
    grenades: dict[str, GrenadeState] = field(default_factory=dict)
    mines: dict[str, MineState] = field(default_factory=dict)
    poison_projectiles: dict[str, PoisonProjectileState] = field(default_factory=dict)
    poison_pools: dict[str, PoisonPoolState] = field(default_factory=dict)

    loot: dict[str, LootState] = field(default_factory=dict)
    inputs: dict[str, InputCommand] = field(default_factory=dict)
    buildings: dict[str, BuildingState] = field(default_factory=dict)

    sound_events: list[SoundEvent] = field(default_factory=list)
    domain_events: Deque[dict[str, Any]] = field(default_factory=deque)

    grenade_cooldowns: dict[str, float] = field(default_factory=dict)

    spawn_timer: float = 0.0
    loot_timer: float = 0.0

    geometry_version: int = 0
    closed_walls_cache: dict[int, tuple[int, tuple[RectState, ...]]] = field(default_factory=dict)