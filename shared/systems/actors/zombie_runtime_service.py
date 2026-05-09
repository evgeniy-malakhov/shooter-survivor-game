from __future__ import annotations

import math
import random
from dataclasses import dataclass, fields
from typing import TYPE_CHECKING

from shared.ai.context import ActorTarget, SoundEvent, ZombieContext
from shared.constants import PLAYER_RADIUS, SEARCH_DURATION, SPRINT_NOISE, ZOMBIES, SOLDIERS, MAP_WIDTH, MAP_HEIGHT
from shared.factions import hostile
from shared.models import (
    PlayerState,
    PoisonProjectileState,
    SoldierState,
    Vec2,
    ZombieState,
)
from shared.systems.events.game_events import SpawnProjectileEvent, SpawnPoisonEvent, DamagePlayerEvent, DamageSoldierEvent
from shared.systems.actors.decision.actor_decision_result import ActorDecisionOutput
if TYPE_CHECKING:
    from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


@dataclass(slots=True)
class ZombieRuntimeResult:
    zombie: ZombieState
    player_hits: list[tuple[str, int]]
    soldier_hits: list[tuple[str, int]]
    poison_spits: list[object]


class ZombieRuntimeService:
    def __init__(
        self,
        *,
        state: WorldState,
        rng: random.Random,
        zombie_ai_registry,
        difficulty,
        pathfinder,
    ) -> None:
        self._state = state
        self._rng = rng
        self._zombie_ai_registry = zombie_ai_registry
        self._difficulty = difficulty
        self._pathfinder = pathfinder

        self._zombie_rngs: dict[str, random.Random] = {}
        self._path_cache: dict[str, tuple[Vec2, list[Vec2]]] = {}

    @property
    def registry(self):
        return self._zombie_ai_registry

    @property
    def state_time(self) -> float:
        return self._state.time

    def living_players(self) -> tuple[PlayerState, ...]:
        return tuple(player for player in self._state.players.values() if player.alive)

    def zombie_spec(self, kind: str):
        return ZOMBIES[kind]

    def targets_near_zombie(self, zombie: ZombieState, ctx) -> tuple[ActorTarget, ...]:
        spec = ZOMBIES[zombie.kind]

        query_radius = max(
            spec.sight_range,
            spec.hearing_range * max(0.1, spec.sensitivity),
            1200.0,
        )

        targets: list[ActorTarget] = []

        for player in ctx.spatial.nearby_players(
            zombie.pos,
            query_radius,
            zombie.floor,
        ):
            if not player.alive:
                continue
            if not hostile(zombie.faction, player.faction):
                continue

            targets.append(
                ActorTarget(
                    id=player.id,
                    kind="player",
                    pos=player.pos.copy(),
                    floor=player.floor,
                    alive=True,
                    radius=PLAYER_RADIUS,
                    actor_kind="player",
                    health=player.health,
                    sprinting=player.sprinting,
                    inside_building=player.inside_building,
                    faction=player.faction,
                )
            )

        for soldier in ctx.spatial.nearby_soldiers(
            zombie.pos,
            query_radius,
            zombie.floor,
        ):
            if not soldier.alive:
                continue
            if not hostile(zombie.faction, soldier.faction):
                continue

            soldier_spec = SOLDIERS[soldier.kind]

            targets.append(
                ActorTarget(
                    id=soldier.id,
                    kind="soldier",
                    pos=soldier.pos.copy(),
                    floor=soldier.floor,
                    alive=True,
                    radius=soldier_spec.radius,
                    actor_kind=soldier.kind,
                    health=soldier.health,
                    sprinting=False,
                    inside_building=None,
                    faction=soldier.faction,
                )
            )

        return tuple(targets)

    def can_see(self, zombie: ZombieState, target: ActorTarget, ctx) -> bool:
        if zombie.floor != target.floor:
            return False

        if target.inside_building and zombie.inside_building != target.inside_building:
            return False

        spec = ZOMBIES[zombie.kind]

        distance = zombie.pos.distance_to(target.pos)

        if distance > spec.sight_range:
            return False

        angle_to_target = zombie.pos.angle_to(target.pos)
        angle_delta = (angle_to_target - zombie.facing + math.pi) % math.tau - math.pi

        if abs(angle_delta) > math.radians(spec.fov_degrees * 0.5):
            return False

        return not ctx.geometry.line_blocked(zombie.pos, target.pos, zombie.floor)

    def can_hear(self, zombie: ZombieState, ctx) -> SoundEvent | None:
        spec = ZOMBIES[zombie.kind]

        max_hearing_radius = spec.hearing_range * max(0.1, spec.sensitivity) + 1800.0

        best: SoundEvent | None = None
        best_distance = float("inf")

        for sound in ctx.spatial.nearby_sounds(
            zombie.pos,
            max_hearing_radius,
            zombie.floor,
        ):
            distance = zombie.pos.distance_to(sound.pos)

            hearing_radius = sound.radius * spec.sensitivity

            if distance > hearing_radius:
                continue

            if ctx.geometry.line_blocked(
                zombie.pos,
                sound.pos,
                zombie.floor,
                sound=True,
            ):
                continue

            if distance < best_distance:
                best = sound
                best_distance = distance

        return best

    def pick_search_waypoint(
            self,
            zombie: ZombieState,
            base: Vec2,
            rng: random.Random,
            ctx,
    ) -> Vec2 | None:
        spec = ZOMBIES[zombie.kind]

        for _ in range(20):
            angle = rng.uniform(0.0, math.tau)
            distance = rng.uniform(80.0, 240.0)

            pos = Vec2(
                base.x + math.cos(angle) * distance,
                base.y + math.sin(angle) * distance,
            )
            pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)

            if not ctx.geometry.blocked_at(pos, spec.radius, zombie.floor):
                return pos

        return None

    def update_local(self, ctx, dt: float) -> None:
        zombies = list(self._state.zombies.values())

        if not zombies:
            return

        active_ids = {zombie.id for zombie in zombies}

        for zombie_id in list(self._zombie_rngs):
            if zombie_id not in active_ids:
                self._zombie_rngs.pop(zombie_id, None)

        for zombie_id in list(self._path_cache):
            if zombie_id not in active_ids:
                self._path_cache.pop(zombie_id, None)

        inputs = ctx.actor_snapshots.build_zombie_inputs(
            zombies,
            ctx=ctx,
            dt=dt,
            rng=self._rng,
        )

        for output in ctx.actor_decisions.execute(inputs, ctx):
            self.apply_decision_output(output, ctx)

    def zombie_rng(self, zombie_id: str) -> random.Random:
        rng = self._zombie_rngs.get(zombie_id)

        if rng is None:
            rng = random.Random(self._rng.randrange(1, 2**63))
            self._zombie_rngs[zombie_id] = rng

        return rng

    def advance_actor(
        self,
        zombie: ZombieState,
        dt: float,
        living_players: tuple[PlayerState, ...],
        rng: random.Random,
        ctx,
    ) -> ZombieRuntimeResult:
        if not living_players and zombie.mode != "patrol":
            zombie.mode = "patrol"
            zombie.target_player_id = None
            zombie.last_known_pos = None
            zombie.waypoint = None
            zombie.alertness = 0.0

        ai = self._zombie_ai_registry.get(zombie.kind)

        if not ai:
            ai = self._zombie_ai_registry["walker"]

        zombie_ctx = self.make_context(
            zombie=zombie,
            dt=dt,
            players=living_players,
            rng=rng,
            ctx=ctx,
        )

        ai_result = ai.update(zombie_ctx)

        zombie.inside_building = ctx.buildings.point_building(zombie.pos)

        return ZombieRuntimeResult(
            zombie=zombie,
            player_hits=ai_result.player_hits,
            soldier_hits=ai_result.soldier_hits,
            poison_spits=ai_result.poison_spits,
        )

    def apply_result(self, result: ZombieRuntimeResult, ctx: "WorldContext") -> None:
        for player_id, damage in result.player_hits:
            player = self._state.players.get(player_id)

            if player and player.alive:
                ctx.events.emit(
                    DamagePlayerEvent(
                        player_id=player_id,
                        damage=damage,
                    )
                )

        for soldier_id, damage in result.soldier_hits:
            soldier = self._state.soldiers.get(soldier_id)

            if soldier and soldier.alive:
                ctx.events.emit(
                    DamageSoldierEvent(
                        soldier_id=soldier_id,
                        damage=damage,
                        attacker_id=result.zombie.id,
                    )
                )

        for spit in result.poison_spits:
            if isinstance(spit, dict):
                ctx.events.emit(
                    SpawnPoisonEvent(
                        owner_id=spit["owner_id"],
                        pos=spit["pos"],
                        velocity=spit["velocity"],
                        target=spit["target"],
                        floor=spit["floor"],
                    )
                )
                continue

            ctx.events.emit(
                SpawnPoisonEvent(
                    owner_id=spit.owner_id,
                    pos=spit.pos,
                    velocity=spit.velocity,
                    target=spit.target,
                    floor=spit.floor,
                )
            )

    def apply_decision_output(self, output: ActorDecisionOutput, ctx: "WorldContext") -> None:
        zombie = self._state.zombies.get(output.actor_id)

        if not zombie or output.actor_state is None:
            return

        updated = ZombieState.from_dict(output.actor_state)
        self._copy_state(zombie, updated)

        self.apply_result(
            ZombieRuntimeResult(
                zombie=zombie,
                player_hits=output.player_hits,
                soldier_hits=output.soldier_hits,
                poison_spits=output.poison_spits,
            ),
            ctx,
        )

    def _copy_state(self, target: ZombieState, source: ZombieState) -> None:
        for field in fields(ZombieState):
            setattr(target, field.name, getattr(source, field.name))

    def make_context(
        self,
        *,
        zombie: ZombieState,
        dt: float,
        players: tuple[PlayerState, ...],
        rng: random.Random,
        ctx: "WorldContext",
    ) -> ZombieContext:
        return ZombieContext(
            zombie=zombie,
            players=players,
            targets=self.targets_near_zombie(zombie, ctx),
            dt=dt,
            time=self._state.time,
            rng=rng,
            difficulty=self._difficulty,

            can_see=lambda actor, target: self.can_see(actor, target, ctx),
            can_hear=lambda actor: self.can_hear(actor, ctx),

            line_blocked=lambda a, b, floor: ctx.geometry.line_blocked(a, b, floor),

            move_toward=lambda actor, target, delta_time, sprint, local_rng: self.move_toward(
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
                blocked_at=lambda p, r: ctx.geometry.blocked_at(p, r, zombie.floor),
            ),

            pick_search_waypoint=lambda actor, base, local_rng: self.pick_search_waypoint(
                actor,
                base,
                local_rng,
                ctx,
            ),

            building_entry_target=ctx.buildings.building_entry_target,

            path_next_point=lambda actor, target: self.path_next_point(
                actor,
                target,
                ctx,
            ),
        )

    def find_player(
        self,
        players: tuple[PlayerState, ...],
        player_id: str | None,
    ) -> PlayerState | None:
        if not player_id:
            return None

        for player in players:
            if player.id == player_id:
                return player

        return None

    def path_next_point(
        self,
        zombie: ZombieState,
        target: Vec2,
        ctx: "WorldContext",
    ) -> Vec2:
        if not ctx.geometry.line_blocked(zombie.pos, target, zombie.floor):
            self._path_cache.pop(zombie.id, None)
            return target

        cached = self._path_cache.get(zombie.id)

        if cached:
            cached_target, path = cached

            if cached_target.distance_to(target) < 96 and path:
                while path and zombie.pos.distance_to(path[0]) < 48:
                    path.pop(0)

                if path:
                    return path[0]

        path = self._pathfinder.find_path(
            start=zombie.pos,
            goal=target,
            walls=ctx.geometry.closed_walls(zombie.floor),
            map_width=MAP_WIDTH,
            map_height=MAP_HEIGHT,
        )

        if not path:
            return target

        self._path_cache[zombie.id] = (target.copy(), path)

        return path[0]

    def move_toward(
        self,
        zombie: ZombieState,
        target: Vec2,
        dt: float,
        sprint: bool,
        rng: random.Random,
        ctx: "WorldContext",
    ) -> None:
        spec = ZOMBIES[zombie.kind]
        direction = Vec2(target.x - zombie.pos.x, target.y - zombie.pos.y)

        if direction.length() <= 0.01:
            return

        zombie.facing = math.atan2(direction.y, direction.x)

        speed = (
            spec.speed
            * self._difficulty.zombie_speed_multiplier
            * (1.22 if sprint else 1.0)
        )

        step = direction.normalized().scaled(speed * dt)
        old_pos = zombie.pos.copy()

        ctx.movement.move_circle(
            zombie.pos,
            step,
            spec.radius,
            zombie.floor,
        )

        if zombie.pos.distance_to(old_pos) < 0.5:
            door = ctx.buildings.nearest_door(zombie.pos, 160, zombie.floor)

            if door and door.open:
                zombie.waypoint = door.rect.center
                return

            angle = zombie.facing + rng.choice([-1.0, 1.0]) * math.pi * 0.5
            sidestep = Vec2(
                math.cos(angle),
                math.sin(angle),
            ).scaled(spec.radius * 1.8)

            ctx.movement.move_circle(
                zombie.pos,
                sidestep,
                spec.radius,
                zombie.floor,
            )

        zombie.pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)

    def leaper_move_toward(
        self,
        zombie: ZombieState,
        target: Vec2,
        dt: float,
        rng: random.Random,
        ctx: "WorldContext",
    ) -> None:
        spec = ZOMBIES[zombie.kind]
        to_target = Vec2(target.x - zombie.pos.x, target.y - zombie.pos.y)
        distance = to_target.length()

        if distance <= 0.01:
            return

        forward = to_target.normalized()

        if zombie.sidestep_timer <= 0.0:
            zombie.sidestep_timer = rng.uniform(0.55, 1.05)
            zombie.sidestep_bias = rng.choice([-1.0, 1.0]) * rng.uniform(0.42, 0.78)

        zombie.strafe_phase += dt * (
            1.75 + min(1.0, distance / 620.0) * 0.55
        )

        wave = (
            math.sin(zombie.strafe_phase) * 0.55
            + math.sin(zombie.strafe_phase * 0.43 + zombie.sidestep_bias) * 0.25
        )

        lateral_strength = max(
            -0.74,
            min(0.74, wave + zombie.sidestep_bias * 0.32),
        )

        if distance < 150:
            lateral_strength *= distance / 150.0

        perpendicular = Vec2(-forward.y, forward.x)

        blended = Vec2(
            forward.x + perpendicular.x * lateral_strength,
            forward.y + perpendicular.y * lateral_strength,
        ).normalized()

        zombie.facing = math.atan2(forward.y, forward.x)

        speed = spec.speed * self._difficulty.zombie_speed_multiplier * 1.16

        old_pos = zombie.pos.copy()

        ctx.movement.move_circle(
            zombie.pos,
            blended.scaled(speed * dt),
            spec.radius,
            zombie.floor,
        )

        if zombie.pos.distance_to(old_pos) < 0.5:
            zombie.sidestep_bias *= -1.0
            self.move_toward(
                zombie,
                target,
                dt,
                sprint=True,
                rng=rng,
                ctx=ctx,
            )

        zombie.pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
