from __future__ import annotations

from typing import Any

import pygame

from client.controllers.overlay_state import GameplayOverlayState
from shared.models import WorldSnapshot


class ScoreboardController:
    def __init__(self, app: Any) -> None:
        self.app = app

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type != pygame.MOUSEWHEEL:
            return False
        if not pygame.key.get_pressed()[pygame.K_TAB]:
            return False
        snapshot = self.app._snapshot()
        if not snapshot:
            return False
        self.scroll(self.app.overlay_state, snapshot, -int(event.y))
        return True

    def scroll(self, overlay: GameplayOverlayState, snapshot: WorldSnapshot, direction: int) -> None:
        max_scroll = max(0, len(snapshot.players) * 52 - (520 - 176) + 12)
        overlay.scoreboard_scroll = max(0, min(max_scroll, overlay.scoreboard_scroll + direction * 36))
