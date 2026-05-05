from __future__ import annotations

from shared.models import ClientCommand, PlayerState
from shared.systems.commands.base_handler import CommandHandler
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class RepairHandler(CommandHandler):
    def handle(self, state: WorldState, ctx: WorldContext, player: PlayerState, command: ClientCommand) -> tuple[bool, str]:
        slot = str(command.payload.get("slot", ""))

        if not slot:
            return False, "invalid_slot"

        ctx.inventory.repair_armor(player, slot)
        return True, ""