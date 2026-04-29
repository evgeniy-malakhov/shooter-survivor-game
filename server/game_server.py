from __future__ import annotations

import asyncio
import contextlib
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque

from server.config import ServerTuning, load_server_tuning
from server.events import derive_events, filter_events_for_snapshot
from server.spatial import SnapshotInterestIndex, filter_snapshot_area, snapshot_with_local_player
from server.workers import AsyncLogWorker, ServerProfiler
from shared.constants import SNAPSHOT_RATE, TICK_RATE
from shared.net_schema import SNAPSHOT_SCHEMA, compact_delta, compact_snapshot
from shared.models import ClientCommand, InputCommand, PlayerState
from shared.protocol import FrameDecoder, SERIALIZER_NAME, encode_message
from shared.simulation import GameWorld
from shared.snapshot_delta import make_snapshot_delta


@dataclass(slots=True)
class SimulationSnapshot:
    data: dict[str, Any]
    tick: int


class SimulationRunner:
    def __init__(self, difficulty_key: str, zombie_workers: int | None = None) -> None:
        self.world = GameWorld(difficulty_key=difficulty_key, zombie_workers=zombie_workers)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="simulation-runner", daemon=True)
        self._input_lock = threading.Lock()
        self._pending_inputs: dict[str, tuple[int, InputCommand]] = {}
        self._pending_commands: dict[str, Deque[ClientCommand]] = {}
        self._pending_command_ids: dict[str, set[int]] = {}
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
            self._acked_inputs.pop(player_id, None)
        self.world.remove_player(player_id)
        self._refresh_snapshot()

    def rename_player(self, player_id: str, name: str) -> None:
        self.world.rename_player(player_id, name)
        self._refresh_snapshot()

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
            if len(queue) >= 128:
                return False, "command_queue_full"
            queue.append(command)
            pending_ids.add(command.command_id)
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

    def tick_seconds(self) -> float:
        return self._last_tick_seconds

    def _run(self) -> None:
        dt = 1.0 / TICK_RATE
        snapshot_delay = 1.0 / SNAPSHOT_RATE
        next_tick = time.perf_counter()
        next_snapshot = next_tick
        while not self._stop.is_set():
            now = time.perf_counter()
            did_work = False

            if now >= next_tick:
                started = time.perf_counter()
                self._apply_pending_commands()
                self._apply_pending_inputs()
                self.world.update(dt)
                self._collect_domain_events()
                self._tick_id += 1
                self._last_tick_seconds = time.perf_counter() - started
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
        return result

    def _collect_domain_events(self) -> None:
        events = self.world.drain_domain_events()
        if not events:
            return
        with self._input_lock:
            self._domain_events.extend(events)

    def _refresh_snapshot(self) -> None:
        self._publish_snapshot(SimulationSnapshot(self.world.snapshot().to_dict(), self._tick_id))

    def _publish_snapshot(self, snapshot: SimulationSnapshot) -> None:
        with self._snapshot_lock:
            self._snapshot = snapshot


