from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class PredictionState:
    player_data: dict[str, Any] | None = None
    last_prediction_at: float = 0.0
    correction_x: float = 0.0
    correction_y: float = 0.0

    @property
    def correction_px(self) -> float:
        return (self.correction_x * self.correction_x + self.correction_y * self.correction_y) ** 0.5


