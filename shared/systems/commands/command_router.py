from __future__ import annotations

from shared.models import ClientCommand, PlayerState
from shared.systems.commands.base_handler import CommandHandler
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class CommandRouter:
    def __init__(self) -> None:
        self._handlers: dict[str, CommandHandler] = {}

    def register(self, kind: str, handler: CommandHandler) -> None:
        self._handlers[kind] = handler

    def has_handler(self, kind: str) -> bool:
        return kind in self._handlers

    def handle(
        self,
        state: WorldState,
        ctx: WorldContext,
        player: PlayerState,
        command: ClientCommand,
    ) -> tuple[bool, str]:
        handler = self._handlers.get(command.kind)

        if not handler:
            return False, "unknown_command"

        return handler.handle(state, ctx, player, command)