from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from shared.ai.context import ActorTarget
from shared.ai.memory import memory_pos, most_dangerous_sound
from shared.models import Vec2
from shared.ai.soldiers.configs.schema import SoldierDecisionWeights, SoldierHearingTuning
from shared.ai.soldiers.context import SoldierContext


class SoldierDecisionKind(str, Enum):
    GUARD = "guard"
    COMBAT = "combat"
    RELOAD = "reload"
    RETREAT = "retreat"
    INVESTIGATE = "investigate"
    INVESTIGATE_SOUND = "investigate_sound"
    THROW_GRENADE = "throw_grenade"
    HEAL_ALLY = "heal_ally"


@dataclass(slots=True)
class SoldierDecision:
    kind: SoldierDecisionKind
    score: float
    target: ActorTarget | None = None
    pos: Vec2 | None = None


class SoldierDecisionScorer:
    weights = SoldierDecisionWeights()
    hearing_tuning = SoldierHearingTuning()

    def choose(self, ctx: SoldierContext) -> SoldierDecision:
        decisions: list[SoldierDecision] = []

        if ctx.soldier.weapon.reload_left > 0.0:
            return SoldierDecision(SoldierDecisionKind.RELOAD, 999.0)

        if ctx.soldier.weapon.ammo_in_mag <= 0 and ctx.soldier.weapon.reserve_ammo > 0:
            return SoldierDecision(SoldierDecisionKind.RELOAD, self.weights.low_ammo_reload)

        visible_targets = self._visible_targets(ctx)

        for target in visible_targets:
            dist = ctx.soldier.pos.distance_to(target.pos)

            if dist < self._danger_distance(ctx):
                decisions.append(
                    SoldierDecision(
                        kind=SoldierDecisionKind.RETREAT,
                        score=self.weights.close_threat_retreat + max(0.0, 200.0 - dist),
                        target=target,
                    )
                )

            base = self.weights.zombie_priority if target.kind == "zombie" else self.weights.player_priority
            score = base + max(0.0, self.weights.distance - dist / 10.0)

            if target.health <= 35:
                score += self.weights.wounded_target

            if target.sprinting:
                score += self.weights.sprinting_target

            if ctx.soldier.target_id == target.id:
                score += ctx.soldier.alertness * 18.0

            decisions.append(
                SoldierDecision(
                    kind=SoldierDecisionKind.COMBAT,
                    score=score,
                    target=target,
                )
            )

        special = self._score_special(ctx, visible_targets)
        if special:
            decisions.append(special)

        sound = self._score_sound(ctx)
        if sound:
            decisions.append(sound)

        if ctx.soldier.last_known_pos and ctx.soldier.mode in {"combat", "investigate"}:
            decisions.append(
                SoldierDecision(
                    kind=SoldierDecisionKind.INVESTIGATE,
                    score=self.weights.investigate_last_known + 36.0 + ctx.soldier.alertness * 24.0,
                    pos=ctx.soldier.last_known_pos.copy(),
                )
            )

        decisions.append(SoldierDecision(SoldierDecisionKind.GUARD, self.weights.guard))

        return max(decisions, key=lambda d: d.score)

    def _visible_targets(self, ctx: SoldierContext) -> list[ActorTarget]:
        result: list[ActorTarget] = []

        for target in ctx.targets:
            if not target.alive:
                continue

            if target.floor != ctx.soldier.floor:
                continue

            if target.kind not in {"zombie", "player"}:
                continue

            dist = ctx.soldier.pos.distance_to(target.pos)

            if dist > ctx.spec.sight_range:
                continue

            angle = ctx.soldier.pos.angle_to(target.pos)
            delta = (angle - ctx.soldier.facing + math.pi) % math.tau - math.pi

            if abs(delta) > math.radians(ctx.spec.fov_degrees * 0.5):
                continue

            if ctx.line_blocked(ctx.soldier.pos, target.pos, ctx.soldier.floor):
                continue

            result.append(target)

        return result

    def _danger_distance(self, ctx: SoldierContext) -> float:
        return max(170.0, ctx.spec.radius + 120.0)

    def _score_sound(self, ctx: SoldierContext) -> SoldierDecision | None:
        sound = ctx.can_hear(ctx.soldier)
        if not sound:
            memory = most_dangerous_sound(ctx.soldier.ai_memory, now=ctx.time, floor=ctx.soldier.floor)
            pos = memory_pos(memory) if memory else None
            if not pos or ctx.soldier.mode == "investigate":
                return None
            return SoldierDecision(
                kind=SoldierDecisionKind.INVESTIGATE_SOUND,
                score=self.weights.sound_interest + float(memory.get("danger", 0.0)) * 38.0,
                pos=pos,
            )

        distance = ctx.soldier.pos.distance_to(sound.pos)
        score = self.weights.sound_interest
        score += sound.intensity * 42.0
        score += max(0.0, self.weights.sound_distance - distance / 34.0)

        if sound.kind == "shot":
            score += self.hearing_tuning.shot_bonus
        elif sound.kind == "explosion":
            score += self.hearing_tuning.explosion_bonus
        elif sound.kind == "movement":
            score += self.hearing_tuning.movement_penalty

        if ctx.soldier.mode == "investigate":
            score += self.hearing_tuning.already_investigating_penalty
            if ctx.soldier.last_known_pos:
                score -= 38.0

        if score < self.hearing_tuning.min_reaction_score:
            return None

        return SoldierDecision(
            kind=SoldierDecisionKind.INVESTIGATE_SOUND,
            score=score,
            pos=sound.pos.copy(),
        )

    def _score_special(
        self,
        ctx: SoldierContext,
        visible_targets: list[ActorTarget],
    ) -> SoldierDecision | None:
        return None
