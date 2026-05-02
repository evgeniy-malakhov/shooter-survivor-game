from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from shared.ai.context import SoundEvent, ZombieContext
from shared.constants import ZOMBIE_TARGET_RADIUS, ZOMBIES
from shared.models import PlayerState, Vec2


class ZombieDecisionKind(str, Enum):
    PATROL = "patrol"
    ORIENT_TO_SOUND = "orient_to_sound"
    INVESTIGATE_SOUND = "investigate_sound"
    SEARCH_LAST_KNOWN = "search_last_known"
    CHASE_VISIBLE_TARGET = "chase_visible_target"
    ATTACK = "attack"
    SPECIAL = "special"


@dataclass(slots=True)
class ZombieDecision:
    kind: ZombieDecisionKind
    score: float
    target: PlayerState | None = None
    sound: SoundEvent | None = None
    pos: Vec2 | None = None

@dataclass(frozen=True, slots=True)
class SoundReactionTuning:
    min_reaction_score: float = 45.0
    instant_reaction_score: float = 95.0
    reaction_delay_min: float = 0.2
    reaction_delay_max: float = 0.7

@dataclass(frozen=True, slots=True)
class DecisionWeights:
    visible_target: float = 100.0
    sound_interest: float = 55.0
    distance_to_target: float = 45.0
    wounded_target: float = 18.0
    sprinting_target: float = 10.0
    sneaking_target: float = -18.0
    attack: float = 140.0
    patrol: float = 8.0
    search: float = 35.0
    persistence: float = 20.0
    special: float = 0.0


class DecisionScorer:
    weights = DecisionWeights()
    sound_tuning = SoundReactionTuning()

    def choose(self, ctx: ZombieContext) -> ZombieDecision:
        decisions: list[ZombieDecision] = []

        visible = self._score_visible_targets(ctx)
        decisions.extend(visible)

        attack = self._score_attack(ctx, visible)
        if attack:
            decisions.append(attack)

        sound = self._score_sound(ctx)
        if sound:
            decisions.append(sound)

        search = self._score_search(ctx)
        if search:
            decisions.append(search)

        special = self._score_special(ctx, visible)
        if special:
            decisions.append(special)

        decisions.append(ZombieDecision(ZombieDecisionKind.PATROL, self.weights.patrol))

        return max(decisions, key=lambda decision: decision.score)

    def _score_visible_targets(self, ctx: ZombieContext) -> list[ZombieDecision]:
        result: list[ZombieDecision] = []

        for player in ctx.players:
            if player.floor != ctx.zombie.floor or not player.alive:
                continue

            if not ctx.can_see(ctx.zombie, player):
                continue

            distance = ctx.zombie.pos.distance_to(player.pos)
            score = self.weights.visible_target
            score += max(0.0, self.weights.distance_to_target - distance / 14.0)

            if player.health <= 35:
                score += self.weights.wounded_target

            if player.sprinting:
                score += self.weights.sprinting_target

            if player.sneaking:
                score += self.weights.sneaking_target

            result.append(
                ZombieDecision(
                    kind=ZombieDecisionKind.CHASE_VISIBLE_TARGET,
                    score=score,
                    target=player,
                    pos=player.pos.copy(),
                )
            )

        return result

    def _score_attack(
        self,
        ctx: ZombieContext,
        visible_decisions: list[ZombieDecision],
    ) -> ZombieDecision | None:
        zombie = ctx.zombie
        spec = ZOMBIES[zombie.kind]

        best: ZombieDecision | None = None

        for decision in visible_decisions:
            target = decision.target
            if not target:
                continue

            distance = zombie.pos.distance_to(target.pos)
            attack_range = ZOMBIE_TARGET_RADIUS + spec.radius

            if distance > attack_range:
                continue

            if zombie.attack_cooldown > 0:
                continue

            score = self.weights.attack + decision.score

            candidate = ZombieDecision(
                kind=ZombieDecisionKind.ATTACK,
                score=score,
                target=target,
                pos=target.pos.copy(),
            )

            if best is None or candidate.score > best.score:
                best = candidate

        return best

    def _score_sound(self, ctx: ZombieContext) -> ZombieDecision | None:
        sound = ctx.can_hear(ctx.zombie)
        if not sound:
            return None

        distance = ctx.zombie.pos.distance_to(sound.pos)

        score = self.weights.sound_interest
        score += sound.intensity * 45.0
        score += max(0.0, sound.radius / 35.0)
        score += max(0.0, 35.0 - distance / 22.0)

        if sound.kind == "shot":
            score += 35.0

        if ctx.zombie.mode in {"investigate", "search"}:
            score -= 22.0

        if ctx.zombie.mode == "orient_to_sound":
            score -= 40.0

        if ctx.zombie.mode == "chase":
            return None

        if sound.kind == "explosion":
            score += 60.0

        if sound.kind == "movement":
            score -= 12.0

        if score < self.sound_tuning.min_reaction_score:
            return None

        return ZombieDecision(
            kind=ZombieDecisionKind.ORIENT_TO_SOUND,
            score=score,
            sound=sound,
            pos=sound.pos.copy(),
        )

    def _score_special(
            self,
            ctx: ZombieContext,
            visible_decisions: list[ZombieDecision],
    ) -> ZombieDecision | None:
        return None

    def _score_search(self, ctx: ZombieContext) -> ZombieDecision | None:
        zombie = ctx.zombie

        if not zombie.last_known_pos:
            return None

        if zombie.mode not in {"investigate", "search", "chase"}:
            return None

        score = self.weights.search + zombie.alertness * self.weights.persistence

        return ZombieDecision(
            kind=ZombieDecisionKind.SEARCH_LAST_KNOWN,
            score=score,
            pos=zombie.last_known_pos.copy(),
        )