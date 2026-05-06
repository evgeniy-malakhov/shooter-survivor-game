from __future__ import annotations

from client.input.action_buffer import ClientAction
from client.network import OnlineClient
from shared.models import InputCommand, WorldSnapshot


class OnlineSession:
    def __init__(self, client: OnlineClient) -> None:
        self.client = client

    @property
    def local_player_id(self) -> str | None:
        return self.client.player_id

    def update(self, dt: float) -> None:
        return

    def send_input(self, command: InputCommand) -> None:
        self.client.send_input(command)

    def dispatch_action(self, action: ClientAction) -> None:
        self.client.send_command(action.type, dict(action.payload))

    def snapshot(self) -> WorldSnapshot | None:
        return self.client.snapshot()

    def close(self) -> None:
        self.client.close()

