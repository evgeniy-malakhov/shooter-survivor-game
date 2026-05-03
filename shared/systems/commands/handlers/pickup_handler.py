from __future__ import annotations

from shared.systems.commands.base_handler import CommandHandler


class PickupHandler(CommandHandler):
    def handle(self, state, ctx, player, command) -> tuple[bool, str]:
        if ctx.inventory.nearest_loot(player) is None:
            return False, "no_item_nearby"

        if ctx.inventory.pickup_nearby(player):
            return True, ""

        return False, "pickup_rejected"