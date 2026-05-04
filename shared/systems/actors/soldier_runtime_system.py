from __future__ import annotations

from shared.systems.base import WorldSystem
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class SoldierRuntimeSystem(WorldSystem):
    def update(self, state: WorldState, ctx: WorldContext, dt: float) -> None:
        for soldier in list(state.soldiers.values()):
            if not soldier.alive:
                state.soldiers.pop(soldier.id, None)
                continue

            ai = ctx.soldier_runtime.registry.get(soldier.kind)

            if not ai:
                continue

            soldier_ctx = ctx.soldier_runtime.make_context(
                soldier,
                dt,
                ctx,
            )

            result = ai.update(soldier_ctx)

            ctx.soldier_runtime.apply_result(
                soldier,
                result,
                ctx,
            )