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
from server.spatial import SnapshotInterestIndex, filter_snapshot_for_player
from server.workers import AsyncLogWorker, ServerProfiler
from shared.constants import SNAPSHOT_RATE, TICK_RATE
from shared.models import InputCommand, PlayerState
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
        self._pending_inputs: dict[str, InputCommand] = {}
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
        snapshot = SimulationSnapshot(self.world.snapshot().to_dict(), self._tick_id)
        self._publish_snapshot(snapshot)
        return player, snapshot

    def remove_player(self, player_id: str) -> None:
        with self._input_lock:
            self._pending_inputs.pop(player_id, None)
        self.world.remove_player(player_id)
        self._refresh_snapshot()

    def rename_player(self, player_id: str, name: str) -> None:
        self.world.rename_player(player_id, name)
        self._refresh_snapshot()

    def set_input(self, command: InputCommand) -> None:
        with self._input_lock:
            self._pending_inputs[command.player_id] = command

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
                self._apply_pending_inputs()
                self.world.update(dt)
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
        for command in commands:
            self.world.set_input(command)

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
        self._items: Deque[OutboundPacket] = deque()
        self._event = asyncio.Event()
        self._closed = False

    def __len__(self) -> int:
        return len(self._items)

    @property
    def full(self) -> bool:
        return len(self._items) >= self._max_packets

    def close(self) -> None:
        self._closed = True
        self._event.set()

    def make_room_for_snapshot(self) -> bool:
        if not self.full:
            return False
        return self._drop_oldest_snapshot()

    def put(self, packet: OutboundPacket) -> bool:
        if self._closed or self.full:
            return False
        self._items.append(packet)
        self._event.set()
        return True

    async def get(self) -> OutboundPacket | None:
        while not self._items:
            if self._closed:
                return None
            self._event.clear()
            if self._items:
                break
            await self._event.wait()
        return self._items.popleft() if self._items else None

    def _drop_oldest_snapshot(self) -> bool:
        for index, packet in enumerate(self._items):
            if packet.kind == "snapshot":
                del self._items[index]
                return True
        return False


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
    last_input_seq: int = 0
    dropped_snapshots: int = 0


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

    async def start(self) -> None:
        await self.log_worker.start()
        self.simulation.start()
        loop = asyncio.get_running_loop()
        try:
            self._server = await loop.create_server(lambda: GameProtocol(self), self.host, self.port)
            self._tasks = [
                asyncio.create_task(self._snapshot_loop(), name="snapshot-sender"),
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
            snapshot=filtered,
            tick=snapshot.tick,
            seq=0,
            codec=SERIALIZER_NAME,
        )
        self.log_worker.info(f"player connected: {name} ({player.id})")

    def _handle_input(self, session: ClientSession, message: dict[str, Any]) -> None:
        try:
            sequence = int(message.get("seq", 0))
        except (TypeError, ValueError):
            sequence = 0
        if sequence and sequence <= session.last_input_seq:
            return
        session.last_input_seq = sequence
        command = InputCommand.from_dict(message.get("command", {}))
        command.player_id = session.player_id
        self.simulation.set_input(command)

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
            "protocol": "tcp-frame-v2",
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
            for session in list(self.clients.values()):
                if snapshot.tick <= session.last_snapshot_tick:
                    continue
                filtered = filter_snapshot_for_player(
                    snapshot.data,
                    session.player_id,
                    index,
                    self.tuning.network.interest_radius,
                    self.tuning.network.building_interest_radius,
                )
                self._queue_snapshot(session, filtered, snapshot.tick)
            self.profiler.record("snapshot_loop", time.perf_counter() - started)

    def _filter_snapshot(self, snapshot: dict[str, Any], player_id: str) -> dict[str, Any]:
        index = SnapshotInterestIndex(snapshot, self.tuning.network.grid_cell_size)
        return filter_snapshot_for_player(
            snapshot,
            player_id,
            index,
            self.tuning.network.interest_radius,
            self.tuning.network.building_interest_radius,
        )

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
                full=True,
                snapshot=snapshot,
            )
            session.snapshots_since_full = 0
        else:
            delta = make_snapshot_delta(snapshot, session.last_snapshot)
            payload = encode_message(
                "snapshot",
                tick=tick,
                seq=session.sequence,
                full=False,
                base_tick=session.last_snapshot_tick,
                delta=delta,
            )
            session.snapshots_since_full += 1
        if session.outbox.put(OutboundPacket(payload, kind="snapshot")):
            session.last_snapshot = snapshot
            session.last_snapshot_tick = tick

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
