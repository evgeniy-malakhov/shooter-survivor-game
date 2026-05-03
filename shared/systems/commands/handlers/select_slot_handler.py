from __future__ import annotations

from shared.constants import SLOTS
from shared.models import ClientCommand, PlayerState
from shared.systems.commands.base_handler import CommandHandler
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class SelectSlotHandler(CommandHandler):
    def handle(
        self,
        state: WorldState,
        ctx: WorldContext,
        player: PlayerState,
        command: ClientCommand,
    ) -> tuple[bool, str]:
        slot = str(command.payload.get("slot", ""))

        if slot not in SLOTS:
            return False, "invalid_slot"

        player.active_slot = slot
        return True, ""