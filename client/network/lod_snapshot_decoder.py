from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from shared.net_schema import expand_delta, expand_snapshot


@dataclass(slots=True)
class SnapshotPayloadMetrics:
    snapshot_bytes: int = 0
    delta_bytes: int = 0
    events_bytes: int = 0
    actors_full: int = 0
    actors_simple: int = 0
    actors_dot: int = 0
    compression_ratio: float = 1.0


class LodSnapshotDecoder:
    def decode_snapshot(self, payload: dict[str, Any], schema: object) -> tuple[dict[str, Any], SnapshotPayloadMetrics]:
        metrics = payload_metrics(payload, is_delta=False)
        return expand_snapshot(payload), metrics

    def decode_delta(self, payload: dict[str, Any]) -> tuple[dict[str, Any], SnapshotPayloadMetrics]:
        metrics = payload_metrics(payload, is_delta=True)
        return expand_delta(payload), metrics


def payload_metrics(payload: dict[str, Any], *, is_delta: bool = False) -> SnapshotPayloadMetrics:
    size = _encoded_size(payload)
    metrics = SnapshotPayloadMetrics(
        snapshot_bytes=0 if is_delta else size,
        delta_bytes=size if is_delta else 0,
        actors_full=_actor_rows(payload.get("z")) + _actor_rows(payload.get("so")),
        actors_simple=_actor_rows(payload.get("zs")) + _actor_rows(payload.get("sos")),
        actors_dot=_actor_rows(payload.get("zd")) + _actor_rows(payload.get("sod")),
    )
    compact_count = metrics.actors_full + metrics.actors_simple + metrics.actors_dot
    if compact_count:
        estimated_full_actor_bytes = max(1, compact_count * 115)
        metrics.compression_ratio = min(1.0, size / estimated_full_actor_bytes)
    return metrics


def event_payload_metrics(message: dict[str, Any]) -> SnapshotPayloadMetrics:
    return SnapshotPayloadMetrics(events_bytes=_encoded_size(message))


def _encoded_size(payload: dict[str, Any]) -> int:
    try:
        return len(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        return 0


def _actor_rows(value: object) -> int:
    if isinstance(value, dict):
        rows = value.get("u", [])
        return len(rows) if isinstance(rows, list) else 0
    return len(value) if isinstance(value, list) else 0
