from __future__ import annotations

import random

from shared.constants import MAP_HEIGHT, MAP_WIDTH, PLAYER_RADIUS
from shared.level import point_building, nearest_door, nearest_prop, nearest_stairs
from shared.models import BuildingState, Vec2


class BuildingService:
    def __init__(self, buildings: dict[str, BuildingState]) -> None:
        self._buildings = buildings

    def point_building(self, pos: Vec2) -> str | None:
        return point_building(self._buildings, pos)

    def near_building(self, pos: Vec2, margin: float) -> bool:
        for building in self._buildings.values():
            if building.bounds.inflated(margin).contains(pos):
                return True

        return False

    def building_entry_target(self, building_id: str) -> Vec2 | None:
        building = self._buildings.get(building_id)

        if not building:
            return None

        open_doors = [
            door
            for door in building.doors
            if door.open and door.floor == 0
        ]

        if open_doors:
            return min(
                open_doors,
                key=lambda door: door.rect.center.distance_to(building.bounds.center),
            ).rect.center

        front = min(building.doors, key=lambda door: door.rect.center.y)
        center = front.rect.center

        return Vec2(center.x, center.y - 80)

    def nearest_door(self, pos: Vec2, radius: float, floor: int):
        return nearest_door(self._buildings, pos, radius, floor)

    def nearest_prop(self, pos: Vec2, radius: float, floor: int):
        return nearest_prop(self._buildings, pos, radius, floor)

    def nearest_stairs(self, pos: Vec2, radius: float, floor: int):
        return nearest_stairs(self._buildings, pos, radius, floor)

    def random_open_pos(
        self,
        *,
        centered: bool,
        rng: random.Random,
        blocked_at,
    ) -> Vec2:
        for _ in range(500):
            if centered:
                pos = Vec2(
                    MAP_WIDTH * 0.5 + rng.uniform(-360, 360),
                    MAP_HEIGHT * 0.5 + rng.uniform(-300, 300),
                )
            else:
                pos = Vec2(
                    rng.uniform(160, MAP_WIDTH - 160),
                    rng.uniform(160, MAP_HEIGHT - 160),
                )

            if not blocked_at(pos, PLAYER_RADIUS):
                return pos

        return Vec2(MAP_WIDTH * 0.5, MAP_HEIGHT * 0.5)