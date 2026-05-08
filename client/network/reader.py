from __future__ import annotations

import queue
from typing import Any


def reader_loop(client: Any, epoch: int) -> None:
    sock = client._socket
    try:
        while client._running and client._connection_epoch == epoch and sock:
            if client._pending_messages:
                message = client._pending_messages.pop(0)
            else:
                chunk = sock.recv(65_536)
                if not chunk:
                    break
                messages = client._decoder.feed(chunk)
                if not messages:
                    continue
                client._pending_messages.extend(messages[1:])
                message = messages[0]
            client._handle_message(message)
    except (OSError, ValueError) as exc:
        if client._connection_epoch == epoch:
            client.error = str(exc)
    finally:
        if client._connection_epoch != epoch:
            return
        should_resume = client._should_resume_after_drop()
        client._running = False
        if sock:
            try:
                sock.close()
            except OSError:
                pass
        if client._socket is sock:
            client._socket = None
        try:
            client._outbox.put_nowait(None)
        except queue.Full:
            pass
        if should_resume:
            client._start_resume_loop()
        elif not client._manual_close and client._connection_state != "offline":
            client._connection_state = "lost"
