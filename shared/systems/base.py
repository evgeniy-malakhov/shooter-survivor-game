from __future__ import annotations

from abc import ABC, abstractmethod

from shared.world.world_state import WorldState
from shared.world.world_context import WorldContext


class WorldSystem(ABC):
    @abstractmethod
    def update(self, state: WorldState, ctx: WorldContext, dt: float) -> None:
        pass