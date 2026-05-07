from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable

import pygame


class IconScaleCache:
    def __init__(self, max_entries: int = 1024) -> None:
        self.max_entries = max_entries
        self._cache: OrderedDict[tuple[str, int, int], pygame.Surface] = OrderedDict()
        self.hits = 0
        self.misses = 0

    @property
    def raw(self) -> dict[tuple[str, int, int], pygame.Surface]:
        return self._cache

    def get_or_create(self, key: str, size: tuple[int, int], factory: Callable[[], pygame.Surface]) -> pygame.Surface:
        cache_key = (key, max(1, int(size[0])), max(1, int(size[1])))
        cached = self._cache.get(cache_key)
        if cached is not None:
            self.hits += 1
            self._cache.move_to_end(cache_key)
            return cached
        self.misses += 1
        surface = factory()
        self._cache[cache_key] = surface
        if len(self._cache) > self.max_entries:
            self._cache.popitem(last=False)
        return surface


class BarSurfaceCache:
    def __init__(self, max_entries: int = 256) -> None:
        self.max_entries = max_entries
        self._cache: OrderedDict[tuple[int, int, tuple[int, int, int], int], pygame.Surface] = OrderedDict()

    def frame(self, size: tuple[int, int], color: tuple[int, int, int], radius: int = 3) -> pygame.Surface:
        key = (max(1, size[0]), max(1, size[1]), color, radius)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        surface = pygame.Surface((key[0], key[1]), pygame.SRCALPHA)
        pygame.draw.rect(surface, (18, 24, 36), surface.get_rect(), border_radius=radius)
        pygame.draw.rect(surface, color, surface.get_rect(), 1, border_radius=radius)
        self._cache[key] = surface
        if len(self._cache) > self.max_entries:
            self._cache.popitem(last=False)
        return surface


class PanelSurfaceCache:
    def __init__(self, max_entries: int = 128) -> None:
        self.max_entries = max_entries
        self._cache: OrderedDict[tuple[int, int, tuple[int, int, int], tuple[int, int, int], int], pygame.Surface] = OrderedDict()

    def panel(
        self,
        size: tuple[int, int],
        fill: tuple[int, int, int],
        outline: tuple[int, int, int],
        radius: int = 8,
    ) -> pygame.Surface:
        key = (max(1, size[0]), max(1, size[1]), fill, outline, radius)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        surface = pygame.Surface((key[0], key[1]), pygame.SRCALPHA)
        pygame.draw.rect(surface, fill, surface.get_rect(), border_radius=radius)
        pygame.draw.rect(surface, outline, surface.get_rect(), 1, border_radius=radius)
        self._cache[key] = surface
        if len(self._cache) > self.max_entries:
            self._cache.popitem(last=False)
        return surface

