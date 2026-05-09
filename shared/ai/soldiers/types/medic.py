from __future__ import annotations

from shared.ai.context import ActorTarget
from shared.ai.soldiers.base import BaseSoldierAI
from shared.ai.soldiers.configs.medic import MEDIC_DECISION_WEIGHTS, MEDIC_HEARING, MEDIC_TUNING
from shared.ai.soldiers.configs.schema import MedicTuning, SoldierDecisionWeights, SoldierHearingTuning
from shared.ai.soldiers.context import SoldierActionResult, SoldierContext
from shared.ai.soldiers.decisions import SoldierDecision, SoldierDecisionKind, SoldierDecisionScorer
from shared.constants import SOLDIERS


class MedicDecisionScorer(SoldierDecisionScorer):
    weights = SoldierDecisionWeights(**MEDIC_DECISION_WEIGHTS)
    hearing_tuning = SoldierHearingTuning(**MEDIC_HEARING)
    tuning = MedicTuning(**MEDIC_TUNING)

    def _score_special(
        self,
        ctx: SoldierContext,
        visible_targets: list[ActorTarget],
    ) -> SoldierDecision | None:
        if visible_targets or ctx.soldier.support_cooldown > 0.0 or ctx.soldier.weapon.reload_left > 0.0:
            return None

        candidate = self._best_heal_target(ctx)
        if candidate is None:
            return None

        target, ratio = candidate
        distance = ctx.soldier.pos.distance_to(target.pos)
        if target.id != ctx.soldier.id and distance > self.tuning.move_to_heal_range:
            return None

        score = 210.0
        score += max(0.0, (self.tuning.wounded_health_ratio - ratio) * 180.0)
        if ratio <= self.tuning.critical_health_ratio:
            score += 90.0
        if target.id == ctx.soldier.id:
            score += 28.0
        score += max(0.0, 80.0 - distance / 4.0)

        return SoldierDecision(
            kind=SoldierDecisionKind.HEAL_ALLY,
            score=score,
            target=target,
            pos=target.pos.copy(),
        )

    def _best_heal_target(self, ctx: SoldierContext) -> tuple[ActorTarget, float] | None:
        self_spec = SOLDIERS[ctx.soldier.kind]
        candidates: list[tuple[ActorTarget, float]] = []
        self_ratio = ctx.soldier.health / max(1, self_spec.health)
        if self_ratio < self.tuning.wounded_health_ratio:
            candidates.append(
                (
                    ActorTarget(
                        id=ctx.soldier.id,
                        kind="soldier",
                        actor_kind=ctx.soldier.kind,
                        pos=ctx.soldier.pos.copy(),
                        floor=ctx.soldier.floor,
                        alive=ctx.soldier.alive,
                        radius=ctx.spec.radius,
                        health=ctx.soldier.health,
                        faction=ctx.soldier.faction,
                    ),
                    self_ratio,
                )
            )
        for mate in ctx.squad_mates:
            spec = SOLDIERS.get(mate.actor_kind or "rifleman")
            if not spec:
                continue
            ratio = mate.health / max(1, spec.health)
            if ratio < self.tuning.wounded_health_ratio:
                candidates.append((mate, ratio))
        if not candidates:
            return None
        return min(candidates, key=lambda item: (item[1], ctx.soldier.pos.distance_to(item[0].pos)))


class MedicSoldierAI(BaseSoldierAI):
    kind = "medic"
    scorer = MedicDecisionScorer()
    tuning = MedicTuning(**MEDIC_TUNING)

    def _try_heal(
        self,
        ctx: SoldierContext,
        target: ActorTarget,
        result: SoldierActionResult,
    ) -> None:
        soldier = ctx.soldier
        if soldier.support_cooldown > 0.0:
            return
        if target.id != soldier.id and soldier.pos.distance_to(target.pos) > self.tuning.heal_range:
            soldier.sprinting = True
            ctx.move_toward(soldier, target.pos, ctx.dt, ctx.rng)
            return
        amount = self.tuning.self_heal_amount if target.id == soldier.id else self.tuning.heal_amount
        result.soldier_heals.append((target.id, amount))
        soldier.support_cooldown = self.tuning.cooldown
        soldier.alertness = max(0.0, soldier.alertness - 0.08)
