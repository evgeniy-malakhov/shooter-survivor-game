from __future__ import annotations

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.ui.settings_overlay_renderer import SettingsOverlayRenderer


class OptionsRenderer:
    def __init__(self, app) -> None:
        self.app = app
        self.settings_renderer = SettingsOverlayRenderer(app)

    def render(self, ctx: RenderContext) -> None:
        ctx.screen.fill(palette.BG)
        MenuBgMixin.draw_neon_background(ctx)
        if not ctx.text or not ctx.fonts:
            return
        self.settings_renderer._render_settings_panel(ctx, in_game=False)


class MenuBgMixin:
    @staticmethod
    def draw_neon_background(ctx: RenderContext) -> None:
        for i in range(18):
            x = 680 + i * 42
            pygame.draw.line(ctx.screen, (18, 36 + i * 3 % 50, 58 + i * 4 % 90), (x, 0), (x - 360, ctx.screen.get_height()), 2)

