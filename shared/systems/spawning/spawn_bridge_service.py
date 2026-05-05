from __future__ import annotations

from typing import Callable


class SpawnBridgeService:
    def __init__(self, spawn_zombie: Callable[[], object]) -> None:
        self._spawn_zombie = spawn_zombie

    def spawn_zombie(self) -> object:
        return self._spawn_zombie()