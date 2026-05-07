from __future__ import annotations

import pygame

from client.render.render_context import RenderContext
from client.render.render_frame import RenderFrame
from client.render.world.static_world_cache import StaticWorldChunkCache


class ChunkedMapRenderer:
    def __init__(self, cache: StaticWorldChunkCache | None = None) -> None:
        self.cache = cache or StaticWorldChunkCache()

    def render_static(self, ctx: RenderContext, frame: RenderFrame) -> None:
        player = ctx.local_player
        floor = player.floor if player else 0
        if floor < 0:
            return
        self.cache.prepare(frame.snapshot)
        view = ctx.camera_controller.visible_world_rect(ctx.camera, margin=160.0)
        zoom = max(0.1, ctx.camera_controller.zoom)
        for key in self.cache.visible_keys(view, floor):
            chunk = self.cache.chunk_rect(key)
            surface = self.cache.get_or_build(key, frame.snapshot)
            screen_rect = pygame.Rect(
                int((chunk.x - ctx.camera.x) * zoom),
                int((chunk.y - ctx.camera.y) * zoom),
                max(1, int(chunk.w * zoom)),
                max(1, int(chunk.h * zoom)),
            )
            if not screen_rect.colliderect(ctx.screen.get_rect().inflate(160, 160)):
                continue
            ctx.screen.blit(self.cache.scaled(key, surface, screen_rect.size), screen_rect)
            self.cache.stats.visible += 1
        if ctx.perf:
            ctx.perf.visible_chunks = self.cache.stats.visible
            ctx.perf.static_chunk_hits = self.cache.stats.hits
            ctx.perf.static_chunk_misses = self.cache.stats.misses

