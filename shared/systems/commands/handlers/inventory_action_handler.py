from __future__ import annotations

from shared.models import ClientCommand, PlayerState
from shared.systems.commands.base_handler import CommandHandler
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class InventoryActionHandler(CommandHandler):
    def handle(self, state: WorldState, ctx: WorldContext, player: PlayerState, command: ClientCommand) -> tuple[bool, str]:
        action = command.payload.get("action", command.payload)

        if not isinstance(action, dict):
            return False, "invalid_payload"

        ctx.inventory.apply_inventory_action(player, action)
        return True, ""