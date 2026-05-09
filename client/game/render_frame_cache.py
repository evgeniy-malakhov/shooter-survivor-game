from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RenderFrameCacheKey:
    snapshot_tick: int
    camera_cell_x: int
    camera_cell_y: int
    floor: int
    zoom_bucket: int
    local_facing_bucket: int


