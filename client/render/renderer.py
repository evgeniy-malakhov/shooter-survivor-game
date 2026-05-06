from __future__ import annotations

from typing import Protocol

from client.render.render_context import RenderContext


class Renderer(Protocol):
    def render(self, ctx: RenderContext) -> None:
        ...


class RenderPipeline:
    def __init__(self, renderers: list[Renderer] | None = None) -> None:
        self._renderers = list(renderers or [])

    def add(self, renderer: Renderer) -> None:
        self._renderers.append(renderer)

    def render(self, ctx: RenderContext) -> None:
        for renderer in self._renderers:
            renderer.render(ctx)

