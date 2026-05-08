from __future__ import annotations

import math

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.world.render_utils import draw_text_fit


def draw_button(ctx: RenderContext, rect: pygame.Rect, label: str, hovered: bool) -> None:
    pulse = (math.sin((ctx.now or 0.0) * 5.0 + rect.x * 0.01) + 1.0) * 0.5
    cache = ctx.ui_cache
    if hovered:
        if cache:
            ctx.screen.blit(cache.rounded_rect("button-hover", rect.size, (40, 55, 85), palette.CYAN, outline_width=3, radius=10), rect)
        else:
            pygame.draw.rect(ctx.screen, (40, 55, 85), rect, border_radius=10)
            pygame.draw.rect(ctx.screen, palette.CYAN, rect, 3, border_radius=10)
        pygame.draw.rect(ctx.screen, (76, 225, 255, 30), rect.inflate(-6, -6), 2, border_radius=8)
    else:
        if cache:
            ctx.screen.blit(cache.rounded_rect("button", rect.size, palette.PANEL, (53, 68, 98), outline_width=2, radius=10), rect)
        else:
            pygame.draw.rect(ctx.screen, palette.PANEL, rect, border_radius=10)
            pygame.draw.rect(ctx.screen, (53, 68, 98), rect, 2, border_radius=10)
    glow = pygame.Surface(rect.inflate(12, 12).size, pygame.SRCALPHA)
    pygame.draw.rect(glow, (88, 204, 255, int(12 + pulse * 34)), glow.get_rect(), 1, border_radius=12)
    ctx.screen.blit(glow, rect.inflate(12, 12))
    if ctx.fonts:
        draw_text_fit(ctx, label, rect.inflate(-24, -12), palette.TEXT if hovered else (200, 210, 230), ctx.fonts.mid if hovered else ctx.fonts.normal, center=True)

