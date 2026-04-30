from __future__ import annotations

import hashlib
import json
from typing import Any


IGNORED_SNAPSHOT_KEYS = {"server_time"}


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    """Return a stable short hash for an authoritative snapshot dictionary."""
    normalized = _normalize(snapshot)
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.blake2s(payload, digest_size=12).hexdigest()


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _normalize(raw)
            for key, raw in sorted(value.items(), key=lambda item: str(item[0]))
            if str(key) not in IGNORED_SNAPSHOT_KEYS
        }
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, float):
        return round(value, 4)
    return value
