from __future__ import annotations

import pygame

from client.render import palette
from client.render.render_context import RenderContext


def draw_panel(ctx: RenderContext, rect: pygame.Rect, *, accent: tuple[int, int, int] = palette.CYAN) -> None:
    if ctx.ui_cache:
        ctx.screen.blit(ctx.ui_cache.rounded_rect("panel", rect.size, palette.PANEL, accent, outline_width=2, radius=12), rect)
        return
    pygame.draw.rect(ctx.screen, palette.PANEL, rect, border_radius=12)
    pygame.draw.rect(ctx.screen, accent, rect, 2, border_radius=12)

