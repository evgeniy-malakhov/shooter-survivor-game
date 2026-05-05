from __future__ import annotations

from shared.models import ClientCommand, PlayerState
from shared.systems.commands.base_handler import CommandHandler
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class ReloadHandler(CommandHandler):
    def handle(
        self,
        state: WorldState,
        ctx: WorldContext,
        player: PlayerState,
        command: ClientCommand,
    ) -> tuple[bool, str]:
        weapon = player.active_weapon()

        if not weapon:
            return False, "no_weapon"

        if weapon.reserve_ammo <= 0 or weapon.ammo_in_mag >= ctx.weapons.magazine_size(weapon):
            return False, "cannot_reload"

        ctx.weapons.start_reload(player)
        return True, ""