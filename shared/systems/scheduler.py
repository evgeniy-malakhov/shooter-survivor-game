from __future__ import annotations

from shared.systems.base import WorldSystem
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class SystemScheduler:
    def __init__(self, systems: list[WorldSystem]) -> None:
        self._systems = systems

    def update_all(self, state: WorldState, ctx: WorldContext, dt: float) -> None:
        for system in self._systems:
            system.update(state, ctx, dt)