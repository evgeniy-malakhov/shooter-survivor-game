from __future__ import annotations

import asyncio
import contextlib
import secrets
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque

from server.config import ServerTuning, load_server_tuning
from server.events import derive_events, filter_events_for_snapshot
from server.http_endpoints import ServerHTTPProbe
from server.journal import ServerJournal
from server.persistence import PersistenceWorker
from server.runtime_metrics import ServerMetrics
from server.spatial import POSITION_COLLECTIONS, SnapshotInterestIndex, filter_snapshot_area, snapshot_with_local_player
from server.workers import AsyncLogWorker, ServerProfiler
from shared.constants import SNAPSHOT_RATE, TICK_RATE
from shared.net_schema import SNAPSHOT_SCHEMA, compact_delta, compact_snapshot
from shared.models import ClientCommand, InputCommand, PlayerState
from shared.protocol import FrameDecoder, SERIALIZER_NAME, encode_message
from shared.protocol_meta import PROTOCOL_VERSION, SERVER_FEATURES, SERVER_VERSION
from shared.simulation import GameWorld
from shared.snapshot_delta import make_snapshot_delta
from shared.state_hash import snapshot_hash


@dataclass(slots=True)
class SimulationSnapshot:
    data: dict[str, Any]
    tick: int


class SimulationRunner:
    def __init__(
        self,
        difficulty_key: str,
        *,
        tick_rate: int = TICK_RATE,
        snapshot_rate: int = SNAPSHOT_RATE,
        command_queue_limit: int = 128,
        zombie_workers: int | None = 0,
        zombie_ai_decision_rate: float = 6.0,
        zombie_ai_far_decision_rate: float = 2.0,
        zombie_ai_active_radius: float = 1800.0,
        zombie_ai_far_radius: float = 3200.0,
        zombie_ai_batch_size: int = 8,
        pvp: bool = False,
        tick_observer: Callable[[float], None] | None = None,
        stage_observer: Callable[[str, float], None] | None = None,
    ) -> None:
        self.pvp = pvp
        self.world = GameWorld(
            difficulty_key=difficulty_key,
            initial_zombies=0 if pvp else None,
            max_zombies=0 if pvp else None,
            zombie_workers=0 if pvp else zombie_workers,
            zombie_ai_decision_rate=zombie_ai_decision_rate,
            zombie_ai_far_decision_rate=zombie_ai_far_decision_rate,
            zombie_ai_active_radius=zombie_ai_active_radius,
            zombie_ai_far_radius=zombie_ai_far_radius,
            zombie_ai_batch_size=zombie_ai_batch_size,
        )
        self.tick_rate = max(1, int(tick_rate))
        self.snapshot_rate = max(1, int(snapshot_rate))
        self.command_queue_limit = max(1, int(command_queue_limit))
        self.tick_observer = tick_observer
        self.stage_observer = stage_observer
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="simulation-runner", daemon=True)
        self._input_lock = threading.Lock()
        self._pending_inputs: dict[str, tuple[int, InputCommand]] = {}
        self._pending_commands: dict[str, Deque[ClientCommand]] = {}
        self._pending_command_ids: dict[str, set[int]] = {}
        self._command_received_at: dict[tuple[str, int], float] = {}
        self._last_command_ids: dict[str, int] = {}
        self._command_results: Deque[dict[str, Any]] = deque()
        self._domain_events: Deque[dict[str, Any]] = deque()
        self._acked_inputs: dict[str, int] = {}
        self._snapshot_lock = threading.Lock()
        self._snapshot = SimulationSnapshot(self.world.snapshot().to_dict(), tick=0)
        self._last_tick_seconds = 0.0
        self._tick_id = 0

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)
        self.world.close()

    def add_player(self, name: str) -> tuple[PlayerState, SimulationSnapshot]:
        player = self.world.add_player(name)
        with self._input_lock:
            self._acked_inputs[player.id] = 0
            self._pending_commands[player.id] = deque()
            self._pending_command_ids[player.id] = set()
            self._last_command_ids[player.id] = 0
        snapshot = SimulationSnapshot(self.world.snapshot().to_dict(), self._tick_id)
        self._publish_snapshot(snapshot)
        return player, snapshot

    def remove_player(self, player_id: str) -> None:
        with self._input_lock:
            self._pending_inputs.pop(player_id, None)
            self._pending_commands.pop(player_id, None)
            self._pending_command_ids.pop(player_id, None)
            self._last_command_ids.pop(player_id, None)
            for key in [key for key in self._command_received_at if key[0] == player_id]:
                self._command_received_at.pop(key, None)
            self._acked_inputs.pop(player_id, None)
        self.world.remove_player(player_id)
        self._refresh_snapshot()

    def rename_player(self, player_id: str, name: str) -> None:
        self.world.rename_player(player_id, name)
        self._refresh_snapshot()

    def stop_player_input(self, player_id: str) -> None:
        self.world.set_input(InputCommand(player_id=player_id))
        with self._input_lock:
            self._pending_inputs.pop(player_id, None)

    def set_input(self, command: InputCommand, sequence: int) -> None:
        with self._input_lock:
            previous = self._pending_inputs.get(command.player_id)
            if previous and sequence <= previous[0]:
                return
            self._pending_inputs[command.player_id] = (sequence, command)

    def ack_input_seq(self, player_id: str) -> int:
        with self._input_lock:
            return self._acked_inputs.get(player_id, 0)

    def queue_command(self, command: ClientCommand) -> tuple[bool, str]:
        with self._input_lock:
            last_id = self._last_command_ids.get(command.player_id, 0)
            pending_ids = self._pending_command_ids.setdefault(command.player_id, set())
            if command.command_id <= last_id:
                self._command_results.append(
                    self._command_result(command, True, "", duplicate=True)
                )
                return True, ""
            if command.command_id in pending_ids:
                return False, "duplicate_pending"
            queue = self._pending_commands.setdefault(command.player_id, deque())
            if len(queue) >= self.command_queue_limit:
                return False, "command_queue_full"
            queue.append(command)
            pending_ids.add(command.command_id)
            self._command_received_at[(command.player_id, command.command_id)] = time.perf_counter()
            return True, ""

    def drain_command_results(self) -> list[dict[str, Any]]:
        with self._input_lock:
            results = list(self._command_results)
            self._command_results.clear()
            return results

    def drain_domain_events(self) -> list[dict[str, Any]]:
        with self._input_lock:
            events = list(self._domain_events)
            self._domain_events.clear()
            return events

    def snapshot(self) -> SimulationSnapshot:
        with self._snapshot_lock:
            return self._snapshot

    def zombie_count(self) -> int:
        return self.world.zombie_count()

    def player_profile(self, player_id: str) -> dict[str, Any] | None:
        snapshot = self.world.snapshot().to_dict()
        player = snapshot.get("players", {}).get(player_id) if isinstance(snapshot.get("players"), dict) else None
        if not isinstance(player, dict):
            return None
        return {
            "player_id": player_id,
            "position": player.get("pos"),
            "floor": player.get("floor", 0),
            "inside_building": player.get("inside_building"),
            "health": player.get("health", 0),
            "armor": player.get("armor", 0),
            "score": player.get("score", 0),
            "kills_by_kind": player.get("kills_by_kind", {}),
            "backpack": player.get("backpack", []),
            "equipment": player.get("equipment", {}),
            "quick_items": player.get("quick_items", {}),
            "weapons": player.get("weapons", {}),
        }

    def tick_seconds(self) -> float:
        return self._last_tick_seconds

    def is_alive(self) -> bool:
        return self._thread.is_alive() and not self._stop.is_set()

    def _run(self) -> None:
        dt = 1.0 / self.tick_rate
        snapshot_delay = 1.0 / self.snapshot_rate
        next_tick = time.perf_counter()
        next_snapshot = next_tick
        while not self._stop.is_set():
            now = time.perf_counter()
            did_work = False

            if now >= next_tick:
                started = time.perf_counter()
                stage_started = time.perf_counter()
                self._apply_pending_commands()
                self._observe_stage("command_apply_ms", time.perf_counter() - stage_started)
                stage_started = time.perf_counter()
                self._apply_pending_inputs()
                self._observe_stage("input_apply_ms", time.perf_counter() - stage_started)
                stage_started = time.perf_counter()
                self.world.update(dt)
                self._observe_stage("world_update_ms", time.perf_counter() - stage_started)
                self._collect_domain_events()
                self._tick_id += 1
                self._last_tick_seconds = time.perf_counter() - started
                if self.tick_observer:
                    self.tick_observer(self._last_tick_seconds)
                next_tick += dt
                if next_tick < now - dt:
                    next_tick = now + dt
                did_work = True

            if now >= next_snapshot:
                self._refresh_snapshot()
                next_snapshot += snapshot_delay
                if next_snapshot < now - snapshot_delay:
                    next_snapshot = now + snapshot_delay
                did_work = True

            if not did_work:
                sleep_for = min(next_tick, next_snapshot) - time.perf_counter()
                self._stop.wait(max(0.001, min(0.01, sleep_for)))

    def _apply_pending_inputs(self) -> None:
        with self._input_lock:
            commands = list(self._pending_inputs.values())
            self._pending_inputs.clear()
        for sequence, command in commands:
            self.world.set_input(command)
            with self._input_lock:
                self._acked_inputs[command.player_id] = max(self._acked_inputs.get(command.player_id, 0), sequence)

    def _apply_pending_commands(self) -> None:
        with self._input_lock:
            commands: list[ClientCommand] = []
            for queue in self._pending_commands.values():
                commands.extend(queue)
                queue.clear()
        for command in commands:
            ok, reason = self.world.apply_client_command(command)
            with self._input_lock:
                self._pending_command_ids.setdefault(command.player_id, set()).discard(command.command_id)
                self._last_command_ids[command.player_id] = max(
                    self._last_command_ids.get(command.player_id, 0),
                    command.command_id,
                )
                self._command_results.append(self._command_result(command, ok, reason))
            self._collect_domain_events()

    def _command_result(
        self,
        command: ClientCommand,
        ok: bool,
        reason: str,
        duplicate: bool = False,
    ) -> dict[str, Any]:
        result = {
            "player_id": command.player_id,
            "command_id": command.command_id,
            "kind": command.kind,
            "ok": ok,
            "server_tick": self._tick_id,
        }
        if reason:
            result["reason"] = reason
        if duplicate:
            result["duplicate"] = True
        received_at = self._command_received_at.pop((command.player_id, command.command_id), None)
        if received_at is not None:
            result["server_command_latency_ms"] = round((time.perf_counter() - received_at) * 1000.0, 3)
        return result

    def _collect_domain_events(self) -> None:
        events = self.world.drain_domain_events()
        if not events:
            return
        with self._input_lock:
            self._domain_events.extend(events)

    def _refresh_snapshot(self) -> None:
        started = time.perf_counter()
        snapshot = SimulationSnapshot(self.world.snapshot().to_dict(), self._tick_id)
        self._observe_stage("snapshot_collect_ms", time.perf_counter() - started)
        self._publish_snapshot(snapshot)

    def _publish_snapshot(self, snapshot: SimulationSnapshot) -> None:
        with self._snapshot_lock:
            self._snapshot = snapshot

    def _observe_stage(self, name: str, seconds: float) -> None:
        if self.stage_observer:
            self.stage_observer(name, seconds)


