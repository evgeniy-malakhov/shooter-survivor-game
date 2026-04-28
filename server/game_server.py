from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from dataclasses import dataclass

from shared.constants import SNAPSHOT_RATE, TICK_RATE
from shared.models import InputCommand, PlayerState
from shared.protocol import decode_message, encode_message
from shared.simulation import GameWorld


@dataclass(slots=True)
class ClientSession:
    player_id: str
    name: str
    writer: asyncio.StreamWriter


class SimulationRunner:
    def __init__(self, difficulty_key: str) -> None:
        self.world = GameWorld(difficulty_key=difficulty_key)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="simulation-runner", daemon=True)
        self._input_lock = threading.Lock()
        self._pending_inputs: dict[str, InputCommand] = {}
        self._snapshot_lock = threading.Lock()
        self._snapshot_payload = encode_message("snapshot", snapshot=self.world.snapshot().to_dict())
        self._last_tick_seconds = 0.0

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)
        self.world.close()

    def add_player(self, name: str) -> tuple[PlayerState, dict[str, object]]:
        player = self.world.add_player(name)
        snapshot = self.world.snapshot().to_dict()
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

    def snapshot_payload(self) -> bytes:
        with self._snapshot_lock:
            return self._snapshot_payload

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
        self._publish_snapshot(self.world.snapshot().to_dict())

    def _publish_snapshot(self, snapshot: dict[str, object]) -> None:
        payload = encode_message("snapshot", snapshot=snapshot)
        with self._snapshot_lock:
            self._snapshot_payload = payload


class GameServer:
    def __init__(self, host: str, port: int, difficulty_key: str = "medium") -> None:
        self.host = host
        self.port = port
        self.difficulty_key = difficulty_key
        self.simulation = SimulationRunner(difficulty_key)
        self.clients: dict[str, ClientSession] = {}
        self._server: asyncio.AbstractServer | None = None
        self._running = asyncio.Event()

    async def start(self) -> None:
        self.simulation.start()
        try:
            self._server = await asyncio.start_server(self.handle_client, self.host, self.port)
            self._running.set()
            sockets = ", ".join(str(sock.getsockname()) for sock in self._server.sockets or [])
            print(f"Neon Outbreak server listening on {sockets} [{self.difficulty_key}]")
            async with self._server:
                await asyncio.gather(
                    self._server.serve_forever(),
                    self._snapshot_loop(),
                )
        finally:
            self.simulation.stop()

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        player_id: str | None = None
        try:
            first_raw = await asyncio.wait_for(reader.readline(), timeout=6.0)
            if not first_raw:
                return
            first = decode_message(first_raw)
            if first["type"] == "ping":
                writer.write(
                    encode_message(
                        "pong",
                        sent=first.get("sent", time.time()),
                        players=len(self.clients),
                        zombies=self.simulation.zombie_count(),
                        difficulty=self.difficulty_key,
                        tick_ms=round(self.simulation.tick_seconds() * 1000.0, 2),
                    )
                )
                await writer.drain()
                return
            if first["type"] != "hello":
                writer.write(encode_message("error", message="expected hello"))
                await writer.drain()
                return

            name = str(first.get("name", "Player"))[:18]
            player, snapshot = self.simulation.add_player(name)
            player_id = player.id
            self.clients[player_id] = ClientSession(player_id, name, writer)
            writer.write(encode_message("welcome", player_id=player_id, snapshot=snapshot))
            await writer.drain()
            print(f"player connected: {name} ({player_id})")

            while not reader.at_eof():
                raw = await reader.readline()
                if not raw:
                    break
                message = decode_message(raw)
                message_type = message["type"]
                if message_type == "input":
                    command = InputCommand.from_dict(message.get("command", {}))
                    command.player_id = player_id
                    self.simulation.set_input(command)
                elif message_type == "profile":
                    name = str(message.get("name", ""))[:18]
                    self.simulation.rename_player(player_id, name)
                elif message_type == "ping":
                    writer.write(
                        encode_message(
                            "pong",
                            sent=message.get("sent", time.time()),
                            players=len(self.clients),
                            zombies=self.simulation.zombie_count(),
                            difficulty=self.difficulty_key,
                            tick_ms=round(self.simulation.tick_seconds() * 1000.0, 2),
                        )
                    )
                    await writer.drain()
        except (asyncio.TimeoutError, ConnectionError, ValueError) as exc:
            print(f"client closed with {exc!r}")
        finally:
            if player_id:
                self.clients.pop(player_id, None)
                self.simulation.remove_player(player_id)
                print(f"player disconnected: {player_id}")
            writer.close()
            with contextlib.suppress(ConnectionError, RuntimeError):
                await writer.wait_closed()

    async def _snapshot_loop(self) -> None:
        await self._running.wait()
        delay = 1.0 / SNAPSHOT_RATE
        while True:
            await asyncio.sleep(delay)
            if not self.clients:
                continue
            payload = self.simulation.snapshot_payload()
            dead: list[str] = []
            drain_tasks: list[tuple[str, asyncio.Task[None]]] = []
            for player_id, session in list(self.clients.items()):
                try:
                    session.writer.write(payload)
                    drain_tasks.append((player_id, asyncio.create_task(session.writer.drain())))
                except (ConnectionError, OSError, RuntimeError):
                    dead.append(player_id)
            if drain_tasks:
                results = await asyncio.gather(*(task for _, task in drain_tasks), return_exceptions=True)
                for (player_id, _task), result in zip(drain_tasks, results):
                    if isinstance(result, Exception):
                        dead.append(player_id)
            for player_id in dead:
                self.clients.pop(player_id, None)
                self.simulation.remove_player(player_id)
