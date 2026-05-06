from __future__ import annotations

from typing import Any

import pygame

from client.app.app_state import AppState
from client.render.render_context import RenderContext


class MenuScene:
    def __init__(self, app: Any) -> None:
        self.app = app

    def handle_events(self, events: list[pygame.event.Event]) -> None:
        for event in events:
            if event.type == pygame.KEYDOWN:
                self._handle_keydown(event)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_click(self.app._display_to_screen(event.pos))

    def update(self, dt: float) -> None:
        self.app._sync_menu_music()

    def render(self, ctx: RenderContext) -> None:
        self.app._draw_menu()

    def _handle_keydown(self, event: pygame.event.Event) -> None:
        if event.key == pygame.K_ESCAPE:
            self.app.running = False

    def _handle_click(self, pos: tuple[int, int]) -> None:
        for button in self.app._menu_buttons:
            if not button.hovered(pos):
                continue

            if button.action == "single":
                self.app.scene_manager.set_state(AppState.SINGLE_SETUP)
            elif button.action == "online":
                self.app._show_servers()
            elif button.action == "options":
                self.app.settings_tab = "general"
                self.app.options_scroll = 0
                self.app.scene_manager.set_state(AppState.OPTIONS)
            elif button.action == "quit":
                self.app.running = False
            return

