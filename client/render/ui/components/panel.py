from __future__ import annotations

import pygame

from client.render import palette
from client.render.render_context import RenderContext


def draw_panel(ctx: RenderContext, rect: pygame.Rect, *, accent: tuple[int, int, int] = palette.CYAN) -> None:
    pygame.draw.rect(ctx.screen, palette.PANEL, rect, border_radius=12)
    pygame.draw.rect(ctx.screen, accent, rect, 2, border_radius=12)

