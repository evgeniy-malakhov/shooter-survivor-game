from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pygame

from client.render.render_context import RenderContext


class LegacyBridgeScene:
    def __init__(
        self,
        app: Any,
        *,
        update: Callable[[float], None] | None,
        render: Callable[[], None],
    ) -> None:
        self.app = app
        self._update = update
        self._render = render

    def handle_events(self, events: list[pygame.event.Event]) -> None:
        for event in events:
            if event.type == pygame.KEYDOWN:
                self.app._handle_keydown(event)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self.app._handle_mouse_down(event)
            elif event.type == pygame.MOUSEBUTTONUP:
                self.app._handle_mouse_up(event)
            elif event.type == pygame.MOUSEMOTION:
                self.app._handle_mouse_motion(event)
            elif event.type == pygame.MOUSEWHEEL:
                self.app._handle_mouse_wheel(event)

    def update(self, dt: float) -> None:
        if self._update:
            self._update(dt)

    def render(self, ctx: RenderContext) -> None:
        self._render()

