from __future__ import annotations

import math

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.ui.components.button import draw_button
from client.render.world.render_utils import draw_item_icon, draw_text, draw_text_fit


class MenuRenderer:
    def __init__(self, app) -> None:
        self.app = app

    def render(self, ctx: RenderContext) -> None:
        ctx.screen.fill(palette.BG)
        self._draw_neon_background(ctx)
        panel = pygame.Rect(48, (ctx.screen.get_height() - 580) // 2, 420, 580)
        pulse = (math.sin((ctx.now or 0.0) * 2.8) + 1.0) * 0.5
        pygame.draw.rect(ctx.screen, (10, 15, 25), panel, border_radius=12)
        pygame.draw.rect(ctx.screen, palette.CYAN, panel, 2, border_radius=12)
        glow = pygame.Surface(panel.inflate(26, 26).size, pygame.SRCALPHA)
        pygame.draw.rect(glow, (76, 225, 255, int(22 + pulse * 34)), glow.get_rect(), 2, border_radius=16)
        ctx.screen.blit(glow, panel.inflate(26, 26))
        if ctx.text and ctx.fonts:
            draw_text_fit(ctx, ctx.text.tr("app.title"), pygame.Rect(panel.x + 28, panel.y + 32, panel.w - 56, 64), palette.TEXT, ctx.fonts.big, center=True)
            draw_text_fit(ctx, ctx.text.tr("menu.subtitle"), pygame.Rect(panel.x + 30, panel.y + 110, panel.w - 60, 24), palette.CYAN, ctx.fonts.normal, center=True)
            draw_text_fit(ctx, ctx.text.tr("menu.caption"), pygame.Rect(panel.x + 30, panel.y + 140, panel.w - 60, 20), palette.MUTED, ctx.fonts.small, center=True)
            mouse = pygame.mouse.get_pos()
            mouse = self.app._display_to_screen(mouse)
            for button in self.app._menu_buttons:
                draw_button(ctx, button.rect, ctx.text.tr(button.label), button.hovered(mouse))
            self._draw_showcase(ctx)

    def _draw_neon_background(self, ctx: RenderContext) -> None:
        for i in range(18):
            x = 680 + i * 42
            pygame.draw.line(ctx.screen, (18, 36 + i * 3 % 50, 58 + i * 4 % 90), (x, 0), (x - 360, ctx.screen.get_height()), 2)
        pygame.draw.circle(ctx.screen, (20, 62, 92), (1050, 180), 210, 2)
        pygame.draw.circle(ctx.screen, (54, 31, 91), (1040, 180), 140, 2)

    def _draw_showcase(self, ctx: RenderContext) -> None:
        if not ctx.text or not ctx.fonts:
            return
        pulse = (math.sin((ctx.now or 0.0) * 3.3) + 1.0) * 0.5
        showcase = pygame.Rect(492, 96, 662, 548)
        pygame.draw.rect(ctx.screen, (12, 18, 28), showcase, border_radius=10)
        pygame.draw.rect(ctx.screen, (58, 78, 108), showcase, 2, border_radius=10)
        outline = pygame.Surface((676, 562), pygame.SRCALPHA)
        pygame.draw.rect(outline, (104, 198, 255, int(16 + pulse * 48)), outline.get_rect(), 1, border_radius=12)
        ctx.screen.blit(outline, (485, 89))
        draw_text(ctx, ctx.text.tr("menu.systems"), 536, 132, palette.TEXT, ctx.fonts.big)
        cards = [
            (ctx.text.tr("menu.card.stealth.title"), ctx.text.tr("menu.card.stealth.body"), palette.CYAN, "silence"),
            (ctx.text.tr("menu.card.ai.title"), ctx.text.tr("menu.card.ai.body"), palette.YELLOW, "ai"),
            (ctx.text.tr("menu.card.craft.title"), ctx.text.tr("menu.card.craft.body"), palette.GREEN, "loot"),
            (ctx.text.tr("menu.card.online.title"), ctx.text.tr("menu.card.online.body"), palette.PURPLE, "online"),
        ]
        for index, (title, body, color, image_key) in enumerate(cards):
            rect = pygame.Rect(530, 226 + index * 92, 556, 74)
            pygame.draw.rect(ctx.screen, palette.PANEL, rect, border_radius=8)
            pygame.draw.rect(ctx.screen, (54, 74, 104), rect, 1, border_radius=8)
            image_rect = pygame.Rect(rect.x + 14, rect.y + 11, 52, 52)
            pygame.draw.rect(ctx.screen, (10, 16, 28), image_rect, border_radius=9)
            pygame.draw.rect(ctx.screen, color, image_rect, 2, border_radius=9)
            draw_item_icon(ctx, image_key, image_rect.inflate(-8, -8), aura=False, shadow=False)
            draw_text(ctx, title, rect.x + 80, rect.y + 10, palette.TEXT, ctx.fonts.mid)
            draw_text(ctx, body, rect.x + 82, rect.y + 44, palette.MUTED, ctx.fonts.small)
