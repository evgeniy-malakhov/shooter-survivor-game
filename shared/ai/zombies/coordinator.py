from __future__ import annotations

from shared.ai.zombies.base_zombie import BaseZombieAI
from shared.ai.zombies.scores import WalkerDecisionScorer


class CoordinatorZombieAI(BaseZombieAI):
    kind = "coordinator"
    scorer = WalkerDecisionScorer()

    def _sound_reaction_delay(self, ctx, decision) -> float:
        return min(0.18, super()._sound_reaction_delay(ctx, decision))

    def _update_search(self, ctx) -> None:
        ctx.zombie.alertness = min(1.0, ctx.zombie.alertness + ctx.dt * 0.08)
        super()._update_search(ctx)
