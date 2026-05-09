from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ActorDecisionOutput:
    actor_type: str
    actor_id: str
    actor_kind: str
    actor_state: dict[str, Any] | None = None
    player_hits: list[tuple[str, int]] = field(default_factory=list)
    soldier_hits: list[tuple[str, int]] = field(default_factory=list)
    soldier_heals: list[tuple[str, int]] = field(default_factory=list)
    projectiles: list[dict[str, Any]] = field(default_factory=list)
    grenades: list[dict[str, Any]] = field(default_factory=list)
    sounds: list[dict[str, Any]] = field(default_factory=list)
    poison_spits: list[Any] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def no_op(cls, actor_type: str, actor_id: str, actor_kind: str) -> "ActorDecisionOutput":
        return cls(
            actor_type=actor_type,
            actor_id=actor_id,
            actor_kind=actor_kind,
        )
