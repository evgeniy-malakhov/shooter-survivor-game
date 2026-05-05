from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from shared.ai.context import ActorTarget
from shared.ai.soldiers.context import SoldierContext
from shared.constants import MAP_HEIGHT, MAP_WIDTH, PLAYER_RADIUS, SOLDIERS, ZOMBIES, WEAPONS
from shared.models import PlayerState, ProjectileState, SoldierState, Vec2
from shared.world.world_state import WorldState
from shared.systems.events.game_events import EmitSoundEvent
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
            dt=dt,
            time=self._state.time,
            rng=self._rng,
            spec=spec,
            weapon=weapon,
            line_blocked=lambda a, b, floor: ctx.geometry.line_blocked(a, b, floor),
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

            zombie_spec = ZOMBIES[zombie.kind]

            targets.append(
                ActorTarget(
                    id=zombie.id,
                    kind="zombie",
                    pos=zombie.pos.copy(),
                    floor=zombie.floor,
                    alive=True,
                    radius=zombie_spec.radius,
                    health=zombie.health,
                    inside_building=zombie.inside_building,
                )
            )

        for player in ctx.spatial.nearby_players(
            soldier.pos,
            query_radius,
            soldier.floor,
        ):
            if not player.alive:
                continue

            targets.append(
                ActorTarget(
                    id=player.id,
                    kind="player",
                    pos=player.pos.copy(),
                    floor=player.floor,
                    alive=True,
                    radius=PLAYER_RADIUS,
                    health=player.health,
                    sprinting=player.sprinting,
                    inside_building=player.inside_building,
                )
            )

        return tuple(targets)

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

        ctx.movement.move_circle(
            soldier.pos,
            step,
            spec.radius,
            soldier.floor,
        )

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