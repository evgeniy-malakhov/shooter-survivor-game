from __future__ import annotations

from typing import Protocol

from shared.systems.actors.decision.actor_decision_dto import ActorDecisionInput
from shared.systems.actors.decision.actor_decision_result import ActorDecisionOutput


class ActorDecisionWorker(Protocol):
    supports_threads: bool
    supports_processes: bool

    def execute(self, decision_input: ActorDecisionInput, ctx=None) -> ActorDecisionOutput:
        ...


class ActorDecisionRegistry:
    def __init__(self) -> None:
        self._workers: dict[str, ActorDecisionWorker] = {}

    def register(self, actor_type: str, worker: ActorDecisionWorker) -> None:
        self._workers[actor_type] = worker

    def get(self, actor_type: str) -> ActorDecisionWorker:
        return self._workers[actor_type]

    def try_get(self, actor_type: str) -> ActorDecisionWorker | None:
        return self._workers.get(actor_type)
