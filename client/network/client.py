from __future__ import annotations

import math
import contextlib
import queue
import socket
import threading
import time
from collections import deque
from copy import deepcopy
from dataclasses import replace
from typing import Any

from client.game.prediction.input_history import PendingInputRecord
from client.game.snapshot_handoff import SnapshotHandoff, SnapshotPacket
from client.network.connection import movement_payload, open_connection, rect_from_data
from client.network.delta_applier import decode_snapshot_payload, snapshot_from_message
from client.network.heartbeat import heartbeat_loop, send_heartbeat, send_state_hash
from client.network.interpolator import INTERPOLATION_DELAY_SECONDS, estimated_server_time, interpolated_data
from client.network.lod_snapshot_decoder import event_payload_metrics
from client.network.online_metrics import OnlinePerfStats
from client.network.reader import reader_loop
from client.network.reconnect import resume_loop
from client.network.snapshot_buffer import BufferedSnapshot
from client.network.writer import writer_loop
from shared.collision import move_circle_against_rects
from shared.constants import MAP_HEIGHT, MAP_WIDTH, PLAYER_RADIUS, SPRINT_MULTIPLIER
from shared.level import tunnel_walls
from shared.models import BuildingState, InputCommand, RectState, Vec2, WorldSnapshot
from shared.net_schema import SNAPSHOT_SCHEMA
from shared.protocol import FrameDecoder, encode_message
from shared.protocol_meta import CLIENT_FEATURES, CLIENT_VERSION, PROTOCOL_VERSION


MAX_INTERPOLATION_BUFFER = 32
MAX_PENDING_INPUTS = 80
INPUT_SEND_RATE = 25.0
INPUT_FORCE_INTERVAL_SECONDS = 0.25
PREDICTION_MAX_FRAME_DT = 1.0 / 30.0
PREDICTION_CORRECTION_DEADZONE = 36.0
PREDICTION_HARD_SNAP_DISTANCE = 180.0
PREDICTION_CORRECTION_SPEED = 14.0
PREDICTION_CORRECTION_EPSILON = 0.05


