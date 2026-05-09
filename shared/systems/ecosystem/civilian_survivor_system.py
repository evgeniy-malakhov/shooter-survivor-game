from __future__ import annotations

import math
import random

from shared.combat_ecosystem import CivilianState
from shared.constants import MAP_HEIGHT, MAP_WIDTH
from shared.models import Vec2
from shared.systems.base import WorldSystem
from shared.systems.events.game_events import EmitSoundEvent
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class CivilianSurvivorSystem(WorldSystem):
    def __init__(self) -> None:
        self._spawn_timer = 0.0

    def update(self, state: WorldState, ctx: WorldContext, dt: float) -> None:
        self._spawn_timer = max(0.0, self._spawn_timer - dt)
        self._maybe_spawn(state, ctx)
        for civilian in list(state.civilians.values()):
            if not civilian.alive:
                state.civilians.pop(civilian.id, None)
                continue
            self._update_civilian(state, ctx, civilian, dt)

    def _maybe_spawn(self, state: WorldState, ctx: WorldContext) -> None:
        if self._spawn_timer > 0.0 or len(state.civilians) >= 10:
            return
        candidates = [
            district
            for district in state.district_simulation.values()
            if "survivors" in district.tags or district.danger_level < 0.55
        ]
        if not candidates:
            return
        if ctx.rng.random() > 0.22:
            self._spawn_timer = ctx.rng.uniform(8.0, 18.0)
            return
        district = ctx.rng.choice(candidates)
        pos = self._random_near(ctx.rng, district.center, min(420.0, district.radius * 0.35))
        if ctx.geometry.blocked_at(pos, 18.0, district.floor):
            self._spawn_timer = ctx.rng.uniform(8.0, 18.0)
            return
        civilian_id = ctx.ids.next("civ")
        state.civilians[civilian_id] = CivilianState(
            id=civilian_id,
            pos=pos,
            floor=district.floor,
            panic=min(0.65, district.danger_level),
            last_safe_pos=pos.copy(),
        )
        self._spawn_timer = ctx.rng.uniform(14.0, 30.0)

    def _update_civilian(self, state: WorldState, ctx: WorldContext, civilian: CivilianState, dt: float) -> None:
        local_pressure = ctx.horde_director.pressure_for_position(civilian.pos, civilian.floor)
        nearby_zombies = list(ctx.spatial.nearby_zombies(civilian.pos, 520.0, civilian.floor))
        immediate = any(zombie.health > 0 and zombie.pos.distance_to(civilian.pos) < 260.0 for zombie in nearby_zombies)
        civilian.panic = max(0.0, min(1.0, civilian.panic + local_pressure * dt * 0.55 + (dt * 0.42 if immediate else -dt * 0.08)))
        civilian.help_timer = max(0.0, civilian.help_timer - dt)

        if civilian.panic >= 0.72:
            civilian.mode = "flee"
            target = self._flee_target(ctx, civilian, nearby_zombies)
            self._move(ctx, civilian, target, dt, sprint=True)
            if civilian.help_timer <= 0.0:
                ctx.events.emit(
                    EmitSoundEvent(
                        pos=civilian.pos.copy(),
                        floor=civilian.floor,
                        radius=520.0 + civilian.panic * 420.0,
                        kind="panic",
                        intensity=0.55 + civilian.panic * 0.35,
                    )
                )
                civilian.help_timer = 3.5 + ctx.rng.uniform(0.0, 2.0)
            return

        if civilian.panic >= 0.35:
            civilian.mode = "hide"
            if civilian.last_safe_pos and civilian.pos.distance_to(civilian.last_safe_pos) > 38.0:
                self._move(ctx, civilian, civilian.last_safe_pos, dt, sprint=False)
            return

        civilian.mode = "scavenge" if ctx.rng.random() < 0.003 else "hide"
        if civilian.mode == "scavenge":
            target = self._random_near(ctx.rng, civilian.pos, 180.0)
            if not ctx.geometry.blocked_at(target, 18.0, civilian.floor):
                self._move(ctx, civilian, target, dt, sprint=False)
                civilian.last_safe_pos = civilian.pos.copy()

    def _flee_target(self, ctx: WorldContext, civilian: CivilianState, zombies) -> Vec2:
        if not zombies:
            return civilian.last_safe_pos.copy() if civilian.last_safe_pos else civilian.pos.copy()
        avg = Vec2(0.0, 0.0)
        count = 0
        for zombie in zombies:
            if zombie.health <= 0:
                continue
            avg.x += zombie.pos.x
            avg.y += zombie.pos.y
            count += 1
        if count <= 0:
            return civilian.pos.copy()
        avg.x /= count
        avg.y /= count
        away = Vec2(civilian.pos.x - avg.x, civilian.pos.y - avg.y)
        if away.length() <= 0.01:
            away = Vec2(math.cos(ctx.rng.random() * math.tau), math.sin(ctx.rng.random() * math.tau))
        target = Vec2(civilian.pos.x + away.normalized().x * 520.0, civilian.pos.y + away.normalized().y * 520.0)
        target.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
        return target

    def _move(self, ctx: WorldContext, civilian: CivilianState, target: Vec2, dt: float, *, sprint: bool) -> None:
        direction = Vec2(target.x - civilian.pos.x, target.y - civilian.pos.y)
        if direction.length() <= 0.01:
            return
        speed = 190.0 if sprint else 105.0
        step = direction.normalized().scaled(speed * dt)
        ctx.movement.move_circle(civilian.pos, step, 18.0, civilian.floor)
        civilian.pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)

    def _random_near(self, rng: random.Random, center: Vec2, radius: float) -> Vec2:
        angle = rng.uniform(0.0, math.tau)
        distance = rng.uniform(0.0, radius)
        pos = Vec2(center.x + math.cos(angle) * distance, center.y + math.sin(angle) * distance)
        pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
        return pos
