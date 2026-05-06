from __future__ import annotations

from dataclasses import dataclass

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

