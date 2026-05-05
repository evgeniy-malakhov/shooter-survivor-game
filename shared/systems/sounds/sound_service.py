from __future__ import annotations

from shared.ai.context import SoundEvent
from shared.models import Vec2
from shared.world.world_state import WorldState


class SoundService:
    def __init__(self, state: WorldState) -> None:
        self._state = state

    def emit(
        self,
        *,
        pos: Vec2,
        floor: int,
        radius: float,
        source_player_id: str | None = None,
        kind: str = "generic",
        intensity: float = 1.0,
    ) -> None:
        self._state.sound_events.append(
            SoundEvent(
                pos=pos.copy(),
                floor=floor,
                radius=max(0.0, radius),
                timer=0.75,
                source_player_id=source_player_id,
                kind=kind,
                intensity=intensity,
            )
        )