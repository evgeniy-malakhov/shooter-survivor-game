from __future__ import annotations

import math
import queue
import socket
import threading
import time
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from shared.constants import MAP_HEIGHT, MAP_WIDTH, SPRINT_MULTIPLIER
from shared.interpolation import interpolate_snapshot
from shared.models import InputCommand, WorldSnapshot
from shared.net_schema import SNAPSHOT_SCHEMA, expand_delta, expand_snapshot
from shared.protocol import FrameDecoder, encode_message
from shared.snapshot_delta import apply_snapshot_delta


INTERPOLATION_DELAY_SECONDS = 0.10
MAX_INTERPOLATION_BUFFER = 32
MAX_PENDING_INPUTS = 80


@dataclass(slots=True)
class _BufferedSnapshot:
    tick: int
    server_time: float
    received_at: float
    data: dict[str, Any]


@dataclass(slots=True)
class _PendingInput:
    seq: int
    command: dict[str, Any]
    dt: float


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
        self._writer_thread: threading.Thread | None = None
        self._outbox: queue.Queue[bytes | None] = queue.Queue(maxsize=256)
        self._input_seq = 0
        self._command_id = 0
        self._last_snapshot_tick = -1
        self._last_snapshot_seq = 0
        self._ack_input_seq = 0
        self._last_input_sent_at = time.perf_counter()
        self._snapshot_buffer: deque[_BufferedSnapshot] = deque(maxlen=MAX_INTERPOLATION_BUFFER)
        self._pending_inputs: deque[_PendingInput] = deque(maxlen=MAX_PENDING_INPUTS)
        self._latest_server_time = 0.0
        self._latest_received_at = 0.0
        self._snapshot_interval = 0.05
        self._render_cache_time = 0.0
        self._render_cache_snapshot: WorldSnapshot | None = None
        self.events: deque[dict[str, Any]] = deque(maxlen=256)
        self._pending_commands: dict[int, dict[str, Any]] = {}
        self._command_results: deque[dict[str, Any]] = deque(maxlen=128)
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
        snapshot_data = self._decode_snapshot_payload(snapshot_data, first.get("schema"))
        self.player_id = str(first["player_id"])
        with self._snapshot_lock:
            self._snapshot_data = snapshot_data
            self.latest_snapshot = WorldSnapshot.from_dict(snapshot_data)
            self._last_snapshot_tick = int(first.get("tick", 0))
            self._last_snapshot_seq = int(first.get("seq", 0))
            self._ack_input_seq = int(first.get("ack_input_seq", 0))
            self._latest_server_time = float(first.get("server_time", snapshot_data.get("time", 0.0)))
            self._latest_received_at = time.perf_counter()
            self._snapshot_interval = float(first.get("snapshot_interval", self._snapshot_interval))
            self._snapshot_buffer.clear()
            self._snapshot_buffer.append(
                _BufferedSnapshot(
                    self._last_snapshot_tick,
                    self._latest_server_time,
                    self._latest_received_at,
                    snapshot_data,
                )
            )
            self._pending_inputs.clear()
            self._pending_commands.clear()
            self._command_results.clear()
            self._render_cache_snapshot = None
        sock.settimeout(None)
        self._socket = sock
        self._decoder = decoder
        self._pending_messages = pending
        self._running = True
        self._input_seq = 0
        self._command_id = 0
        self._outbox = queue.Queue(maxsize=256)
        self._last_input_sent_at = time.perf_counter()
        self.error = None
        self._writer_thread = threading.Thread(target=self._write_loop, name="online-writer", daemon=True)
        self._writer_thread.start()
        self._thread = threading.Thread(target=self._read_loop, name="online-reader", daemon=True)
        self._thread.start()

    def send_input(self, command: InputCommand) -> None:
        if not self._socket or not self._running:
            return
        try:
            with self._lock:
                self._input_seq += 1
                now = time.perf_counter()
                dt = max(1.0 / 120.0, min(1.0 / 20.0, now - self._last_input_sent_at))
                self._last_input_sent_at = now
                command_data = _movement_payload(command)
                self._pending_inputs.append(_PendingInput(self._input_seq, command_data, dt))
                self._enqueue(encode_message("input", seq=self._input_seq, command=command_data))
        except (OSError, queue.Full) as exc:
            self.error = str(exc)
            self._running = False

    def send_command(self, kind: str, payload: dict[str, Any] | None = None) -> int | None:
        if not self._socket or not self._running:
            return None
        try:
            with self._lock:
                self._command_id += 1
                command_id = self._command_id
                command_payload = dict(payload or {})
                with self._snapshot_lock:
                    self._pending_commands[command_id] = {
                        "command_id": command_id,
                        "kind": kind,
                        "payload": command_payload,
                        "sent_at": time.perf_counter(),
                    }
                self._enqueue(
                    encode_message(
                        "command",
                        command_id=command_id,
                        kind=kind,
                        payload=command_payload,
                    )
                )
                return command_id
        except (OSError, queue.Full) as exc:
            self.error = str(exc)
            self._running = False
            return None

    def send_profile_name(self, name: str) -> None:
        if not self._socket or not self._running:
            return
        try:
            with self._lock:
                self._enqueue(encode_message("profile", name=name[:18]))
        except (OSError, queue.Full) as exc:
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
        try:
            self._outbox.put_nowait(None)
        except queue.Full:
            pass
        with self._snapshot_lock:
            self._snapshot_buffer.clear()
            self._pending_inputs.clear()
            self._pending_commands.clear()
            self._command_results.clear()
            self._render_cache_snapshot = None

    def snapshot(self) -> WorldSnapshot | None:
        with self._snapshot_lock:
            now = time.perf_counter()
            if self._render_cache_snapshot and now - self._render_cache_time < 1.0 / 120.0:
                return self._render_cache_snapshot
            data = self._render_snapshot_data(now)
            if data is None:
                return self.latest_snapshot
            snapshot = WorldSnapshot.from_dict(data)
            self._render_cache_snapshot = snapshot
            self._render_cache_time = now
            return snapshot

    def poll_events(self) -> list[dict[str, Any]]:
        with self._snapshot_lock:
            events = list(self.events)
            self.events.clear()
            return events

    def poll_command_results(self) -> list[dict[str, Any]]:
        with self._snapshot_lock:
            results = list(self._command_results)
            self._command_results.clear()
            return results

    def pending_command_count(self) -> int:
        with self._snapshot_lock:
            return len(self._pending_commands)

    def has_pending_commands(self) -> bool:
        return self.pending_command_count() > 0

    def _enqueue(self, payload: bytes) -> None:
        if self._running:
            self._outbox.put_nowait(payload)

    def _write_loop(self) -> None:
        try:
            while self._running and self._socket:
                payload = self._outbox.get()
                if payload is None:
                    return
                self._socket.sendall(payload)
        except OSError as exc:
            self.error = str(exc)
            self._running = False

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
                self._ack_input_seq = max(self._ack_input_seq, int(message.get("ack_input_seq", self._ack_input_seq)))
                self._drop_acked_inputs()
                self._latest_server_time = float(message.get("server_time", snapshot_data.get("time", self._latest_server_time)))
                self._latest_received_at = time.perf_counter()
                self._snapshot_interval = float(message.get("snapshot_interval", self._snapshot_interval))
                self._snapshot_buffer.append(
                    _BufferedSnapshot(
                        self._last_snapshot_tick,
                        self._latest_server_time,
                        self._latest_received_at,
                        snapshot_data,
                    )
                )
                self._render_cache_snapshot = None
        elif message_type == "events":
            with self._snapshot_lock:
                for event in message.get("events", []):
                    if isinstance(event, dict):
                        self.events.append(event)
        elif message_type == "command_result":
            with self._snapshot_lock:
                command_id = int(message.get("command_id", 0))
                self._pending_commands.pop(command_id, None)
                self._command_results.append(dict(message))
        elif message_type == "error":
            self.error = str(message.get("message", "server error"))

    def _snapshot_from_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        if message.get("full", True) or "snapshot" in message:
            snapshot = message.get("snapshot")
            return self._decode_snapshot_payload(snapshot, message.get("schema")) if isinstance(snapshot, dict) else None
        delta = message.get("delta")
        if not isinstance(delta, dict) or self._snapshot_data is None:
            return None
        if message.get("schema") == SNAPSHOT_SCHEMA:
            delta = expand_delta(delta)
        return apply_snapshot_delta(self._snapshot_data, delta)

    def _decode_snapshot_payload(self, snapshot: dict[str, Any], schema: object) -> dict[str, Any]:
        return expand_snapshot(snapshot) if schema == SNAPSHOT_SCHEMA or snapshot.get("v") == 1 else snapshot

    def _drop_acked_inputs(self) -> None:
        while self._pending_inputs and self._pending_inputs[0].seq <= self._ack_input_seq:
            self._pending_inputs.popleft()

    def _render_snapshot_data(self, now: float) -> dict[str, Any] | None:
        if not self._snapshot_data:
            return None
        render_time = self._estimated_server_time(now) - INTERPOLATION_DELAY_SECONDS
        source = self._interpolated_data(render_time)
        if source is None:
            source = self._snapshot_data
        data = deepcopy(source)
        self._apply_local_prediction(data)
        return data

    def _estimated_server_time(self, now: float) -> float:
        if self._latest_received_at <= 0.0:
            return self._latest_server_time
        return self._latest_server_time + max(0.0, now - self._latest_received_at)

    def _interpolated_data(self, render_time: float) -> dict[str, Any] | None:
        if len(self._snapshot_buffer) < 2:
            return self._snapshot_data
        previous = self._snapshot_buffer[0]
        for current in list(self._snapshot_buffer)[1:]:
            if current.server_time >= render_time:
                span = max(0.0001, current.server_time - previous.server_time)
                alpha = (render_time - previous.server_time) / span
                return interpolate_snapshot(previous.data, current.data, alpha, self.player_id)
            previous = current
        return self._snapshot_buffer[-1].data

    def _apply_local_prediction(self, data: dict[str, Any]) -> None:
        if not self.player_id or not self._snapshot_data:
            return
        latest_players = self._snapshot_data.get("players", {})
        latest_player = latest_players.get(self.player_id) if isinstance(latest_players, dict) else None
        if not isinstance(latest_player, dict):
            return
        players = data.setdefault("players", {})
        if not isinstance(players, dict):
            return
        player = deepcopy(latest_player)
        for pending in self._pending_inputs:
            self._apply_predicted_input(player, pending.command, pending.dt)
        players[self.player_id] = player

    def _apply_predicted_input(self, player: dict[str, Any], command: dict[str, Any], dt: float) -> None:
        if not player.get("alive", True):
            return
        pos = player.get("pos")
        if not isinstance(pos, dict):
            return
        move_x = float(command.get("move_x", 0.0))
        move_y = float(command.get("move_y", 0.0))
        length = math.hypot(move_x, move_y)
        if length > 0.0001:
            move_x /= length
            move_y /= length
            sneak = bool(command.get("sneak", False))
            sprint = bool(command.get("sprint", False)) and not sneak
            speed = float(player.get("speed", 245.0))
            speed *= 0.48 if sneak else SPRINT_MULTIPLIER if sprint else 1.0
            pos["x"] = max(0.0, min(float(MAP_WIDTH), float(pos.get("x", 0.0)) + move_x * speed * dt))
            pos["y"] = max(0.0, min(float(MAP_HEIGHT), float(pos.get("y", 0.0)) + move_y * speed * dt))
            player["sneaking"] = sneak
            player["sprinting"] = sprint
        aim_x = command.get("aim_x")
        aim_y = command.get("aim_y")
        if aim_x is not None and aim_y is not None:
            player["angle"] = math.atan2(float(aim_y) - float(pos.get("y", 0.0)), float(aim_x) - float(pos.get("x", 0.0)))


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


def _movement_payload(command: InputCommand) -> dict[str, Any]:
    return {
        "move_x": round(command.move_x, 3),
        "move_y": round(command.move_y, 3),
        "aim_x": round(command.aim_x, 3),
        "aim_y": round(command.aim_y, 3),
        "shooting": command.shooting,
        "sprint": command.sprint,
        "sneak": command.sneak,
    }
