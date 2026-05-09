from __future__ import annotations

import math
import random

from shared.ai.context import SoundEvent
from shared.ai.squads import SquadIntent
from shared.ai.soldiers.context import SoldierContext
from shared.ai.soldiers.configs.heavy_grenadier import HEAVY_GRENADIER_HEARING
from shared.ai.soldiers.configs.medic import MEDIC_HEARING
from shared.ai.soldiers.configs.rifleman import RIFLEMAN_HEARING
from shared.ai.soldiers.configs.schema import SoldierHearingTuning
from shared.constants import MAP_HEIGHT, MAP_WIDTH, SOLDIERS, WEAPONS
from shared.models import SoldierState, Vec2
from shared.systems.actors.decision.actor_decision_dto import ActorDecisionInput
from shared.systems.actors.decision.actor_decision_result import ActorDecisionOutput


class SoldierDecisionPolicy:
    def decide(self, decision_input: ActorDecisionInput, ctx) -> ActorDecisionOutput:
        if ctx is None:
            return ActorDecisionOutput.no_op(
                decision_input.actor_type,
                decision_input.actor_id,
                decision_input.actor_kind,
            )

        soldier = SoldierState.from_dict(decision_input.actor_state)
        rng = random.Random(decision_input.rng_seed)
        spec = SOLDIERS[soldier.kind]
        weapon = WEAPONS[spec.weapon_key]

        ai = ctx.soldier_runtime.registry.get(soldier.kind)
        if not ai:
            return ActorDecisionOutput.no_op(
                decision_input.actor_type,
                decision_input.actor_id,
                decision_input.actor_kind,
            )

        soldier_ctx = SoldierContext(
            soldier=soldier,
            targets=decision_input.targets,
            dt=decision_input.dt,
            time=decision_input.time,
            rng=rng,
            spec=spec,
            weapon=weapon,
            sounds=decision_input.nearby_sounds,
            squad_mates=decision_input.nearby_soldiers,
            squad_intent=SquadIntent.from_dict(decision_input.squad_intent),
            squad_role=decision_input.squad_role,
            squad_memory=decision_input.squad_memory,
            line_blocked=lambda start, end, floor: ctx.geometry.line_blocked(start, end, floor),
            can_hear=lambda actor: self._can_hear(actor, decision_input, ctx),
            move_toward=lambda actor, target, delta_time, local_rng=None: self._move_toward(
                actor,
                target,
                delta_time,
                ctx,
            ),
            random_guard_pos=lambda actor, local_rng=None: self._random_guard_pos(
                actor,
                ctx,
                rng,
            ),
            projectile_life=ctx.weapons.projectile_life,
        )

        result = ai.update(soldier_ctx)

        return ActorDecisionOutput(
            actor_type=decision_input.actor_type,
            actor_id=decision_input.actor_id,
            actor_kind=decision_input.actor_kind,
            actor_state=soldier.to_dict(),
            projectiles=list(result.projectiles),
            grenades=list(result.grenades),
            sounds=list(result.sounds),
            soldier_heals=list(result.soldier_heals),
        )

    def _can_hear(
        self,
        soldier: SoldierState,
        decision_input: ActorDecisionInput,
        ctx,
    ) -> SoundEvent | None:
        tuning = self._hearing_tuning(soldier.kind)
        best: SoundEvent | None = None
        best_distance = float("inf")

        for sound in decision_input.nearby_sounds:
            if sound.floor != soldier.floor:
                continue

            distance = soldier.pos.distance_to(sound.pos)
            if distance > sound.radius * tuning.hearing_multiplier:
                continue

            if ctx.geometry.line_blocked(soldier.pos, sound.pos, soldier.floor, sound=True):
                continue

            if distance < best_distance:
                best = sound
                best_distance = distance

        return best

    def _hearing_tuning(self, kind: str) -> SoldierHearingTuning:
        if kind == "heavy_grenadier":
            return SoldierHearingTuning(**HEAVY_GRENADIER_HEARING)
        if kind == "medic":
            return SoldierHearingTuning(**MEDIC_HEARING)
        return SoldierHearingTuning(**RIFLEMAN_HEARING)

    def _move_toward(
        self,
        soldier: SoldierState,
        target: Vec2,
        dt: float,
        ctx,
    ) -> None:
        spec = SOLDIERS[soldier.kind]
        direction = Vec2(target.x - soldier.pos.x, target.y - soldier.pos.y)

        if direction.length() <= 0.01:
            return

        soldier.facing = math.atan2(direction.y, direction.x)
        step = direction.normalized().scaled(spec.speed * dt)
        old_pos = soldier.pos.copy()

        ctx.movement.move_circle(
            soldier.pos,
            step,
            spec.radius,
            soldier.floor,
        )
        if soldier.pos.distance_to(old_pos) < 0.5:
            door = ctx.buildings.nearest_door(soldier.pos, 140.0, soldier.floor)
            if door and not door.open:
                door.open = True
                ctx.geometry.mark_dirty()
                soldier.waypoint = door.rect.center
                return
        soldier.pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)

    def _random_guard_pos(
        self,
        soldier: SoldierState,
        ctx,
        rng: random.Random,
    ) -> Vec2:
        base = soldier.guard_point or soldier.pos

        for _ in range(30):
            angle = rng.uniform(0.0, math.tau)
            distance = rng.uniform(80.0, 220.0)
            pos = Vec2(
                base.x + math.cos(angle) * distance,
                base.y + math.sin(angle) * distance,
            )
            pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)

            if not ctx.geometry.blocked_at(
                pos,
                SOLDIERS[soldier.kind].radius,
                soldier.floor,
            ):
                return pos

        return base.copy()
