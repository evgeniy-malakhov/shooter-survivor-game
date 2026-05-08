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


class RenderSnapshotViewPool:
    def __init__(self) -> None:
        self._tick = -1
        self._view: RenderSnapshotView | None = None

    def view_for(self, snapshot: WorldSnapshot, tick: int) -> RenderSnapshotView:
        if self._view is not None and self._tick == tick:
            return self._view
        self._tick = tick
        self._view = RenderSnapshotView(
            tick=tick,
            time=snapshot.time,
            players=tuple(snapshot.players.values()),
            zombies=tuple(snapshot.zombies.values()),
            soldiers=tuple(snapshot.soldiers.values()),
            loot=tuple(snapshot.loot.values()),
            projectiles=tuple(snapshot.projectiles.values()),
        )
        return self._view


class SnapshotRenderAdapter:
    def __init__(self) -> None:
        self.pool = RenderSnapshotViewPool()

    def from_world_snapshot(self, snapshot: WorldSnapshot, tick: int) -> RenderSnapshotView:
        return self.pool.view_for(snapshot, tick)

