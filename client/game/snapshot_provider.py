from __future__ import annotations

from typing import Protocol

from shared.models import InputCommand, WorldSnapshot


class SnapshotProvider(Protocol):
    @property
    def player_id(self) -> str | None:
        ...

    def snapshot(self) -> WorldSnapshot | None:
        ...

    def send_input(self, command: InputCommand) -> None:
        ...


