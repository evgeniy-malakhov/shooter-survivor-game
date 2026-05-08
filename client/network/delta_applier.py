from __future__ import annotations

import time
from typing import Any

from shared.net_schema import SNAPSHOT_SCHEMA, expand_delta, expand_snapshot
from shared.snapshot_delta import apply_snapshot_delta


def decode_snapshot_payload(snapshot: dict[str, Any], schema: object) -> dict[str, Any]:
    return expand_snapshot(snapshot) if schema == SNAPSHOT_SCHEMA or snapshot.get("v") == 1 else snapshot


def snapshot_from_message(
    base_snapshot: dict[str, Any] | None,
    message: dict[str, Any],
) -> tuple[dict[str, Any] | None, float]:
    started = time.perf_counter()
    if message.get("full", True) or "snapshot" in message:
        snapshot = message.get("snapshot")
        result = decode_snapshot_payload(snapshot, message.get("schema")) if isinstance(snapshot, dict) else None
        return result, (time.perf_counter() - started) * 1000.0
    delta = message.get("delta")
    if not isinstance(delta, dict) or base_snapshot is None:
        return None, (time.perf_counter() - started) * 1000.0
    if message.get("schema") == SNAPSHOT_SCHEMA:
        delta = expand_delta(delta)
    return apply_snapshot_delta(base_snapshot, delta), (time.perf_counter() - started) * 1000.0