@dataclass(slots=True)
class OutboundPacket:
    payload: bytes
    kind: str = "control"
    created_at: float = field(default_factory=time.perf_counter)


class ClientOutputQueue:
    def __init__(self, max_packets: int) -> None:
        self._max_packets = max_packets
        self._reliable: Deque[OutboundPacket] = deque()
        self._unreliable: Deque[OutboundPacket] = deque()
        self._event = asyncio.Event()
        self._closed = False

    def __len__(self) -> int:
        return len(self._reliable) + len(self._unreliable)

    @property
    def full(self) -> bool:
        return len(self) >= self._max_packets

    def close(self) -> None:
        self._closed = True
        self._event.set()

    def make_room_for_snapshot(self) -> bool:
        if not self.full:
            return False
        return self._drop_oldest_snapshot()

    def pending_snapshots(self) -> int:
        return len(self._unreliable)

    def trim_snapshots(self, max_pending: int = 1) -> int:
        dropped = 0
        while len(self._unreliable) > max(0, max_pending):
            self._unreliable.popleft()
            dropped += 1
        return dropped

    def replace_snapshot(self, packet: OutboundPacket, max_pending: int = 1) -> int:
        dropped = self.trim_snapshots(max(0, max_pending - 1))
        if max_pending <= 1 and self._unreliable:
            self._unreliable.clear()
            dropped += 1
        self._unreliable.append(packet)
        self._event.set()
        return dropped

    def put(self, packet: OutboundPacket) -> bool:
        if self._closed:
            return False
        if packet.kind == "snapshot":
            self.replace_snapshot(packet)
            return True
        if self.full:
            self._drop_oldest_snapshot()
        if self.full:
            return False
        if packet.kind == "snapshot":
            self._unreliable.append(packet)
        else:
            self._reliable.append(packet)
        self._event.set()
        return True

    async def get(self) -> OutboundPacket | None:
        while not self._reliable and not self._unreliable:
            if self._closed:
                return None
            self._event.clear()
            if self._reliable or self._unreliable:
                break
            await self._event.wait()
        if self._reliable:
            return self._reliable.popleft()
        return self._unreliable.popleft() if self._unreliable else None

    def _drop_oldest_snapshot(self) -> bool:
        if not self._unreliable:
            return False
        kept: Deque[OutboundPacket] = deque()
        dropped = False
        while self._unreliable:
            packet = self._unreliable.popleft()
            if packet.kind == "snapshot":
                dropped = True
                break
            kept.append(packet)
        kept.extend(self._unreliable)
        self._unreliable = kept
        return dropped


@dataclass(slots=True)
class ClientSession:
    player_id: str
    name: str
    session_token: str
    protocol: "GameProtocol"
    outbox: ClientOutputQueue
    writer_task: asyncio.Task[None] | None = None
    last_snapshot: dict[str, Any] | None = None
    last_snapshot_tick: int = -1
    snapshots_since_full: int = 0
    sequence: int = 0
    last_received_input_seq: int = 0
    dropped_snapshots: int = 0
    snapshot_stride: int = 1
    snapshot_skip: int = 0
    ping_ms: float | None = None
    last_seen: float = 0.0
    last_hash_tick: int = -1
    slow_until: float = 0.0
    snapshot_hashes: Deque[tuple[int, str]] = field(default_factory=lambda: deque(maxlen=96))
    rate_window_started: float = 0.0
    input_count_window: int = 0
    command_count_window: int = 0
    bytes_count_window: int = 0


@dataclass(slots=True)
class ResumeTicket:
    player_id: str
    name: str
    session_token: str
    expires_at: float
    last_input_seq: int = 0
    last_snapshot_tick: int = 0
    ping_ms: float | None = None


