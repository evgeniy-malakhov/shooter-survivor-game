from __future__ import annotations

from typing import Any

from client.render.render_context import RenderContext


class ServerBrowserRenderer:
    def __init__(self, app: Any) -> None:
        self.app = app

    def render(self, ctx: RenderContext) -> None:
        self.app._draw_servers()

