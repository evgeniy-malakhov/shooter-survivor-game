from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class FramePhase(str, Enum):
    INPUT = "input"
    NETWORK_HANDOFF = "network_handoff"
    SESSION_UPDATE = "session_update"
    PREDICTION_RECONCILIATION = "prediction_reconciliation"
    RENDER_FRAME_BUILD = "render_frame_build"
    RENDER = "render"
    AUDIO_EFFECTS = "audio_effects"
    PERF_LOG = "perf_log"


@dataclass(slots=True)
class FramePhaseTrace:
    order: tuple[FramePhase, ...] = (
        FramePhase.INPUT,
        FramePhase.NETWORK_HANDOFF,
        FramePhase.SESSION_UPDATE,
        FramePhase.PREDICTION_RECONCILIATION,
        FramePhase.RENDER_FRAME_BUILD,
        FramePhase.RENDER,
        FramePhase.AUDIO_EFFECTS,
        FramePhase.PERF_LOG,
    )
    _started_at: dict[FramePhase, float] = field(default_factory=dict)
    durations_ms: dict[FramePhase, float] = field(default_factory=dict)

    def begin_frame(self) -> None:
        self._started_at.clear()
        self.durations_ms.clear()

    def begin(self, phase: FramePhase) -> None:
        self._started_at[phase] = time.perf_counter()

    def end(self, phase: FramePhase) -> float:
        started = self._started_at.pop(phase, None)
        if started is None:
            return 0.0
        elapsed = (time.perf_counter() - started) * 1000.0
        self.durations_ms[phase] = elapsed
        return elapsed
