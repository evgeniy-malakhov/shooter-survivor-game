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
        self._last_dynamic_update_at = 0.0
        self._last_surface: pygame.Surface | None = None
        self._last_rect_size: tuple[int, int] | None = None

    def render(self, ctx: RenderContext) -> None:
        started = time.perf_counter()
        rect = self.rect(ctx)
        rate = ctx.quality.minimap_update_rate if ctx.quality else 10.0
        interval = 1.0 / max(1.0, rate)
        now = ctx.now or time.time()
        if (
            self._last_surface is not None
            and self._last_rect_size == rect.size
            and now - self._last_dynamic_update_at < interval
        ):
            ctx.screen.blit(self._last_surface, rect)
        elif ctx.snapshot:
            self.paint_minimap(ctx, ctx.snapshot)
            self._last_surface = ctx.screen.subsurface(rect).copy()
            self._last_rect_size = rect.size
            self._last_dynamic_update_at = now
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
        for zone in getattr(snapshot, "horde_pressure_zones", {}).values():
            if not isinstance(zone, dict):
                zone = zone.to_dict()
            if player and int(zone.get("floor", 0)) != player.floor:
                continue
            raw_center = zone.get("center")
            if not isinstance(raw_center, dict):
                continue
            center = Vec2.from_dict(raw_center)
            if not inside(center):
                continue
            pressure = max(0.0, min(1.0, float(zone.get("pressure", 0.0))))
            radius = int(max(8, float(zone.get("radius", 700.0)) / span_x * rect.w))
            marker = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(marker, (255, 56, 76, int(28 + pressure * 76)), (radius, radius), radius)
            pygame.draw.circle(marker, (255, 96, 112, int(80 + pressure * 110)), (radius, radius), radius, 1)
            pos = mp(center)
            ctx.screen.blit(marker, (pos[0] - radius, pos[1] - radius))
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
        for civilian in getattr(snapshot, "civilians", {}).values():
            data = civilian if isinstance(civilian, dict) else civilian.to_dict()
            if player and int(data.get("floor", 0)) != player.floor:
                continue
            raw_pos = data.get("pos")
            if not isinstance(raw_pos, dict):
                continue
            pos = Vec2.from_dict(raw_pos)
            if inside(pos):
                color = (255, 214, 110) if float(data.get("panic", 0.0)) > 0.6 else (180, 224, 170)
                pygame.draw.circle(ctx.screen, color, mp(pos), 3)
        for safe_zone in getattr(snapshot, "safe_zones", {}).values():
            data = safe_zone if isinstance(safe_zone, dict) else safe_zone.to_dict()
            if player and int(data.get("floor", 0)) != player.floor:
                continue
            raw_pos = data.get("pos")
            if not isinstance(raw_pos, dict):
                continue
            pos = Vec2.from_dict(raw_pos)
            if not inside(pos):
                continue
            status = str(data.get("status", "inactive"))
            active = status == "active"
            color = (76, 235, 154) if active else (120, 190, 210)
            radius = max(5, int(float(data.get("radius", 420.0)) / span_x * rect.w))
            marker = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(marker, (*color, 38 if active else 24), (radius, radius), radius)
            pygame.draw.circle(marker, (*color, 180 if active else 110), (radius, radius), radius, 1)
            center = mp(pos)
            ctx.screen.blit(marker, (center[0] - radius, center[1] - radius))
            pygame.draw.rect(ctx.screen, color, pygame.Rect(center[0] - 3, center[1] - 3, 6, 6), border_radius=2)
        for convoy in getattr(snapshot, "supply_convoys", {}).values():
            data = convoy if isinstance(convoy, dict) else convoy.to_dict()
            if str(data.get("status", "en_route")) != "en_route":
                continue
            if player and int(data.get("floor", 0)) != player.floor:
                continue
            raw_pos = data.get("pos")
            raw_target = data.get("target_pos")
            if not isinstance(raw_pos, dict):
                continue
            pos = Vec2.from_dict(raw_pos)
            if not inside(pos):
                continue
            point = mp(pos)
            pygame.draw.circle(ctx.screen, (106, 180, 255), point, 3)
            if isinstance(raw_target, dict):
                target = Vec2.from_dict(raw_target)
                if inside(target):
                    pygame.draw.line(ctx.screen, (106, 180, 255, 120), point, mp(target), 1)
        for mission in getattr(snapshot, "missions", {}).values():
            data = mission if isinstance(mission, dict) else mission.to_dict()
            if str(data.get("status", "available")) not in {"available", "active"}:
                continue
            if player and int(data.get("floor", 0)) != player.floor:
                continue
            raw_pos = data.get("target_pos")
            if not isinstance(raw_pos, dict):
                continue
            pos = Vec2.from_dict(raw_pos)
            if inside(pos):
                center = mp(pos)
                pygame.draw.circle(ctx.screen, (255, 226, 84), center, 5, 1)
                pygame.draw.circle(ctx.screen, (255, 226, 84), center, 2)
        for extraction in getattr(snapshot, "extraction_points", {}).values():
            data = extraction if isinstance(extraction, dict) else extraction.to_dict()
            if str(data.get("status", "closed")) == "closed":
                continue
            if player and int(data.get("floor", 0)) != player.floor:
                continue
            raw_pos = data.get("pos")
            if not isinstance(raw_pos, dict):
                continue
            pos = Vec2.from_dict(raw_pos)
            if inside(pos):
                color = (255, 112, 96) if str(data.get("status")) == "contested" else (88, 255, 198)
                self.triangle(ctx, mp(pos), color, -math.pi * 0.5, 7)
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
        if floor < 0:
            for tunnel in tunnel_segments(snapshot.buildings):
                if not self.rect_intersects_bounds(tunnel, bounds):
                    continue
                mini = pygame.Rect(
                    int((tunnel.x - min_x) / span_x * rect.w),
                    int((tunnel.y - min_y) / span_y * rect.h),
                    max(1, int(tunnel.w / span_x * rect.w)),
                    max(1, int(tunnel.h / span_y * rect.h)),
                )
                mini.clamp_ip(surface.get_rect())
                pygame.draw.rect(surface, (35, 52, 76, 52), mini, border_radius=2)
                pygame.draw.rect(surface, (74, 108, 148, 70), mini, 1, border_radius=2)
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
