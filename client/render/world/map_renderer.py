from __future__ import annotations

import math

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.render_frame import RenderFrame
from client.render.world.render_utils import draw_text_fit, world_rect_to_screen, world_size, world_to_screen
from shared.constants import MAP_HEIGHT, MAP_WIDTH


class MapRenderer:
    def render(self, ctx: RenderContext, frame: RenderFrame) -> None:
        self.paint_background(ctx)
        self.paint_tunnels(ctx, frame)
        self.paint_buildings(ctx, frame)
        if ctx.local_player and ctx.settings.get("noise_radius", False):
            self.paint_noise_radius(ctx)

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

    def paint_tunnels(self, ctx: RenderContext, frame: RenderFrame) -> None:
        player = ctx.local_player
        if not player or player.floor >= 0:
            return
        for index, tunnel in enumerate(frame.tunnels):
            rect = world_rect_to_screen(ctx, tunnel)
            if not rect.colliderect(pygame.Rect(-120, -120, ctx.screen.get_width() + 240, ctx.screen.get_height() + 240)):
                continue
            pulse = 0.5 + 0.5 * math.sin(frame.snapshot.time * 2.6 + index * 0.33)
            pygame.draw.rect(ctx.screen, (8, 12, 18), rect, border_radius=10)
            pygame.draw.rect(ctx.screen, (34, 49, 66), rect, 2, border_radius=10)
            center_line = rect.inflate(-max(8, rect.w // 7), -max(8, rect.h // 7))
            if center_line.w > 6 and center_line.h > 6:
                glow = pygame.Surface(center_line.size, pygame.SRCALPHA)
                pygame.draw.rect(glow, (34, 52, 78, int(42 + pulse * 24)), glow.get_rect(), border_radius=7)
                pygame.draw.rect(glow, (66, 106, 146, int(28 + pulse * 36)), glow.get_rect(), 1, border_radius=7)
                ctx.screen.blit(glow, center_line)
            pygame.draw.circle(ctx.screen, (98, 136, 176), world_to_screen(ctx, tunnel.center), 2)

    def paint_buildings(self, ctx: RenderContext, frame: RenderFrame) -> None:
        player = ctx.local_player
        for building in frame.buildings:
            rect = world_rect_to_screen(ctx, building.bounds)
            if not rect.colliderect(pygame.Rect(-120, -120, ctx.screen.get_width() + 240, ctx.screen.get_height() + 240)):
                continue
            player_inside = bool(player and player.inside_building == building.id)
            fill = (18, 26, 34) if player_inside else (15, 20, 30)
            outline = palette.CYAN if player_inside else (55, 72, 94)
            pygame.draw.rect(ctx.screen, fill, rect, border_radius=3)
            pygame.draw.rect(ctx.screen, outline, rect, 2, border_radius=3)
            if player_inside and ctx.text and ctx.fonts:
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
            for wall in building.walls:
                pygame.draw.rect(ctx.screen, (77, 91, 117), world_rect_to_screen(ctx, wall), border_radius=2)
            for prop in building.props:
                if prop.floor != (player.floor if player_inside and player else 0):
                    continue
                if not player_inside and prop.kind not in {"shelf", "crate", "barrel", "pallet", "roadblock"}:
                    continue
                prop_rect = world_rect_to_screen(ctx, prop.rect)
                if prop.kind == "glass_wall":
                    glass = pygame.Surface(prop_rect.size, pygame.SRCALPHA)
                    pygame.draw.rect(glass, (136, 220, 255, 76), glass.get_rect(), border_radius=3)
                    pygame.draw.rect(glass, (196, 246, 255, 122), glass.get_rect(), 2, border_radius=3)
                    ctx.screen.blit(glass, prop_rect)
                else:
                    color = (111, 92, 72) if prop.kind in {"desk", "table", "pallet"} else (110, 74, 54) if prop.kind == "barrel" else (82, 96, 124)
                    pygame.draw.rect(ctx.screen, color, prop_rect, border_radius=2)
            for stairs in building.stairs:
                if player_inside or not player:
                    pygame.draw.rect(ctx.screen, (86, 126, 164), world_rect_to_screen(ctx, stairs), border_radius=2)
            for door in building.doors:
                if player_inside and player and door.floor != player.floor:
                    continue
                if not player_inside and door.floor != 0:
                    continue
                pygame.draw.rect(ctx.screen, palette.GREEN if door.open else palette.YELLOW, world_rect_to_screen(ctx, door.rect), border_radius=2)

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
