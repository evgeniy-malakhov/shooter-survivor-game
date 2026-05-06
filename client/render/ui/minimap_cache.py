from __future__ import annotations

from dataclasses import dataclass

import pygame


@dataclass(slots=True)
class MinimapCacheKey:
    size: tuple[int, int]
    bounds: tuple[float, float, float, float]
    building_count: int
    map_size: tuple[int, int]


class MinimapStaticCache:
    def __init__(self) -> None:
        self.key: MinimapCacheKey | None = None
        self.surface: pygame.Surface | None = None

    def get(self, key: MinimapCacheKey) -> pygame.Surface | None:
        return self.surface if self.key == key else None

    def set(self, key: MinimapCacheKey, surface: pygame.Surface) -> None:
        self.key = key
        self.surface = surface
