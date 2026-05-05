from __future__ import annotations

from shared.models import ClientCommand, PlayerState
from shared.systems.commands.base_handler import CommandHandler
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class CraftHandler(CommandHandler):
    def handle(self, state: WorldState, ctx: WorldContext, player: PlayerState, command: ClientCommand) -> tuple[bool, str]:
        recipe_key = str(command.payload.get("key", ""))

        if not recipe_key:
            return False, "invalid_recipe"

        ctx.inventory.craft(player, recipe_key)
        return True, ""