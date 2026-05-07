from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

import pygame


@dataclass(slots=True)
class RenderSpatialItem:
    id: str
    kind: str
    rect: pygame.Rect
    floor: int
    ref: object


class RenderSpatialIndex:
    def __init__(self, cell_size: int = 512) -> None:
        self.cell_size = max(64, int(cell_size))
        self._cells: dict[tuple[int, int, int], list[RenderSpatialItem]] = defaultdict(list)

    def rebuild(self, items: Iterable[RenderSpatialItem]) -> None:
        self._cells.clear()
        for item in items:
            self.insert(item)

    def insert(self, item: RenderSpatialItem) -> None:
        for key in self._keys_for_rect(item.rect, item.floor):
            self._cells[key].append(item)

    def query(self, rect: pygame.Rect, floor: int | None = None) -> list[RenderSpatialItem]:
        result: list[RenderSpatialItem] = []
        self.query_into(rect, result, floor)
        return result

    def query_into(self, rect: pygame.Rect, out: list[RenderSpatialItem], floor: int | None = None) -> None:
        out.clear()
        seen: set[str] = set()
        floors = [floor] if floor is not None else self._floors_for_rect(rect)
        for target_floor in floors:
            for key in self._keys_for_rect(rect, target_floor):
                for item in self._cells.get(key, ()):
                    if item.id in seen or not item.rect.colliderect(rect):
                        continue
                    seen.add(item.id)
                    out.append(item)

    def _keys_for_rect(self, rect: pygame.Rect, floor: int) -> Iterable[tuple[int, int, int]]:
        left = rect.left // self.cell_size
        right = max(left, rect.right // self.cell_size)
        top = rect.top // self.cell_size
        bottom = max(top, rect.bottom // self.cell_size)
        for cx in range(left, right + 1):
            for cy in range(top, bottom + 1):
                yield (floor, cx, cy)

    def _floors_for_rect(self, rect: pygame.Rect) -> list[int]:
        floors = {key[0] for key in self._cells}
        return list(floors) or [0]
