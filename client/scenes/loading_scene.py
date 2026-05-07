from __future__ import annotations

from typing import Any

import pygame

from client.game.loading_service import LoadingService
from client.render.render_context import RenderContext
from client.render.ui.loading_renderer import LoadingRenderer


class LoadingScene:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.loading = LoadingService(app)
        self.renderer = LoadingRenderer(app)

    def handle_events(self, events: list[pygame.event.Event]) -> None:
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and self.app.loading_error:
                self.app.navigation.go_single_setup()

    def update(self, dt: float) -> None:
        self.app._sync_menu_music()
        self.loading.finish_single_loading_if_ready()

    def render(self, ctx: RenderContext) -> None:
        self.renderer.render(ctx)
