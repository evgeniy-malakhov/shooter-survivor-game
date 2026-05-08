from __future__ import annotations

from typing import Protocol

from client.input.action_buffer import ClientAction
from shared.models import InputCommand, WorldSnapshot


class GameSession(Protocol):
    @property
    def local_player_id(self) -> str | None:
        ...

    def update(self, dt: float) -> None:
        ...

    def send_input(self, command: InputCommand) -> None:
        ...

    def dispatch_action(self, action: ClientAction) -> None:
        ...

    def snapshot(self) -> WorldSnapshot | None:
        ...

    def close(self) -> None:
        ...


