from __future__ import annotations

from shared.models import ClientCommand, PlayerState
from shared.systems.commands.base_handler import CommandHandler
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class ToggleUtilityHandler(CommandHandler):
    def handle(
        self,
        state: WorldState,
        ctx: WorldContext,
        player: PlayerState,
        command: ClientCommand,
    ) -> tuple[bool, str]:
        if not ctx.weapons.toggle_utility(player):
            return False, "no_utility_module"

        return True, ""