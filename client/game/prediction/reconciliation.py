from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    prediction_error_px: float = 0.0
    correction_px: float = 0.0
    hard_snap: bool = False

