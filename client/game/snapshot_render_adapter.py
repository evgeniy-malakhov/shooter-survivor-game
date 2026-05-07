from __future__ import annotations

from dataclasses import dataclass

from shared.models import (
    LootState,
    PlayerState,
    ProjectileState,
    SoldierState,
    WorldSnapshot,
    ZombieState,
)


@dataclass(frozen=True, slots=True)
class RenderSnapshotView:
    tick: int
    time: float
    players: tuple[PlayerState, ...]
    zombies: tuple[ZombieState, ...]
    soldiers: tuple[SoldierState, ...]
    loot: tuple[LootState, ...]
    projectiles: tuple[ProjectileState, ...]


class SnapshotRenderAdapter:
    def from_world_snapshot(self, snapshot: WorldSnapshot, tick: int) -> RenderSnapshotView:
        return RenderSnapshotView(
            tick=tick,
            time=snapshot.time,
            players=tuple(snapshot.players.values()),
            zombies=tuple(snapshot.zombies.values()),
            soldiers=tuple(snapshot.soldiers.values()),
            loot=tuple(snapshot.loot.values()),
            projectiles=tuple(snapshot.projectiles.values()),
        )

