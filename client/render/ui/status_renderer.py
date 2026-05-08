from __future__ import annotations

import math

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.ui.minimap_renderer import MinimapRenderer
from client.render.world.render_utils import draw_item_icon, draw_text_fit


class StatusRenderer:
    def __init__(self, minimap: MinimapRenderer) -> None:
        self.minimap = minimap

    def render(self, ctx: RenderContext, *, connection_quality: str = "stable-connection", error: str = "") -> None:
        if ctx.snapshot and ctx.settings.get("show_zombie_count", False):
            self.paint_zombie_counter(ctx)
        if ctx.online_player_id:
            self.paint_connection_status(ctx, connection_quality)
            self.paint_network_notice(ctx, connection_quality, error)

    def paint_zombie_counter(self, ctx: RenderContext) -> None:
        if not ctx.snapshot or not ctx.text or not ctx.fonts:
            return
        minimap = self.minimap.rect(ctx)
        rect = pygame.Rect(minimap.x, minimap.bottom + 12, minimap.w, 42)
        pulse = (math.sin((ctx.now or 0.0) * 3.6) + 1.0) * 0.5
        bg = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (20, 13, 24, 220), bg.get_rect(), border_radius=9)
        pygame.draw.rect(bg, (255, 91, 111, int(110 + pulse * 70)), bg.get_rect(), 2, border_radius=9)
        ctx.screen.blit(bg, rect)
        icon_rect = pygame.Rect(rect.x + 12, rect.y + 8, 26, 26)
        if not draw_item_icon(ctx, "dead", icon_rect, aura=False, shadow=False):
            pygame.draw.circle(ctx.screen, palette.RED, icon_rect.center, 10)
        draw_text_fit(ctx, ctx.text.tr("hud.zombies"), pygame.Rect(rect.x + 44, rect.y + 7, rect.w - 96, 15), palette.MUTED, ctx.fonts.small)
        draw_text_fit(ctx, str(len(ctx.snapshot.zombies)), pygame.Rect(rect.right - 58, rect.y + 5, 42, 30), palette.RED, ctx.fonts.mid, center=True)

    def paint_connection_status(self, ctx: RenderContext, quality: str) -> None:
        if quality == "stable-connection":
            return
        minimap = self.minimap.rect(ctx)
        rect = pygame.Rect(minimap.x - 54, minimap.y + 8, 38, 38)
        color = {
            "stable-connection": palette.GREEN,
            "unstable-connection": palette.YELLOW,
            "packet-lost": palette.RED,
            "lost-connection": palette.RED,
        }.get(quality, palette.MUTED)
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(surface, (10, 16, 28, 206), surface.get_rect(), border_radius=8)
        pygame.draw.rect(surface, (*color, 170), surface.get_rect(), 1, border_radius=8)
        ctx.screen.blit(surface, rect)
        icon_rect = pygame.Rect(rect.x + 7, rect.y + 7, 24, 24)
        if not draw_item_icon(ctx, quality, icon_rect, aura=False, shadow=False):
            pygame.draw.circle(ctx.screen, color, icon_rect.center, 8)

    def paint_network_notice(self, ctx: RenderContext, quality: str, error: str) -> None:
        if not ctx.text or not ctx.fonts:
            return
        if quality == "stable-connection" and not error:
            return
        color = {"unstable-connection": palette.YELLOW, "packet-lost": palette.RED, "lost-connection": palette.RED}.get(quality, palette.CYAN)
        key = {
            "unstable-connection": "online.notice.unstable",
            "packet-lost": "online.notice.packet_loss",
            "lost-connection": "online.notice.lost",
        }.get(quality, "online.notice.reconnecting")
        text = error if error and quality == "lost-connection" else ctx.text.tr(key)
        rect = pygame.Rect(0, 0, 420, 38)
        rect.center = (ctx.screen.get_width() // 2, 34)
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(surface, (9, 14, 26, 220), surface.get_rect(), border_radius=10)
        pygame.draw.rect(surface, (*color, 180), surface.get_rect(), 1, border_radius=10)
        ctx.screen.blit(surface, rect)
        icon_rect = pygame.Rect(rect.x + 14, rect.y + 7, 24, 24)
        if not draw_item_icon(ctx, quality, icon_rect, aura=False, shadow=False):
            pygame.draw.circle(ctx.screen, color, icon_rect.center, 8)
        draw_text_fit(ctx, text, pygame.Rect(rect.x + 46, rect.y + 9, rect.w - 62, 18), palette.TEXT, ctx.fonts.small, center=True)

