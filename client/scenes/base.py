from __future__ import annotations

from typing import Protocol

import pygame

from client.render.render_context import RenderContext


class Scene(Protocol):
    def handle_events(self, events: list[pygame.event.Event]) -> None:
        ...

    def update(self, dt: float) -> None:
        ...

    def render(self, ctx: RenderContext) -> None:
        ...

