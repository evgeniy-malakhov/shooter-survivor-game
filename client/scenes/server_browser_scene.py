from __future__ import annotations

from typing import Any

import pygame

from client.controllers.server_browser_controller import ServerBrowserController
from client.render.render_context import RenderContext
from client.render.ui.server_browser_renderer import ServerBrowserRenderer


class ServerBrowserScene:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.controller = ServerBrowserController(app)
        self.renderer = ServerBrowserRenderer(app)
        app.server_browser_controller = self.controller

    def handle_events(self, events: list[pygame.event.Event]) -> None:
        import time
        started = time.perf_counter()
        for event in events:
            self.controller.handle_event(event)
        self.app.perf_stats.controller_ms = (time.perf_counter() - started) * 1000.0

    def update(self, dt: float) -> None:
        self.app._sync_menu_music()
        self.controller.update(dt)

    def render(self, ctx: RenderContext) -> None:
        self.renderer.render(ctx)

