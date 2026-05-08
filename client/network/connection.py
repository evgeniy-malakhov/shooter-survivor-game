from __future__ import annotations

import socket
import time
from typing import Any

from shared.models import InputCommand, RectState
from shared.protocol import FrameDecoder, encode_message


def ping_server(host: str, port: int, timeout: float = 0.75) -> tuple[float | None, dict[str, Any] | None]:
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sent = time.time()
            sock.sendall(encode_message("ping", sent=sent))
            message = recv_one(sock, FrameDecoder(), [], timeout)
            if message["type"] != "pong":
                return None, None
            return (time.perf_counter() - started) * 1000.0, message
    except (OSError, ValueError):
        return None, None


def open_connection(
    host: str,
    port: int,
    payload: bytes,
) -> tuple[socket.socket, FrameDecoder, list[dict[str, Any]], dict[str, Any]]:
    sock = socket.create_connection((host, port), timeout=4.0)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    sock.settimeout(4.0)
    decoder = FrameDecoder()
    pending: list[dict[str, Any]] = []
    sock.sendall(payload)
    try:
        first = recv_one(sock, decoder, pending, 4.0)
    except (ConnectionError, OSError, TimeoutError, ValueError):
        sock.close()
        raise
    return sock, decoder, pending, first


def recv_one(
    sock: socket.socket,
    decoder: FrameDecoder,
    pending: list[dict[str, Any]],
    timeout: float,
) -> dict[str, Any]:
    if pending:
        return pending.pop(0)
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        chunk = sock.recv(65_536)
        if not chunk:
            raise ConnectionError("server closed connection")
        messages = decoder.feed(chunk)
        if messages:
            pending.extend(messages[1:])
            return messages[0]
    raise TimeoutError("server did not respond")


def rect_from_data(data: object) -> RectState | None:
    if not isinstance(data, dict):
        return None
    try:
        rect = RectState.from_dict(data)
    except (TypeError, ValueError):
        return None
    if rect.w <= 0.0 or rect.h <= 0.0:
        return None
    return rect


def movement_payload(command: InputCommand) -> dict[str, Any]:
    return {
        "move_x": round(command.move_x, 3),
        "move_y": round(command.move_y, 3),
        "aim_x": round(command.aim_x, 3),
        "aim_y": round(command.aim_y, 3),
        "shooting": command.shooting,
        "sprint": command.sprint,
        "sneak": command.sneak,
    }