class GameProtocol(asyncio.Protocol):
    def __init__(self, server: "GameServer") -> None:
        self.server = server
        self.decoder = FrameDecoder()
        self.transport: asyncio.Transport | None = None
        self.player_id: str | None = None
        self._write_ready = asyncio.Event()
        self._write_ready.set()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]
        self.server.metrics.accepted_connections_total += 1
        self.server.note_connection_attempt()
        if self.transport:
            self.transport.set_write_buffer_limits(
                high=self.server.tuning.network.write_buffer_high_water,
                low=self.server.tuning.network.write_buffer_low_water,
            )
        raw_socket = transport.get_extra_info("socket")
        with contextlib.suppress(OSError, AttributeError):
            raw_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def data_received(self, data: bytes) -> None:
        self.server.metrics.bytes_received_total += len(data)
        if self.player_id and self.server._bytes_rate_limited(self.player_id, len(data)):
            self.close()
            return
        try:
            messages = self.decoder.feed(data)
        except ValueError as exc:
            self.server.reject(self, f"protocol error: {exc}")
            return
        for message in messages:
            self.server.handle_message(self, message)

    def pause_writing(self) -> None:
        self._write_ready.clear()

    def resume_writing(self) -> None:
        self._write_ready.set()

    def connection_lost(self, exc: Exception | None) -> None:
        self.server.protocol_lost(self)

    async def wait_writable(self) -> None:
        await self._write_ready.wait()

    def write(self, payload: bytes) -> None:
        if self.transport and not self.transport.is_closing():
            self.server.metrics.bytes_sent_total += len(payload)
            self.transport.write(payload)

    def close(self) -> None:
        if self.transport and not self.transport.is_closing():
            self.transport.close()


