from __future__ import annotations

import math

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.ui.components.button import draw_button
from client.render.world.render_utils import draw_text_fit


class SingleSetupRenderer:
    def __init__(self, app) -> None:
        self.app = app

    def render(self, ctx: RenderContext) -> None:
        app = self.app
        ctx.screen.fill(palette.BG)
        panel = pygame.Rect((ctx.screen.get_width() - 660) // 2, 120, 660, 500)
        pygame.draw.rect(ctx.screen, palette.PANEL, panel, border_radius=12)
        pygame.draw.rect(ctx.screen, palette.CYAN, panel, 2, border_radius=12)
        if not ctx.text or not ctx.fonts:
            return
        draw_text_fit(ctx, ctx.text.tr("single.setup.title"), pygame.Rect(panel.x + 24, panel.y + 28, panel.w - 48, 42), palette.TEXT, ctx.fonts.big, center=True)
        rows = [
            (ctx.text.tr("single.setup.map"), app.single_map_titles.get(app.single_map_key, app.single_map_key.replace("_", " ").title())),
            (ctx.text.tr("single.setup.difficulty"), ctx.text.tr(f"difficulty.{app.difficulty_key}")),
            (ctx.text.tr("single.setup.bots"), ctx.text.tr("state.on") if app.single_bots_enabled else ctx.text.tr("state.off")),
            (ctx.text.tr("single.setup.bot_density"), ctx.text.tr(f"density.{app.bot_density}")),
        ]
        mouse = app._mouse_pos()
        for index, (left, right) in enumerate(rows):
            rect = pygame.Rect(panel.x + 56, panel.y + 130 + index * 70, panel.w - 112, 50)
            pygame.draw.rect(ctx.screen, palette.PANEL_2 if rect.collidepoint(mouse) else palette.PANEL, rect, border_radius=10)
            pygame.draw.rect(ctx.screen, palette.CYAN, rect, 2, border_radius=10)
            draw_text_fit(ctx, left, pygame.Rect(rect.x + 16, rect.y + 14, rect.w - 180, 22), palette.TEXT, ctx.fonts.normal)
            draw_text_fit(ctx, right, pygame.Rect(rect.right - 190, rect.y + 14, 170, 22), palette.CYAN, ctx.fonts.hud_title, center=True)
        if app.single_map_dropdown_alpha > 0.01:
            self._draw_dropdown(ctx, panel)
        back_rect = pygame.Rect(panel.x + 56, panel.bottom - 72, 230, 46)
        start_rect = pygame.Rect(panel.right - 286, panel.bottom - 72, 230, 46)
        draw_button(ctx, back_rect, ctx.text.tr("settings.back"), back_rect.collidepoint(mouse))
        draw_button(ctx, start_rect, ctx.text.tr("single.setup.start"), start_rect.collidepoint(mouse))

    def _draw_dropdown(self, ctx: RenderContext, panel: pygame.Rect) -> None:
        app = self.app
        row = pygame.Rect(panel.x + 56, panel.y + 130, panel.w - 112, 50)
        options = list(app.single_map_options)
        popup = pygame.Rect(row.x, row.bottom + 6, row.w, max(58, 20 + len(options) * 36))
        pygame.draw.rect(ctx.screen, (14, 20, 32), popup, border_radius=10)
        pygame.draw.rect(ctx.screen, palette.CYAN, popup, 2, border_radius=10)
        for index, option in enumerate(options):
            item = pygame.Rect(popup.x + 10, popup.y + 10 + index * 36, popup.w - 30, 30)
            pygame.draw.rect(ctx.screen, palette.PANEL_2 if item.collidepoint(app._mouse_pos()) else palette.BG, item, border_radius=7)
            pygame.draw.rect(ctx.screen, palette.CYAN if option == app.single_map_key else (64, 84, 116), item, 1, border_radius=7)
            if ctx.text and ctx.fonts:
                title = app.single_map_titles.get(option, option.replace("_", " ").title())
                draw_text_fit(ctx, title.upper(), item.inflate(-10, -6), palette.CYAN if option == app.single_map_key else palette.TEXT, ctx.fonts.normal)

