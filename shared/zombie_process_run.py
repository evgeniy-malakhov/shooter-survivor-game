"""
Полный тик AI одного зомби для выполнения в дочернем процессе (Windows spawn).
Топ-уровневая функция и picklable-данные — требования multiprocessing.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

from shared.ai.context import SoundEvent, ZombieContext
from shared.ai.registry import ZOMBIE_AI_REGISTRY
from shared.collision import move_circle_against_rects, segment_rect_intersects, blocked_at as walls_blocked_at
from shared.constants import (
    MAP_HEIGHT,
    MAP_WIDTH,
    PLAYER_RADIUS,
    ZOMBIE_TARGET_RADIUS,
    ZOMBIES,
)
from shared.difficulty import DifficultyConfig
from shared.level import all_closed_walls, nearest_door, point_building
from shared.models import BuildingState, PlayerState, RectState, Vec2, ZombieState


@dataclass(slots=True)
class ZombieProcessEnv:
    map_width: float
    map_height: float
    difficulty: DifficultyConfig
    buildings: dict[str, BuildingState]
    walls_by_floor: dict[int, tuple[RectState, ...]]
    sound_events: tuple[SoundEvent, ...]


def _angle_delta(a: float, b: float) -> float:
    return (b - a + math.pi) % math.tau - math.pi


def _line_blocked_env(
    env: ZombieProcessEnv,
    start: Vec2,
    end: Vec2,
    floor: int,
    *,
    sound: bool = False,
) -> bool:
    walls = env.walls_by_floor.get(floor, ())
    for wall in walls:
        if segment_rect_intersects(start, end, wall):
            if sound and wall.w < 28 and wall.h < 90:
                continue
            return True
    return False


def _blocked_at_env(env: ZombieProcessEnv, pos: Vec2, radius: float, floor: int) -> bool:
    walls = env.walls_by_floor.get(floor, ())
    return walls_blocked_at(pos, radius, walls)


def _move_circle_env(env: ZombieProcessEnv, pos: Vec2, delta: Vec2, radius: float, floor: int) -> None:
    walls = env.walls_by_floor.get(floor, ())
    move_circle_against_rects(pos, delta, radius, walls)


def _near_building_env(env: ZombieProcessEnv, pos: Vec2, margin: float) -> bool:
    for building in env.buildings.values():
        if building.bounds.inflated(margin).contains(pos):
            return True
    return False


def _random_open_env(env: ZombieProcessEnv, centered: bool, rng: random.Random) -> Vec2:
    for _ in range(500):
        if centered:
            pos = Vec2(
                env.map_width * 0.5 + rng.uniform(-360, 360),
                env.map_height * 0.5 + rng.uniform(-300, 300),
            )
        else:
            pos = Vec2(
                160 + rng.uniform(0, env.map_width - 320),
                160 + rng.uniform(0, env.map_height - 320),
            )
        if not _blocked_at_env(env, pos, PLAYER_RADIUS, 0):
            return pos
    return Vec2(env.map_width * 0.5, env.map_height * 0.5)


def _random_patrol_pos_env(env: ZombieProcessEnv, rng: random.Random) -> Vec2:
    for _ in range(500):
        pos = _random_open_env(env, centered=False, rng=rng)
        if not _near_building_env(env, pos, 340):
            return pos
    return _random_open_env(env, centered=False, rng=rng)


def _building_entry_target_env(env: ZombieProcessEnv, building_id: str) -> Vec2 | None:
    building = env.buildings.get(building_id)
    if not building:
        return None
    open_doors = [door for door in building.doors if door.open and door.floor == 0]
    if open_doors:
        return min(
            open_doors,
            key=lambda door: door.rect.center.distance_to(building.bounds.center),
        ).rect.center
    front = min(building.doors, key=lambda door: door.rect.center.y)
    center = front.rect.center
    return Vec2(center.x, center.y - 80)


def _pick_search_waypoint_env(
    env: ZombieProcessEnv,
    zombie: ZombieState,
    anchor: Vec2,
    rng: random.Random,
) -> Vec2 | None:
    spec = ZOMBIES[zombie.kind]
    radius = spec.radius
    clearance = 52.0
    for _ in range(72):
        angle = rng.uniform(0.0, math.tau)
        dist = rng.uniform(72.0, 312.0)
        pos = Vec2(anchor.x + math.cos(angle) * dist, anchor.y + math.sin(angle) * dist)
        pos.clamp_to_map(env.map_width, env.map_height)
        if point_building(env.buildings, pos) is not None:
            continue
        if _near_building_env(env, pos, clearance):
            continue
        if _blocked_at_env(env, pos, radius, zombie.floor):
            continue
        return pos
    for _ in range(28):
        pos = Vec2(
            anchor.x + rng.uniform(-240.0, 240.0),
            anchor.y + rng.uniform(-240.0, 240.0),
        )
        pos.clamp_to_map(env.map_width, env.map_height)
        if point_building(env.buildings, pos) is not None:
            continue
        if _near_building_env(env, pos, clearance * 0.88):
            continue
        if _blocked_at_env(env, pos, radius, zombie.floor):
            continue
        return pos
    return None


def _unstick_zombie_env(
    env: ZombieProcessEnv,
    zombie: ZombieState,
    radius: float,
    rng: random.Random,
) -> bool:
    nearest = min(
        env.buildings.values(),
        key=lambda building: building.bounds.center.distance_to(zombie.pos),
        default=None,
    )
    if not nearest or not nearest.bounds.inflated(120).contains(zombie.pos):
        return False
    if nearest.bounds.inflated(8).contains(zombie.pos):
        exits = [
            Vec2(nearest.bounds.x - 90, zombie.pos.y),
            Vec2(nearest.bounds.x + nearest.bounds.w + 90, zombie.pos.y),
            Vec2(zombie.pos.x, nearest.bounds.y - 90),
            Vec2(zombie.pos.x, nearest.bounds.y + nearest.bounds.h + 90),
        ]
        exits.sort(key=lambda candidate: candidate.distance_to(zombie.pos))
        for candidate in exits:
            candidate.clamp_to_map(env.map_width, env.map_height)
            if not _blocked_at_env(env, candidate, radius, zombie.floor):
                zombie.pos = candidate
                zombie.facing = zombie.pos.angle_to(nearest.bounds.center) + math.pi
                return True
    center = nearest.bounds.center
    away = Vec2(zombie.pos.x - center.x, zombie.pos.y - center.y).normalized()
    if away.length() <= 0.0:
        away = Vec2(rng.choice([-1.0, 1.0]), rng.choice([-1.0, 1.0])).normalized()
    for distance in (72, 128, 196, 280):
        candidate = Vec2(zombie.pos.x + away.x * distance, zombie.pos.y + away.y * distance)
        candidate.clamp_to_map(env.map_width, env.map_height)
        if not _blocked_at_env(env, candidate, radius, zombie.floor) and not _near_building_env(env, candidate, 38):
            zombie.pos = candidate
            zombie.facing = math.atan2(away.y, away.x)
            return True
    return False


def _zombie_move_toward_env(
    env: ZombieProcessEnv,
    zombie: ZombieState,
    target: Vec2,
    dt: float,
    sprint: bool,
    rng: random.Random,
) -> None:
    spec = ZOMBIES[zombie.kind]
    direction = Vec2(target.x - zombie.pos.x, target.y - zombie.pos.y)
    if direction.length() <= 0.01:
        return
    zombie.facing = math.atan2(direction.y, direction.x)
    speed = spec.speed * env.difficulty.zombie_speed_multiplier * (1.22 if sprint else 1.0)
    step = direction.normalized().scaled(speed * dt)
    old_pos = zombie.pos.copy()
    _move_circle_env(env, zombie.pos, step, spec.radius, zombie.floor)
    if zombie.pos.distance_to(old_pos) < 0.5:
        if _unstick_zombie_env(env, zombie, spec.radius, rng):
            return
        door = nearest_door(env.buildings, zombie.pos, 160, zombie.floor)
        if door and door.open:
            zombie.waypoint = door.rect.center
            return
        angle = zombie.facing + rng.choice([-1.0, 1.0]) * math.pi * 0.5
        sidestep = Vec2(math.cos(angle), math.sin(angle)).scaled(spec.radius * 1.8)
        _move_circle_env(env, zombie.pos, sidestep, spec.radius, zombie.floor)


def _can_see_env(env: ZombieProcessEnv, zombie: ZombieState, player: PlayerState) -> bool:
    if zombie.floor != player.floor:
        return False
    if player.inside_building and zombie.inside_building != player.inside_building:
        return False
    spec = ZOMBIES[zombie.kind]
    distance = zombie.pos.distance_to(player.pos)
    if distance > spec.sight_range:
        return False
    angle_to_player = zombie.pos.angle_to(player.pos)
    if abs(_angle_delta(zombie.facing, angle_to_player)) > math.radians(spec.fov_degrees * 0.5):
        return False
    return not _line_blocked_env(env, zombie.pos, player.pos, zombie.floor, sound=False)


def _can_hear_env(env: ZombieProcessEnv, zombie: ZombieState) -> SoundEvent | None:
    spec = ZOMBIES[zombie.kind]
    hearing_radius = spec.hearing_range * max(0.1, spec.sensitivity)
    best_event: SoundEvent | None = None
    best_dist = float("inf")
    for event in env.sound_events:
        if event.floor != zombie.floor:
            continue
        dist = zombie.pos.distance_to(event.pos)
        if dist > hearing_radius + event.radius:
            continue
        if _line_blocked_env(env, zombie.pos, event.pos, zombie.floor, sound=True):
            continue
        if dist < best_dist:
            best_dist = dist
            best_event = event
    return best_event


def _make_zombie_context(
    env: ZombieProcessEnv,
    zombie: ZombieState,
    dt: float,
    living_players: tuple[PlayerState, ...],
    rng: random.Random,
    sim_time: float,
) -> ZombieContext:
    def can_see(z: ZombieState, p: PlayerState) -> bool:
        return _can_see_env(env, z, p)

    def can_hear(z: ZombieState) -> SoundEvent | None:
        return _can_hear_env(env, z)

    def line_blocked(start: Vec2, end: Vec2, floor: int) -> bool:
        return _line_blocked_env(env, start, end, floor, sound=False)

    def move_toward(z: ZombieState, target: Vec2, step_dt: float, sprint: bool, r: random.Random) -> None:
        _zombie_move_toward_env(env, z, target, step_dt, sprint, r)

    def random_patrol(r: random.Random) -> Vec2:
        return _random_patrol_pos_env(env, r)

    def pick_wp(z: ZombieState, anchor: Vec2, r: random.Random) -> Vec2 | None:
        return _pick_search_waypoint_env(env, z, anchor, r)

    def entry_target(bid: str) -> Vec2 | None:
        return _building_entry_target_env(env, bid)

    return ZombieContext(
        zombie=zombie,
        players=living_players,
        dt=dt,
        time=sim_time,
        rng=rng,
        difficulty=env.difficulty,
        can_see=can_see,
        can_hear=can_hear,
        line_blocked=line_blocked,
        move_toward=move_toward,
        random_patrol_pos=random_patrol,
        pick_search_waypoint=pick_wp,
        building_entry_target=entry_target,
    )


def build_process_env(
    difficulty: DifficultyConfig,
    buildings: dict[str, BuildingState],
    sound_events: list[SoundEvent],
    floors: set[int],
) -> ZombieProcessEnv:
    walls: dict[int, tuple[RectState, ...]] = {}
    for floor in floors:
        walls[floor] = tuple(all_closed_walls(buildings, floor))
    return ZombieProcessEnv(
        map_width=float(MAP_WIDTH),
        map_height=float(MAP_HEIGHT),
        difficulty=difficulty,
        buildings=dict(buildings),
        walls_by_floor=walls,
        sound_events=tuple(sound_events),
    )


def run_one_zombie_task(
    payload: tuple[ZombieProcessEnv, dict[str, Any], tuple[dict[str, Any], ...], float, float, int],
) -> dict[str, Any]:
    env, zdict, pdicts, dt, sim_time, seed = payload
    zombie = ZombieState.from_dict(zdict)
    players = tuple(PlayerState.from_dict(p) for p in pdicts)
    rng = random.Random(seed)

    if not players and zombie.mode != "patrol":
        zombie.mode = "patrol"
        zombie.target_player_id = None
        zombie.last_known_pos = None
        zombie.waypoint = None
        zombie.alertness = 0.0

    ai = ZOMBIE_AI_REGISTRY.get(zombie.kind) or ZOMBIE_AI_REGISTRY["walker"]
    ctx = _make_zombie_context(env, zombie, dt, players, rng, sim_time)
    ai_result = ai.update(ctx)
    zombie.inside_building = point_building(env.buildings, zombie.pos)

    return {
        "id": zombie.id,
        "zombie": zombie.to_dict(),
        "player_hits": list(ai_result.player_hits),
        "poison_spits": list(ai_result.poison_spits),
    }
