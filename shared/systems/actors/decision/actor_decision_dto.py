from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shared.ai.context import ActorTarget, SoundEvent


@dataclass(frozen=True, slots=True)
class ActorDecisionInput:
    actor_type: str
    actor_id: str
    actor_kind: str
    actor_state: dict[str, Any]
    dt: float
    time: float
    rng_seed: int
    targets: tuple[ActorTarget, ...] = ()
    nearby_players: tuple[ActorTarget, ...] = ()
    nearby_zombies: tuple[ActorTarget, ...] = ()
    nearby_soldiers: tuple[ActorTarget, ...] = ()
    nearby_sounds: tuple[SoundEvent, ...] = ()
    squad_intent: dict[str, Any] | None = None
    squad_role: str = ""
    squad_memory: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def cpu_heavy(self) -> bool:
        return bool(self.metadata.get("cpu_heavy", False))