@dataclass(slots=True)
class OutboundPacket:
    payload: bytes
    kind: str = "control"


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

    def put(self, packet: OutboundPacket) -> bool:
        if self._closed:
            return False
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
        if self.transport:
            self.transport.set_write_buffer_limits(
                high=self.server.tuning.network.write_buffer_high_water,
                low=self.server.tuning.network.write_buffer_low_water,
            )
        raw_socket = transport.get_extra_info("socket")
        with contextlib.suppress(OSError, AttributeError):
            raw_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def data_received(self, data: bytes) -> None:
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
        profile: bool = False,
        zombie_workers: int | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.difficulty_key = difficulty_key
        self.tuning: ServerTuning = load_server_tuning()
        self.simulation = SimulationRunner(difficulty_key, zombie_workers=zombie_workers)
        self.clients: dict[str, ClientSession] = {}
        self._server: asyncio.AbstractServer | None = None
        self._tasks: list[asyncio.Task[None]] = []
        self.log_worker = AsyncLogWorker()
        self.profiler = ServerProfiler(enabled=profile)
        self.profile_enabled = profile
        self._event_source_snapshot: dict[str, Any] | None = None

    async def start(self) -> None:
        await self.log_worker.start()
        self.simulation.start()
        loop = asyncio.get_running_loop()
        try:
            self._server = await loop.create_server(lambda: GameProtocol(self), self.host, self.port)
            self._tasks = [
                asyncio.create_task(self._snapshot_loop(), name="snapshot-sender"),
                asyncio.create_task(self._command_result_loop(), name="command-results"),
            ]
            if self.profile_enabled:
                self._tasks.append(asyncio.create_task(self._profile_loop(), name="server-profiler"))
            sockets = ", ".join(str(sock.getsockname()) for sock in self._server.sockets or [])
            self.log_worker.info(
                f"Neon Outbreak server listening on {sockets} [{self.difficulty_key}] "
                f"codec={SERIALIZER_NAME} tick={TICK_RATE}Hz snapshots={SNAPSHOT_RATE}Hz"
            )
            async with self._server:
                await self._server.serve_forever()
        finally:
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
            await self.log_worker.stop()

    def handle_message(self, protocol: GameProtocol, message: dict[str, Any]) -> None:
        message_type = str(message.get("type", ""))
        if protocol.player_id is None:
            if message_type == "ping":
                self._send_ping(protocol, message)
                return
            if message_type == "hello":
                self._accept_player(protocol, message)
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
        elif message_type == "profile":
            name = str(message.get("name", ""))[:18]
            session.name = name
            self.simulation.rename_player(session.player_id, name)
        elif message_type == "ping":
            self._queue_control(session, "pong", **self._ping_payload(message))

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
        self.simulation.remove_player(player_id)
        self.log_worker.info(f"player disconnected: {player_id}")

    def reject(self, protocol: GameProtocol, message: str) -> None:
        with contextlib.suppress(ValueError, RuntimeError, OSError):
            protocol.write(encode_message("error", message=message))
        asyncio.get_running_loop().call_later(0.05, protocol.close)

    def _accept_player(self, protocol: GameProtocol, message: dict[str, Any]) -> None:
        name = str(message.get("name", "Player"))[:18]
        player, snapshot = self.simulation.add_player(name)
        outbox = ClientOutputQueue(self.tuning.network.output_queue_packets)
        session = ClientSession(player.id, name, protocol, outbox)
        protocol.player_id = player.id
        self.clients[player.id] = session
        session.writer_task = asyncio.create_task(self._writer_loop(session), name=f"writer-{player.id}")
        filtered = self._filter_snapshot(snapshot.data, player.id)
        session.last_snapshot = filtered
        session.last_snapshot_tick = snapshot.tick
        session.snapshots_since_full = 0
        self._queue_control(
            session,
            "welcome",
            player_id=player.id,
            snapshot=compact_snapshot(filtered, player.id),
            schema=SNAPSHOT_SCHEMA,
            tick=snapshot.tick,
            seq=0,
            ack_input_seq=0,
            server_time=float(filtered.get("time", 0.0)),
            snapshot_interval=1.0 / SNAPSHOT_RATE,
            codec=SERIALIZER_NAME,
        )
        self.log_worker.info(f"player connected: {name} ({player.id})")

    def _handle_input(self, session: ClientSession, message: dict[str, Any]) -> None:
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
            self._queue_control(
                session,
                "command_result",
                command_id=command.command_id,
                kind=command.kind,
                ok=False,
                reason="invalid_command",
                server_tick=self.simulation.snapshot().tick,
            )
            return
        accepted, reason = self.simulation.queue_command(command)
        if not accepted:
            self._queue_control(
                session,
                "command_result",
                command_id=command.command_id,
                kind=command.kind,
                ok=False,
                reason=reason,
                server_tick=self.simulation.snapshot().tick,
            )

    def _send_ping(self, protocol: GameProtocol, message: dict[str, Any]) -> None:
        protocol.write(encode_message("pong", **self._ping_payload(message)))
        asyncio.get_running_loop().call_later(0.05, protocol.close)

    def _ping_payload(self, message: dict[str, Any]) -> dict[str, Any]:
        return {
            "sent": message.get("sent", time.time()),
            "players": len(self.clients),
            "zombies": self.simulation.zombie_count(),
            "difficulty": self.difficulty_key,
            "tick_ms": round(self.simulation.tick_seconds() * 1000.0, 2),
            "tick_rate": TICK_RATE,
            "snapshot_rate": SNAPSHOT_RATE,
            "codec": SERIALIZER_NAME,
            "protocol": "tcp-frame-v4",
            "snapshot_schema": SNAPSHOT_SCHEMA,
        }

    async def _writer_loop(self, session: ClientSession) -> None:
        try:
            while True:
                packet = await session.outbox.get()
                if packet is None:
                    return
                await session.protocol.wait_writable()
                session.protocol.write(packet.payload)
                await session.protocol.wait_writable()
        except (ConnectionError, OSError, RuntimeError):
            session.protocol.close()
        except asyncio.CancelledError:
            raise

    async def _snapshot_loop(self) -> None:
        delay = 1.0 / SNAPSHOT_RATE
        next_send = asyncio.get_running_loop().time()
        while True:
            next_send += delay
            await asyncio.sleep(max(0.0, next_send - asyncio.get_running_loop().time()))
            if not self.clients:
                continue
            started = time.perf_counter()
            snapshot = self.simulation.snapshot()
            index = SnapshotInterestIndex(snapshot.data, self.tuning.network.grid_cell_size)
            events = derive_events(self._event_source_snapshot, snapshot.data, snapshot.tick)
            self._event_source_snapshot = snapshot.data
            area_cache: dict[tuple[int, int, int, str], dict[str, Any]] = {}
            for session in list(self.clients.values()):
                if snapshot.tick <= session.last_snapshot_tick:
                    continue
                session.snapshot_stride = self._adaptive_snapshot_stride(session)
                if session.snapshot_stride > 1:
                    session.snapshot_skip = (session.snapshot_skip + 1) % session.snapshot_stride
                    if session.snapshot_skip:
                        continue
                else:
                    session.snapshot_skip = 0
                bucket = self._interest_bucket(snapshot.data, session.player_id)
                if bucket not in area_cache:
                    floor, cell_x, cell_y, inside = bucket
                    center_x = cell_x * self.tuning.network.grid_cell_size + self.tuning.network.grid_cell_size * 0.5
                    center_y = cell_y * self.tuning.network.grid_cell_size + self.tuning.network.grid_cell_size * 0.5
                    area_cache[bucket] = filter_snapshot_area(
                        snapshot.data,
                        index,
                        center_x,
                        center_y,
                        floor,
                        inside or None,
                        self.tuning.network.interest_radius + self.tuning.network.grid_cell_size * 0.75,
                        self.tuning.network.building_interest_radius + self.tuning.network.grid_cell_size * 0.75,
                    )
                filtered = snapshot_with_local_player(area_cache[bucket], snapshot.data, session.player_id)
                self._queue_snapshot(session, filtered, snapshot.tick)
                visible_events = filter_events_for_snapshot(events, filtered, session.player_id)
                if visible_events:
                    self._queue_events(session, snapshot.tick, float(snapshot.data.get("time", 0.0)), visible_events)
            self.profiler.record("snapshot_loop", time.perf_counter() - started)

    async def _command_result_loop(self) -> None:
        while True:
            await asyncio.sleep(0.01)
            for result in self.simulation.drain_command_results():
                player_id = str(result.get("player_id", ""))
                session = self.clients.get(player_id)
                if not session:
                    continue
                payload = dict(result)
                payload.pop("player_id", None)
                self._queue_control(session, "command_result", **payload)
            for event in self.simulation.drain_domain_events():
                player_id = str(event.get("player_id", ""))
                session = self.clients.get(player_id)
                if not session:
                    continue
                tick = int(event.get("server_tick", self.simulation.snapshot().tick))
                server_time = float(event.get("time", self.simulation.snapshot().data.get("time", 0.0)))
                self._queue_events(session, tick, server_time, [event])

    def _filter_snapshot(self, snapshot: dict[str, Any], player_id: str) -> dict[str, Any]:
        index = SnapshotInterestIndex(snapshot, self.tuning.network.grid_cell_size)
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
        queue_pressure = len(session.outbox) / max(1, self.tuning.network.output_queue_packets)
        if queue_pressure >= 0.72:
            return 4
        if queue_pressure >= 0.42:
            return 2
        return 1

    def _queue_control(self, session: ClientSession, message_type: str, **payload: Any) -> None:
        try:
            packet = OutboundPacket(encode_message(message_type, **payload), kind="control")
        except ValueError as exc:
            self.log_worker.info(f"failed to encode {message_type} for {session.player_id}: {exc}")
            return
        if session.outbox.full and session.outbox.make_room_for_snapshot():
            session.last_snapshot = None
            session.dropped_snapshots += 1
        if not session.outbox.put(packet):
            self.log_worker.info(f"closing slow client {session.player_id}: output queue is full")
            session.protocol.close()

    def _queue_snapshot(self, session: ClientSession, snapshot: dict[str, Any], tick: int) -> None:
        dropped = session.outbox.make_room_for_snapshot()
        if dropped:
            session.last_snapshot = None
            session.dropped_snapshots += 1
        if session.outbox.full:
            session.last_snapshot = None
            session.dropped_snapshots += 1
            return

        full_interval = max(1, int(self.tuning.network.full_snapshot_interval_seconds * SNAPSHOT_RATE))
        force_full = session.last_snapshot is None or session.snapshots_since_full >= full_interval
        session.sequence += 1
        if force_full:
            payload = encode_message(
                "snapshot",
                tick=tick,
                seq=session.sequence,
                ack_input_seq=self.simulation.ack_input_seq(session.player_id),
                server_time=float(snapshot.get("time", 0.0)),
                snapshot_interval=session.snapshot_stride / SNAPSHOT_RATE,
                full=True,
                schema=SNAPSHOT_SCHEMA,
                snapshot=compact_snapshot(snapshot, session.player_id),
            )
            session.snapshots_since_full = 0
        else:
            delta = make_snapshot_delta(snapshot, session.last_snapshot)
            payload = encode_message(
                "snapshot",
                tick=tick,
                seq=session.sequence,
                ack_input_seq=self.simulation.ack_input_seq(session.player_id),
                server_time=float(snapshot.get("time", 0.0)),
                snapshot_interval=session.snapshot_stride / SNAPSHOT_RATE,
                full=False,
                base_tick=session.last_snapshot_tick,
                schema=SNAPSHOT_SCHEMA,
                delta=compact_delta(delta, session.player_id),
            )
            session.snapshots_since_full += 1
        if session.outbox.put(OutboundPacket(payload, kind="snapshot")):
            session.last_snapshot = snapshot
            session.last_snapshot_tick = tick

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
