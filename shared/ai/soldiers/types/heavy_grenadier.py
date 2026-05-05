from __future__ import annotations

import math

from shared.ai.context import ActorTarget
from shared.ai.soldiers.base import BaseSoldierAI
from shared.ai.soldiers.configs.heavy_grenadier import (
    HEAVY_GRENADIER_DECISION_WEIGHTS,
    HEAVY_GRENADIER_HEARING,
    HEAVY_GRENADIER_TUNING,
)
from shared.ai.soldiers.configs.schema import GrenadierTuning, SoldierDecisionWeights, SoldierHearingTuning
from shared.ai.soldiers.context import SoldierActionResult, SoldierContext
from shared.ai.soldiers.decisions import SoldierDecision, SoldierDecisionKind, SoldierDecisionScorer
from shared.explosives import DEFAULT_GRENADE, GRENADE_SPECS
from shared.models import Vec2


class HeavyGrenadierDecisionScorer(SoldierDecisionScorer):
    weights = SoldierDecisionWeights(**HEAVY_GRENADIER_DECISION_WEIGHTS)
    hearing_tuning = SoldierHearingTuning(**HEAVY_GRENADIER_HEARING)
    tuning = GrenadierTuning(**HEAVY_GRENADIER_TUNING)

    def _score_special(
        self,
        ctx: SoldierContext,
        visible_targets: list[ActorTarget],
    ) -> SoldierDecision | None:
        if ctx.soldier.grenade_cooldown > 0.0:
            return None

        best: SoldierDecision | None = None

        for target in visible_targets:
            if target.kind not in {"zombie", "player"}:
                continue

            distance = ctx.soldier.pos.distance_to(target.pos)
            if distance < self.tuning.min_throw_distance or distance > self.tuning.max_throw_distance:
                continue

            if ctx.line_blocked(ctx.soldier.pos, target.pos, ctx.soldier.floor):
                continue

            score = self.weights.grenade
            score += max(0.0, 110.0 - abs(distance - self.tuning.best_throw_distance) / 3.8)

            if target.kind == "zombie":
                score += 26.0

            if target.health <= 45:
                score += 14.0

            cluster = sum(
                1
                for other in visible_targets
                if other.floor == target.floor and other.pos.distance_to(target.pos) <= 170.0
            )
            if cluster >= 2:
                score += self.tuning.minimum_target_cluster_bonus * min(3, cluster - 1)

            candidate = SoldierDecision(
                kind=SoldierDecisionKind.THROW_GRENADE,
                score=score,
                target=target,
                pos=target.pos.copy(),
            )

            if best is None or candidate.score > best.score:
                best = candidate

        return best


class HeavyGrenadierSoldierAI(BaseSoldierAI):
    kind = "heavy_grenadier"
    scorer = HeavyGrenadierDecisionScorer()
    tuning = GrenadierTuning(**HEAVY_GRENADIER_TUNING)

    def _combat(
        self,
        ctx: SoldierContext,
        target: ActorTarget,
        result: SoldierActionResult,
    ) -> None:
        soldier = ctx.soldier
        distance = soldier.pos.distance_to(target.pos)
        soldier.facing = soldier.pos.angle_to(target.pos)

        if distance < self.tuning.min_throw_distance * 0.72:
            self._retreat_from(ctx, target)
            self._try_shoot(ctx, target, result)
            return

        self._try_special(ctx, target, result)

        if distance > ctx.spec.fire_range:
            soldier.sprinting = True
            ctx.move_toward(soldier, target.pos, ctx.dt, ctx.rng)
            return

        self._try_shoot(ctx, target, result)

    def _try_special(
        self,
        ctx: SoldierContext,
        target: ActorTarget,
        result: SoldierActionResult,
    ) -> None:
        soldier = ctx.soldier

        if soldier.grenade_cooldown > 0.0:
            return

        distance = soldier.pos.distance_to(target.pos)
        if distance < self.tuning.min_throw_distance or distance > self.tuning.max_throw_distance:
            return

        if ctx.line_blocked(soldier.pos, target.pos, soldier.floor):
            return

        grenade_spec = GRENADE_SPECS.get(self.tuning.grenade_kind, DEFAULT_GRENADE)
        direction = Vec2(target.pos.x - soldier.pos.x, target.pos.y - soldier.pos.y)
        if direction.length() <= 0.01:
            return

        angle = math.atan2(direction.y, direction.x)
        speed = max(grenade_spec.throw_distance, distance * self.tuning.throw_speed_multiplier)
        start = Vec2(
            soldier.pos.x + math.cos(angle) * (ctx.spec.radius + 14.0),
            soldier.pos.y + math.sin(angle) * (ctx.spec.radius + 14.0),
        )
        velocity = Vec2(math.cos(angle) * speed, math.sin(angle) * speed)

        result.grenades.append(
            {
                "owner_id": soldier.id,
                "kind": grenade_spec.key,
                "pos": start,
                "velocity": velocity,
                "timer": grenade_spec.timer,
                "floor": soldier.floor,
            }
        )
        result.sounds.append(
            {
                "pos": soldier.pos.copy(),
                "floor": soldier.floor,
                "radius": grenade_spec.blast_radius * 2.8,
                "kind": "movement",
                "intensity": 0.58,
                "source_player_id": soldier.id,
            }
        )

        soldier.grenade_cooldown = ctx.rng.uniform(
            self.tuning.cooldown_min,
            self.tuning.cooldown_max,
        )
