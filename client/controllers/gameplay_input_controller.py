from __future__ import annotations

from typing import Any

import pygame


class GameplayInputController:
    def __init__(self, app: Any) -> None:
        self.app = app

    def handle_event(self, event: pygame.event.Event) -> bool:
        return False
