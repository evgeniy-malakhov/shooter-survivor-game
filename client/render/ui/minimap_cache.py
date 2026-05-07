from __future__ import annotations

from dataclasses import dataclass

import pygame


@dataclass(slots=True)
class MinimapCacheKey:
    map_id: str
    size: tuple[int, int]
    scale: float
    mode: str
    floor: int
    bounds: tuple[int, int, int, int]
    static_signature: tuple[int, int, int]


class MinimapStaticCache:
    def __init__(self) -> None:
        self.key: MinimapCacheKey | None = None
        self.surface: pygame.Surface | None = None
        self.hits = 0
        self.misses = 0

    def get(self, key: MinimapCacheKey) -> pygame.Surface | None:
        if self.key == key and self.surface is not None:
            self.hits += 1
            return self.surface
        self.misses += 1
        return None

    def set(self, key: MinimapCacheKey, surface: pygame.Surface) -> None:
        self.key = key
        self.surface = surface
