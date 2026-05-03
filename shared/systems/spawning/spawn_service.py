from __future__ import annotations

import math
import random

from shared.constants import MAP_HEIGHT, MAP_WIDTH, SOLDIERS, ZOMBIES
from shared.models import SoldierState, Vec2, ZombieState
from shared.spawning.soldier_factory import SoldierFactory
from shared.spawning.soldier_spawn_table import SOLDIER_SPAWN_POINTS
from shared.spawning.zombie_factory import ZombieFactory
from shared.spawning.zombie_spawn_table import DEFAULT_ZOMBIE_SPAWN_TABLE
from shared.world.world_state import WorldState
from shared.difficulty import DifficultyConfig


class SpawnService:
    def __init__(
        self,
        *,
        state: WorldState,
        rng: random.Random,
        ids,
        geometry,
        difficulty: DifficultyConfig,
        max_zombies
    ) -> None:
        self._state = state
        self._rng = rng
        self._ids = ids
        self._geometry = geometry

        self.zombie_factory = ZombieFactory()
        self.zombie_spawn_table = DEFAULT_ZOMBIE_SPAWN_TABLE

        self.soldier_factory = SoldierFactory()
        self.soldier_spawn_table = SOLDIER_SPAWN_POINTS

        self._difficulty = difficulty
        self._max_zombies = max_zombies

    def spawn_zombie(self, kind: str | None = None, pos: Vec2 | None = None) -> ZombieState:
        if kind is None:
            current_counts: dict[str, int] = {}

            for zombie in self._state.zombies.values():
                current_counts[zombie.kind] = current_counts.get(zombie.kind, 0) + 1

            kind = self.zombie_spawn_table.choose(
                self._rng,
                current_time=self._state.time,
                current_counts=current_counts,
                total_zombies=len(self._state.zombies),
                max_zombies=max(1, getattr(self, "_max_zombies", 1)),
            )

        if pos is None:
            pos = self.random_zombie_spawn_pos(kind)

        zombie = self.zombie_factory.create(
            zombie_id=self._ids.next("z"),
            kind=kind,
            pos=pos,
            rng=self._rng,
            difficulty=self._difficulty,
        )

        self._state.zombies[zombie.id] = zombie
        return zombie

    def spawn_soldier(
        self,
        *,
        kind: str,
        pos: Vec2,
        guard_point: Vec2 | None = None,
    ) -> SoldierState:
        soldier = self.soldier_factory.create(
            soldier_id=self._ids.next("s"),
            kind=kind,
            pos=pos,
            guard_point=guard_point or pos,
            rng=self._rng,
        )

        self._state.soldiers[soldier.id] = soldier
        return soldier

    def spawn_initial_soldiers(self) -> None:
        for spawn_point in self.soldier_spawn_table:
            count = self._rng.randint(
                spawn_point.min_soldiers,
                spawn_point.max_soldiers,
            )

            for _ in range(count):
                kind = self._rng.choices(
                    population=list(spawn_point.kinds),
                    weights=list(spawn_point.weights),
                    k=1,
                )[0]

                pos = self.random_soldier_spawn_pos(spawn_point)

                if not pos:
                    continue

                self.spawn_soldier(
                    kind=kind,
                    pos=pos,
                    guard_point=spawn_point.pos,
                )

    def random_soldier_spawn_pos(self, spawn_point) -> Vec2 | None:
        for _ in range(40):
            angle = self._rng.uniform(0.0, math.tau)
            distance = self._rng.uniform(0.0, spawn_point.radius)

            pos = Vec2(
                spawn_point.pos.x + math.cos(angle) * distance,
                spawn_point.pos.y + math.sin(angle) * distance,
            )
            pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)

            floor = getattr(spawn_point, "floor", 0)
            radius = SOLDIERS[spawn_point.kinds[0]].radius

            if self._geometry.blocked_at(pos, radius, floor):
                continue

            return pos

        return None

    def random_zombie_spawn_pos(self, kind: str) -> Vec2:
        spec = ZOMBIES[kind]

        for _ in range(200):
            edge = self._rng.choice(("top", "bottom", "left", "right"))

            if edge == "top":
                pos = Vec2(self._rng.uniform(80, MAP_WIDTH - 80), 80)
            elif edge == "bottom":
                pos = Vec2(self._rng.uniform(80, MAP_WIDTH - 80), MAP_HEIGHT - 80)
            elif edge == "left":
                pos = Vec2(80, self._rng.uniform(80, MAP_HEIGHT - 80))
            else:
                pos = Vec2(MAP_WIDTH - 80, self._rng.uniform(80, MAP_HEIGHT - 80))

            if not self._geometry.blocked_at(pos, spec.radius, 0):
                return pos

        return Vec2(MAP_WIDTH * 0.5, MAP_HEIGHT * 0.5)