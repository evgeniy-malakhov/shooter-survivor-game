from __future__ import annotations

import math
import time

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.ui.minimap_cache import MinimapCacheKey, MinimapStaticCache
from shared.constants import MAP_HEIGHT, MAP_WIDTH
from shared.level import tunnel_segments
from shared.models import RectState, Vec2, WorldSnapshot

ONLINE_MINIMAP_MIN_RADIUS = 1400.0
ONLINE_MINIMAP_MAX_RADIUS = 4200.0


class MinimapRenderer:
    def __init__(self, cache: MinimapStaticCache | None = None) -> None:
        self.cache = cache or MinimapStaticCache()

    def render(self, ctx: RenderContext) -> None:
        started = time.perf_counter()
        if ctx.snapshot:
            self.paint_minimap(ctx, ctx.snapshot)
        if ctx.perf:
            ctx.perf.minimap_ms = (time.perf_counter() - started) * 1000.0
            ctx.perf.minimap_cache_hits = self.cache.hits
            ctx.perf.minimap_cache_misses = self.cache.misses

    def rect(self, ctx: RenderContext) -> pygame.Rect:
        big = bool(ctx.overlay and ctx.overlay.minimap_big)
        size = 248 if big else 176
        return pygame.Rect(ctx.screen.get_width() - size - 18, 18, size, int(size * MAP_HEIGHT / MAP_WIDTH))

    def paint_minimap(self, ctx: RenderContext, snapshot: WorldSnapshot) -> None:
        rect = self.rect(ctx)
        pygame.draw.rect(ctx.screen, palette.PANEL, rect, border_radius=8)
        pygame.draw.rect(ctx.screen, palette.CYAN, rect, 2, border_radius=8)
        bounds = self.world_bounds(ctx, rect, snapshot)
        static = self.static_layer(ctx, rect, snapshot, bounds)
        ctx.screen.blit(static, rect)
        min_x, min_y, max_x, max_y = bounds
        span_x = max(1.0, max_x - min_x)
        span_y = max(1.0, max_y - min_y)

        def mp(pos: Vec2) -> tuple[int, int]:
            return int(rect.x + (pos.x - min_x) / span_x * rect.w), int(rect.y + (pos.y - min_y) / span_y * rect.h)

        def inside(pos: Vec2) -> bool:
            return min_x <= pos.x <= max_x and min_y <= pos.y <= max_y

        player = ctx.local_player
        for item in snapshot.loot.values():
            if player and item.floor != player.floor or not inside(item.pos):
                continue
            pygame.draw.circle(ctx.screen, palette.YELLOW, mp(item.pos), 2)
        for mine in snapshot.mines.values():
            if player and mine.floor != player.floor or not inside(mine.pos):
                continue
            self.triangle(ctx, mp(mine.pos), palette.MINE_MAP_COLOR if mine.armed else (136, 102, 170), mine.rotation, 5)
        for zombie in snapshot.zombies.values():
            if player and zombie.floor != player.floor or not inside(zombie.pos):
                continue
            pygame.draw.circle(ctx.screen, palette.RED, mp(zombie.pos), 3)
        for soldier in snapshot.soldiers.values():
            if player and soldier.floor != player.floor or not inside(soldier.pos):
                continue
            pygame.draw.circle(ctx.screen, (44, 124, 255), mp(soldier.pos), 4)
            pygame.draw.circle(ctx.screen, (190, 225, 255), mp(soldier.pos), 4, 1)
        for other in snapshot.players.values():
            if player and other.floor != player.floor:
                continue
            color = palette.CYAN if player and other.id == player.id else palette.GREEN
            if inside(other.pos):
                pygame.draw.circle(ctx.screen, color, mp(other.pos), 4)
            elif player and ctx.online_player_id and other.id != player.id:
                edge, angle = self.edge_marker(rect, other.pos, bounds)
                self.triangle(ctx, edge, color, angle, 6)
        if player and ctx.text and ctx.fonts:
            floor_badge = pygame.Rect(rect.x + 8, rect.bottom - 22, 44, 16)
            pygame.draw.rect(ctx.screen, (10, 16, 28), floor_badge, border_radius=5)
            pygame.draw.rect(ctx.screen, palette.CYAN, floor_badge, 1, border_radius=5)
            from client.render.world.render_utils import draw_text_fit
            draw_text_fit(ctx, ctx.text.floor_label(player.floor), floor_badge.inflate(-4, -2), palette.TEXT, ctx.fonts.small, center=True)

    def static_layer(
        self,
        ctx: RenderContext,
        rect: pygame.Rect,
        snapshot: WorldSnapshot,
        bounds: tuple[float, float, float, float],
    ) -> pygame.Surface:
        player = ctx.local_player
        floor = int(player.floor) if player else 0
        quantized_bounds = tuple(int(value // 256) for value in bounds)
        key = MinimapCacheKey(
            map_id=str(getattr(snapshot, "map_id", "default")),
            size=rect.size,
            scale=round(rect.w / max(1.0, bounds[2] - bounds[0]), 5),
            mode="big" if ctx.overlay and ctx.overlay.minimap_big else "small",
            floor=floor,
            bounds=quantized_bounds,
            static_signature=(
                len(snapshot.buildings),
                sum(len(building.walls) + len(building.doors) + len(building.props) for building in snapshot.buildings.values()),
                int(snapshot.map_width) * 31 + int(snapshot.map_height),
            ),
        )
        cached = self.cache.get(key)
        if cached:
            return cached
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        min_x, min_y, max_x, max_y = bounds
        span_x = max(1.0, max_x - min_x)
        span_y = max(1.0, max_y - min_y)
        for building in snapshot.buildings.values():
            if not self.rect_intersects_bounds(building.bounds, bounds):
                continue
            mini = pygame.Rect(
                int((building.bounds.x - min_x) / span_x * rect.w),
                int((building.bounds.y - min_y) / span_y * rect.h),
                max(2, int(building.bounds.w / span_x * rect.w)),
                max(2, int(building.bounds.h / span_y * rect.h)),
            )
            mini.clamp_ip(surface.get_rect())
            pygame.draw.rect(surface, (84, 95, 118), mini, 1)
        for tunnel in tunnel_segments(snapshot.buildings):
            if not self.rect_intersects_bounds(tunnel, bounds):
                continue
            mini = pygame.Rect(
                int((tunnel.x - min_x) / span_x * rect.w),
                int((tunnel.y - min_y) / span_y * rect.h),
                max(2, int(tunnel.w / span_x * rect.w)),
                max(2, int(tunnel.h / span_y * rect.h)),
            )
            mini.clamp_ip(surface.get_rect())
            pygame.draw.rect(surface, (44, 66, 92), mini, 1)
        pygame.draw.rect(surface, (78, 108, 140), surface.get_rect(), 1, border_radius=6)
        self.cache.set(key, surface)
        return surface

    def world_bounds(self, ctx: RenderContext, rect: pygame.Rect, snapshot: WorldSnapshot) -> tuple[float, float, float, float]:
        player = ctx.local_player
        map_w = float(snapshot.map_width or MAP_WIDTH)
        map_h = float(snapshot.map_height or MAP_HEIGHT)
        if not ctx.online_player_id or not player:
            return (0.0, 0.0, map_w, map_h)
        radius_x = ONLINE_MINIMAP_MIN_RADIUS
        radius_y = radius_x * rect.h / max(1, rect.w)
        return (
            max(0.0, player.pos.x - radius_x),
            max(0.0, player.pos.y - radius_y),
            min(map_w, player.pos.x + min(ONLINE_MINIMAP_MAX_RADIUS, radius_x)),
            min(map_h, player.pos.y + min(ONLINE_MINIMAP_MAX_RADIUS, radius_y)),
        )

    def rect_intersects_bounds(self, rect: RectState, bounds: tuple[float, float, float, float]) -> bool:
        min_x, min_y, max_x, max_y = bounds
        return rect.x <= max_x and rect.x + rect.w >= min_x and rect.y <= max_y and rect.y + rect.h >= min_y

    def edge_marker(self, rect: pygame.Rect, pos: Vec2, bounds: tuple[float, float, float, float]) -> tuple[tuple[int, int], float]:
        min_x, min_y, max_x, max_y = bounds
        px = rect.x + (pos.x - min_x) / max(1.0, max_x - min_x) * rect.w
        py = rect.y + (pos.y - min_y) / max(1.0, max_y - min_y) * rect.h
        return (max(rect.x + 8, min(rect.right - 8, int(px))), max(rect.y + 8, min(rect.bottom - 8, int(py)))), math.atan2(py - rect.centery, px - rect.centerx)

    def triangle(self, ctx: RenderContext, center: tuple[int, int], color: tuple[int, int, int], angle: float, radius: int) -> None:
        points = [
            (int(center[0] + math.cos(angle) * radius), int(center[1] + math.sin(angle) * radius)),
            (int(center[0] + math.cos(angle + math.tau * 0.38) * radius), int(center[1] + math.sin(angle + math.tau * 0.38) * radius)),
            (int(center[0] + math.cos(angle - math.tau * 0.38) * radius), int(center[1] + math.sin(angle - math.tau * 0.38) * radius)),
        ]
        pygame.draw.polygon(ctx.screen, (6, 9, 16), [(x + 1, y + 1) for x, y in points])
        pygame.draw.polygon(ctx.screen, color, points)
