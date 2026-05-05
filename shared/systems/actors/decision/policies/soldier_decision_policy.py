from __future__ import annotations

import math
import random

from shared.ai.soldiers.context import SoldierContext
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
            line_blocked=lambda start, end, floor: ctx.geometry.line_blocked(start, end, floor),
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
            sounds=list(result.sounds),
        )

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

        ctx.movement.move_circle(
            soldier.pos,
            step,
            spec.radius,
            soldier.floor,
        )
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
