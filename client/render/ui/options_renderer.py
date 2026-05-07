from __future__ import annotations

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.ui.components.button import draw_button
from client.render.world.render_utils import draw_text, draw_text_fit
from client.settings_schema import tab_toggle_keys


class OptionsRenderer:
    def __init__(self, app) -> None:
        self.app = app

    def render(self, ctx: RenderContext) -> None:
        app = self.app
        ctx.screen.fill(palette.BG)
        MenuBgMixin.draw_neon_background(ctx)
        panel = app._settings_panel_rect()
        pygame.draw.rect(ctx.screen, palette.PANEL, panel, border_radius=10)
        pygame.draw.rect(ctx.screen, palette.CYAN, panel, 2, border_radius=10)
        if not ctx.text or not ctx.fonts:
            return
        draw_text_fit(ctx, ctx.text.tr("settings.title"), pygame.Rect(panel.x + 34, panel.y + 24, panel.w - 68, 58), palette.TEXT, ctx.fonts.big)
        for index, tab in enumerate(app.settings_tabs):
            rect = pygame.Rect(panel.x + 32 + index * 112, panel.y + 106, 102, 36)
            active = tab == app.settings_tab
            pygame.draw.rect(ctx.screen, palette.PANEL_2 if active else palette.BG, rect, border_radius=8)
            pygame.draw.rect(ctx.screen, palette.CYAN if active else palette.MUTED, rect, 1, border_radius=8)
            draw_text_fit(ctx, tab, rect.inflate(-8, -6), palette.TEXT if active else palette.MUTED, ctx.fonts.small, center=True)
        viewport = pygame.Rect(panel.x + 36, panel.y + 162, panel.w - 72, panel.h - 238)
        pygame.draw.rect(ctx.screen, (9, 13, 23), viewport, border_radius=8)
        y = viewport.y + 8 - app.options_scroll
        for key in tab_toggle_keys(app.settings_tab):
            rect = pygame.Rect(viewport.x + 8, y, viewport.w - 16, 44)
            pygame.draw.rect(ctx.screen, palette.PANEL_2, rect, border_radius=7)
            value = bool(app.settings.get(key, False))
            pygame.draw.rect(ctx.screen, palette.GREEN if value else palette.MUTED, rect, 1, border_radius=7)
            draw_text(ctx, ctx.text.tr(f"settings.{key}") if ctx.text.tr(f"settings.{key}") != f"settings.{key}" else key, rect.x + 14, rect.y + 11, palette.TEXT, ctx.fonts.normal)
            draw_text_fit(ctx, "ON" if value else "OFF", pygame.Rect(rect.right - 70, rect.y + 9, 46, 22), palette.GREEN if value else palette.RED, ctx.fonts.small, center=True)
            y += 56
        back = app._settings_back_rect()
        draw_button(ctx, back, ctx.text.tr("settings.back"), back.collidepoint(app._mouse_pos()))


class MenuBgMixin:
    @staticmethod
    def draw_neon_background(ctx: RenderContext) -> None:
        import pygame
        for i in range(18):
            x = 680 + i * 42
            pygame.draw.line(ctx.screen, (18, 36 + i * 3 % 50, 58 + i * 4 % 90), (x, 0), (x - 360, ctx.screen.get_height()), 2)
