from __future__ import annotations

from typing import Callable
from shared.constants import ARMORS
from shared.models import ClientCommand, PlayerState
from shared.systems.commands.base_handler import CommandHandler
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class EquipArmorHandler(CommandHandler):
    def handle(self, state: WorldState, ctx: WorldContext, player: PlayerState, command: ClientCommand) -> tuple[bool, str]:
        armor_key = str(command.payload.get("armor_key", ""))

        if armor_key not in ARMORS:
            return False, "invalid_armor"

        ctx.inventory.equip_armor(player, armor_key)
        return True, ""