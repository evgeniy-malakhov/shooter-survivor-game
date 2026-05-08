from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from shared.maps.loading import LoadingScreenState, LoadingStage


@dataclass(frozen=True, slots=True)
class LoadingJob:
    stage: LoadingStage
    label: str
    progress: float
    run: Callable[[], None]


class LoadingJobRunner:
    def __init__(self, state: LoadingScreenState) -> None:
        self.state = state
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(self, jobs: list[LoadingJob]) -> None:
        for job in jobs:
            if self.cancelled:
                raise RuntimeError("loading cancelled")
            self.state.update(job.stage, job.label, job.progress)
            job.run()
