from __future__ import annotations

import random

from shared.constants import MAP_HEIGHT, MAP_WIDTH, PLAYER_RADIUS, ZOMBIES
from shared.models import PlayerState, Vec2
from shared.world.world_state import WorldState


class RespawnService:
    def __init__(
        self,
        *,
        state: WorldState,
        rng: random.Random,
        geometry,
    ) -> None:
        self._state = state
        self._rng = rng
        self._geometry = geometry

    def respawn(self, player: PlayerState) -> None:
        pos, floor, building_id = self._safe_respawn()

        player.pos = pos
        player.health = 100
        player.armor = max(0, player.armor // 2)
        player.alive = True
        player.floor = floor
        player.inside_building = building_id
        player.noise = 0.0
        player.sprinting = False
        player.sneaking = False

    def _safe_respawn(self) -> tuple[Vec2, int, str | None]:
        buildings = list(self._state.buildings.values())
        self._rng.shuffle(buildings)

        for building in buildings:
            floors = [
                floor
                for floor in (1, 2, -1, 0)
                if building.min_floor <= floor <= building.max_floor
            ]
            self._rng.shuffle(floors)

            for floor in floors:
                for _ in range(80):
                    pos = Vec2(
                        self._rng.uniform(
                            building.bounds.x + 96,
                            building.bounds.x + building.bounds.w - 96,
                        ),
                        self._rng.uniform(
                            building.bounds.y + 104,
                            building.bounds.y + building.bounds.h - 104,
                        ),
                    )

                    if (
                        not self._geometry.blocked_at(pos, PLAYER_RADIUS, floor)
                        and self._respawn_is_safe(pos, floor)
                    ):
                        return pos, floor, building.id

        for _ in range(800):
            pos = self._random_open_pos(centered=False)

            if self._respawn_is_safe(pos, 0):
                return pos, 0, None

        return self._random_open_pos(centered=True), 0, None

    def _respawn_is_safe(self, pos: Vec2, floor: int) -> bool:
        for zombie in self._state.zombies.values():
            if zombie.floor != floor:
                continue

            spec = ZOMBIES[zombie.kind]
            distance = zombie.pos.distance_to(pos)

            if distance < 760:
                return False

            if (
                distance < spec.sight_range + 140
                and not self._geometry.line_blocked(zombie.pos, pos, floor)
            ):
                return False

        return True

    def _random_open_pos(self, *, centered: bool) -> Vec2:
        for _ in range(500):
            if centered:
                pos = Vec2(
                    MAP_WIDTH * 0.5 + self._rng.uniform(-360, 360),
                    MAP_HEIGHT * 0.5 + self._rng.uniform(-300, 300),
                )
            else:
                pos = Vec2(
                    self._rng.uniform(160, MAP_WIDTH - 160),
                    self._rng.uniform(160, MAP_HEIGHT - 160),
                )

            if not self._geometry.blocked_at(pos, PLAYER_RADIUS, 0):
                return pos

        return Vec2(MAP_WIDTH * 0.5, MAP_HEIGHT * 0.5)