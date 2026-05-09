from __future__ import annotations

import random

from shared.ai.context import SoundEvent, ZombieContext
from shared.ai.zombie_ecology import ZombieInterest
from shared.constants import ZOMBIES
from shared.models import PlayerState, Vec2, ZombieState
from shared.systems.actors.decision.actor_decision_dto import ActorDecisionInput
from shared.systems.actors.decision.actor_decision_result import ActorDecisionOutput


class ZombieDecisionPolicy:
    def decide(self, decision_input: ActorDecisionInput, ctx) -> ActorDecisionOutput:
        if ctx is None:
            return ActorDecisionOutput.no_op(
                decision_input.actor_type,
                decision_input.actor_id,
                decision_input.actor_kind,
            )

        zombie = ZombieState.from_dict(decision_input.actor_state)
        rng = random.Random(decision_input.rng_seed)

        if decision_input.metadata.get("living_players", 0) <= 0 and zombie.mode != "patrol":
            zombie.mode = "patrol"
            zombie.target_player_id = None
            zombie.last_known_pos = None
            zombie.waypoint = None
            zombie.alertness = 0.0

        ai = ctx.zombie_runtime.registry.get(zombie.kind) or ctx.zombie_runtime.registry["walker"]

        zombie_ctx = ZombieContext(
            zombie=zombie,
            players=self._nearby_players(decision_input),
            targets=decision_input.targets,
            dt=decision_input.dt,
            time=decision_input.time,
            rng=rng,
            difficulty=ctx.difficulty,
            can_see=lambda actor, target: ctx.zombie_runtime.can_see(actor, target, ctx),
            can_hear=lambda actor: self._can_hear(actor, decision_input, ctx),
            line_blocked=lambda start, end, floor: ctx.geometry.line_blocked(start, end, floor),
            move_toward=lambda actor, target, delta_time, sprint, local_rng: ctx.zombie_runtime.move_toward(
                actor,
                target,
                delta_time,
                sprint,
                local_rng,
                ctx,
            ),
            random_patrol_pos=lambda local_rng: ctx.buildings.random_open_pos(
                centered=False,
                rng=local_rng,
                blocked_at=lambda pos, radius: ctx.geometry.blocked_at(pos, radius, zombie.floor),
            ),
            pick_search_waypoint=lambda actor, base, local_rng: ctx.zombie_runtime.pick_search_waypoint(
                actor,
                base,
                local_rng,
                ctx,
            ),
            building_entry_target=ctx.buildings.building_entry_target,
            path_next_point=lambda actor, target: ctx.zombie_runtime.path_next_point(actor, target, ctx),
            ecology_interest=ZombieInterest.from_dict(
                decision_input.metadata.get("ecology_interest")
                if isinstance(decision_input.metadata.get("ecology_interest"), dict)
                else None
            ),
            horde_target=Vec2.from_dict(decision_input.metadata["horde_target"])
            if isinstance(decision_input.metadata.get("horde_target"), dict)
            else None,
        )

        ai_result = ai.update(zombie_ctx)
        zombie.inside_building = ctx.buildings.point_building(zombie.pos)

        return ActorDecisionOutput(
            actor_type=decision_input.actor_type,
            actor_id=decision_input.actor_id,
            actor_kind=decision_input.actor_kind,
            actor_state=zombie.to_dict(),
            player_hits=list(ai_result.player_hits),
            soldier_hits=list(ai_result.soldier_hits),
            poison_spits=list(ai_result.poison_spits),
        )

    def _can_hear(
        self,
        zombie: ZombieState,
        decision_input: ActorDecisionInput,
        ctx,
    ) -> SoundEvent | None:
        spec = ZOMBIES[zombie.kind]
        best: SoundEvent | None = None
        best_distance = float("inf")

        for sound in decision_input.nearby_sounds:
            if sound.floor != zombie.floor:
                continue

            distance = zombie.pos.distance_to(sound.pos)
            hearing_radius = sound.radius * spec.sensitivity

            if distance > hearing_radius:
                continue

            if ctx.geometry.line_blocked(zombie.pos, sound.pos, zombie.floor, sound=True):
                continue

            if distance < best_distance:
                best = sound
                best_distance = distance

        return best

    def _nearby_players(self, decision_input: ActorDecisionInput) -> tuple[PlayerState, ...]:
        return tuple(
            PlayerState(
                id=target.id,
                name=target.id,
                pos=Vec2(target.pos.x, target.pos.y),
                health=target.health,
                floor=target.floor,
                alive=target.alive,
                sprinting=target.sprinting,
                inside_building=target.inside_building,
            )
            for target in decision_input.nearby_players
        )
