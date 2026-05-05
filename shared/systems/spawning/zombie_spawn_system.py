from __future__ import annotations

from shared.systems.base import WorldSystem
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class ZombieSpawnSystem(WorldSystem):
    def update(self, state: WorldState, ctx: WorldContext, dt: float) -> None:
        state.spawn_timer -= dt

        living_players = [
            player
            for player in state.players.values()
            if player.alive
        ]

        if not living_players:
            return

        if state.spawn_timer > 0.0:
            return

        if ctx.max_zombies <= 0:
            return

        if len(state.zombies) >= ctx.max_zombies:
            return

        ctx.spawning.spawn_zombie()

        state.spawn_timer = max(
            0.8,
            max(1.2, 4.2 - state.time * 0.003)
            * ctx.difficulty.zombie_spawn_interval_multiplier,
        )