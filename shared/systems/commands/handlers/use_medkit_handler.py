from __future__ import annotations

from shared.models import ClientCommand, PlayerState
from shared.systems.commands.base_handler import CommandHandler
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class UseMedkitHandler(CommandHandler):
    def handle(
        self,
        state: WorldState,
        ctx: WorldContext,
        player: PlayerState,
        command: ClientCommand,
    ) -> tuple[bool, str]:
        if player.medkits <= 0:
            return False, "no_medkit"

        if player.health >= 100:
            return False, "health_full"

        player.medkits -= 1
        player.health = min(100, player.health + 42)

        return True, ""