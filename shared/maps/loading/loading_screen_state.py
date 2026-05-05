from __future__ import annotations

import threading
from dataclasses import dataclass

from shared.maps.loading.loading_stage import LoadingStage


@dataclass(frozen=True, slots=True)
class LoadingSnapshot:
    stage: LoadingStage
    label: str
    progress: float
    map_id: str | None
    error: str | None


class LoadingScreenState:
    def __init__(self, map_id: str | None = None) -> None:
        self._lock = threading.Lock()
        self._stage = LoadingStage.INIT
        self._label = "Initializing"
        self._progress = 0.0
        self._map_id = map_id
        self._error: str | None = None

    def update(
        self,
        stage: LoadingStage,
        label: str,
        progress: float,
    ) -> None:
        with self._lock:
            self._stage = stage
            self._label = label
            self._progress = max(0.0, min(1.0, progress))

    def fail(self, error: str) -> None:
        with self._lock:
            self._stage = LoadingStage.FAILED
            self._label = "Loading failed"
            self._progress = 1.0
            self._error = error

    def snapshot(self) -> LoadingSnapshot:
        with self._lock:
            return LoadingSnapshot(
                stage=self._stage,
                label=self._label,
                progress=self._progress,
                map_id=self._map_id,
                error=self._error,
            )
