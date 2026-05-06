from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class VisualEffectsState:
    damage_flash: float = 0.0
    explosion_effects: list[dict[str, object]] = field(default_factory=list)
    death_effects: list[dict[str, object]] = field(default_factory=list)
    join_notifications: list[dict[str, object]] = field(default_factory=list)
