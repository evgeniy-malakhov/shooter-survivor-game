from __future__ import annotations

from shared.constants import SPRINT_NOISE, UNARMED_MELEE_NOISE, WALK_NOISE
from shared.models import PlayerState, Vec2


class PlayerStatusService:
    def update_notice(self, player: PlayerState, dt: float) -> None:
        if player.notice_timer <= 0.0:
            player.notice = ""
            player.notice_timer = 0.0
            return

        player.notice_timer = max(0.0, player.notice_timer - dt)

        if player.notice_timer <= 0.0:
            player.notice = ""

    def update_healing(self, player: PlayerState, dt: float) -> None:
        if player.healing_left <= 0.0 or player.healing_pool <= 0.0 or player.health >= 100:
            if player.healing_pool <= 0.0 or player.health >= 100:
                player.healing_stacks = 0
            return

        stacks = max(1, player.healing_stacks)
        healed = min(player.healing_pool, player.healing_rate * dt * stacks)

        player.healing_pool -= healed
        player.healing_left = max(0.0, player.healing_left - dt)
        player.health = min(100, player.health + healed)

        if player.healing_left <= 0.0 or player.healing_pool <= 0.0 or player.health >= 100:
            player.healing_stacks = 0

    def noise(
        self,
        player: PlayerState,
        movement: Vec2,
        shooting: bool,
        meleeing: bool = False,
    ) -> float:
        if player.sneaking:
            return 0.0

        move_noise = 0.0

        if movement.length() > 0:
            move_noise = SPRINT_NOISE if player.sprinting else WALK_NOISE

        melee_noise = UNARMED_MELEE_NOISE if meleeing else 0.0

        return max(move_noise, melee_noise)