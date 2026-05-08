from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SnapshotPacket:
    tick: int
    seq: int
    ack_input_seq: int
    server_time: float
    received_at: float
    snapshot_data: dict[str, Any]
    decode_ms: float = 0.0


class SnapshotHandoff:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: SnapshotPacket | None = None

    def publish(self, packet: SnapshotPacket) -> None:
        with self._lock:
            self._latest = packet

    def latest(self) -> SnapshotPacket | None:
        with self._lock:
            return self._latest

    def clear(self) -> None:
        with self._lock:
            self._latest = None


