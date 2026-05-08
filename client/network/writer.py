from __future__ import annotations

from typing import Any


def writer_loop(client: Any, epoch: int) -> None:
    sock = client._socket
    try:
        while client._running and client._connection_epoch == epoch and sock:
            payload = client._outbox.get()
            if payload is None:
                return
            sock.sendall(payload)
    except OSError as exc:
        if client._connection_epoch == epoch:
            client.error = str(exc)
            client._running = False
