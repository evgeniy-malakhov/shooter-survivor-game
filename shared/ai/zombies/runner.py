from __future__ import annotations

from shared.ai.zombies.base_zombie import BaseZombieAI


class RunnerZombieAI(BaseZombieAI):
    kind = "runner"

    def _try_attack(self, ctx, target, result):
        super()._try_attack(ctx, target, result)

        # Runner attack often, but not strong.
        if ctx.zombie.attack_cooldown > 0:
            ctx.zombie.attack_cooldown *= 0.75