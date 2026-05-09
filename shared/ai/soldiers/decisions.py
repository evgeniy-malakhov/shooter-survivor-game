from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from shared.ai.context import ActorTarget
from shared.ai.memory import memory_pos, most_dangerous_sound, most_relevant_threat, remember_seen_enemy
from shared.ai.squads import SquadMode, SquadRole
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
    SQUAD_MOVE = "squad_move"
    HOLD_POSITION = "hold_position"


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
            remember_seen_enemy(
                ctx.soldier.ai_memory,
                actor_id=target.id,
                actor_kind=target.actor_kind or target.kind,
                pos=target.pos,
                floor=target.floor,
                now=ctx.time,
                danger=0.95 if target.kind == "player" else 0.72,
            )

            if self._role(ctx) == SquadRole.MEDIC and dist < 920.0:
                decisions.append(
                    SoldierDecision(
                        kind=SoldierDecisionKind.RETREAT,
                        score=285.0 + max(0.0, 260.0 - dist / 2.5),
                        target=target,
                    )
                )

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

        squad = self._score_squad_intent(ctx, visible_targets)
        if squad:
            decisions.append(squad)

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
                memory = most_relevant_threat(
                    list(ctx.squad_memory),
                    now=ctx.time,
                    floor=ctx.soldier.floor,
                    kinds={"last_heard_sound", "sound"},
                )
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

    def _score_squad_intent(
        self,
        ctx: SoldierContext,
        visible_targets: list[ActorTarget],
    ) -> SoldierDecision | None:
        intent = ctx.squad_intent
        if not intent or (intent.expires_at and intent.expires_at <= ctx.time):
            return None

        role = self._role(ctx)
        target_pos = intent.target_pos.copy() if intent.target_pos else None
        danger = max(0.0, intent.danger_score)

        if intent.mode == SquadMode.ENGAGE_TARGET:
            target = self._target_for_intent(intent.target_actor_id, visible_targets)
            if target:
                return SoldierDecision(
                    kind=SoldierDecisionKind.RETREAT if role == SquadRole.MEDIC else SoldierDecisionKind.COMBAT,
                    score=245.0 + danger * 80.0 + (40.0 if ctx.soldier.target_id == target.id else 0.0),
                    target=target,
                )
            if not target_pos:
                return None
            if role == SquadRole.MEDIC:
                support_pos = self._medic_support_position(ctx, target_pos)
                if ctx.soldier.pos.distance_to(support_pos) > 80.0:
                    return SoldierDecision(
                        kind=SoldierDecisionKind.SQUAD_MOVE,
                        score=170.0 + danger * 35.0,
                        pos=support_pos,
                    )
                return SoldierDecision(SoldierDecisionKind.HOLD_POSITION, 150.0 + danger * 20.0, pos=support_pos)
            return SoldierDecision(
                kind=SoldierDecisionKind.INVESTIGATE,
                score=178.0 + danger * 72.0 + ctx.soldier.alertness * 18.0,
                pos=target_pos,
            )

        if intent.mode == SquadMode.INVESTIGATE_SOUND and target_pos:
            score = 132.0 + danger * 80.0
            if ctx.soldier.mode == "investigate":
                score -= 22.0
            return SoldierDecision(SoldierDecisionKind.INVESTIGATE_SOUND, score, pos=target_pos)

        if intent.mode in {SquadMode.FALLBACK, SquadMode.REGROUP, SquadMode.EVACUATE_WOUNDED} and target_pos:
            if role == SquadRole.MEDIC and intent.mode == SquadMode.EVACUATE_WOUNDED:
                if visible_targets:
                    target = self._target_for_intent(None, visible_targets)
                    if target:
                        return SoldierDecision(
                            kind=SoldierDecisionKind.RETREAT,
                            score=285.0 + danger * 70.0,
                            target=target,
                        )
                target = self._mate_for_intent(ctx, intent.target_actor_id)
                if target:
                    return SoldierDecision(
                        kind=SoldierDecisionKind.HEAL_ALLY,
                        score=255.0 + danger * 80.0,
                        target=target,
                        pos=target.pos.copy(),
                    )
            return SoldierDecision(
                kind=SoldierDecisionKind.SQUAD_MOVE,
                score=165.0 + danger * 70.0,
                pos=target_pos,
            )

        if intent.mode == SquadMode.HOLD_POSITION:
            return SoldierDecision(SoldierDecisionKind.HOLD_POSITION, 95.0 + danger * 30.0, pos=target_pos)

        return None

    def _target_for_intent(self, target_actor_id: str | None, visible_targets: list[ActorTarget]) -> ActorTarget | None:
        if target_actor_id:
            for target in visible_targets:
                if target.id == target_actor_id:
                    return target
        return visible_targets[0] if visible_targets else None

    def _mate_for_intent(self, ctx: SoldierContext, target_actor_id: str | None) -> ActorTarget | None:
        if target_actor_id == ctx.soldier.id:
            return ActorTarget(
                id=ctx.soldier.id,
                kind="soldier",
                actor_kind=ctx.soldier.kind,
                pos=ctx.soldier.pos.copy(),
                floor=ctx.soldier.floor,
                alive=ctx.soldier.alive,
                radius=ctx.spec.radius,
                health=ctx.soldier.health,
                faction=ctx.soldier.faction,
            )
        for mate in ctx.squad_mates:
            if not target_actor_id or mate.id == target_actor_id:
                return mate
        return None

    def _medic_support_position(self, ctx: SoldierContext, frontline_pos: Vec2) -> Vec2:
        offset = Vec2(ctx.soldier.pos.x - frontline_pos.x, ctx.soldier.pos.y - frontline_pos.y)
        if offset.length() <= 0.01:
            offset = Vec2(math.cos(ctx.soldier.facing + math.pi), math.sin(ctx.soldier.facing + math.pi))
        direction = offset.normalized()
        desired_distance = 860.0
        return Vec2(
            frontline_pos.x + direction.x * desired_distance,
            frontline_pos.y + direction.y * desired_distance,
        )

    def _role(self, ctx: SoldierContext) -> SquadRole:
        try:
            return SquadRole(ctx.squad_role)
        except ValueError:
            return SquadRole.RIFLEMAN
