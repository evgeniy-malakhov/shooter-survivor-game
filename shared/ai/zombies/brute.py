from __future__ import annotations

from shared.ai.context import ZombieActionResult, ZombieContext
from shared.ai.decisions import select_best_target
from shared.ai.zombies.base_zombie import BaseZombieAI
from shared.constants import SEARCH_DURATION, ZOMBIE_TARGET_RADIUS, ZOMBIES


class BruteZombieAI(BaseZombieAI):
    kind = "brute"

    # def update(self, ctx: ZombieContext) -> ZombieActionResult:
    #     zombie = ctx.zombie
    #     result = ZombieActionResult()
    #
    #     zombie.attack_cooldown = max(0.0, zombie.attack_cooldown - ctx.dt)
    #     zombie.special_cooldown = max(0.0, zombie.special_cooldown - ctx.dt)
    #     zombie.sidestep_timer = max(0.0, zombie.sidestep_timer - ctx.dt)
    #
    #     target = select_best_target(ctx)
    #
    #     if target:
    #         zombie.mode = "chase"
    #         zombie.target_player_id = target.id
    #         zombie.last_known_pos = target.pos.copy()
    #         zombie.search_timer = SEARCH_DURATION
    #         zombie.alertness = 1.0
    #
    #         # Brute медленнее реагирует, но идёт напролом.
    #         destination = self._resolve_destination(ctx, target)
    #         ctx.move_toward(zombie, destination, ctx.dt, True, ctx.rng)
    #
    #         self._try_heavy_attack(ctx, target, result)
    #         return result
    #
    #     if zombie.last_known_pos:
    #         zombie.mode = "investigate"
    #         self._move_to_last_known(ctx)
    #         return result
    #
    #     self._patrol(ctx)
    #     return result

    def _try_attack(self, ctx: ZombieContext, target, result: ZombieActionResult) -> None:
        zombie = ctx.zombie
        spec = ZOMBIES[zombie.kind]

        if zombie.attack_cooldown > 0:
            return

        if zombie.pos.distance_to(target.pos) > ZOMBIE_TARGET_RADIUS + spec.radius + 12:
            return

        if ctx.line_blocked(zombie.pos, target.pos, zombie.floor):
            return

        damage = max(1, int(round(spec.damage * 1.35 * ctx.difficulty.zombie_damage_multiplier)))
        result.player_hits.append((target.id, damage))

        # Brute bite rare but hurt.
        zombie.attack_cooldown = 1.35