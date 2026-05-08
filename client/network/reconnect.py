from __future__ import annotations

import time
from typing import Any

from shared.net_schema import SNAPSHOT_SCHEMA
from shared.protocol import encode_message
from shared.protocol_meta import CLIENT_FEATURES, CLIENT_VERSION, PROTOCOL_VERSION

RESUME_RETRY_SECONDS = 0.75


def resume_loop(client: Any) -> None:
    while not client._manual_close and time.perf_counter() < client._resume_deadline:
        try:
            payload = encode_message(
                "resume",
                player_id=client.player_id,
                session_token=client.session_token,
                last_snapshot_tick=client._last_snapshot_tick,
                client_version=CLIENT_VERSION,
                protocol_version=PROTOCOL_VERSION,
                snapshot_schema=SNAPSHOT_SCHEMA,
                features=CLIENT_FEATURES,
            )
            sock, decoder, pending, first = client._open_connection(client._host, client._port, payload)
            if first.get("type") != "welcome":
                sock.close()
                raise ConnectionError(str(first.get("message", "resume refused")))
            client._manual_close = False
            client._apply_welcome(sock, decoder, pending, first, reset_session=False)
            return
        except (OSError, ConnectionError, TimeoutError, ValueError) as exc:
            client.error = f"reconnecting: {exc}"
            time.sleep(RESUME_RETRY_SECONDS)
    if not client._manual_close:
        client._connection_state = "lost"
        client.error = "connection lost"
