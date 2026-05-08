from __future__ import annotations

from client.game.session import GameSession
from client.input.action_buffer import ClientActionBuffer


class CommandDispatcher:
    def __init__(self, session: GameSession) -> None:
        self.session = session

    def dispatch_buffer(self, actions: ClientActionBuffer) -> None:
        for action in actions.drain():
            self.session.dispatch_action(action)


