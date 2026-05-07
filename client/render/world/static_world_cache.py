from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pygame

from shared.level import tunnel_segments
from shared.models import BuildingState, RectState, WorldSnapshot


@dataclass(frozen=True, slots=True)
class StaticChunkKey:
    signature: tuple[int, int, int, int]
    floor: int
    chunk_x: int
    chunk_y: int


@dataclass(slots=True)
class StaticChunkStats:
    visible: int = 0
    hits: int = 0
    misses: int = 0


class StaticWorldChunkCache:
    def __init__(self, chunk_size: int = 512) -> None:
        self.chunk_size = chunk_size
        self._surfaces: dict[StaticChunkKey, pygame.Surface] = {}
        self._scaled: dict[tuple[StaticChunkKey, int], pygame.Surface] = {}
        self._signature: tuple[int, int, int, int] | None = None
        self.stats = StaticChunkStats()

    def signature(self, snapshot: WorldSnapshot) -> tuple[int, int, int, int]:
        return (
            int(snapshot.map_width),
            int(snapshot.map_height),
            len(snapshot.buildings),
            sum(len(building.walls) + len(building.props) + len(building.doors) for building in snapshot.buildings.values()),
        )

    def prepare(self, snapshot: WorldSnapshot) -> None:
        signature = self.signature(snapshot)
        if signature == self._signature:
            self.stats = StaticChunkStats()
            return
        self._signature = signature
        self._surfaces.clear()
        self._scaled.clear()
        self.stats = StaticChunkStats()

    def visible_keys(self, view: pygame.Rect, floor: int) -> Iterable[StaticChunkKey]:
        if self._signature is None:
            return ()
        size = self.chunk_size
        map_w = self._signature[0]
        map_h = self._signature[1]
        left = max(0, view.left // size)
        top = max(0, view.top // size)
        right = min(max(left, view.right // size), max(0, map_w // size))
        bottom = min(max(top, view.bottom // size), max(0, map_h // size))
        signature = self._signature
        return (
            StaticChunkKey(signature, floor, chunk_x, chunk_y)
            for chunk_y in range(top, bottom + 1)
            for chunk_x in range(left, right + 1)
        )

    def warm_snapshot(self, snapshot: WorldSnapshot, floors: tuple[int, ...] = (0, -1)) -> None:
        self.prepare(snapshot)
        view = pygame.Rect(0, 0, int(snapshot.map_width), int(snapshot.map_height))
        for floor in floors:
            for key in self.visible_keys(view, floor):
                self.get_or_build(key, snapshot)

    def chunk_rect(self, key: StaticChunkKey) -> pygame.Rect:
        size = self.chunk_size
        return pygame.Rect(key.chunk_x * size, key.chunk_y * size, size, size)

    def get_or_build(self, key: StaticChunkKey, snapshot: WorldSnapshot) -> pygame.Surface:
        cached = self._surfaces.get(key)
        if cached is not None:
            self.stats.hits += 1
            return cached
        self.stats.misses += 1
        surface = pygame.Surface((self.chunk_size, self.chunk_size), pygame.SRCALPHA)
        chunk = self.chunk_rect(key)
        if key.floor < 0:
            for tunnel in tunnel_segments(snapshot.buildings):
                if self._rect_intersects(tunnel, chunk):
                    local = self._local_rect(tunnel, chunk)
                    pygame.draw.rect(surface, (8, 12, 18), local, border_radius=10)
                    pygame.draw.rect(surface, (34, 49, 66), local, 2, border_radius=10)
                    center_line = local.inflate(-max(8, local.w // 7), -max(8, local.h // 7))
                    if center_line.w > 6 and center_line.h > 6:
                        pygame.draw.rect(surface, (34, 52, 78, 54), center_line, border_radius=7)
                        pygame.draw.rect(surface, (66, 106, 146, 56), center_line, 1, border_radius=7)
            self._surfaces[key] = surface
            return surface
        for building in snapshot.buildings.values():
            if not self._rect_intersects(building.bounds, chunk):
                continue
            self._paint_building(surface, chunk, building, key.floor)
        self._surfaces[key] = surface
        return surface

    def scaled(self, key: StaticChunkKey, surface: pygame.Surface, size: tuple[int, int]) -> pygame.Surface:
        width = max(1, int(size[0]))
        height = max(1, int(size[1]))
        zoom_key = int(round(width / max(1, self.chunk_size) * 1000.0))
        cached = self._scaled.get((key, zoom_key))
        if cached is not None and cached.get_size() == (width, height):
            return cached
        if (width, height) == surface.get_size():
            scaled = surface
        else:
            scaled = pygame.transform.scale(surface, (width, height))
        self._scaled[(key, zoom_key)] = scaled
        return scaled

    def _paint_building(self, surface: pygame.Surface, chunk: pygame.Rect, building: BuildingState, floor: int) -> None:
        bounds = self._local_rect(building.bounds, chunk)
        pygame.draw.rect(surface, (15, 20, 30), bounds, border_radius=3)
        pygame.draw.rect(surface, (55, 72, 94), bounds, 2, border_radius=3)
        for wall in building.walls:
            if self._rect_intersects(wall, chunk):
                pygame.draw.rect(surface, (77, 91, 117), self._local_rect(wall, chunk), border_radius=2)
        for prop in building.props:
            if prop.floor != floor or not self._rect_intersects(prop.rect, chunk):
                continue
            if prop.kind not in {"shelf", "crate", "barrel", "pallet", "roadblock", "desk", "table", "glass_wall"}:
                continue
            prop_rect = self._local_rect(prop.rect, chunk)
            if prop.kind == "glass_wall":
                pygame.draw.rect(surface, (136, 220, 255, 76), prop_rect, border_radius=3)
                pygame.draw.rect(surface, (196, 246, 255, 122), prop_rect, 2, border_radius=3)
            else:
                color = (111, 92, 72) if prop.kind in {"desk", "table", "pallet"} else (110, 74, 54) if prop.kind == "barrel" else (82, 96, 124)
                pygame.draw.rect(surface, color, prop_rect, border_radius=2)
        for door in building.doors:
            if door.floor == floor and self._rect_intersects(door.rect, chunk):
                pygame.draw.rect(surface, (80, 216, 150) if door.open else (255, 209, 102), self._local_rect(door.rect, chunk), border_radius=2)

    def _local_rect(self, rect: RectState, chunk: pygame.Rect) -> pygame.Rect:
        return pygame.Rect(
            int(rect.x - chunk.x),
            int(rect.y - chunk.y),
            max(1, int(rect.w)),
            max(1, int(rect.h)),
        )

    def _rect_intersects(self, rect: RectState, chunk: pygame.Rect) -> bool:
        return rect.x <= chunk.right and rect.x + rect.w >= chunk.left and rect.y <= chunk.bottom and rect.y + rect.h >= chunk.top