class GameServer:
    def __init__(
        self,
        host: str,
        port: int,
        difficulty_key: str = "medium",
        *,
        pvp: bool = False,
        profile: bool = False,
        zombie_workers: int | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.difficulty_key = difficulty_key
        self.pvp = pvp
        self.server_mode = "pvp" if pvp else "survival"
        self.tuning: ServerTuning = load_server_tuning()
        self.metrics = ServerMetrics()
        self.tick_rate = self.tuning.simulation.tick_rate
        self.snapshot_rate = self.tuning.simulation.snapshot_rate
        self._current_snapshot_rate = self.snapshot_rate
        self.simulation = SimulationRunner(
            difficulty_key,
            tick_rate=self.tick_rate,
            snapshot_rate=self.snapshot_rate,
            command_queue_limit=self.tuning.network.command_queue_limit,
            zombie_workers=zombie_workers
            if zombie_workers is not None
            else self.tuning.simulation.zombie_ai_process_workers,
            zombie_ai_decision_rate=self.tuning.simulation.zombie_ai_decision_rate,
            zombie_ai_far_decision_rate=self.tuning.simulation.zombie_ai_far_decision_rate,
            zombie_ai_active_radius=self.tuning.simulation.zombie_ai_active_radius,
            zombie_ai_far_radius=self.tuning.simulation.zombie_ai_far_radius,
            zombie_ai_batch_size=self.tuning.simulation.zombie_ai_batch_size,
            pvp=pvp,
            tick_observer=self.metrics.observe_tick,
            stage_observer=self.metrics.observe_stage,
        )
        self.clients: dict[str, ClientSession] = {}
        self.resume_tickets: dict[str, ResumeTicket] = {}
        self._player_tokens: dict[str, str] = {}
        self._server: asyncio.AbstractServer | None = None
        self._tasks: list[asyncio.Task[None]] = []
        self._shutdown_event: asyncio.Event | None = None
        self._shutdown_requested = False
        self.log_worker = AsyncLogWorker()
        self.persistence = PersistenceWorker()
        self.journal = ServerJournal(self.tuning.network.journal_seconds)
        self.http_probe: ServerHTTPProbe | None = None
        self.profiler = ServerProfiler(enabled=profile)
        self.profile_enabled = profile
        self._event_source_snapshot: dict[str, Any] | None = None
        self._snapshot_cursor = 0
        self._interest_index_cache_key: tuple[Any, ...] | None = None
        self._interest_index_cache: SnapshotInterestIndex | None = None
        self._connection_times: Deque[float] = deque()

    async def start(self) -> None:
        await self.log_worker.start()
        await self.persistence.start()
        self.simulation.start()
        loop = asyncio.get_running_loop()
        try:
            self._shutdown_event = asyncio.Event()
            if self.tuning.observability.enabled:
                self.http_probe = ServerHTTPProbe(
                    self.tuning.observability.host,
                    self.tuning.observability.port,
                    metrics_text=self._metrics_text,
                    health=self._health_payload,
                    ready=self._ready_payload,
                )
                try:
                    await self.http_probe.start()
                except OSError as exc:
                    self.log_worker.info(
                        f"HTTP probes disabled: {self.tuning.observability.host}:{self.tuning.observability.port} "
                        f"is unavailable ({exc})"
                    )
                    self.http_probe = None
            self._server = await loop.create_server(
                lambda: GameProtocol(self),
                self.host,
                self.port,
                backlog=self.tuning.network.listen_backlog,
            )
            self._tasks = [
                asyncio.create_task(self._snapshot_loop(), name="snapshot-sender"),
                asyncio.create_task(self._command_result_loop(), name="command-results"),
                asyncio.create_task(self._resume_cleanup_loop(), name="resume-cleanup"),
            ]
            if self.profile_enabled:
                self._tasks.append(asyncio.create_task(self._profile_loop(), name="server-profiler"))
            sockets = ", ".join(str(sock.getsockname()) for sock in self._server.sockets or [])
            self.log_worker.info(
                f"Neon Outbreak server listening on {sockets} [{self.server_mode}/{self.difficulty_key}] "
                f"codec={SERIALIZER_NAME} tick={self.tick_rate}Hz snapshots={self.snapshot_rate}Hz"
            )
            if self.http_probe:
                self.log_worker.info(
                    f"HTTP probes listening on {self.tuning.observability.host}:{self.tuning.observability.port} "
                    "(/metrics /health /ready)"
                )
            self.persistence.record_session(
                "server_started",
                host=self.host,
                port=self.port,
                difficulty=self.difficulty_key,
                mode=self.server_mode,
            )
            async with self._server:
                await self._shutdown_event.wait()
        finally:
            self.persistence.record_session("server_stopping", active_clients=len(self.clients), resume_tickets=len(self.resume_tickets))
            for session in list(self.clients.values()):
                self._persist_player_profile(session.player_id)
            for ticket in list(self.resume_tickets.values()):
                self._persist_player_profile(ticket.player_id)
            for task in self._tasks:
                task.cancel()
            if self._tasks:
                await asyncio.gather(*self._tasks, return_exceptions=True)
            for session in list(self.clients.values()):
                session.protocol.close()
                session.outbox.close()
                if session.writer_task:
                    session.writer_task.cancel()
            self.clients.clear()
            self.simulation.stop()
            await self.persistence.stop()
            if self.http_probe:
                await self.http_probe.stop()
            await self.log_worker.stop()

    def request_shutdown(self, reason: str = "shutdown") -> None:
        if self._shutdown_requested:
            return
        self._shutdown_requested = True
        if self._server:
            self._server.close()
        for session in list(self.clients.values()):
            self._queue_events(
                session,
                self.simulation.snapshot().tick,
                float(self.simulation.snapshot().data.get("time", 0.0)),
                [{"kind": "server_shutdown", "reason": reason}],
            )
        self.persistence.record_session("server_shutdown_requested", reason=reason)
        asyncio.create_task(self._finish_shutdown())

    async def _finish_shutdown(self) -> None:
        await asyncio.sleep(0.35)
        for session in list(self.clients.values()):
            session.protocol.close()
        if self._shutdown_event:
            self._shutdown_event.set()

    def handle_message(self, protocol: GameProtocol, message: dict[str, Any]) -> None:
        message_type = str(message.get("type", ""))
        if protocol.player_id is None:
            if message_type == "ping":
                self._send_ping(protocol, message)
                return
            if message_type == "hello":
                self._accept_player(protocol, message)
                return
            if message_type == "resume":
                self._resume_player(protocol, message)
                return
            self.reject(protocol, "expected hello")
            return

        session = self.clients.get(protocol.player_id)
        if not session:
            self.reject(protocol, "unknown session")
            return
        if message_type == "input":
            self._handle_input(session, message)
        elif message_type == "command":
            self._handle_command(session, message)
        elif message_type == "state_hash":
            self._handle_state_hash(session, message)
        elif message_type == "profile":
            name = str(message.get("name", ""))[:18]
            session.name = name
            self.simulation.rename_player(session.player_id, name)
        elif message_type == "ping":
            self._handle_session_ping(session, message)

    def protocol_lost(self, protocol: GameProtocol) -> None:
        player_id = protocol.player_id
        if not player_id:
            return
        session = self.clients.pop(player_id, None)
        if not session:
            return
        session.outbox.close()
        if session.writer_task:
            session.writer_task.cancel()
        expires_at = time.monotonic() + self.tuning.network.resume_timeout_seconds
        self.resume_tickets[player_id] = ResumeTicket(
            player_id=player_id,
            name=session.name,
            session_token=session.session_token,
            expires_at=expires_at,
            last_input_seq=session.last_received_input_seq,
            last_snapshot_tick=session.last_snapshot_tick,
            ping_ms=session.ping_ms,
        )
        self.simulation.stop_player_input(player_id)
        self._persist_player_profile(player_id)
        self.persistence.record_session(
            "player_disconnected",
            player_id=player_id,
            resume_until=time.time() + self.tuning.network.resume_timeout_seconds,
        )
        self.log_worker.info(f"player disconnected: {player_id}, resume window {self.tuning.network.resume_timeout_seconds:.0f}s")

    def reject(self, protocol: GameProtocol, message: str) -> None:
        with contextlib.suppress(ValueError, RuntimeError, OSError):
            protocol.write(encode_message("error", message=message))
        asyncio.get_running_loop().call_later(0.05, protocol.close)

    def _accept_player(self, protocol: GameProtocol, message: dict[str, Any]) -> None:
        if self._shutdown_requested:
            self.reject(protocol, "server is shutting down")
            return
        if not self._handshake_ok(protocol, message):
            return
        if len(self.clients) >= self.tuning.network.max_clients:
            self.reject(protocol, "server is full")
            return
        name = str(message.get("name", "Player"))[:18]
        player, snapshot = self.simulation.add_player(name)
        session_token = secrets.token_urlsafe(32)
        self._player_tokens[player.id] = session_token
        outbox = ClientOutputQueue(self.tuning.network.output_queue_packets)
        session = ClientSession(player.id, name, session_token, protocol, outbox, last_seen=time.monotonic())
        protocol.player_id = player.id
        self.clients[player.id] = session
        session.writer_task = asyncio.create_task(self._writer_loop(session), name=f"writer-{player.id}")
        snapshot_data = self._snapshot_with_network_stats(snapshot.data)
        filtered = self._bootstrap_snapshot(snapshot_data, player.id)
        session.last_snapshot = filtered
        session.last_snapshot_tick = snapshot.tick
        self._remember_snapshot_hash(session, snapshot.tick, filtered, force=True)
        session.snapshots_since_full = 0
        self._queue_control(
            session,
            "welcome",
            player_id=player.id,
            session_token=session_token,
            resume_timeout=self.tuning.network.resume_timeout_seconds,
            snapshot=compact_snapshot(filtered, player.id),
            schema=SNAPSHOT_SCHEMA,
            tick=snapshot.tick,
            seq=0,
            ack_input_seq=0,
            server_time=float(filtered.get("time", 0.0)),
            snapshot_interval=1.0 / self.snapshot_rate,
            codec=SERIALIZER_NAME,
            protocol_version=PROTOCOL_VERSION,
            snapshot_schema=SNAPSHOT_SCHEMA,
            server_version=SERVER_VERSION,
            server_features=SERVER_FEATURES,
            mode=self.server_mode,
            pvp=self.pvp,
            interest_radius=self.tuning.network.interest_radius,
            building_interest_radius=self.tuning.network.building_interest_radius,
        )
        self._broadcast_player_joined(player.id, name, snapshot.tick, float(snapshot.data.get("time", 0.0)))
        self.log_worker.info(f"player connected: {name} ({player.id})")
        self.persistence.record_session("player_connected", player_id=player.id, name=name)

    def _resume_player(self, protocol: GameProtocol, message: dict[str, Any]) -> None:
        if self._shutdown_requested:
            self.reject(protocol, "server is shutting down")
            return
        if not self._handshake_ok(protocol, message):
            return
        player_id = str(message.get("player_id", ""))
        token = str(message.get("session_token", ""))
        ticket = self.resume_tickets.get(player_id)
        if not ticket or ticket.session_token != token or ticket.expires_at < time.monotonic():
            self.reject(protocol, "resume expired")
            return
        if player_id in self.clients:
            self.reject(protocol, "session already connected")
            return
        snapshot = self.simulation.snapshot()
        snapshot_data = self._snapshot_with_network_stats(snapshot.data)
        if player_id not in snapshot_data.get("players", {}):
            self.reject(protocol, "player no longer exists")
            return
        outbox = ClientOutputQueue(self.tuning.network.output_queue_packets)
        session = ClientSession(
            player_id,
            ticket.name,
            token,
            protocol,
            outbox,
            last_received_input_seq=ticket.last_input_seq,
            ping_ms=ticket.ping_ms,
            last_seen=time.monotonic(),
        )
        protocol.player_id = player_id
        self.clients[player_id] = session
        self.resume_tickets.pop(player_id, None)
        session.writer_task = asyncio.create_task(self._writer_loop(session), name=f"writer-{player_id}")
        filtered = self._filter_snapshot(snapshot_data, player_id, snapshot.tick)
        session.last_snapshot = filtered
        session.last_snapshot_tick = snapshot.tick
        self._remember_snapshot_hash(session, snapshot.tick, filtered, force=True)
        self._queue_control(
            session,
            "welcome",
            resumed=True,
            player_id=player_id,
            session_token=token,
            resume_timeout=self.tuning.network.resume_timeout_seconds,
            snapshot=compact_snapshot(filtered, player_id),
            schema=SNAPSHOT_SCHEMA,
            tick=snapshot.tick,
            seq=0,
            ack_input_seq=self.simulation.ack_input_seq(player_id),
            server_time=float(filtered.get("time", 0.0)),
            snapshot_interval=1.0 / self.snapshot_rate,
            codec=SERIALIZER_NAME,
            protocol_version=PROTOCOL_VERSION,
            snapshot_schema=SNAPSHOT_SCHEMA,
            server_version=SERVER_VERSION,
            server_features=SERVER_FEATURES,
            mode=self.server_mode,
            pvp=self.pvp,
            interest_radius=self.tuning.network.interest_radius,
            building_interest_radius=self.tuning.network.building_interest_radius,
        )
        last_tick = int(message.get("last_snapshot_tick", 0))
        results, events = self.journal.replay_for_player(player_id, last_tick)
        for result in results:
            payload = dict(result)
            payload.pop("player_id", None)
            self._queue_control(session, "command_result", replay=True, **payload)
        if events:
            self._queue_events(session, snapshot.tick, float(filtered.get("time", 0.0)), events)
        self.persistence.record_session("player_resumed", player_id=player_id, name=ticket.name)
        self.metrics.reconnect_total += 1
        self.log_worker.info(f"player resumed: {ticket.name} ({player_id})")

    def _handshake_ok(self, protocol: GameProtocol, message: dict[str, Any]) -> bool:
        try:
            protocol_version = int(message.get("protocol_version", 0))
        except (TypeError, ValueError):
            protocol_version = 0
        snapshot_schema = str(message.get("snapshot_schema", SNAPSHOT_SCHEMA))
        if protocol_version != PROTOCOL_VERSION:
            self.reject(protocol, f"unsupported protocol version {message.get('protocol_version')}")
            return False
        if snapshot_schema != SNAPSHOT_SCHEMA:
            self.reject(protocol, "unsupported snapshot schema")
            return False
        return True

    def _handle_input(self, session: ClientSession, message: dict[str, Any]) -> None:
        if not self._allow_message_rate(session, "input"):
            self.metrics.rate_limited_inputs_total += 1
            return
        session.last_seen = time.monotonic()
        try:
            sequence = int(message.get("seq", 0))
        except (TypeError, ValueError):
            sequence = 0
        if sequence and sequence <= session.last_received_input_seq:
            return
        session.last_received_input_seq = sequence
        raw = message.get("command", {})
        raw = raw if isinstance(raw, dict) else {}
        command = InputCommand(
            player_id=session.player_id,
            move_x=float(raw.get("move_x", 0.0)),
            move_y=float(raw.get("move_y", 0.0)),
            aim_x=float(raw.get("aim_x", 0.0)),
            aim_y=float(raw.get("aim_y", 0.0)),
            shooting=bool(raw.get("shooting", False)),
            sprint=bool(raw.get("sprint", False)),
            sneak=bool(raw.get("sneak", False)),
        )
        command.player_id = session.player_id
        self.simulation.set_input(command, sequence)

    def _handle_command(self, session: ClientSession, message: dict[str, Any]) -> None:
        if not self._allow_message_rate(session, "command"):
            self.metrics.rate_limited_commands_total += 1
            self.metrics.commands_rejected_total += 1
            self._queue_control(
                session,
                "command_result",
                command_id=int(message.get("command_id", 0) or 0),
                kind=str(message.get("kind", "")),
                ok=False,
                reason="rate_limited",
                server_tick=self.simulation.snapshot().tick,
            )
            return
        session.last_seen = time.monotonic()
        try:
            command_id = int(message.get("command_id", 0))
        except (TypeError, ValueError):
            command_id = 0
        kind = str(message.get("kind", ""))
        payload = message.get("payload", {})
        command = ClientCommand(
            player_id=session.player_id,
            command_id=command_id,
            kind=kind,
            payload=payload if isinstance(payload, dict) else {},
        )
        if command.command_id <= 0 or not command.kind:
            result = {
                "player_id": session.player_id,
                "command_id": command.command_id,
                "kind": command.kind,
                "ok": False,
                "reason": "invalid_command",
                "server_tick": self.simulation.snapshot().tick,
            }
            self.journal.append_command_result(result)
            self.metrics.commands_rejected_total += 1
            self.persistence.record_match_event(
                "command_result",
                player_id=result["player_id"],
                command_id=result["command_id"],
                kind=result["kind"],
                ok=False,
                reason=result["reason"],
                tick=result["server_tick"],
            )
            payload = dict(result)
            payload.pop("player_id", None)
            self._queue_control(session, "command_result", **payload)
            return
        accepted, reason = self.simulation.queue_command(command)
        if not accepted:
            result = {
                "player_id": session.player_id,
                "command_id": command.command_id,
                "kind": command.kind,
                "ok": False,
                "reason": reason,
                "server_tick": self.simulation.snapshot().tick,
            }
            self.journal.append_command_result(result)
            self.metrics.commands_rejected_total += 1
            self.persistence.record_match_event(
                "command_result",
                player_id=result["player_id"],
                command_id=result["command_id"],
                kind=result["kind"],
                ok=False,
                reason=result["reason"],
                tick=result["server_tick"],
            )
            payload = dict(result)
            payload.pop("player_id", None)
            self._queue_control(session, "command_result", **payload)

    def _send_ping(self, protocol: GameProtocol, message: dict[str, Any]) -> None:
        protocol.write(encode_message("pong", **self._ping_payload(message)))
        asyncio.get_running_loop().call_later(0.05, protocol.close)

    def _handle_session_ping(self, session: ClientSession, message: dict[str, Any]) -> None:
        session.last_seen = time.monotonic()
        with contextlib.suppress(TypeError, ValueError):
            session.ping_ms = max(0.0, float(message.get("client_ping_ms")))
        self._queue_control(session, "pong", **self._ping_payload(message))

    def _ping_payload(self, message: dict[str, Any]) -> dict[str, Any]:
        return {
            "sent": message.get("sent", time.time()),
            "players": len(self.clients),
            "max_players": self.tuning.network.max_clients,
            "ready": self._ready_payload()["ready"],
            "zombies": self.simulation.zombie_count(),
            "difficulty": self.difficulty_key,
            "mode": self.server_mode,
            "pvp": self.pvp,
            "interest_radius": self.tuning.network.interest_radius,
            "building_interest_radius": self.tuning.network.building_interest_radius,
            "tick_ms": round(self.simulation.tick_seconds() * 1000.0, 2),
            "tick_rate": self.tick_rate,
            "snapshot_rate": self.snapshot_rate,
            "effective_snapshot_rate": self._current_snapshot_rate,
            "codec": SERIALIZER_NAME,
            "protocol": "tcp-frame-v4",
            "protocol_version": PROTOCOL_VERSION,
            "snapshot_schema": SNAPSHOT_SCHEMA,
            "server_version": SERVER_VERSION,
            "server_features": SERVER_FEATURES,
            "resume_timeout": self.tuning.network.resume_timeout_seconds,
            "metrics_url": f"http://{self.tuning.observability.host}:{self.tuning.observability.port}/metrics"
            if self.tuning.observability.enabled
            else "",
        }

    async def _writer_loop(self, session: ClientSession) -> None:
        try:
            while True:
                packet = await session.outbox.get()
                if packet is None:
                    return
                outbox_wait = time.perf_counter() - packet.created_at
                self.metrics.observe_stage("outbox_wait_ms", outbox_wait)
                if outbox_wait * 1000.0 >= self.tuning.network.slow_client_outbox_wait_ms:
                    self._mark_slow_client(session)
                write_started = time.perf_counter()
                await session.protocol.wait_writable()
                session.protocol.write(packet.payload)
                await session.protocol.wait_writable()
                self.metrics.observe_stage("transport_write_ms", time.perf_counter() - write_started)
        except (ConnectionError, OSError, RuntimeError):
            session.protocol.close()
        except asyncio.CancelledError:
            raise

    async def _snapshot_loop(self) -> None:
        loop = asyncio.get_running_loop()
        next_send = loop.time()
        while True:
            effective_snapshot_rate = self._effective_snapshot_rate()
            self._current_snapshot_rate = effective_snapshot_rate
            delay = 1.0 / effective_snapshot_rate
            next_send += delay
            await asyncio.sleep(max(0.0, next_send - loop.time()))
            if not self.clients:
                continue
            round_started = loop.time()
            started = time.perf_counter()
            sleeping_seconds = 0.0
            snapshot = self.simulation.snapshot()
            snapshot_data = self._snapshot_with_network_stats(snapshot.data)
            self.journal.append_snapshot_meta(
                snapshot.tick,
                {
                    "tick": snapshot.tick,
                    "server_time": snapshot_data.get("time", 0.0),
                    "active_clients": len(self.clients),
                    "resume_tickets": len(self.resume_tickets),
                },
            )
            index = self._interest_index(snapshot_data, snapshot.tick)
            events = derive_events(self._event_source_snapshot, snapshot_data, snapshot.tick)
            for event in events:
                self.journal.append_event(event, snapshot.tick)
                self.persistence.record_match_event(
                    "snapshot_event",
                    tick=snapshot.tick,
                    kind=event.get("kind", "unknown"),
                    payload=event,
                )
            self._event_source_snapshot = snapshot_data
            area_cache: dict[tuple[int, int, int, str], dict[str, Any]] = {}
            batches = self._snapshot_batches()
            batch_spacing = delay / max(1, len(batches))
            for batch_index, sessions in enumerate(batches):
                interest_started = time.perf_counter()
                for session in sessions:
                    if self.clients.get(session.player_id) is not session:
                        continue
                    if snapshot.tick <= session.last_snapshot_tick:
                        continue
                    session.snapshot_stride = self._adaptive_snapshot_stride(session)
                    if session.snapshot_stride > 1:
                        session.snapshot_skip = (session.snapshot_skip + 1) % session.snapshot_stride
                        if session.snapshot_skip:
                            continue
                    else:
                        session.snapshot_skip = 0
                    if self._skip_snapshot_for_backpressure(session):
                        continue
                    bucket = self._interest_bucket(snapshot_data, session.player_id)
                    if bucket not in area_cache:
                        floor, cell_x, cell_y, inside = bucket
                        center_x = cell_x * self.tuning.network.grid_cell_size + self.tuning.network.grid_cell_size * 0.5
                        center_y = cell_y * self.tuning.network.grid_cell_size + self.tuning.network.grid_cell_size * 0.5
                        area_cache[bucket] = filter_snapshot_area(
                            snapshot_data,
                            index,
                            center_x,
                            center_y,
                            floor,
                            inside or None,
                            self.tuning.network.interest_radius + self.tuning.network.grid_cell_size * 0.75,
                            self.tuning.network.building_interest_radius + self.tuning.network.grid_cell_size * 0.75,
                        )
                    filtered = snapshot_with_local_player(area_cache[bucket], snapshot_data, session.player_id)
                    self._queue_snapshot(session, filtered, snapshot.tick)
                    visible_events = filter_events_for_snapshot(events, filtered, session.player_id)
                    if visible_events:
                        self._queue_events(session, snapshot.tick, float(snapshot_data.get("time", 0.0)), visible_events)
                self.metrics.observe_stage("interest_filter_ms", time.perf_counter() - interest_started)
                if batch_index + 1 < len(batches):
                    batch_deadline = round_started + (batch_index + 1) * batch_spacing
                    sleep_for = max(0.0, batch_deadline - loop.time())
                    if sleep_for > 0.0:
                        sleep_started = time.perf_counter()
                        await asyncio.sleep(sleep_for)
                        sleeping_seconds += time.perf_counter() - sleep_started
            elapsed = max(0.0, time.perf_counter() - started - sleeping_seconds)
            self.metrics.observe_snapshot(elapsed)
            self.profiler.record("snapshot_loop", elapsed)

    async def _command_result_loop(self) -> None:
        while True:
            await asyncio.sleep(0.002)
            for result in self.simulation.drain_command_results():
                self.journal.append_command_result(result)
                self.metrics.observe_command_ack(result.get("server_command_latency_ms"))
                if not result.get("ok", False):
                    self.metrics.commands_rejected_total += 1
                self.persistence.record_match_event(
                    "command_result",
                    player_id=result.get("player_id"),
                    command_id=result.get("command_id"),
                    kind=result.get("kind"),
                    ok=result.get("ok"),
                    reason=result.get("reason", ""),
                    tick=result.get("server_tick", 0),
                )
                player_id = str(result.get("player_id", ""))
                session = self.clients.get(player_id)
                if not session:
                    continue
                payload = dict(result)
                payload.pop("player_id", None)
                self._queue_control(session, "command_result", **payload)
            for event in self.simulation.drain_domain_events():
                self.journal.append_event(event, int(event.get("server_tick", self.simulation.snapshot().tick)))
                self.persistence.record_match_event(
                    "domain_event",
                    player_id=event.get("player_id"),
                    kind=event.get("kind", "unknown"),
                    tick=event.get("server_tick", self.simulation.snapshot().tick),
                    payload=event,
                )
                player_id = str(event.get("player_id", ""))
                session = self.clients.get(player_id)
                if not session:
                    continue
                tick = int(event.get("server_tick", self.simulation.snapshot().tick))
                server_time = float(event.get("time", self.simulation.snapshot().data.get("time", 0.0)))
                self._queue_events(session, tick, server_time, [event])

    async def _resume_cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            now = time.monotonic()
            expired = [player_id for player_id, ticket in self.resume_tickets.items() if ticket.expires_at <= now]
            for player_id in expired:
                ticket = self.resume_tickets.pop(player_id, None)
                if not ticket:
                    continue
                self._persist_player_profile(player_id)
                self.simulation.remove_player(player_id)
                self.persistence.record_session("resume_expired", player_id=player_id, name=ticket.name)
                self.log_worker.info(f"resume expired: {ticket.name} ({player_id})")

    def _filter_snapshot(self, snapshot: dict[str, Any], player_id: str, tick: int | None = None) -> dict[str, Any]:
        index = self._interest_index(snapshot, tick)
        floor, cell_x, cell_y, inside = self._interest_bucket(snapshot, player_id)
        center_x = cell_x * self.tuning.network.grid_cell_size + self.tuning.network.grid_cell_size * 0.5
        center_y = cell_y * self.tuning.network.grid_cell_size + self.tuning.network.grid_cell_size * 0.5
        area = filter_snapshot_area(
            snapshot,
            index,
            center_x,
            center_y,
            floor,
            inside or None,
            self.tuning.network.interest_radius + self.tuning.network.grid_cell_size * 0.75,
            self.tuning.network.building_interest_radius + self.tuning.network.grid_cell_size * 0.75,
        )
        return snapshot_with_local_player(area, snapshot, player_id)

    def _bootstrap_snapshot(self, snapshot: dict[str, Any], player_id: str) -> dict[str, Any]:
        players = snapshot.get("players", {})
        local = players.get(player_id) if isinstance(players, dict) else None
        if not isinstance(local, dict):
            return self._filter_snapshot(snapshot, player_id)
        boot: dict[str, Any] = {
            "time": snapshot.get("time", 0.0),
            "map_width": snapshot.get("map_width", 1),
            "map_height": snapshot.get("map_height", 1),
            "players": {player_id: local},
            "buildings": {},
        }
        for collection in POSITION_COLLECTIONS:
            boot[collection] = {}
        return boot

    def _interest_index(self, snapshot: dict[str, Any], tick: int | None) -> SnapshotInterestIndex:
        key = self._interest_index_key(snapshot, tick)
        if self._interest_index_cache_key == key and self._interest_index_cache is not None:
            return self._interest_index_cache
        index = SnapshotInterestIndex(snapshot, self.tuning.network.grid_cell_size)
        self._interest_index_cache_key = key
        self._interest_index_cache = index
        return index

    def _interest_index_key(self, snapshot: dict[str, Any], tick: int | None) -> tuple[Any, ...]:
        counts = tuple(len(_snapshot_collection(snapshot, collection)) for collection in POSITION_COLLECTIONS)
        return (tick, self.tuning.network.grid_cell_size, counts)

    def _snapshot_with_network_stats(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        players = snapshot.get("players")
        if not isinstance(players, dict):
            return snapshot
        patched = dict(snapshot)
        patched_players: dict[str, Any] = {}
        for player_id, player in players.items():
            if not isinstance(player, dict):
                continue
            data = dict(player)
            session = self.clients.get(player_id)
            ticket = self.resume_tickets.get(player_id)
            if session:
                ping_ms = int(min(9999, round(session.ping_ms or 0)))
                data["ping_ms"] = ping_ms
                data["connection_quality"] = _connection_quality(ping_ms, time.monotonic() - session.last_seen)
            elif ticket:
                ping_ms = int(min(9999, round(ticket.ping_ms or 0)))
                data["ping_ms"] = ping_ms
                data["connection_quality"] = "lost"
            else:
                data["ping_ms"] = int(data.get("ping_ms", 0))
                data["connection_quality"] = data.get("connection_quality", "stable")
            patched_players[player_id] = data
        patched["players"] = patched_players
        return patched

    def _interest_bucket(self, snapshot: dict[str, Any], player_id: str) -> tuple[int, int, int, str]:
        players = snapshot.get("players", {})
        player = players.get(player_id, {}) if isinstance(players, dict) else {}
        pos = player.get("pos", {}) if isinstance(player, dict) and isinstance(player.get("pos"), dict) else {}
        cell_size = self.tuning.network.grid_cell_size
        return (
            int(player.get("floor", 0)) if isinstance(player, dict) else 0,
            int(float(pos.get("x", 0.0)) // cell_size),
            int(float(pos.get("y", 0.0)) // cell_size),
            str(player.get("inside_building") or "") if isinstance(player, dict) else "",
        )

    def _adaptive_snapshot_stride(self, session: ClientSession) -> int:
        stride = 1
        queued = len(session.outbox)
        if queued >= 32:
            stride = 16
        elif queued >= 16:
            stride = 8
        elif queued >= 8:
            stride = 4
        elif queued >= 4:
            stride = 2
        queue_pressure = queued / max(1, self.tuning.network.output_queue_packets)
        if queue_pressure >= 0.72:
            stride = max(stride, 8)
        if queue_pressure >= 0.42:
            stride = max(stride, 4)
        if self._is_slow_client(session):
            stride = max(stride, self.tuning.network.slow_client_snapshot_stride)
        return stride

    def _effective_snapshot_rate(self) -> int:
        clients = len(self.clients)
        network = self.tuning.network
        if clients >= network.adaptive_snapshot_extreme_clients:
            rate = max(1, min(self.snapshot_rate, network.adaptive_snapshot_extreme_rate))
        elif clients >= network.adaptive_snapshot_high_clients:
            rate = max(1, min(self.snapshot_rate, network.adaptive_snapshot_high_rate))
        elif clients >= network.adaptive_snapshot_medium_clients:
            rate = max(1, min(self.snapshot_rate, network.adaptive_snapshot_medium_rate))
        else:
            rate = max(1, self.snapshot_rate)
        if self._connection_burst_count() >= network.connection_burst_threshold:
            rate = max(1, min(rate, network.connection_burst_snapshot_rate))
        return rate

    def note_connection_attempt(self) -> None:
        now = time.monotonic()
        self._connection_times.append(now)
        self._trim_connection_times(now)

    def _connection_burst_count(self) -> int:
        now = time.monotonic()
        self._trim_connection_times(now)
        return len(self._connection_times)

    def _trim_connection_times(self, now: float) -> None:
        cutoff = now - self.tuning.network.connection_burst_window_seconds
        while self._connection_times and self._connection_times[0] < cutoff:
            self._connection_times.popleft()

    def _is_slow_client(self, session: ClientSession) -> bool:
        return session.slow_until > time.monotonic()

    def _mark_slow_client(self, session: ClientSession) -> None:
        session.slow_until = max(
            session.slow_until,
            time.monotonic() + self.tuning.network.slow_client_recovery_seconds,
        )

    def _skip_snapshot_for_backpressure(self, session: ClientSession) -> bool:
        if not session.outbox.full:
            return False
        self._mark_slow_client(session)
        session.last_snapshot = None
        session.dropped_snapshots += 1
        self.metrics.skipped_snapshots_total += 1
        return True

    def _snapshot_batches(self) -> list[list[ClientSession]]:
        sessions = list(self.clients.values())
        if not sessions:
            return []
        batch_size = min(len(sessions), max(1, self.tuning.network.snapshot_send_batch_size))
        start = self._snapshot_cursor % len(sessions)
        ordered = sessions[start:] + sessions[:start]
        self._snapshot_cursor = (start + 1) % len(sessions)
        return [ordered[index : index + batch_size] for index in range(0, len(ordered), batch_size)]

    def _queue_control(self, session: ClientSession, message_type: str, **payload: Any) -> None:
        try:
            packet = OutboundPacket(encode_message(message_type, **payload), kind="control")
        except ValueError as exc:
            self.log_worker.info(f"failed to encode {message_type} for {session.player_id}: {exc}")
            return
        if session.outbox.full and session.outbox.make_room_for_snapshot():
            session.last_snapshot = None
            session.dropped_snapshots += 1
            self.metrics.dropped_snapshots_total += 1
        if not session.outbox.put(packet):
            self.log_worker.info(f"closing slow client {session.player_id}: output queue is full")
            session.protocol.close()

    def _remember_snapshot_hash(self, session: ClientSession, tick: int, snapshot: dict[str, Any], *, force: bool = False) -> None:
        interval_ticks = max(1, int(self.tick_rate * self.tuning.network.state_hash_sample_seconds))
        if force or session.last_hash_tick < 0 or tick - session.last_hash_tick >= interval_ticks:
            session.snapshot_hashes.append((tick, snapshot_hash(snapshot)))
            session.last_hash_tick = tick

    def _queue_snapshot(self, session: ClientSession, snapshot: dict[str, Any], tick: int) -> None:
        max_pending = self.tuning.network.max_pending_snapshots_per_client
        trimmed = 0
        if session.outbox.pending_snapshots() >= max_pending:
            trimmed = session.outbox.trim_snapshots(0)
        if trimmed:
            session.last_snapshot = None
            session.dropped_snapshots += trimmed
            self.metrics.dropped_snapshots_total += trimmed
        if session.outbox.full:
            self._mark_slow_client(session)
            session.last_snapshot = None
            session.dropped_snapshots += 1
            self.metrics.dropped_snapshots_total += 1
            self.metrics.skipped_snapshots_total += 1
            return

        snapshot_rate = max(1, self._current_snapshot_rate)
        full_interval = max(1, int(self.tuning.network.full_snapshot_interval_seconds * snapshot_rate))
        force_full = session.last_snapshot is None or session.snapshots_since_full >= full_interval
        session.sequence += 1
        if force_full:
            encode_started = time.perf_counter()
            payload = encode_message(
                "snapshot",
                tick=tick,
                seq=session.sequence,
                ack_input_seq=self.simulation.ack_input_seq(session.player_id),
                server_time=float(snapshot.get("time", 0.0)),
                snapshot_interval=session.snapshot_stride / snapshot_rate,
                full=True,
                schema=SNAPSHOT_SCHEMA,
                snapshot=compact_snapshot(snapshot, session.player_id),
            )
            self.metrics.observe_stage("compact_encode_ms", time.perf_counter() - encode_started)
            session.snapshots_since_full = 0
        else:
            delta_started = time.perf_counter()
            delta = make_snapshot_delta(snapshot, session.last_snapshot)
            self.metrics.observe_stage("delta_build_ms", time.perf_counter() - delta_started)
            encode_started = time.perf_counter()
            payload = encode_message(
                "snapshot",
                tick=tick,
                seq=session.sequence,
                ack_input_seq=self.simulation.ack_input_seq(session.player_id),
                server_time=float(snapshot.get("time", 0.0)),
                snapshot_interval=session.snapshot_stride / snapshot_rate,
                full=False,
                base_tick=session.last_snapshot_tick,
                schema=SNAPSHOT_SCHEMA,
                delta=compact_delta(delta, session.player_id, session.last_snapshot),
            )
            self.metrics.observe_stage("compact_encode_ms", time.perf_counter() - encode_started)
            session.snapshots_since_full += 1
        dropped_pending = session.outbox.replace_snapshot(
            OutboundPacket(payload, kind="snapshot"),
            max_pending,
        )
        if dropped_pending:
            session.dropped_snapshots += dropped_pending
            self.metrics.dropped_snapshots_total += dropped_pending
        session.last_snapshot = snapshot
        session.last_snapshot_tick = tick
        self._remember_snapshot_hash(session, tick, snapshot)

    def _queue_events(
        self,
        session: ClientSession,
        tick: int,
        server_time: float,
        events: list[dict[str, Any]],
    ) -> None:
        self._queue_control(
            session,
            "events",
            tick=tick,
            server_time=server_time,
            events=events,
            channel="reliable",
        )

    def _broadcast_player_joined(self, player_id: str, name: str, tick: int, server_time: float) -> None:
        event = {
            "kind": "player_joined",
            "tick": tick,
            "server_tick": tick,
            "time": round(server_time, 3),
            "player_id": player_id,
            "name": name,
        }
        self.persistence.record_match_event(
            "domain_event",
            player_id=player_id,
            kind="player_joined",
            tick=tick,
            payload=event,
        )
        for session_id, session in list(self.clients.items()):
            if session_id == player_id:
                continue
            self._queue_events(session, tick, server_time, [event])

    def _persist_player_profile(self, player_id: str) -> None:
        profile = self.simulation.player_profile(player_id)
        if profile:
            self.persistence.save_player_profile(player_id, profile)

    def _handle_state_hash(self, session: ClientSession, message: dict[str, Any]) -> None:
        session.last_seen = time.monotonic()
        self.metrics.desync_reports_total += 1
        try:
            tick = int(message.get("tick", -1))
        except (TypeError, ValueError):
            tick = -1
        client_hash = str(message.get("hash", ""))
        server_hash = next((value for snapshot_tick, value in session.snapshot_hashes if snapshot_tick == tick), "")
        if not server_hash:
            return
        if client_hash != server_hash:
            self.metrics.desync_mismatch_total += 1
            self.metrics.desync_forced_full_total += 1
            session.last_snapshot = None
            self._queue_control(
                session,
                "state_hash_result",
                ok=False,
                tick=tick,
                client_hash=client_hash,
                server_hash=server_hash,
                force_full=True,
            )

    def _allow_message_rate(self, session: ClientSession, kind: str) -> bool:
        now = time.monotonic()
        if session.rate_window_started <= 0.0 or now - session.rate_window_started >= 1.0:
            session.rate_window_started = now
            session.input_count_window = 0
            session.command_count_window = 0
            session.bytes_count_window = 0
        if kind == "input":
            session.input_count_window += 1
            return session.input_count_window <= self.tuning.rate_limits.input_per_second
        if kind == "command":
            session.command_count_window += 1
            return session.command_count_window <= self.tuning.rate_limits.command_per_second
        return True

    def _bytes_rate_limited(self, player_id: str, byte_count: int) -> bool:
        session = self.clients.get(player_id)
        if not session:
            return False
        now = time.monotonic()
        if session.rate_window_started <= 0.0 or now - session.rate_window_started >= 1.0:
            session.rate_window_started = now
            session.input_count_window = 0
            session.command_count_window = 0
            session.bytes_count_window = 0
        session.bytes_count_window += byte_count
        if session.bytes_count_window > self.tuning.rate_limits.inbound_bytes_per_second:
            self.metrics.rate_limited_bytes_total += 1
            return True
        return False

    def _runtime_metrics(self) -> dict[str, Any]:
        return {
            "connected_players": len(self.clients),
            "resume_tickets": len(self.resume_tickets),
            "output_queue_packets": sum(len(session.outbox) for session in self.clients.values()),
            "slow_clients": sum(1 for session in self.clients.values() if self._is_slow_client(session)),
            "connection_burst_count": self._connection_burst_count(),
            "persistence_queue_size": self.persistence.queue_size,
            "asyncio_tasks": len(asyncio.all_tasks()),
            "effective_snapshot_rate": self._current_snapshot_rate,
        }

    def _metrics_text(self) -> str:
        return self.metrics.prometheus_text(self._runtime_metrics())

    def _health_payload(self) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "shutting_down" if self._shutdown_requested else "healthy",
            "players": len(self.clients),
            "uptime_seconds": round(time.time() - self.metrics.started_at, 3),
        }

    def _ready_payload(self) -> dict[str, Any]:
        ready = (
            not self._shutdown_requested
            and self.simulation.is_alive()
            and self.persistence.is_running
            and len(self.clients) < self.tuning.network.max_clients
        )
        return {
            "ready": ready,
            "accepting_players": not self._shutdown_requested and len(self.clients) < self.tuning.network.max_clients,
            "simulation_alive": self.simulation.is_alive(),
            "persistence_ready": self.persistence.is_running,
            "players": len(self.clients),
            "max_players": self.tuning.network.max_clients,
            "tick_rate": self.tick_rate,
            "snapshot_rate": self.snapshot_rate,
            "effective_snapshot_rate": self._current_snapshot_rate,
            "mode": self.server_mode,
            "pvp": self.pvp,
            "zombies": self.simulation.zombie_count(),
        }

    async def _profile_loop(self) -> None:
        delay = self.tuning.profiling.log_interval_seconds
        while True:
            await asyncio.sleep(delay)
            summary = self.profiler.summary()
            queued = sum(len(session.outbox) for session in self.clients.values())
            dropped = sum(session.dropped_snapshots for session in self.clients.values())
            tick_ms = self.simulation.tick_seconds() * 1000.0
            if summary:
                self.log_worker.info(
                    f"profile {summary} | tick={tick_ms:.2f}ms clients={len(self.clients)} "
                    f"queued={queued} dropped_snapshots={dropped}"
                )


def _connection_quality(ping_ms: int, silence_seconds: float) -> str:
    if silence_seconds > 3.0:
        return "lost"
    if silence_seconds > 1.2 or ping_ms >= 1000:
        return "packet-lost"
    if ping_ms >= 350:
        return "unstable"
    return "stable"


def _snapshot_collection(snapshot: dict[str, Any], key: str) -> dict[str, Any]:
    value = snapshot.get(key, {})
    return value if isinstance(value, dict) else {}