class OnlineClient:
    def __init__(self) -> None:
        self.player_id: str | None = None
        self.session_token: str | None = None
        self.resume_timeout: float = 0.0
        self.server_features: list[str] = []
        self.server_interest_radius: float = 1600.0
        self.server_building_interest_radius: float = 2200.0
        self.latest_snapshot: WorldSnapshot | None = None
        self.handoff = SnapshotHandoff()
        self.perf = OnlinePerfStats()
        self._snapshot_data: dict[str, Any] | None = None
        self._socket: socket.socket | None = None
        self._decoder = FrameDecoder()
        self._pending_messages: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._snapshot_lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._writer_thread: threading.Thread | None = None
        self._heartbeat_thread: threading.Thread | None = None
        self._reconnect_thread: threading.Thread | None = None
        self._outbox: queue.Queue[bytes | None] = queue.Queue(maxsize=256)
        self._host = ""
        self._port = 0
        self._name = ""
        self._manual_close = False
        self._connection_state = "offline"
        self._resume_deadline = 0.0
        self._connection_epoch = 0
        self._ping_ms: float | None = None
        self._last_ping_at = 0.0
        self._last_pong_at = 0.0
        self._last_state_hash_at = 0.0
        self._input_seq = 0
        self._command_id = 0
        self._last_snapshot_tick = -1
        self._last_snapshot_seq = 0
        self._ack_input_seq = 0
        self._last_input_sent_at = time.perf_counter()
        self._last_input_payload: dict[str, Any] | None = None
        self._last_prediction_at = 0.0
        self._predicted_player_data: dict[str, Any] | None = None
        self._prediction_correction_x = 0.0
        self._prediction_correction_y = 0.0
        self._collision_cache_key: tuple[int, int, int] | None = None
        self._collision_walls_cache: tuple[RectState, ...] = ()
        self._snapshot_buffer: deque[BufferedSnapshot] = deque(maxlen=MAX_INTERPOLATION_BUFFER)
        self._pending_inputs: deque[PendingInputRecord] = deque(maxlen=MAX_PENDING_INPUTS)
        self._latest_server_time = 0.0
        self._latest_received_at = 0.0
        self._snapshot_interval = 0.05
        self._render_cache_time = 0.0
        self._render_cache_snapshot: WorldSnapshot | None = None
        self._last_decode_ms = 0.0
        self._last_interpolation_ms = 0.0
        self._last_prediction_ms = 0.0
        self._last_prediction_error_px = 0.0
        self._last_snapshot_bytes = 0
        self._last_delta_bytes = 0
        self._last_events_bytes = 0
        self._last_actors_full = 0
        self._last_actors_simple = 0
        self._last_actors_dot = 0
        self._last_compression_ratio = 1.0
        self.events: deque[dict[str, Any]] = deque(maxlen=256)
        self._pending_commands: dict[int, dict[str, Any]] = {}
        self._command_results: deque[dict[str, Any]] = deque(maxlen=128)
        self.error: str | None = None

    def connect(self, host: str, port: int, name: str) -> None:
        self.close()
        self._manual_close = False
        self._connection_state = "connecting"
        self._host = host
        self._port = port
        self._name = name
        sock, decoder, pending, first = self._open_connection(
            host,
            port,
            encode_message(
                "hello",
                name=name,
                client_version=CLIENT_VERSION,
                protocol_version=PROTOCOL_VERSION,
                snapshot_schema=SNAPSHOT_SCHEMA,
                features=CLIENT_FEATURES,
            ),
        )
        if first["type"] != "welcome":
            sock.close()
            self._connection_state = "lost"
            raise ConnectionError(first.get("message", "server refused connection"))
        self._apply_welcome(sock, decoder, pending, first, reset_session=True)

    def _open_connection(
        self,
        host: str,
        port: int,
        payload: bytes,
    ) -> tuple[socket.socket, FrameDecoder, list[dict[str, Any]], dict[str, Any]]:
        return open_connection(host, port, payload)

    def _apply_welcome(
        self,
        sock: socket.socket,
        decoder: FrameDecoder,
        pending: list[dict[str, Any]],
        message: dict[str, Any],
        *,
        reset_session: bool,
    ) -> None:
        snapshot_data = message.get("snapshot")
        if not isinstance(snapshot_data, dict):
            sock.close()
            raise ConnectionError("server sent invalid world snapshot")
        decode_started = time.perf_counter()
        snapshot_data = self._decode_snapshot_payload(snapshot_data, message.get("schema"))
        self._last_decode_ms = (time.perf_counter() - decode_started) * 1000.0
        with self._lock:
            self._connection_epoch += 1
            epoch = self._connection_epoch
            self.player_id = str(message["player_id"])
            self.session_token = str(message.get("session_token", self.session_token or ""))
            self.resume_timeout = float(message.get("resume_timeout", self.resume_timeout or 0.0))
            features = message.get("server_features", [])
            self.server_features = [str(feature) for feature in features] if isinstance(features, list) else []
            self.server_interest_radius = float(message.get("interest_radius", self.server_interest_radius))
            self.server_building_interest_radius = float(message.get("building_interest_radius", self.server_building_interest_radius))
            self._socket = sock
            self._decoder = decoder
            self._pending_messages = pending
            self._running = True
            self._connection_state = "connected"
            self._outbox = queue.Queue(maxsize=256)
            self._last_input_sent_at = time.perf_counter()
            self._last_input_payload = None
            self._last_ping_at = 0.0
            self._last_pong_at = time.perf_counter()
            self._last_state_hash_at = 0.0
            self.error = None
            if reset_session:
                self._input_seq = 0
                self._command_id = 0
                self._ping_ms = None
        with self._snapshot_lock:
            self._snapshot_data = snapshot_data
            self.latest_snapshot = None
            self._last_snapshot_tick = int(message.get("tick", 0))
            self._last_snapshot_seq = int(message.get("seq", 0))
            self._ack_input_seq = int(message.get("ack_input_seq", 0))
            self._latest_server_time = float(message.get("server_time", snapshot_data.get("time", 0.0)))
            self._latest_received_at = time.perf_counter()
            self._snapshot_interval = float(message.get("snapshot_interval", self._snapshot_interval))
            self._snapshot_buffer.clear()
            self._snapshot_buffer.append(
                BufferedSnapshot(
                    self._last_snapshot_tick,
                    self._latest_server_time,
                    self._latest_received_at,
                    snapshot_data,
                )
            )
            self._pending_inputs.clear()
            if reset_session:
                self._pending_commands.clear()
                self._command_results.clear()
            self._reset_local_prediction(snapshot_data)
            self._collision_cache_key = None
            self._collision_walls_cache = ()
            self._render_cache_snapshot = None
            self.handoff.publish(
                SnapshotPacket(
                    tick=self._last_snapshot_tick,
                    seq=self._last_snapshot_seq,
                    ack_input_seq=self._ack_input_seq,
                    server_time=self._latest_server_time,
                    received_at=self._latest_received_at,
                    snapshot_data=snapshot_data,
                    decode_ms=self._last_decode_ms,
                )
            )
            self._update_perf_locked()
        sock.settimeout(None)
        self._writer_thread = threading.Thread(target=self._write_loop, args=(epoch,), name="online-writer", daemon=True)
        self._writer_thread.start()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, args=(epoch,), name="online-heartbeat", daemon=True)
        self._heartbeat_thread.start()
        self._thread = threading.Thread(target=self._read_loop, args=(epoch,), name="online-reader", daemon=True)
        self._thread.start()
        if not reset_session:
            self._resend_pending_commands()

    def send_input(self, command: InputCommand) -> None:
        if not self._socket or not self._running:
            return
        try:
            now = time.perf_counter()
            command_data = movement_payload(command)
            with self._snapshot_lock:
                self._predict_local_frame(command_data, now)
            with self._lock:
                if not self._should_send_input(command_data, now):
                    return
                self._input_seq += 1
                dt = max(1.0 / 120.0, min(1.0 / 20.0, now - self._last_input_sent_at))
                self._last_input_sent_at = now
                self._last_input_payload = command_data
                self._pending_inputs.append(PendingInputRecord(self._input_seq, command_data, dt))
                self._enqueue(encode_message("input", seq=self._input_seq, command=command_data))
        except (OSError, queue.Full) as exc:
            self.error = str(exc)
            self._running = False

    def _should_send_input(self, command_data: dict[str, Any], now: float) -> bool:
        previous = self._last_input_payload
        if previous is None:
            return True
        elapsed = now - self._last_input_sent_at
        movement_changed = any(
            abs(float(previous.get(key, 0.0)) - float(command_data.get(key, 0.0))) > 0.001
            for key in ("move_x", "move_y")
        )
        aim_changed = any(
            abs(float(previous.get(key, 0.0)) - float(command_data.get(key, 0.0))) > 4.0
            for key in ("aim_x", "aim_y")
        )
        urgent = movement_changed or aim_changed or any(previous.get(key) != command_data.get(key) for key in ("shooting", "sprint", "sneak"))
        if not urgent and elapsed < 1.0 / INPUT_SEND_RATE:
            return False
        if command_data == previous and elapsed < INPUT_FORCE_INTERVAL_SECONDS:
            return False
        return True

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

    @property
    def ping_ms(self) -> float | None:
        return self._ping_ms

    @property
    def connection_state(self) -> str:
        return self._connection_state

    def connection_quality(self) -> str:
        if self._connection_state in {"reconnecting", "lost"}:
            return "lost-connection"
        if not self._running:
            return "lost-connection"
        if self._last_pong_at and time.perf_counter() - self._last_pong_at > 3.0:
            return "packet-lost"
        ping = self._ping_ms
        if ping is None:
            return "unstable-connection"
        if ping >= 1000.0:
            return "packet-lost"
        if ping >= 350.0:
            return "unstable-connection"
        return "stable-connection"

    def close(self) -> None:
        self._manual_close = True
        self._running = False
        self._connection_epoch += 1
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
        self._connection_state = "offline"
        self._resume_deadline = 0.0
        self.player_id = None
        self.latest_snapshot = None
        self.handoff.clear()
        self._snapshot_data = None
        self.session_token = None
        self.resume_timeout = 0.0
        self.server_features = []
        self.server_interest_radius = 1600.0
        self.server_building_interest_radius = 2200.0
        self._ping_ms = None
        self._last_pong_at = 0.0
        self._last_input_payload = None
        self._host = ""
        self._port = 0
        self._name = ""
        try:
            self._outbox.put_nowait(None)
        except queue.Full:
            pass
        with self._snapshot_lock:
            self._snapshot_buffer.clear()
            self._pending_inputs.clear()
            self._pending_commands.clear()
            self._command_results.clear()
            self._predicted_player_data = None
            self._last_prediction_at = 0.0
            self._prediction_correction_x = 0.0
            self._prediction_correction_y = 0.0
            self._collision_cache_key = None
            self._collision_walls_cache = ()
            self._render_cache_snapshot = None
            self._update_perf_locked()

    def snapshot(self) -> WorldSnapshot | None:
        with self._snapshot_lock:
            now = time.perf_counter()
            if self._render_cache_snapshot and now - self._render_cache_time < 1.0 / 120.0:
                self._update_perf_locked(now)
                return self._render_cache_snapshot
            data = self._render_snapshot_data(now)
            if data is None:
                return self.latest_snapshot
            decode_started = time.perf_counter()
            snapshot = WorldSnapshot.from_dict(data)
            self._last_decode_ms = (time.perf_counter() - decode_started) * 1000.0
            self._render_cache_snapshot = snapshot
            self._render_cache_time = now
            self.latest_snapshot = snapshot
            self._update_perf_locked(now)
            return snapshot

    def snapshot_tick(self) -> int:
        with self._snapshot_lock:
            return self._last_snapshot_tick

    def flush_handoff(self) -> SnapshotPacket | None:
        packet = self.handoff.latest()
        if packet is None:
            return None
        with self._snapshot_lock:
            self._last_decode_ms = packet.decode_ms
            self._update_perf_locked()
        return packet

    def online_perf(self) -> OnlinePerfStats:
        with self._snapshot_lock:
            self._update_perf_locked()
            return replace(self.perf)

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

    def _write_loop(self, epoch: int) -> None:
        writer_loop(self, epoch)

    def _heartbeat_loop(self, epoch: int) -> None:
        heartbeat_loop(self, epoch)

    def _send_heartbeat(self) -> None:
        send_heartbeat(self)

    def _send_state_hash(self) -> None:
        send_state_hash(self)

    def _read_loop(self, epoch: int) -> None:
        reader_loop(self, epoch)

    def _handle_message(self, message: dict[str, Any]) -> None:
        message_type = message.get("type")
        if message_type == "snapshot":
            with self._snapshot_lock:
                snapshot_data = self._snapshot_from_message(message)
                if snapshot_data is None:
                    return
                self._snapshot_data = snapshot_data
                self.latest_snapshot = None
                self._last_snapshot_tick = int(message.get("tick", self._last_snapshot_tick))
                self._last_snapshot_seq = int(message.get("seq", self._last_snapshot_seq))
                self._ack_input_seq = max(self._ack_input_seq, int(message.get("ack_input_seq", self._ack_input_seq)))
                self._drop_acked_inputs()
                self._latest_server_time = float(message.get("server_time", snapshot_data.get("time", self._latest_server_time)))
                self._latest_received_at = time.perf_counter()
                self._snapshot_interval = float(message.get("snapshot_interval", self._snapshot_interval))
                self._snapshot_buffer.append(
                    BufferedSnapshot(
                        self._last_snapshot_tick,
                        self._latest_server_time,
                        self._latest_received_at,
                        snapshot_data,
                    )
                )
                self._reconcile_local_prediction(snapshot_data)
                self._collision_cache_key = None
                self._collision_walls_cache = ()
                self._render_cache_snapshot = None
                self.handoff.publish(
                    SnapshotPacket(
                        tick=self._last_snapshot_tick,
                        seq=self._last_snapshot_seq,
                        ack_input_seq=self._ack_input_seq,
                        server_time=self._latest_server_time,
                        received_at=self._latest_received_at,
                        snapshot_data=snapshot_data,
                        decode_ms=self._last_decode_ms,
                    )
                )
                self._update_perf_locked()
        elif message_type == "events":
            event_metrics = event_payload_metrics(message)
            self._last_events_bytes = event_metrics.events_bytes
            with self._snapshot_lock:
                for event in message.get("events", []):
                    if isinstance(event, dict):
                        self.events.append(event)
        elif message_type == "command_result":
            with self._snapshot_lock:
                command_id = int(message.get("command_id", 0))
                self._pending_commands.pop(command_id, None)
                self._command_results.append(dict(message))
        elif message_type == "state_hash_result":
            if not message.get("ok", True):
                with self._snapshot_lock:
                    self._snapshot_buffer.clear()
                    self._predicted_player_data = None
                    self._last_prediction_at = 0.0
                    self._prediction_correction_x = 0.0
                self._prediction_correction_y = 0.0
                self._collision_cache_key = None
                self._collision_walls_cache = ()
                self._render_cache_snapshot = None
                self.handoff.clear()
                self.events.append({"kind": "desync_resync", **dict(message)})
        elif message_type == "pong":
            sent = message.get("sent")
            with contextlib.suppress(TypeError, ValueError):
                self._ping_ms = max(0.0, (time.time() - float(sent)) * 1000.0)
                self.server_interest_radius = float(message.get("interest_radius", self.server_interest_radius))
                self.server_building_interest_radius = float(message.get("building_interest_radius", self.server_building_interest_radius))
            self._last_pong_at = time.perf_counter()
        elif message_type == "welcome":
            self.session_token = str(message.get("session_token", self.session_token or ""))
            self.resume_timeout = float(message.get("resume_timeout", self.resume_timeout or 0.0))
        elif message_type == "error":
            self.error = str(message.get("message", "server error"))
            if not self._manual_close:
                self._connection_state = "lost"

    def _should_resume_after_drop(self) -> bool:
        return (
            not self._manual_close
            and bool(self._host and self._port and self.player_id and self.session_token)
            and self.resume_timeout > 0.0
        )

    def _start_resume_loop(self) -> None:
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            return
        self._connection_state = "reconnecting"
        self._resume_deadline = time.perf_counter() + max(1.0, self.resume_timeout)
        self._reconnect_thread = threading.Thread(target=self._resume_loop, name="online-resume", daemon=True)
        self._reconnect_thread.start()

    def _resume_loop(self) -> None:
        resume_loop(self)

    def _resend_pending_commands(self) -> None:
        with self._snapshot_lock:
            commands = list(self._pending_commands.values())
        for command in commands:
            payload = command.get("payload", {})
            try:
                self._enqueue(
                    encode_message(
                        "command",
                        command_id=int(command.get("command_id", 0)),
                        kind=str(command.get("kind", "")),
                        payload=payload if isinstance(payload, dict) else {},
                    )
                )
            except (OSError, queue.Full, ValueError) as exc:
                self.error = str(exc)
                self._running = False
                return

    def _snapshot_from_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        result, decode_ms, payload_metrics = snapshot_from_message(self._snapshot_data, message)
        self._last_decode_ms = decode_ms
        self._last_snapshot_bytes = payload_metrics.snapshot_bytes
        self._last_delta_bytes = payload_metrics.delta_bytes
        self._last_actors_full = payload_metrics.actors_full
        self._last_actors_simple = payload_metrics.actors_simple
        self._last_actors_dot = payload_metrics.actors_dot
        self._last_compression_ratio = payload_metrics.compression_ratio
        return result

    def _decode_snapshot_payload(self, snapshot: dict[str, Any], schema: object) -> dict[str, Any]:
        return decode_snapshot_payload(snapshot, schema)

    def _drop_acked_inputs(self) -> None:
        while self._pending_inputs and self._pending_inputs[0].seq <= self._ack_input_seq:
            self._pending_inputs.popleft()

    def _update_perf_locked(self, now: float | None = None) -> None:
        current = now if now is not None else time.perf_counter()
        self.perf.snapshot_tick = self._last_snapshot_tick
        self.perf.snapshot_age_ms = max(0.0, (current - self._latest_received_at) * 1000.0) if self._latest_received_at else 0.0
        self.perf.snapshot_buffer_size = len(self._snapshot_buffer)
        self.perf.snapshot_interval_ms = max(0.0, self._snapshot_interval * 1000.0)
        self.perf.ping_ms = 0.0 if self._ping_ms is None else float(self._ping_ms)
        self.perf.pending_inputs = len(self._pending_inputs)
        self.perf.ack_input_seq = self._ack_input_seq
        self.perf.pending_commands = len(self._pending_commands)
        self.perf.prediction_error_px = self._last_prediction_error_px
        self.perf.correction_px = math.hypot(self._prediction_correction_x, self._prediction_correction_y)
        self.perf.network_state = self._connection_state
        self.perf.decode_ms = self._last_decode_ms
        self.perf.interpolation_ms = self._last_interpolation_ms
        self.perf.prediction_ms = self._last_prediction_ms
        self.perf.server_interest_radius = self.server_interest_radius
        self.perf.render_radius = min(self.server_interest_radius, self.server_building_interest_radius)
        self.perf.minimap_radius = max(self.server_interest_radius, 1400.0)
        self.perf.audio_radius = self.server_interest_radius
        self.perf.snapshot_bytes = self._last_snapshot_bytes
        self.perf.delta_bytes = self._last_delta_bytes
        self.perf.events_bytes = self._last_events_bytes
        self.perf.actors_full = self._last_actors_full
        self.perf.actors_simple = self._last_actors_simple
        self.perf.actors_dot = self._last_actors_dot
        self.perf.compression_ratio = self._last_compression_ratio

    def _render_snapshot_data(self, now: float) -> dict[str, Any] | None:
        if not self._snapshot_data:
            return None
        render_time = self._estimated_server_time(now) - INTERPOLATION_DELAY_SECONDS
        interpolation_started = time.perf_counter()
        source = self._interpolated_data(render_time)
        self._last_interpolation_ms = (time.perf_counter() - interpolation_started) * 1000.0
        if source is None:
            source = self._snapshot_data
        if self.player_id and (self._predicted_player_data is not None or self._pending_inputs):
            data = dict(source)
            players = source.get("players", {})
            data["players"] = dict(players) if isinstance(players, dict) else {}
        else:
            data = source
        prediction_started = time.perf_counter()
        self._apply_local_prediction(data)
        self._last_prediction_ms = (time.perf_counter() - prediction_started) * 1000.0
        return data

    def _estimated_server_time(self, now: float) -> float:
        return estimated_server_time(now, self._latest_server_time, self._latest_received_at)

    def _interpolated_data(self, render_time: float) -> dict[str, Any] | None:
        return interpolated_data(self._snapshot_buffer, self._snapshot_data, render_time, self.player_id)

    def _apply_local_prediction(self, data: dict[str, Any]) -> None:
        if not self.player_id or not self._snapshot_data:
            return
        players = data.setdefault("players", {})
        if not isinstance(players, dict):
            return
        if self._predicted_player_data is not None:
            players[self.player_id] = deepcopy(self._predicted_player_data)
            return
        player = self._replayed_authoritative_player(self._snapshot_data)
        if player is not None:
            players[self.player_id] = player

    def _reset_local_prediction(self, snapshot_data: dict[str, Any]) -> None:
        player = self._local_player_from_data(snapshot_data)
        self._predicted_player_data = deepcopy(player) if player is not None else None
        self._last_prediction_at = time.perf_counter()
        self._prediction_correction_x = 0.0
        self._prediction_correction_y = 0.0

    def _reconcile_local_prediction(self, snapshot_data: dict[str, Any]) -> None:
        target = self._replayed_authoritative_player(snapshot_data)
        if target is None:
            self._predicted_player_data = None
            self._last_prediction_at = 0.0
            self._prediction_correction_x = 0.0
            self._prediction_correction_y = 0.0
            return
        current = self._predicted_player_data
        if current is None:
            self._predicted_player_data = target
            self._last_prediction_at = time.perf_counter()
            self._prediction_correction_x = 0.0
            self._prediction_correction_y = 0.0
            return
        current_pos = current.get("pos")
        target_pos = target.get("pos")
        if not isinstance(current_pos, dict) or not isinstance(target_pos, dict):
            self._predicted_player_data = target
            self._prediction_correction_x = 0.0
            self._prediction_correction_y = 0.0
            return
        critical_changed = (
            bool(current.get("alive", True)) != bool(target.get("alive", True))
            or int(current.get("floor", 0)) != int(target.get("floor", 0))
        )
        current_x = float(current_pos.get("x", 0.0))
        current_y = float(current_pos.get("y", 0.0))
        target_x = float(target_pos.get("x", current_x))
        target_y = float(target_pos.get("y", current_y))
        error_x = target_x - current_x
        error_y = target_y - current_y
        distance = math.hypot(error_x, error_y)
        self._last_prediction_error_px = distance
        if critical_changed or distance >= PREDICTION_HARD_SNAP_DISTANCE:
            self._predicted_player_data = target
            self._prediction_correction_x = 0.0
            self._prediction_correction_y = 0.0
            self._last_prediction_at = time.perf_counter()
            return
        target["pos"] = {"x": current_x, "y": current_y}
        target["angle"] = current.get("angle", target.get("angle", 0.0))
        target["sprinting"] = bool(current.get("sprinting", target.get("sprinting", False)))
        target["sneaking"] = bool(current.get("sneaking", target.get("sneaking", False)))
        self._predicted_player_data = target
        if distance > PREDICTION_CORRECTION_DEADZONE:
            self._prediction_correction_x = error_x
            self._prediction_correction_y = error_y
        else:
            self._prediction_correction_x = 0.0
            self._prediction_correction_y = 0.0

    def _replayed_authoritative_player(self, snapshot_data: dict[str, Any]) -> dict[str, Any] | None:
        player = self._local_player_from_data(snapshot_data)
        if player is None:
            return None
        replayed = deepcopy(player)
        for pending in self._pending_inputs:
            self._apply_predicted_input(replayed, pending.command, pending.dt)
        return replayed

    def _local_player_from_data(self, snapshot_data: dict[str, Any]) -> dict[str, Any] | None:
        if not self.player_id:
            return None
        players = snapshot_data.get("players", {})
        player = players.get(self.player_id) if isinstance(players, dict) else None
        return player if isinstance(player, dict) else None

    def _predict_local_frame(self, command: dict[str, Any], now: float) -> None:
        if not self.player_id or not self._snapshot_data:
            return
        if self._predicted_player_data is None:
            self._reset_local_prediction(self._snapshot_data)
        if self._predicted_player_data is None:
            return
        if self._last_prediction_at <= 0.0:
            self._last_prediction_at = now
            return
        dt = max(0.0, min(PREDICTION_MAX_FRAME_DT, now - self._last_prediction_at))
        self._last_prediction_at = now
        if dt <= 0.0:
            return
        self._apply_predicted_input(self._predicted_player_data, command, dt)
        self._apply_prediction_correction(self._predicted_player_data, dt)
        self._render_cache_snapshot = None

    def _apply_prediction_correction(self, player: dict[str, Any], dt: float) -> None:
        if abs(self._prediction_correction_x) <= PREDICTION_CORRECTION_EPSILON and abs(self._prediction_correction_y) <= PREDICTION_CORRECTION_EPSILON:
            self._prediction_correction_x = 0.0
            self._prediction_correction_y = 0.0
            return
        pos = player.get("pos")
        if not isinstance(pos, dict):
            self._prediction_correction_x = 0.0
            self._prediction_correction_y = 0.0
            return
        blend = 1.0 - math.exp(-PREDICTION_CORRECTION_SPEED * dt)
        apply_x = self._prediction_correction_x * blend
        apply_y = self._prediction_correction_y * blend
        pos["x"] = max(0.0, min(float(MAP_WIDTH), float(pos.get("x", 0.0)) + apply_x))
        pos["y"] = max(0.0, min(float(MAP_HEIGHT), float(pos.get("y", 0.0)) + apply_y))
        self._prediction_correction_x -= apply_x
        self._prediction_correction_y -= apply_y

    def _apply_predicted_input(self, player: dict[str, Any], command: dict[str, Any], dt: float) -> None:
        if not player.get("alive", True):
            return
        pos = player.get("pos")
        if not isinstance(pos, dict):
            return
        move_x = float(command.get("move_x", 0.0))
        move_y = float(command.get("move_y", 0.0))
        length = math.hypot(move_x, move_y)
        sneak = bool(command.get("sneak", False))
        sprint = bool(command.get("sprint", False)) and not sneak
        player["sneaking"] = sneak and length > 0.0001
        player["sprinting"] = sprint and length > 0.0001
        if length > 0.0001:
            move_x /= length
            move_y /= length
            speed = float(player.get("speed", 245.0))
            speed *= 0.48 if sneak else SPRINT_MULTIPLIER if sprint else 1.0
            predicted_pos = Vec2(float(pos.get("x", 0.0)), float(pos.get("y", 0.0)))
            floor = int(player.get("floor", 0))
            move_circle_against_rects(
                predicted_pos,
                Vec2(move_x * speed * dt, move_y * speed * dt),
                PLAYER_RADIUS,
                self._prediction_walls(floor),
            )
            predicted_pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
            pos["x"] = predicted_pos.x
            pos["y"] = predicted_pos.y
        aim_x = command.get("aim_x")
        aim_y = command.get("aim_y")
        if aim_x is not None and aim_y is not None:
            player["angle"] = math.atan2(float(aim_y) - float(pos.get("y", 0.0)), float(aim_x) - float(pos.get("x", 0.0)))

    def _prediction_walls(self, floor: int) -> tuple[RectState, ...]:
        snapshot_data = self._snapshot_data
        if not snapshot_data:
            return ()
        cache_key = (id(snapshot_data), self._last_snapshot_tick, floor)
        if self._collision_cache_key == cache_key:
            return self._collision_walls_cache
        walls: list[RectState] = []
        buildings = snapshot_data.get("buildings", {})
        if isinstance(buildings, dict):
            parsed_buildings: dict[str, BuildingState] = {}
            for building in buildings.values():
                if not isinstance(building, dict):
                    continue
                with contextlib.suppress(TypeError, ValueError, KeyError):
                    parsed = BuildingState.from_dict(building)
                    parsed_buildings[parsed.id] = parsed
                for wall_data in building.get("walls") or []:
                    wall = rect_from_data(wall_data)
                    if wall:
                        walls.append(wall)
                for prop in building.get("props") or []:
                    if not isinstance(prop, dict):
                        continue
                    if int(prop.get("floor", 0)) != floor or not bool(prop.get("blocks", True)):
                        continue
                    wall = rect_from_data(prop.get("rect"))
                    if wall:
                        walls.append(wall)
                for door in building.get("doors") or []:
                    if not isinstance(door, dict):
                        continue
                    if bool(door.get("open", False)) or int(door.get("floor", 0)) != floor:
                        continue
                    wall = rect_from_data(door.get("rect"))
                    if wall:
                        walls.append(wall)
            if floor == -1 and parsed_buildings:
                walls.extend(tunnel_walls(parsed_buildings))
        self._collision_cache_key = cache_key
        self._collision_walls_cache = tuple(walls)
        return self._collision_walls_cache



