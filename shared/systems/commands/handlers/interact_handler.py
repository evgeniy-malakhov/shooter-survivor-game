from __future__ import annotations

from typing import Callable

from shared.models import ClientCommand, PlayerState
from shared.systems.commands.base_handler import CommandHandler
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class InteractHandler(CommandHandler):
    def __init__(self, *, interact: Callable) -> None:
        self._interact = interact

    def handle(
        self,
        state: WorldState,
        ctx: WorldContext,
        player: PlayerState,
        command: ClientCommand,
    ) -> tuple[bool, str]:
        if self._interact(player):
            return True, ""

        return False, "nothing_to_interact"