from __future__ import annotations

import math

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.ui.components.button import draw_button
from client.render.world.render_utils import draw_text_fit
from shared.game_modes import get_game_mode


class SingleSetupRenderer:
    def __init__(self, app) -> None:
        self.app = app

    def render(self, ctx: RenderContext) -> None:
        app = self.app
        ctx.screen.fill(palette.BG)
        panel = pygame.Rect((ctx.screen.get_width() - 700) // 2, 90, 700, 590)
        pygame.draw.rect(ctx.screen, palette.PANEL, panel, border_radius=12)
        pygame.draw.rect(ctx.screen, palette.CYAN, panel, 2, border_radius=12)
        if not ctx.text or not ctx.fonts:
            return
        draw_text_fit(ctx, ctx.text.tr("single.setup.title"), pygame.Rect(panel.x + 24, panel.y + 28, panel.w - 48, 42), palette.TEXT, ctx.fonts.big, center=True)
        mode = get_game_mode(app.single_game_mode_key)
        faction_key = f"faction.{app.single_player_faction}"
        faction_label = ctx.text.tr(faction_key)
        if faction_label == faction_key:
            faction_label = app.single_player_faction.replace("_", " ").title()
        rows = [
            (ctx.text.tr("single.setup.map"), app.single_map_titles.get(app.single_map_key, app.single_map_key.replace("_", " ").title())),
            (ctx.text.tr("single.setup.mode"), ctx.text.tr(mode.title_key)),
            (ctx.text.tr("single.setup.faction"), faction_label),
            (ctx.text.tr("single.setup.difficulty"), ctx.text.tr(f"difficulty.{app.difficulty_key}")),
            (ctx.text.tr("single.setup.bots"), ctx.text.tr("state.on") if app.single_bots_enabled else ctx.text.tr("state.off")),
            (ctx.text.tr("single.setup.bot_density"), ctx.text.tr(f"density.{app.bot_density}")),
        ]
        mouse = app._mouse_pos()
        for index, (left, right) in enumerate(rows):
            rect = pygame.Rect(panel.x + 56, panel.y + 120 + index * 58, panel.w - 112, 46)
            disabled = (index in {3, 5}) and not app.single_bots_enabled
            border = self._row_color(index, app)
            pygame.draw.rect(ctx.screen, palette.PANEL_2 if rect.collidepoint(mouse) and not disabled else palette.PANEL, rect, border_radius=10)
            pygame.draw.rect(ctx.screen, (72, 78, 96) if disabled else border, rect, 2, border_radius=10)
            draw_text_fit(ctx, left, pygame.Rect(rect.x + 16, rect.y + 12, rect.w - 200, 22), palette.MUTED if disabled else palette.TEXT, ctx.fonts.normal)
            draw_text_fit(ctx, right, pygame.Rect(rect.right - 210, rect.y + 12, 190, 22), (104, 110, 126) if disabled else border, ctx.fonts.hud_title, center=True)
        desc = ctx.text.tr(mode.description_key)
        draw_text_fit(ctx, desc, pygame.Rect(panel.x + 56, panel.bottom - 118, panel.w - 112, 24), palette.MUTED, ctx.fonts.small, center=True)
        if app.single_map_dropdown_alpha > 0.01:
            self._draw_dropdown(ctx, panel)
        back_rect = pygame.Rect(panel.x + 56, panel.bottom - 72, 230, 46)
        start_rect = pygame.Rect(panel.right - 286, panel.bottom - 72, 230, 46)
        draw_button(ctx, back_rect, ctx.text.tr("settings.back"), back_rect.collidepoint(mouse))
        draw_button(ctx, start_rect, ctx.text.tr("single.setup.start"), start_rect.collidepoint(mouse))

    def _draw_dropdown(self, ctx: RenderContext, panel: pygame.Rect) -> None:
        app = self.app
        row = pygame.Rect(panel.x + 56, panel.y + 120, panel.w - 112, 46)
        options = list(app.single_map_options)
        popup = pygame.Rect(row.x, row.bottom + 6, row.w, max(58, 20 + len(options) * 32))
        pygame.draw.rect(ctx.screen, (14, 20, 32), popup, border_radius=10)
        pygame.draw.rect(ctx.screen, palette.CYAN, popup, 2, border_radius=10)
        for index, option in enumerate(options):
            item = pygame.Rect(popup.x + 10, popup.y + 10 + index * 32, popup.w - 30, 26)
            pygame.draw.rect(ctx.screen, palette.PANEL_2 if item.collidepoint(app._mouse_pos()) else palette.BG, item, border_radius=7)
            pygame.draw.rect(ctx.screen, palette.CYAN if option == app.single_map_key else (64, 84, 116), item, 1, border_radius=7)
            if ctx.text and ctx.fonts:
                title = app.single_map_titles.get(option, option.replace("_", " ").title())
                draw_text_fit(ctx, title.upper(), item.inflate(-10, -6), palette.CYAN if option == app.single_map_key else palette.TEXT, ctx.fonts.normal)

    def _row_color(self, index: int, app) -> tuple[int, int, int]:
        if index == 3:
            return {
                "easy": (78, 220, 142),
                "medium": (255, 211, 92),
                "hard": (255, 139, 80),
                "insane": (255, 76, 118),
            }.get(app.difficulty_key, palette.CYAN)
        if index == 4:
            return palette.GREEN if app.single_bots_enabled else palette.RED
        if index == 5:
            return {"low": palette.GREEN, "normal": palette.CYAN, "high": palette.YELLOW}.get(app.bot_density, palette.CYAN)
        if index == 1:
            return palette.PURPLE
        if index == 2:
            return palette.YELLOW
        return palette.CYAN

