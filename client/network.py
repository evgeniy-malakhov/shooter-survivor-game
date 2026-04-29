from __future__ import annotations

import socket
import threading
import time
from typing import Any

from shared.models import InputCommand, WorldSnapshot
from shared.protocol import FrameDecoder, encode_message
from shared.snapshot_delta import apply_snapshot_delta


def ping_server(host: str, port: int, timeout: float = 0.75) -> tuple[float | None, dict[str, Any] | None]:
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sent = time.time()
            sock.sendall(encode_message("ping", sent=sent))
            message = _recv_one(sock, FrameDecoder(), [], timeout)
            if message["type"] != "pong":
                return None, None
            return (time.perf_counter() - started) * 1000.0, message
    except (OSError, ValueError):
        return None, None


class OnlineClient:
    def __init__(self) -> None:
        self.player_id: str | None = None
        self.latest_snapshot: WorldSnapshot | None = None
        self._snapshot_data: dict[str, Any] | None = None
        self._socket: socket.socket | None = None
        self._decoder = FrameDecoder()
        self._pending_messages: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._snapshot_lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._input_seq = 0
        self._last_snapshot_tick = -1
        self._last_snapshot_seq = 0
        self.error: str | None = None

    def connect(self, host: str, port: int, name: str) -> None:
        self.close()
        sock = socket.create_connection((host, port), timeout=4.0)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(4.0)
        decoder = FrameDecoder()
        pending: list[dict[str, Any]] = []
        sock.sendall(encode_message("hello", name=name))
        try:
            first = _recv_one(sock, decoder, pending, 4.0)
        except ValueError:
            raise ConnectionError("server sent invalid response")
        if first["type"] != "welcome":
            raise ConnectionError(first.get("message", "server refused connection"))

        snapshot_data = first["snapshot"]
        if not isinstance(snapshot_data, dict):
            raise ConnectionError("server sent invalid world snapshot")
        self.player_id = str(first["player_id"])
        with self._snapshot_lock:
            self._snapshot_data = snapshot_data
            self.latest_snapshot = WorldSnapshot.from_dict(snapshot_data)
            self._last_snapshot_tick = int(first.get("tick", 0))
            self._last_snapshot_seq = int(first.get("seq", 0))
        sock.settimeout(None)
        self._socket = sock
        self._decoder = decoder
        self._pending_messages = pending
        self._running = True
        self._input_seq = 0
        self.error = None
        self._thread = threading.Thread(target=self._read_loop, name="online-reader", daemon=True)
        self._thread.start()

    def send_input(self, command: InputCommand) -> None:
        if not self._socket or not self._running:
            return
        try:
            with self._lock:
                self._input_seq += 1
                self._socket.sendall(encode_message("input", seq=self._input_seq, command=command.to_dict()))
        except OSError as exc:
            self.error = str(exc)
            self._running = False

    def send_profile_name(self, name: str) -> None:
        if not self._socket or not self._running:
            return
        try:
            with self._lock:
                self._socket.sendall(encode_message("profile", name=name[:18]))
        except OSError as exc:
            self.error = str(exc)
            self._running = False

    def close(self) -> None:
        self._running = False
        if self._socket:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._socket.close()
            except OSError:
                pass
        self._socket = None
        self._pending_messages = []

    def snapshot(self) -> WorldSnapshot | None:
        with self._snapshot_lock:
            return self.latest_snapshot

    def _read_loop(self) -> None:
        try:
            while self._running and self._socket:
                if self._pending_messages:
                    message = self._pending_messages.pop(0)
                else:
                    chunk = self._socket.recv(65_536)
                    if not chunk:
                        break
                    messages = self._decoder.feed(chunk)
                    if not messages:
                        continue
                    self._pending_messages.extend(messages[1:])
                    message = messages[0]
                self._handle_message(message)
        except (OSError, ValueError) as exc:
            self.error = str(exc)
        finally:
            self._running = False

    def _handle_message(self, message: dict[str, Any]) -> None:
        message_type = message.get("type")
        if message_type == "snapshot":
            with self._snapshot_lock:
                snapshot_data = self._snapshot_from_message(message)
                if snapshot_data is None:
                    return
                self._snapshot_data = snapshot_data
                self.latest_snapshot = WorldSnapshot.from_dict(snapshot_data)
                self._last_snapshot_tick = int(message.get("tick", self._last_snapshot_tick))
                self._last_snapshot_seq = int(message.get("seq", self._last_snapshot_seq))
        elif message_type == "error":
            self.error = str(message.get("message", "server error"))

    def _snapshot_from_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        if message.get("full", True) or "snapshot" in message:
            snapshot = message.get("snapshot")
            return snapshot if isinstance(snapshot, dict) else None
        delta = message.get("delta")
        if not isinstance(delta, dict) or self._snapshot_data is None:
            return None
        return apply_snapshot_delta(self._snapshot_data, delta)


def _recv_one(
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
