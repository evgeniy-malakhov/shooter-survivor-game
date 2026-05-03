from __future__ import annotations

import threading

from shared.collision import blocked_at as walls_blocked_at
from shared.collision import move_circle_against_rects
from shared.collision import segment_rect_intersects
from shared.level import all_closed_walls
from shared.models import BuildingState, RectState, Vec2


class GeometryService:
    def __init__(
        self,
        buildings: dict[str, BuildingState],
        cache_lock: threading.Lock,
    ) -> None:
        self._buildings = buildings
        self._cache_lock = cache_lock
        self._geometry_version = 0
        self._closed_walls_cache: dict[int, tuple[int, tuple[RectState, ...]]] = {}

    @property
    def version(self) -> int:
        return self._geometry_version

    def mark_dirty(self) -> None:
        with self._cache_lock:
            self._geometry_version += 1
            self._closed_walls_cache.clear()

    def closed_walls(self, floor: int) -> tuple[RectState, ...]:
        cached = self._closed_walls_cache.get(floor)

        if cached and cached[0] == self._geometry_version:
            return cached[1]

        with self._cache_lock:
            cached = self._closed_walls_cache.get(floor)

            if cached and cached[0] == self._geometry_version:
                return cached[1]

            walls = tuple(all_closed_walls(self._buildings, floor))
            self._closed_walls_cache[floor] = (self._geometry_version, walls)

            return walls

    def blocked_at(self, pos: Vec2, radius: float, floor: int = 0) -> bool:
        return walls_blocked_at(pos, radius, self.closed_walls(floor))

    def move_circle(self, pos: Vec2, delta: Vec2, radius: float, floor: int) -> None:
        move_circle_against_rects(
            pos,
            delta,
            radius,
            self.closed_walls(floor),
        )

    def line_blocked(
        self,
        start: Vec2,
        end: Vec2,
        floor: int,
        *,
        sound: bool = False,
    ) -> bool:
        for wall in self.closed_walls(floor):
            if segment_rect_intersects(start, end, wall):
                if sound and wall.w < 28 and wall.h < 90:
                    continue

                return True

        return False