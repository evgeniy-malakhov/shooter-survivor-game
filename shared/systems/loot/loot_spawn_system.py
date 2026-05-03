from __future__ import annotations

from shared.systems.base import WorldSystem
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class LootSpawnSystem(WorldSystem):
    def update(self, state: WorldState, ctx: WorldContext, dt: float) -> None:
        state.loot_timer -= dt

        if state.loot_timer > 0.0:
            return

        if len(state.loot) >= ctx.difficulty.world_loot_cap:
            return

        kind, payload, amount = ctx.loot.random_world_loot()
        pos = ctx.buildings.random_open_pos(
            centered=False,
            rng=ctx.rng,
            blocked_at=lambda p, r: ctx.geometry.blocked_at(p, r, 0),
        )

        ctx.loot.spawn_loot(
            loot_id=ctx.ids.next("l"),
            pos=pos,
            kind=kind,
            payload=payload,
            amount=amount,
        )

        state.loot_timer = (
            ctx.rng.uniform(2.5, 5.4)
            * ctx.difficulty.loot_spawn_interval_multiplier
        )