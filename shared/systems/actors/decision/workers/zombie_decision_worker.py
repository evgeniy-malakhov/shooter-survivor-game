from __future__ import annotations

from shared.systems.actors.decision.actor_decision_dto import ActorDecisionInput
from shared.systems.actors.decision.actor_decision_result import ActorDecisionOutput
from shared.systems.actors.decision.policies.zombie_decision_policy import ZombieDecisionPolicy


class ZombieDecisionWorker:
    supports_threads = False
    supports_processes = False

    def __init__(self, policy: ZombieDecisionPolicy | None = None) -> None:
        self._policy = policy or ZombieDecisionPolicy()

    def execute(self, decision_input: ActorDecisionInput, ctx=None) -> ActorDecisionOutput:
        return self._policy.decide(decision_input, ctx)
