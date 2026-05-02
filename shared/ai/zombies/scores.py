from __future__ import annotations

from dataclasses import dataclass

from shared.ai.decisions import DecisionScorer, DecisionWeights, ZombieDecision, ZombieDecisionKind, SoundReactionTuning


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
    sound_tuning = SoundReactionTuning(
        min_reaction_score=45,
        instant_reaction_score=95,
        reaction_delay_min=0.25,
        reaction_delay_max=0.65,
    )

    weights = DecisionWeights(
        visible_target=100.0,
        sound_interest=55.0,
        distance_to_target=35.0,
        wounded_target=10.0,
        sprinting_target=8.0,
        sneaking_target=-18.0,
        attack=130.0,
        patrol=12.0,
        search=35.0,
        persistence=18.0,
    )


class RunnerDecisionScorer(DecisionScorer):
    sound_tuning = SoundReactionTuning(
        min_reaction_score=35,
        instant_reaction_score=80,
        reaction_delay_min=0.08,
        reaction_delay_max=0.28,
    )

    weights = DecisionWeights(
        visible_target=115.0,
        sound_interest=75.0,
        distance_to_target=65.0,
        wounded_target=25.0,
        sprinting_target=22.0,
        sneaking_target=-10.0,
        attack=145.0,
        patrol=6.0,
        search=45.0,
        persistence=25.0,
    )


class BruteDecisionScorer(DecisionScorer):
    sound_tuning = SoundReactionTuning(
        min_reaction_score=60,
        instant_reaction_score=115,
        reaction_delay_min=0.45,
        reaction_delay_max=0.95,
    )

    weights = DecisionWeights(
        visible_target=95.0,
        sound_interest=35.0,
        distance_to_target=20.0,
        wounded_target=8.0,
        sprinting_target=5.0,
        sneaking_target=-25.0,
        attack=180.0,
        patrol=18.0,
        search=28.0,
        persistence=12.0,
    )


class LeaperDecisionScorer(DecisionScorer):
    tuning = LeaperTuning()

    sound_tuning = SoundReactionTuning(
        min_reaction_score=38,
        instant_reaction_score=78,
        reaction_delay_min=0.06,
        reaction_delay_max=0.24,
    )

    weights = DecisionWeights(
        visible_target=120.0,
        sound_interest=65.0,
        distance_to_target=70.0,
        wounded_target=20.0,
        sprinting_target=16.0,
        sneaking_target=-12.0,
        attack=40.0,
        patrol=7.0,
        search=48.0,
        persistence=28.0,
        special=185.0,
    )

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

            if target.sprinting:
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
