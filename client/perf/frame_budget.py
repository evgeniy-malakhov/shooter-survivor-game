from __future__ import annotations

from collections import deque
from dataclasses import dataclass


TARGET_FRAME_MS = 16.67


@dataclass(slots=True)
class FrameBudgetState:
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    over_budget_frames: int = 0
    suggested_lod_bias: float = 1.0
    suggested_render_radius_scale: float = 1.0


class FrameBudgetController:
    def __init__(self, sample_size: int = 180) -> None:
        self.samples: deque[float] = deque(maxlen=max(30, sample_size))
        self.state = FrameBudgetState()

    def observe(self, frame_ms: float, draw_world_ms: float = 0.0) -> FrameBudgetState:
        self.samples.append(max(0.0, float(frame_ms)))
        ordered = sorted(self.samples)
        if ordered:
            self.state.p95_ms = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
            self.state.p99_ms = ordered[min(len(ordered) - 1, int(len(ordered) * 0.99))]
        if frame_ms > 22.0 or draw_world_ms > 8.0:
            self.state.over_budget_frames += 1
        else:
            self.state.over_budget_frames = max(0, self.state.over_budget_frames - 1)
        if self.state.over_budget_frames >= 20:
            self.state.suggested_lod_bias = 0.82
            self.state.suggested_render_radius_scale = 0.9
        elif self.state.p95_ms < 12.0:
            self.state.suggested_lod_bias = 1.0
            self.state.suggested_render_radius_scale = 1.0
        return self.state

