from __future__ import annotations

from typing import Any

from client.scenes.bridge_scene import LegacyBridgeScene


class LoadingScene(LegacyBridgeScene):
    def __init__(self, app: Any) -> None:
        super().__init__(app, update=app._update, render=app._draw_loading_screen)

