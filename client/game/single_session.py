from __future__ import annotations

from client.input.action_buffer import ClientAction
from shared.models import ClientCommand, InputCommand, WorldSnapshot
from shared.simulation import GameWorld


class SingleSession:
    def __init__(self, world: GameWorld, player_id: str) -> None:
        self.world = world
        self._player_id = player_id
        self._command_id = 0

    @property
    def local_player_id(self) -> str | None:
        return self._player_id

    def update(self, dt: float) -> None:
        self.world.update(dt)

    def send_input(self, command: InputCommand) -> None:
        self.world.set_input(command)

    def dispatch_action(self, action: ClientAction) -> None:
        self._command_id += 1
        self.world.apply_client_command(
            ClientCommand(
                self._player_id,
                self._command_id,
                action.type,
                dict(action.payload),
            )
        )

    def snapshot(self) -> WorldSnapshot | None:
        return self.world.snapshot()

    def close(self) -> None:
        self.world.close()

