from __future__ import annotations

from shared.systems.actors.decision.actor_decision_dto import ActorDecisionInput
from shared.systems.actors.decision.actor_decision_result import ActorDecisionOutput
from shared.systems.actors.decision.policies.soldier_decision_policy import SoldierDecisionPolicy


class SoldierDecisionWorker:
    supports_threads = False
    supports_processes = False

    def __init__(self, policy: SoldierDecisionPolicy | None = None) -> None:
        self._policy = policy or SoldierDecisionPolicy()

    def execute(self, decision_input: ActorDecisionInput, ctx=None) -> ActorDecisionOutput:
        return self._policy.decide(decision_input, ctx)
