from __future__ import annotations

from typing import Any

import pygame

from client.controllers.single_setup_controller import SingleSetupController
from client.render.render_context import RenderContext
from client.render.ui.single_setup_renderer import SingleSetupRenderer


class SingleSetupScene:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.controller = SingleSetupController(app)
        self.renderer = SingleSetupRenderer(app)

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
