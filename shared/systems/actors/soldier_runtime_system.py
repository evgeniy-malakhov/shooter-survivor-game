from __future__ import annotations

from shared.systems.base import WorldSystem
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class SoldierRuntimeSystem(WorldSystem):
    def update(self, state: WorldState, ctx: WorldContext, dt: float) -> None:
        soldiers = list(state.soldiers.values())

        for soldier in soldiers:
            if not soldier.alive:
                state.soldiers.pop(soldier.id, None)

        inputs = ctx.actor_snapshots.build_soldier_inputs(
            list(state.soldiers.values()),
            ctx=ctx,
            dt=dt,
            rng=ctx.rng,
        )

        for output in ctx.actor_decisions.execute(inputs, ctx):
            ctx.soldier_runtime.apply_decision_output(output, ctx)
