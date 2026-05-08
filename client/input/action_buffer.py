from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ClientAction:
    type: str
    payload: dict[str, object] = field(default_factory=dict)


class ClientActionBuffer:
    def __init__(self) -> None:
        self._actions: list[ClientAction] = []

    def push(self, action_type: str, payload: dict[str, object] | None = None) -> None:
        self._actions.append(ClientAction(action_type, dict(payload or {})))

    def extend(self, actions: list[ClientAction]) -> None:
        self._actions.extend(actions)

    def drain(self) -> list[ClientAction]:
        actions = self._actions
        self._actions = []
        return actions

    def peek_command_specs(self) -> list[tuple[str, dict[str, object]]]:
        return [(action.type, dict(action.payload)) for action in self._actions]

    def clear(self) -> None:
        self._actions.clear()

    @staticmethod
    def normalize_payload(value: Any) -> dict[str, object]:
        return dict(value) if isinstance(value, dict) else {}


