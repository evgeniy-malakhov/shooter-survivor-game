from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from client.network.snapshot_buffer import BufferedSnapshot
from shared.interpolation import interpolate_snapshot

INTERPOLATION_DELAY_SECONDS = 0.10


def estimated_server_time(now: float, latest_server_time: float, latest_received_at: float) -> float:
    if latest_received_at <= 0.0:
        return latest_server_time
    return latest_server_time + max(0.0, now - latest_received_at)


def interpolated_data(
    buffer: Iterable[BufferedSnapshot],
    fallback: dict[str, Any] | None,
    render_time: float,
    local_player_id: str | None,
) -> dict[str, Any] | None:
    snapshots = tuple(buffer)
    if len(snapshots) < 2:
        return fallback
    previous = snapshots[0]
    for current in snapshots[1:]:
        if current.server_time >= render_time:
            span = max(0.0001, current.server_time - previous.server_time)
            alpha = (render_time - previous.server_time) / span
            return interpolate_snapshot(previous.data, current.data, alpha, local_player_id)
        previous = current
    return snapshots[-1].data
