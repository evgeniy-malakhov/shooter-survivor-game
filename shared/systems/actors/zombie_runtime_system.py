from __future__ import annotations

from shared.systems.base import WorldSystem
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class ZombieRuntimeSystem(WorldSystem):
    def update(self, state: WorldState, ctx: WorldContext, dt: float) -> None:
        ctx.zombie_runtime.update_local(ctx, dt)