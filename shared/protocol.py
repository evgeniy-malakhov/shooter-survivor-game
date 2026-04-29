from __future__ import annotations

import json
import struct
from typing import Any

try:  # msgpack is the preferred runtime codec, JSON stays as a zero-dependency fallback.
    import msgpack  # type: ignore
except ImportError:  # pragma: no cover - depends on optional local dependency.
    msgpack = None  # type: ignore


MAX_MESSAGE_BYTES = 2_000_000
HEADER_BYTES = 4
SERIALIZER_NAME = "msgpack" if msgpack else "json"
_HEADER = struct.Struct("!I")


class FrameDecoder:
    """Incrementally decodes length-prefixed protocol frames."""

    __slots__ = ("_buffer",)

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> list[dict[str, Any]]:
        if not chunk:
            return []
        self._buffer.extend(chunk)
        messages: list[dict[str, Any]] = []
        while True:
            if self._buffer and self._buffer[0] in (ord("{"), ord("[")):
                newline = self._buffer.find(b"\n")
                if newline < 0:
                    break
                raw = bytes(self._buffer[:newline]).strip()
                del self._buffer[: newline + 1]
                if raw:
                    messages.append(_decode_payload(raw))
                continue

            if len(self._buffer) < HEADER_BYTES:
                break
            frame_size = _HEADER.unpack(self._buffer[:HEADER_BYTES])[0]
            if frame_size <= 0 or frame_size > MAX_MESSAGE_BYTES:
                raise ValueError("invalid protocol frame size")
            total_size = HEADER_BYTES + frame_size
            if len(self._buffer) < total_size:
                break
            payload = bytes(self._buffer[HEADER_BYTES:total_size])
            del self._buffer[:total_size]
            messages.append(_decode_payload(payload))
        return messages


def encode_message(message_type: str, **payload: Any) -> bytes:
    data = {"type": message_type, **payload}
    body = _encode_payload(data)
    if len(body) > MAX_MESSAGE_BYTES:
        raise ValueError("message is too large")
    return _HEADER.pack(len(body)) + body


def decode_message(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_MESSAGE_BYTES + HEADER_BYTES:
        raise ValueError("message is too large")
    payload = raw.strip()
    if len(payload) >= HEADER_BYTES:
        frame_size = _HEADER.unpack(payload[:HEADER_BYTES])[0]
        if frame_size == len(payload) - HEADER_BYTES:
            payload = payload[HEADER_BYTES:]
    return _decode_payload(payload)


def _encode_payload(data: dict[str, Any]) -> bytes:
    if msgpack:
        return msgpack.packb(data, use_bin_type=True)
    return json.dumps(data, separators=(",", ":")).encode("utf-8")


def _decode_payload(payload: bytes) -> dict[str, Any]:
    if not payload:
        raise ValueError("empty protocol message")
    if msgpack and payload[:1] not in (b"{", b"["):
        data = msgpack.unpackb(payload, raw=False)
    else:
        data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict) or "type" not in data:
        raise ValueError("invalid protocol message")
    return data
