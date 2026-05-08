from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from shared.models import (
    BuildingState,
    GrenadeState,
    LootState,
    MineState,
    PlayerState,
    PoisonPoolState,
    PoisonProjectileState,
    ProjectileState,
    RectState,
    SoldierState,
    WorldSnapshot,
    ZombieState,
)


class RenderLOD(str, Enum):
    FULL = "full"
    SIMPLE = "simple"
    DOT = "dot"


@dataclass(frozen=True, slots=True)
class ActorRenderItem:
    id: str
    actor_type: str
    kind: str
    x: float
    y: float
    floor: int
    hp_ratio: float
    armor_ratio: float
    facing: float
    radius: float
    color: tuple[int, int, int]
    lod: RenderLOD
    is_local: bool = False
    is_dead: bool = False
    label: str = ""
    mode: str = ""


@dataclass(slots=True)
class RenderFrame:
    snapshot: WorldSnapshot
    buildings: tuple[BuildingState, ...]
    tunnels: tuple[RectState, ...]
    loot: tuple[LootState, ...]
    projectiles: tuple[ProjectileState, ...]
    grenades: tuple[GrenadeState, ...]
    mines: tuple[MineState, ...]
    poison_projectiles: tuple[PoisonProjectileState, ...]
    poison_pools: tuple[PoisonPoolState, ...]
    zombies: tuple[ZombieState, ...]
    soldiers: tuple[SoldierState, ...]
    players: tuple[PlayerState, ...]
    actor_lod: dict[str, RenderLOD]
    actors: tuple[ActorRenderItem, ...]

