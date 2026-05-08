from __future__ import annotations

import queue
import time
from typing import Any

from shared.protocol import encode_message
from shared.state_hash import snapshot_hash

HEARTBEAT_INTERVAL_SECONDS = 1.0
STATE_HASH_INTERVAL_SECONDS = 7.5


def heartbeat_loop(client: Any, epoch: int) -> None:
    while client._running and client._connection_epoch == epoch and client._socket:
        now = time.perf_counter()
        if now - client._last_ping_at >= HEARTBEAT_INTERVAL_SECONDS:
            send_heartbeat(client)
        if now - client._last_state_hash_at >= STATE_HASH_INTERVAL_SECONDS:
            send_state_hash(client)
        time.sleep(0.1)


def send_heartbeat(client: Any) -> None:
    try:
        client._last_ping_at = time.perf_counter()
        client._enqueue(
            encode_message(
                "ping",
                sent=time.time(),
                client_ping_ms=0.0 if client._ping_ms is None else round(client._ping_ms, 2),
            )
        )
    except (OSError, queue.Full, ValueError) as exc:
        client.error = str(exc)
        client._running = False


def send_state_hash(client: Any) -> None:
    with client._snapshot_lock:
        snapshot_data = client._snapshot_data
        tick = client._last_snapshot_tick
    if not snapshot_data or tick < 0:
        return
    try:
        client._last_state_hash_at = time.perf_counter()
        client._enqueue(encode_message("state_hash", tick=tick, hash=snapshot_hash(snapshot_data)))
    except (OSError, queue.Full, ValueError) as exc:
        client.error = str(exc)
        client._running = False
