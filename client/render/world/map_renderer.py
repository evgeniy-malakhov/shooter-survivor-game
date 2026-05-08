from __future__ import annotations

import math
import time

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.render_frame import RenderFrame
from client.render.world.chunked_map_renderer import ChunkedMapRenderer
from client.render.world.render_utils import draw_text_fit, world_rect_to_screen, world_size, world_to_screen
from client.render.world.static_world_cache import StaticWorldChunkCache
from shared.constants import MAP_HEIGHT, MAP_WIDTH


class MapRenderer:
    def __init__(self, static_cache: StaticWorldChunkCache | None = None) -> None:
        self.chunked = ChunkedMapRenderer(static_cache)

    def render(self, ctx: RenderContext, frame: RenderFrame) -> None:
        started = time.perf_counter()
        self.paint_background(ctx)
        static_started = time.perf_counter()
        self.chunked.render_static(ctx, frame)
        self.paint_doors(ctx, frame)
        if not ctx.local_player or ctx.local_player.floor >= 0:
            self.paint_player_inside_overlay(ctx, frame)
        if ctx.perf:
            ctx.perf.world_static_ms = (time.perf_counter() - static_started) * 1000.0
        if ctx.local_player and ctx.settings.get("noise_radius", False):
            self.paint_noise_radius(ctx)
        if ctx.perf:
            ctx.perf.map_ms = (time.perf_counter() - started) * 1000.0

    def paint_background(self, ctx: RenderContext) -> None:
        grid = 80
        zoom = max(0.1, ctx.camera_controller.zoom)
        visible_w = ctx.screen.get_width() / zoom
        visible_h = ctx.screen.get_height() / zoom
        start_world_x = math.floor(ctx.camera.x / grid) * grid
        start_world_y = math.floor(ctx.camera.y / grid) * grid
        end_world_x = ctx.camera.x + visible_w + grid
        end_world_y = ctx.camera.y + visible_h + grid
        x = start_world_x
        while x <= end_world_x:
            sx = int((x - ctx.camera.x) * zoom)
            pygame.draw.line(ctx.screen, (18, 25, 41), (sx, 0), (sx, ctx.screen.get_height()))
            x += grid
        y = start_world_y
        while y <= end_world_y:
            sy = int((y - ctx.camera.y) * zoom)
            pygame.draw.line(ctx.screen, (18, 25, 41), (0, sy), (ctx.screen.get_width(), sy))
            y += grid
        pygame.draw.rect(
            ctx.screen,
            (34, 55, 76),
            pygame.Rect(
                int(-ctx.camera.x * zoom),
                int(-ctx.camera.y * zoom),
                int(MAP_WIDTH * zoom),
                int(MAP_HEIGHT * zoom),
            ),
            3,
        )

    def paint_player_inside_overlay(self, ctx: RenderContext, frame: RenderFrame) -> None:
        player = ctx.local_player
        if not player or not player.inside_building:
            return
        building = frame.snapshot.buildings.get(player.inside_building)
        if not building:
            return
        rect = world_rect_to_screen(ctx, building.bounds)
        if not rect.colliderect(ctx.screen.get_rect().inflate(120, 120)):
            return
        pygame.draw.rect(ctx.screen, (18, 26, 34), rect, 2, border_radius=3)
        pygame.draw.rect(ctx.screen, palette.CYAN, rect, 2, border_radius=3)
        if ctx.text and ctx.fonts:
            label_rect = pygame.Rect(rect.x + 14, rect.y + 10, max(120, rect.w - 28), 24)
            label_bg = pygame.Surface(label_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(label_bg, (8, 14, 24, 128), label_bg.get_rect(), border_radius=8)
            pygame.draw.rect(label_bg, (78, 114, 150, 84), label_bg.get_rect(), 1, border_radius=8)
            ctx.screen.blit(label_bg, label_rect)
            draw_text_fit(
                ctx,
                f"{building.name} {ctx.text.floor_label(player.floor)}",
                label_rect.inflate(-10, -4),
                palette.CYAN,
                ctx.fonts.label,
            )

    def paint_doors(self, ctx: RenderContext, frame: RenderFrame) -> None:
        player_floor = ctx.local_player.floor if ctx.local_player else 0
        for building in frame.buildings:
            for door in building.doors:
                if door.floor != player_floor:
                    continue
                rect = world_rect_to_screen(ctx, door.rect)
                if not rect.colliderect(ctx.screen.get_rect().inflate(120, 120)):
                    continue
                color = (74, 222, 128) if door.open else (255, 210, 112)
                border = (181, 255, 210) if door.open else (255, 238, 170)
                shadow = rect.move(2, 3)
                pygame.draw.rect(ctx.screen, (0, 0, 0, 70), shadow, border_radius=2)
                pygame.draw.rect(ctx.screen, color, rect, border_radius=2)
                pygame.draw.rect(ctx.screen, border, rect, 1, border_radius=2)

    def paint_noise_radius(self, ctx: RenderContext) -> None:
        player = ctx.local_player
        if not player or player.noise <= 0.0 or not player.alive:
            return
        sx, sy = world_to_screen(ctx, player.pos)
        radius = world_size(ctx, max(12, min(460, player.noise)), 8)
        pulse = 0.5 + 0.5 * math.sin((ctx.now or 0.0) * (8.2 if player.sprinting else 6.1))
        surface = pygame.Surface((radius * 2 + 24, radius * 2 + 24), pygame.SRCALPHA)
        center = (radius + 12, radius + 12)
        base = (82, 232, 255) if player.sneaking else (255, 198, 102)
        for layer in range(4, 0, -1):
            layer_radius = int(radius * (0.48 + layer * 0.16 + pulse * 0.04))
            alpha = max(10, int((42 if player.sneaking else 50) - layer * 8 + pulse * 18))
            pygame.draw.circle(surface, (*base, alpha), center, max(8, layer_radius), 2)
        pygame.draw.circle(surface, (*base, 24), center, radius)
        pygame.draw.circle(surface, (255, 255, 255, 56), center, radius, 1)
        ctx.screen.blit(surface, (sx - center[0], sy - center[1]))
