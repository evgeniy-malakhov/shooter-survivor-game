from __future__ import annotations

import math

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.world.render_utils import draw_item_icon, draw_text, draw_text_fit
from shared.models import WorldSnapshot


def connection_icon_from_state(value: str) -> str:
    if value in {"stable-connection", "unstable-connection", "packet-lost", "lost-connection"}:
        return value
    if value == "stable":
        return "stable-connection"
    if value == "unstable":
        return "unstable-connection"
    if value in {"packet_lost", "packet-lost"}:
        return "packet-lost"
    return "lost-connection" if value == "lost" else "unstable-connection"


class ScoreboardRenderer:
    def render(self, ctx: RenderContext) -> None:
        if ctx.snapshot and ctx.text and ctx.fonts:
            self.paint_scoreboard(ctx, ctx.snapshot)

    def paint_scoreboard(self, ctx: RenderContext, snapshot: WorldSnapshot) -> None:
        overlay = pygame.Surface(ctx.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((4, 7, 18, 206))
        ctx.screen.blit(overlay, (0, 0))
        panel = pygame.Rect((ctx.screen.get_width() - 980) // 2, 96, 980, 520)
        glow = pygame.Surface(panel.inflate(26, 26).size, pygame.SRCALPHA)
        pygame.draw.rect(glow, (76, 225, 255, 34), glow.get_rect(), border_radius=16)
        pygame.draw.rect(glow, (255, 91, 111, 24), glow.get_rect().inflate(-10, -10), 2, border_radius=14)
        ctx.screen.blit(glow, panel.inflate(26, 26))
        pygame.draw.rect(ctx.screen, (15, 20, 38), panel, border_radius=10)
        pygame.draw.rect(ctx.screen, palette.CYAN, panel, 2, border_radius=10)
        pygame.draw.line(ctx.screen, palette.PURPLE, (panel.x + 24, panel.y + 92), (panel.right - 24, panel.y + 92), 2)
        draw_text(ctx, ctx.text.tr("scoreboard.title"), panel.x + 34, panel.y + 24, palette.TEXT, ctx.fonts.big)
        headers = [
            ctx.text.tr("scoreboard.player"),
            ctx.text.tr("scoreboard.floor"),
            ctx.text.tr("scoreboard.total"),
            ctx.text.tr("scoreboard.walker"),
            ctx.text.tr("scoreboard.runner"),
            ctx.text.tr("scoreboard.brute"),
            ctx.text.tr("scoreboard.leaper"),
            ctx.text.tr("scoreboard.ping"),
            ctx.text.tr("scoreboard.status"),
        ]
        xs = [panel.x + 42, panel.x + 286, panel.x + 350, panel.x + 426, panel.x + 506, panel.x + 586, panel.x + 666, panel.x + 746, panel.x + 832]
        for x, header in zip(xs, headers):
            draw_text(ctx, header, x, panel.y + 112, palette.CYAN if header == ctx.text.tr("scoreboard.total") else palette.MUTED, ctx.fonts.small)
        viewport = pygame.Rect(panel.x + 22, panel.y + 146, panel.w - 44, panel.h - 176)
        previous_clip = ctx.screen.get_clip()
        ctx.screen.set_clip(viewport)
        scroll = ctx.overlay.scoreboard_scroll if ctx.overlay else 0
        y = panel.y + 150 - scroll
        active_id = ctx.local_player_id or ctx.online_player_id
        for player in sorted(snapshot.players.values(), key=lambda p: p.score, reverse=True):
            row = pygame.Rect(panel.x + 30, y - 8, panel.w - 60, 42)
            if not row.colliderect(viewport.inflate(0, 24)):
                y += 52
                continue
            row_color = (28, 42, 66) if player.alive else (48, 20, 31)
            border = palette.CYAN if player.id == active_id else palette.GREEN if player.alive else palette.RED
            pygame.draw.rect(ctx.screen, row_color, row, border_radius=7)
            pygame.draw.rect(ctx.screen, border, row, 1, border_radius=7)
            if not player.alive:
                draw_item_icon(ctx, "dead", pygame.Rect(xs[0], y - 3, 24, 24), aura=False, shadow=False)
                name_x = xs[0] + 30
            else:
                pygame.draw.circle(ctx.screen, palette.GREEN, (xs[0] + 10, y + 9), 6)
                name_x = xs[0] + 22
            values = [
                ctx.text.floor_label(player.floor),
                str(player.score),
                str(player.kills_by_kind.get("walker", 0)),
                str(player.kills_by_kind.get("runner", 0)),
                str(player.kills_by_kind.get("brute", 0)),
                str(player.kills_by_kind.get("leaper", 0)),
                self.format_ping(player.ping_ms),
                ctx.text.tr("state.alive") if player.alive else ctx.text.tr("state.dead"),
            ]
            draw_text_fit(
                ctx,
                f"{player.name}{'' if player.alive else ' - ' + ctx.text.tr('state.dead')}",
                pygame.Rect(name_x, y, xs[1] - name_x - 12, 22),
                palette.TEXT if player.alive else palette.RED,
                ctx.fonts.emphasis if player.id == active_id else ctx.fonts.normal,
            )
            for index, (x, value) in enumerate(zip(xs[1:], values), start=1):
                if index == len(values):
                    quality = connection_icon_from_state(player.connection_quality)
                    icon_rect = pygame.Rect(x, y - 3, 22, 22)
                    if not draw_item_icon(ctx, quality, icon_rect, aura=False, shadow=False):
                        pygame.draw.circle(ctx.screen, palette.RED if not player.alive else palette.GREEN, icon_rect.center, 7)
                    draw_text_fit(ctx, value, pygame.Rect(x + 28, y, panel.right - x - 48, 20), palette.RED if not player.alive else palette.TEXT, ctx.fonts.small)
                elif index == 1:
                    badge = pygame.Rect(x, y - 2, 46, 24)
                    pygame.draw.rect(ctx.screen, (11, 18, 30), badge, border_radius=7)
                    pygame.draw.rect(ctx.screen, palette.PURPLE if player.floor < 0 else palette.CYAN, badge, 1, border_radius=7)
                    draw_text_fit(ctx, value, badge.inflate(-6, -3), palette.TEXT, ctx.fonts.small, center=True)
                else:
                    draw_text_fit(ctx, value, pygame.Rect(x, y, 66, 22), palette.YELLOW if index == 2 else palette.TEXT, ctx.fonts.normal)
            y += 52
        ctx.screen.set_clip(previous_clip)
        self.paint_scrollbar(ctx, snapshot, viewport)

    def paint_scrollbar(self, ctx: RenderContext, snapshot: WorldSnapshot, viewport: pygame.Rect) -> None:
        max_scroll = self.max_scroll(snapshot)
        if not ctx.overlay or max_scroll <= 0:
            if ctx.overlay:
                ctx.overlay.scoreboard_scroll = 0
            return
        track = pygame.Rect(viewport.right + 6, viewport.y, 10, viewport.h)
        pygame.draw.rect(ctx.screen, (10, 16, 28), track, border_radius=5)
        pygame.draw.rect(ctx.screen, (58, 76, 108), track, 1, border_radius=5)
        knob_h = max(42, int(track.h * track.h / max(track.h, len(snapshot.players) * 52)))
        knob_y = track.y + int((track.h - knob_h) * (ctx.overlay.scoreboard_scroll / max_scroll))
        knob = pygame.Rect(track.x + 2, knob_y, track.w - 4, knob_h)
        pulse = (math.sin((ctx.now or 0.0) * 5.5) + 1.0) * 0.5
        pygame.draw.rect(ctx.screen, (86, 228, 255), knob, border_radius=4)
        pygame.draw.rect(ctx.screen, (210, 250, 255, int(110 + pulse * 100)), knob, 1, border_radius=4)

    def max_scroll(self, snapshot: WorldSnapshot) -> int:
        return max(0, len(snapshot.players) * 52 - (520 - 176) + 12)

    def format_ping(self, ping_ms: float | int | None) -> str:
        if ping_ms is None or float(ping_ms) <= 0.0:
            return "--"
        if float(ping_ms) >= 1000.0:
            return "999+"
        return f"{float(ping_ms):.0f} ms"

