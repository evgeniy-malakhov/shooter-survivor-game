from __future__ import annotations

from dataclasses import dataclass

from shared.maps.loading.loading_stage import LoadingStage


@dataclass(frozen=True, slots=True)
class LoadingTask:
    stage: LoadingStage
    label: str
    progress: float
