from __future__ import annotations

from dataclasses import dataclass

from shared.ai.decisions import DecisionScorer, DecisionWeights, ZombieDecision, ZombieDecisionKind, SoundReactionTuning
from shared.ai.zombies.configs.brute import BRUTE_DECISION_WEIGHTS, BRUTE_SOUND_REACTION
from shared.ai.zombies.configs.leaper import LEAPER_DECISION_WEIGHTS, LEAPER_SOUND_REACTION, LEAPER_TUNING
from shared.ai.zombies.configs.runner import RUNNER_DECISION_WEIGHTS, RUNNER_SOUND_REACTION
from shared.ai.zombies.configs.walker import WALKER_DECISION_WEIGHTS, WALKER_SOUND_REACTION


@dataclass(frozen=True, slots=True)
class LeaperTuning:
    spit_min_distance: float = 220.0
    spit_best_distance: float = 460.0
    spit_max_distance: float = 760.0
    spit_projectile_speed: float = 560.0
    spit_cooldown_min: float = 2.6
    spit_cooldown_max: float = 4.2
    strafe_distance: float = 420.0
    strafe_strength: float = 0.82
    approach_until_distance: float = 540.0

class WalkerDecisionScorer(DecisionScorer):
    sound_tuning = SoundReactionTuning(**WALKER_SOUND_REACTION)
    weights = DecisionWeights(**WALKER_DECISION_WEIGHTS)


class RunnerDecisionScorer(DecisionScorer):
    sound_tuning = SoundReactionTuning(**RUNNER_SOUND_REACTION)
    weights = DecisionWeights(**RUNNER_DECISION_WEIGHTS)


class BruteDecisionScorer(DecisionScorer):
    sound_tuning = SoundReactionTuning(**BRUTE_SOUND_REACTION)
    weights = DecisionWeights(**BRUTE_DECISION_WEIGHTS)


class LeaperDecisionScorer(DecisionScorer):
    tuning = LeaperTuning(**LEAPER_TUNING)
    sound_tuning = SoundReactionTuning(**LEAPER_SOUND_REACTION)
    weights = DecisionWeights(**LEAPER_DECISION_WEIGHTS)

    def _score_special(self, ctx, visible_decisions):
        zombie = ctx.zombie

        if zombie.special_cooldown > 0:
            return None

        best = None

        for decision in visible_decisions:
            target = decision.target
            if not target or target.inside_building:
                continue

            distance = zombie.pos.distance_to(target.pos)

            if distance < self.tuning.spit_min_distance:
                continue

            if distance > self.tuning.spit_max_distance:
                continue

            if ctx.line_blocked(zombie.pos, target.pos, zombie.floor):
                continue

            score = self.weights.special
            score += max(
                0.0,
                90.0 - abs(distance - self.tuning.spit_best_distance) / 3.5,
            )

            if getattr(target, "sprinting", False):
                score += 18.0

            if target.health <= 45:
                score += 16.0

            candidate = ZombieDecision(
                kind=ZombieDecisionKind.SPECIAL,
                score=score,
                target=target,
                pos=target.pos.copy(),
            )

            if best is None or candidate.score > best.score:
                best = candidate

        return best
