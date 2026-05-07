from __future__ import annotations

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.ui.components.button import draw_button
from client.render.world.render_utils import draw_text, draw_text_fit


class ServerBrowserRenderer:
    def __init__(self, app) -> None:
        self.app = app

    def render(self, ctx: RenderContext) -> None:
        app = self.app
        ctx.screen.fill(palette.BG)
        if not ctx.text or not ctx.fonts:
            return
        draw_text(ctx, ctx.text.tr("servers.title"), 72, 90, palette.TEXT, ctx.fonts.big)
        draw_text(ctx, ctx.text.tr("servers.caption"), 76, 150, palette.MUTED, ctx.fonts.normal)
        for index, entry in enumerate(app.server_entries):
            rect = pygame.Rect(72, 190 + index * 72, 720, 56)
            selected = index == app.selected_server
            pygame.draw.rect(ctx.screen, palette.PANEL_2 if selected else palette.PANEL, rect, border_radius=8)
            pygame.draw.rect(ctx.screen, palette.CYAN if selected else (45, 59, 91), rect, 2, border_radius=8)
            draw_text_fit(ctx, entry.name, pygame.Rect(rect.x + 18, rect.y + 8, 160, 26), palette.TEXT, ctx.fonts.mid)
            endpoint = f"{entry.host}:{entry.port}"
            ping = "offline" if entry.ping_ms is None else f"{entry.ping_ms:.0f} ms"
            players = f"{entry.players}/{entry.max_players}" if entry.max_players else str(entry.players)
            draw_text(ctx, endpoint, rect.x + 220, rect.y + 18, palette.MUTED, ctx.fonts.normal)
            draw_text_fit(ctx, f"{ping}  {players}  {entry.status}", pygame.Rect(rect.x + 430, rect.y + 18, 260, 22), palette.GREEN if entry.ready else palette.YELLOW if entry.ping_ms else palette.RED, ctx.fonts.small)
        mouse = app._mouse_pos()
        draw_button(ctx, pygame.Rect(72, 632, 180, 46), ctx.text.tr("servers.back"), pygame.Rect(72, 632, 180, 46).collidepoint(mouse))
        draw_button(ctx, pygame.Rect(270, 632, 180, 46), ctx.text.tr("servers.refresh"), pygame.Rect(270, 632, 180, 46).collidepoint(mouse))
        draw_button(ctx, pygame.Rect(470, 632, 180, 46), ctx.text.tr("servers.connect"), pygame.Rect(470, 632, 180, 46).collidepoint(mouse))
