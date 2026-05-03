from __future__ import annotations

from shared.systems.base import WorldSystem
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class SoundSystem(WorldSystem):
    def update(self, state: WorldState, ctx: WorldContext, dt: float) -> None:
        alive = []

        for event in state.sound_events:
            event.timer -= dt

            if event.timer > 0.0:
                alive.append(event)

        state.sound_events[:] = alive
