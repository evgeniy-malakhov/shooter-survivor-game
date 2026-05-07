from __future__ import annotations

import math
import time

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.world.render_utils import draw_text_fit
from shared.maps.loading import LoadingStage


class LoadingRenderer:
    def __init__(self, app) -> None:
        self.app = app
        self._poster_cache: tuple[tuple[int, int], pygame.Surface] | None = None
        self._spinner_cache: tuple[tuple[int, int], pygame.Surface] | None = None

    def render(self, ctx: RenderContext) -> None:
        app = self.app
        ctx.screen.fill(palette.BG)
        self._poster(ctx)
        snapshot = app.loading_state.snapshot() if app.loading_state else None
        elapsed = max(0.0, time.time() - app._loading_started_at)
        progress = max(snapshot.progress if snapshot else 0.0, min(0.94, 0.08 + elapsed * 0.18))
        if snapshot and snapshot.stage == LoadingStage.READY:
            progress = 1.0
        overlay = pygame.Surface(ctx.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((4, 8, 18, 118))
        ctx.screen.blit(overlay, (0, 0))
        panel = pygame.Rect((ctx.screen.get_width() - 660) // 2, ctx.screen.get_height() - 245, 660, 150)
        glass = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(glass, (10, 16, 30, 202), glass.get_rect(), border_radius=12)
        pygame.draw.rect(glass, palette.CYAN if not app.loading_error else palette.RED, glass.get_rect(), 2, border_radius=12)
        ctx.screen.blit(glass, panel)
        if ctx.text and ctx.fonts:
            title = app.single_map_titles.get(app.single_map_key, app.single_map_key.replace("_", " ").title())
            label = app.loading_error or (snapshot.label if snapshot else ctx.text.tr("loading.init"))
            draw_text_fit(ctx, title, pygame.Rect(panel.x + 112, panel.y + 24, panel.w - 164, 34), palette.TEXT, ctx.fonts.mid)
            draw_text_fit(ctx, label, pygame.Rect(panel.x + 112, panel.y + 62, panel.w - 164, 24), palette.RED if app.loading_error else palette.MUTED, ctx.fonts.normal)
        self._spinner(ctx, pygame.Rect(panel.x + 36, panel.y + 34, 54, 54))
        bar = pygame.Rect(panel.x + 36, panel.bottom - 42, panel.w - 72, 16)
        pygame.draw.rect(ctx.screen, (8, 13, 24), bar, border_radius=8)
        fill = pygame.Rect(bar.x, bar.y, int(bar.w * max(0.0, min(1.0, progress))), bar.h)
        pygame.draw.rect(ctx.screen, palette.CYAN if not app.loading_error else palette.RED, fill, border_radius=8)
        pygame.draw.rect(ctx.screen, (144, 228, 255), bar, 1, border_radius=8)

    def _poster(self, ctx: RenderContext) -> None:
        source = self.app.loading_poster
        if not source:
            return
        scale = max(ctx.screen.get_width() / source.get_width(), ctx.screen.get_height() / source.get_height())
        size = (max(1, int(source.get_width() * scale)), max(1, int(source.get_height() * scale)))
        if self._poster_cache and self._poster_cache[0] == size:
            poster = self._poster_cache[1]
        else:
            poster = pygame.transform.smoothscale(source, size)
            self._poster_cache = (size, poster)
        ctx.screen.blit(poster, ((ctx.screen.get_width() - size[0]) // 2, (ctx.screen.get_height() - size[1]) // 2))

    def _spinner(self, ctx: RenderContext, rect: pygame.Rect) -> None:
        if self.app.loading_spinner:
            if self._spinner_cache and self._spinner_cache[0] == rect.size:
                source = self._spinner_cache[1]
            else:
                source = pygame.transform.smoothscale(self.app.loading_spinner, rect.size)
                self._spinner_cache = (rect.size, source)
            rotated = pygame.transform.rotozoom(source, -(time.time() * 180.0) % 360.0, 1.0)
            ctx.screen.blit(rotated, rotated.get_rect(center=rect.center))
            return
        angle = time.time() * math.tau
        pygame.draw.circle(ctx.screen, (22, 32, 52), rect.center, rect.w // 2, 4)
        for index in range(8):
            a = angle + index * math.tau / 8.0
            pygame.draw.circle(ctx.screen, (76, 225, 255), (int(rect.centerx + math.cos(a) * 22), int(rect.centery + math.sin(a) * 22)), 4)
