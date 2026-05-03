from __future__ import annotations

from abc import ABC, abstractmethod

from shared.models import InputCommand, PlayerState
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class CommandHandler(ABC):
    @abstractmethod
    def handle(
        self,
        state: WorldState,
        ctx: WorldContext,
        player: PlayerState,
        command: InputCommand,
    ) -> type[bool, str]:
        pass