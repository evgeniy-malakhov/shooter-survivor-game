from __future__ import annotations

import socket
import threading
import time
from typing import Any

from shared.models import InputCommand, WorldSnapshot
from shared.protocol import decode_message, encode_message


def ping_server(host: str, port: int, timeout: float = 0.75) -> tuple[float | None, dict[str, Any] | None]:
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sent = time.time()
            sock.sendall(encode_message("ping", sent=sent))
            raw = sock.makefile("rb").readline()
            message = decode_message(raw)
            if message["type"] != "pong":
                return None, None
            return (time.perf_counter() - started) * 1000.0, message
    except OSError:
        return None, None


class OnlineClient:
    def __init__(self) -> None:
        self.player_id: str | None = None
        self.latest_snapshot: WorldSnapshot | None = None
        self._socket: socket.socket | None = None
        self._reader: Any = None
        self._lock = threading.Lock()
        self._snapshot_lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self.error: str | None = None

    def connect(self, host: str, port: int, name: str) -> None:
        self.close()
        sock = socket.create_connection((host, port), timeout=4.0)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.sendall(encode_message("hello", name=name))
        reader = sock.makefile("rb")
        first = decode_message(reader.readline())
        if first["type"] != "welcome":
            raise ConnectionError(first.get("message", "server refused connection"))

        self.player_id = str(first["player_id"])
        with self._snapshot_lock:
            self.latest_snapshot = WorldSnapshot.from_dict(first["snapshot"])
        self._socket = sock
        self._reader = reader
        self._running = True
        self.error = None
        self._thread = threading.Thread(target=self._read_loop, name="online-reader", daemon=True)
        self._thread.start()

    def send_input(self, command: InputCommand) -> None:
        if not self._socket or not self._running:
            return
        try:
            with self._lock:
                self._socket.sendall(encode_message("input", command=command.to_dict()))
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
        self._reader = None

    def snapshot(self) -> WorldSnapshot | None:
        with self._snapshot_lock:
            return self.latest_snapshot

    def _read_loop(self) -> None:
        try:
            while self._running and self._reader:
                raw = self._reader.readline()
                if not raw:
                    break
                message = decode_message(raw)
                if message["type"] == "snapshot":
                    with self._snapshot_lock:
                        self.latest_snapshot = WorldSnapshot.from_dict(message["snapshot"])
                elif message["type"] == "error":
                    self.error = str(message.get("message", "server error"))
        except (OSError, ValueError) as exc:
            self.error = str(exc)
        finally:
            self._running = False
