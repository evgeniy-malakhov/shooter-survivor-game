from __future__ import annotations

from shared.systems.commands.base_handler import CommandHandler


class ThrowGrenadeHandler(CommandHandler):
    def handle(self, state, ctx, player, command) -> tuple[bool, str]:
        if state.grenade_cooldowns.get(player.id, 0.0) > 0.0:
            return False, "cooldown"

        ctx.player_combat.throw_grenade(player, ctx)
        return True, ""