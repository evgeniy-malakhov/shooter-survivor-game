from __future__ import annotations

import math
from collections import OrderedDict

import pygame

from client.render.render_frame import RenderLOD


class ActorSpriteCache:
    def __init__(self, max_entries: int = 512) -> None:
        self.max_entries = max_entries
        self._cache: OrderedDict[tuple[object, ...], pygame.Surface] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def sprite(
        self,
        *,
        actor_type: str,
        kind: str,
        lod: RenderLOD,
        radius: int,
        color: tuple[int, int, int],
        facing: float,
        is_local: bool = False,
    ) -> pygame.Surface:
        facing_bucket = int((facing % math.tau) / math.tau * 16) if lod == RenderLOD.FULL else 0
        key = (actor_type, kind, lod.value, max(2, radius), color, facing_bucket, is_local)
        cached = self._cache.get(key)
        if cached is not None:
            self.hits += 1
            self._cache.move_to_end(key)
            return cached
        self.misses += 1
        surface = self._build(actor_type, lod, max(2, radius), color, facing_bucket, is_local)
        self._cache[key] = surface
        if len(self._cache) > self.max_entries:
            self._cache.popitem(last=False)
        return surface

    def warm_defaults(self) -> None:
        for actor_type, color in (
            ("player", (76, 225, 255)),
            ("player", (92, 230, 155)),
            ("soldier", (44, 124, 255)),
            ("zombie", (94, 190, 112)),
            ("zombie", (210, 92, 84)),
        ):
            for lod, radius in ((RenderLOD.FULL, 18), (RenderLOD.SIMPLE, 14), (RenderLOD.DOT, 4)):
                for bucket in range(16 if lod == RenderLOD.FULL else 1):
                    self.sprite(
                        actor_type=actor_type,
                        kind="default",
                        lod=lod,
                        radius=radius,
                        color=color,
                        facing=bucket * math.tau / 16,
                    )

    def _build(
        self,
        actor_type: str,
        lod: RenderLOD,
        radius: int,
        color: tuple[int, int, int],
        facing_bucket: int,
        is_local: bool,
    ) -> pygame.Surface:
        padding = max(8, radius + 10)
        size = max(18, radius * 2 + padding * 2)
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        cx = cy = size // 2
        facing = facing_bucket * math.tau / 16
        if lod == RenderLOD.DOT:
            pygame.draw.circle(surface, (4, 7, 13), (cx, cy), radius + 2)
            pygame.draw.circle(surface, color, (cx, cy), radius)
            pygame.draw.circle(surface, (232, 239, 255), (cx, cy), radius, 1)
            return surface
        if actor_type == "soldier":
            points = []
            for i in range(5):
                angle = facing - math.pi / 2 + math.tau * i / 5
                scale = 1.25 if i == 0 else 1.0
                points.append((int(cx + math.cos(angle) * radius * scale), int(cy + math.sin(angle) * radius * scale)))
            pygame.draw.polygon(surface, (7, 12, 22), [(x + 2, y + 2) for x, y in points])
            pygame.draw.polygon(surface, color, points)
            pygame.draw.polygon(surface, (184, 220, 255), points, 2)
            if lod == RenderLOD.FULL:
                end = (int(cx + math.cos(facing) * (radius + 8)), int(cy + math.sin(facing) * (radius + 8)))
                pygame.draw.line(surface, (210, 235, 255), (cx, cy), end, 2)
            return surface
        shadow_radius = radius + (5 if actor_type == "player" else 8)
        pygame.draw.circle(surface, (4, 8, 14) if actor_type == "player" else (12, 18, 28), (cx, cy), shadow_radius)
        pygame.draw.circle(surface, color, (cx, cy), radius)
        pygame.draw.circle(surface, (232, 239, 255), (cx, cy), radius, 2)
        if lod == RenderLOD.FULL:
            nose_len = radius + (12 if actor_type == "zombie" else 18)
            end = (int(cx + math.cos(facing) * nose_len), int(cy + math.sin(facing) * nose_len))
            pygame.draw.line(surface, (232, 239, 255), (cx, cy), end, 2 if actor_type == "zombie" else 4)
        if is_local:
            pygame.draw.circle(surface, (76, 225, 255, 80), (cx, cy), radius + 6, 2)
        return surface
