from __future__ import annotations

import math
import random
from dataclasses import fields
from typing import TYPE_CHECKING

from shared.ai.context import ActorTarget, SoundEvent
from shared.ai.soldiers.configs.heavy_grenadier import HEAVY_GRENADIER_HEARING
from shared.ai.soldiers.configs.medic import MEDIC_HEARING
from shared.ai.soldiers.configs.rifleman import RIFLEMAN_HEARING
from shared.ai.soldiers.configs.schema import SoldierHearingTuning
from shared.ai.soldiers.context import SoldierContext
from shared.constants import MAP_HEIGHT, MAP_WIDTH, PLAYER_RADIUS, SOLDIERS, ZOMBIES, WEAPONS
from shared.factions import hostile
from shared.models import PlayerState, ProjectileState, SoldierState, Vec2
from shared.world.world_state import WorldState
from shared.systems.events.game_events import EmitSoundEvent
from shared.systems.events.game_events import SpawnGrenadeEvent
from shared.systems.actors.decision.actor_decision_result import ActorDecisionOutput
if TYPE_CHECKING:
    from shared.world.world_context import WorldContext


class SoldierRuntimeService:
    def __init__(
        self,
        *,
        state: WorldState,
        rng: random.Random,
        soldier_ai_registry,
    ) -> None:
        self._state = state
        self._rng = rng
        self._soldier_ai_registry = soldier_ai_registry

    @property
    def registry(self):
        return self._soldier_ai_registry

    @property
    def state_time(self) -> float:
        return self._state.time

    def make_context(
        self,
        soldier: SoldierState,
        dt: float,
        ctx: "WorldContext",
    ) -> SoldierContext:
        spec = SOLDIERS[soldier.kind]
        weapon = WEAPONS[spec.weapon_key]

        return SoldierContext(
            soldier=soldier,
            targets=self.targets_near_soldier(soldier, ctx),
            squad_mates=ctx.squads.mates_for(soldier),
            dt=dt,
            time=self._state.time,
            rng=self._rng,
            spec=spec,
            weapon=weapon,
            sounds=tuple(ctx.spatial.nearby_sounds(
                soldier.pos,
                self.soldier_hearing_query_radius(soldier.kind),
                soldier.floor,
            )),
            line_blocked=lambda a, b, floor: ctx.geometry.line_blocked(a, b, floor),
            can_hear=lambda actor: self.can_hear(actor, ctx),
            move_toward=lambda actor, target, delta_time, rng=None: self.move_toward(
                actor,
                target,
                delta_time,
                ctx,
            ),
            random_guard_pos=lambda actor, rng=None: self.random_guard_pos(
                actor,
                ctx,
            ),
            projectile_life=ctx.weapons.projectile_life,
        )

    def apply_result(
        self,
        soldier: SoldierState,
        result,
        ctx: "WorldContext",
    ) -> None:
        for projectile in result.projectiles:
            projectile_id = ctx.ids.next("shot")

            self._state.projectiles[projectile_id] = ProjectileState(
                id=projectile_id,
                owner_id=str(projectile["owner_id"]),
                pos=projectile["pos"],
                velocity=projectile["velocity"],
                damage=int(projectile["damage"]),
                life=float(projectile["life"]),
                radius=float(projectile["radius"]),
                floor=int(projectile["floor"]),
                weapon_key=str(projectile["weapon_key"]),
            )

        for grenade in result.grenades:
            ctx.events.emit(
                SpawnGrenadeEvent(
                    owner_id=str(grenade["owner_id"]),
                    kind=str(grenade["kind"]),
                    pos=grenade["pos"],
                    velocity=grenade["velocity"],
                    timer=float(grenade["timer"]),
                    floor=int(grenade["floor"]),
                )
            )

        for sound in result.sounds:
            ctx.events.emit(
                EmitSoundEvent(
                    pos=sound["pos"],
                    floor=int(sound["floor"]),
                    radius=float(sound["radius"]),
                    source_player_id=str(sound.get("source_player_id")) if sound.get(
                        "source_player_id") is not None else None,
                    kind=str(sound["kind"]),
                    intensity=float(sound["intensity"]),
                )
            )

        self.apply_heals(result.soldier_heals)

    def apply_heals(self, heals: list[tuple[str, int]]) -> None:
        for soldier_id, amount in heals:
            soldier = self._state.soldiers.get(soldier_id)
            if not soldier or not soldier.alive:
                continue
            soldier.health = min(SOLDIERS[soldier.kind].health, soldier.health + max(1, int(amount)))

    def apply_decision_output(self, output: ActorDecisionOutput, ctx: "WorldContext") -> None:
        soldier = self._state.soldiers.get(output.actor_id)

        if not soldier or output.actor_state is None:
            return

        updated = SoldierState.from_dict(output.actor_state)
        self._copy_state(soldier, updated)
        self.apply_result(soldier, output, ctx)

    def _copy_state(self, target: SoldierState, source: SoldierState) -> None:
        for field in fields(SoldierState):
            setattr(target, field.name, getattr(source, field.name))

    def targets_near_soldier(self, soldier: SoldierState, ctx) -> tuple[ActorTarget, ...]:
        spec = SOLDIERS[soldier.kind]

        query_radius = max(
            spec.sight_range,
            1200.0,
        )

        targets: list[ActorTarget] = []

        for zombie in ctx.spatial.nearby_zombies(
            soldier.pos,
            query_radius,
            soldier.floor,
        ):
            if zombie.health <= 0:
                continue
            if not hostile(soldier.faction, zombie.faction):
                continue

            zombie_spec = ZOMBIES[zombie.kind]

            targets.append(
                ActorTarget(
                    id=zombie.id,
                    kind="zombie",
                    pos=zombie.pos.copy(),
                    floor=zombie.floor,
                    alive=True,
                    radius=zombie_spec.radius,
                    actor_kind=zombie.kind,
                    health=zombie.health,
                    inside_building=zombie.inside_building,
                    faction=zombie.faction,
                )
            )

        for player in ctx.spatial.nearby_players(
            soldier.pos,
            query_radius,
            soldier.floor,
        ):
            if not player.alive:
                continue
            if not hostile(soldier.faction, player.faction):
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

        return tuple(targets)

    def can_hear(self, soldier: SoldierState, ctx) -> SoundEvent | None:
        tuning = self.soldier_hearing_tuning(soldier.kind)
        best: SoundEvent | None = None
        best_distance = float("inf")

        for sound in ctx.spatial.nearby_sounds(
            soldier.pos,
            self.soldier_hearing_query_radius(soldier.kind),
            soldier.floor,
        ):
            if sound.floor != soldier.floor:
                continue

            distance = soldier.pos.distance_to(sound.pos)
            hearing_radius = sound.radius * tuning.hearing_multiplier

            if distance > hearing_radius:
                continue

            if ctx.geometry.line_blocked(soldier.pos, sound.pos, soldier.floor, sound=True):
                continue

            if distance < best_distance:
                best = sound
                best_distance = distance

        return best

    def soldier_hearing_query_radius(self, kind: str) -> float:
        spec = SOLDIERS[kind]
        tuning = self.soldier_hearing_tuning(kind)
        return spec.hearing_range * tuning.hearing_multiplier + tuning.extra_radius

    def soldier_hearing_tuning(self, kind: str) -> SoldierHearingTuning:
        if kind == "heavy_grenadier":
            return SoldierHearingTuning(**HEAVY_GRENADIER_HEARING)
        if kind == "medic":
            return SoldierHearingTuning(**MEDIC_HEARING)
        return SoldierHearingTuning(**RIFLEMAN_HEARING)

    def move_toward(
        self,
        soldier: SoldierState,
        target: Vec2,
        dt: float,
        ctx: "WorldContext",
    ) -> None:
        spec = SOLDIERS[soldier.kind]

        direction = Vec2(
            target.x - soldier.pos.x,
            target.y - soldier.pos.y,
        )

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

    def random_guard_pos(
        self,
        soldier: SoldierState,
        ctx: "WorldContext",
    ) -> Vec2:
        base = soldier.guard_point or soldier.pos

        for _ in range(30):
            angle = self._rng.uniform(0.0, math.tau)
            distance = self._rng.uniform(80.0, 220.0)

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
