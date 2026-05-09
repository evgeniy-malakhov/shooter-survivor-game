from __future__ import annotations

from shared.constants import SPRINT_NOISE, UNARMED_MELEE_NOISE, WALK_NOISE
from shared.models import PlayerState, Vec2
from shared.status_effects import STATUS_EFFECTS, active_status_effects, combined_speed_multiplier


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

    def update_status_effects(self, player: PlayerState, dt: float) -> None:
        if not player.status_effects:
            return

        damage = 0.0
        for key in list(player.status_effects):
            remaining = max(0.0, float(player.status_effects.get(key, 0.0)) - dt)
            if remaining <= 0.0:
                player.status_effects.pop(key, None)
                continue
            player.status_effects[key] = remaining
            spec = STATUS_EFFECTS.get(key)
            if spec and spec.damage_per_second > 0.0:
                damage += spec.damage_per_second * dt

        if damage > 0.0 and player.alive:
            player.health -= damage
            if player.health <= 0:
                player.health = 0
                player.alive = False

    def apply_status_effect(self, player: PlayerState, key: str, duration: float) -> None:
        if key not in STATUS_EFFECTS:
            return
        player.status_effects[key] = max(float(duration), player.status_effects.get(key, 0.0))

    def speed_multiplier(self, player: PlayerState) -> float:
        return combined_speed_multiplier(active_status_effects(player.status_effects))

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
