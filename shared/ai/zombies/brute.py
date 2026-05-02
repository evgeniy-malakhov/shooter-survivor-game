from __future__ import annotations

from shared.ai.context import ZombieActionResult, ZombieContext
from shared.ai.zombies.base_zombie import BaseZombieAI
from shared.ai.zombies.scores import BruteDecisionScorer
from shared.constants import SEARCH_DURATION, ZOMBIE_TARGET_RADIUS, ZOMBIES


class BruteZombieAI(BaseZombieAI):
    kind = "brute"
    scorer = BruteDecisionScorer()

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