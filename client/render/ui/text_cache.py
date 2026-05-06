from __future__ import annotations

from collections import OrderedDict

import pygame


class TextCache:
    def __init__(self, max_entries: int = 512) -> None:
        self.max_entries = max_entries
        self._cache: OrderedDict[tuple[int, str, tuple[int, int, int]], pygame.Surface] = OrderedDict()
        self.hits = 0

    def render(self, font: pygame.font.Font, text: str, color: tuple[int, int, int]) -> pygame.Surface:
        key = (id(font), text, color)
        cached = self._cache.get(key)
        if cached is not None:
            self.hits += 1
            self._cache.move_to_end(key)
            return cached
        surface = font.render(text, True, color)
        self._cache[key] = surface
        if len(self._cache) > self.max_entries:
            self._cache.popitem(last=False)
        return surface
