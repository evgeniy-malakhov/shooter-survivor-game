from __future__ import annotations

import time
from typing import Any

from client.network.lod_snapshot_decoder import LodSnapshotDecoder, SnapshotPayloadMetrics
from shared.net_schema import SNAPSHOT_SCHEMA, expand_delta, expand_snapshot
from shared.snapshot_delta import apply_snapshot_delta

_LOD_DECODER = LodSnapshotDecoder()


def decode_snapshot_payload(snapshot: dict[str, Any], schema: object) -> dict[str, Any]:
    return _LOD_DECODER.decode_snapshot(snapshot, schema)[0] if schema == SNAPSHOT_SCHEMA or snapshot.get("v") == 1 else snapshot


def snapshot_from_message(
    base_snapshot: dict[str, Any] | None,
    message: dict[str, Any],
) -> tuple[dict[str, Any] | None, float, SnapshotPayloadMetrics]:
    started = time.perf_counter()
    if message.get("full", True) or "snapshot" in message:
        snapshot = message.get("snapshot")
        if not isinstance(snapshot, dict):
            return None, (time.perf_counter() - started) * 1000.0, SnapshotPayloadMetrics()
        result, metrics = _LOD_DECODER.decode_snapshot(snapshot, message.get("schema"))
        return result, (time.perf_counter() - started) * 1000.0, metrics
    delta = message.get("delta")
    if not isinstance(delta, dict) or base_snapshot is None:
        return None, (time.perf_counter() - started) * 1000.0, SnapshotPayloadMetrics()
    metrics = SnapshotPayloadMetrics()
    if message.get("schema") == SNAPSHOT_SCHEMA:
        delta, metrics = _LOD_DECODER.decode_delta(delta)
    return apply_snapshot_delta(base_snapshot, delta), (time.perf_counter() - started) * 1000.0, metrics
