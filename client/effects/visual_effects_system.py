from __future__ import annotations

from client.effects.visual_effects_state import VisualEffectsState


class VisualEffectsSystem:
    def __init__(self, state: VisualEffectsState | None = None) -> None:
        self.state = state or VisualEffectsState()

    def update(self, dt: float) -> None:
        self.state.damage_flash = max(0.0, self.state.damage_flash - dt * 1.9)

