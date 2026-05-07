from __future__ import annotations

from typing import Any

import pygame

from client.render.render_context import RenderContext
from client.render.ui.menu_renderer import MenuRenderer


class MenuScene:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.renderer = MenuRenderer(app)

    def handle_events(self, events: list[pygame.event.Event]) -> None:
        import time
        started = time.perf_counter()
        for event in events:
            if event.type == pygame.KEYDOWN:
                self._on_keydown(event)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._on_click(self.app._display_to_screen(event.pos))
        self.app.perf_stats.controller_ms = (time.perf_counter() - started) * 1000.0

    def update(self, dt: float) -> None:
        self.app._sync_menu_music()

    def render(self, ctx: RenderContext) -> None:
        self.renderer.render(ctx)

    def _on_keydown(self, event: pygame.event.Event) -> None:
        if event.key == pygame.K_ESCAPE:
            self.app.running = False

    def _on_click(self, pos: tuple[int, int]) -> None:
        for button in self.app._menu_buttons:
            if not button.hovered(pos):
                continue

            if button.action == "single":
                self.app.navigation.go_single_setup()
            elif button.action == "online":
                self.app.navigation.go_servers()
                self.app.server_browser_controller.refresh_initial()
            elif button.action == "options":
                self.app.settings_tab = "general"
                self.app.options_scroll = 0
                self.app.navigation.go_options()
            elif button.action == "quit":
                self.app.running = False
            return
