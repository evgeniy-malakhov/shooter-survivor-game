from __future__ import annotations

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.world.render_utils import draw_text, draw_text_fit


class SettingsOverlayRenderer:
    def render(self, ctx: RenderContext) -> None:
        if not ctx.fonts or not ctx.text:
            return
        overlay = pygame.Surface(ctx.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((1, 3, 8, 166))
        ctx.screen.blit(overlay, (0, 0))
        panel = pygame.Rect(220, 82, 840, 590)
        pygame.draw.rect(ctx.screen, palette.PANEL, panel, border_radius=10)
        pygame.draw.rect(ctx.screen, palette.CYAN, panel, 2, border_radius=10)
        draw_text_fit(ctx, ctx.text.tr("settings.pause"), pygame.Rect(panel.x + 34, panel.y + 24, panel.w - 68, 58), palette.TEXT, ctx.fonts.big)
        y = panel.y + 112
        for key, value in ctx.settings.items():
            rect = pygame.Rect(panel.x + 44, y, panel.w - 88, 42)
            pygame.draw.rect(ctx.screen, palette.PANEL_2, rect, border_radius=7)
            pygame.draw.rect(ctx.screen, palette.CYAN if value else palette.MUTED, rect, 1, border_radius=7)
            draw_text(ctx, ctx.text.tr(f"settings.{key}") if ctx.text.tr(f"settings.{key}") != f"settings.{key}" else key, rect.x + 14, rect.y + 11, palette.TEXT, ctx.fonts.normal)
            draw_text_fit(ctx, "ON" if value else "OFF", pygame.Rect(rect.right - 70, rect.y + 9, 46, 22), palette.GREEN if value else palette.RED, ctx.fonts.small, center=True)
            y += 50
