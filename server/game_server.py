from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass

from shared.constants import SNAPSHOT_RATE, TICK_RATE
from shared.models import InputCommand
from shared.protocol import decode_message, encode_message
from shared.simulation import GameWorld


@dataclass(slots=True)
class ClientSession:
    player_id: str
    name: str
    writer: asyncio.StreamWriter


class GameServer:
    def __init__(self, host: str, port: int, difficulty_key: str = "medium") -> None:
        self.host = host
        self.port = port
        self.difficulty_key = difficulty_key
        self.world = GameWorld(difficulty_key=difficulty_key)
        self.clients: dict[str, ClientSession] = {}
        self._server: asyncio.AbstractServer | None = None
        self._running = asyncio.Event()

    async def start(self) -> None:
        self._server = await asyncio.start_server(self.handle_client, self.host, self.port)
        self._running.set()
        sockets = ", ".join(str(sock.getsockname()) for sock in self._server.sockets or [])
        print(f"Neon Outbreak server listening on {sockets} [{self.difficulty_key}]")
        try:
            async with self._server:
                await asyncio.gather(
                    self._server.serve_forever(),
                    self._tick_loop(),
                    self._snapshot_loop(),
                )
        finally:
            self.world.close()

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
                        zombies=len(self.world.zombies),
                        difficulty=self.difficulty_key,
                    )
                )
                await writer.drain()
                return
            if first["type"] != "hello":
                writer.write(encode_message("error", message="expected hello"))
                await writer.drain()
                return

            name = str(first.get("name", "Player"))[:18]
            player = self.world.add_player(name)
            player_id = player.id
            self.clients[player_id] = ClientSession(player_id, name, writer)
            writer.write(encode_message("welcome", player_id=player_id, snapshot=self.world.snapshot().to_dict()))
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
                    self.world.set_input(command)
                elif message_type == "ping":
                    writer.write(
                        encode_message(
                            "pong",
                            sent=message.get("sent", time.time()),
                            players=len(self.clients),
                            zombies=len(self.world.zombies),
                            difficulty=self.difficulty_key,
                        )
                    )
                    await writer.drain()
        except (asyncio.TimeoutError, ConnectionError, ValueError) as exc:
            print(f"client closed with {exc!r}")
        finally:
            if player_id:
                self.clients.pop(player_id, None)
                self.world.remove_player(player_id)
                print(f"player disconnected: {player_id}")
            writer.close()
            with contextlib.suppress(ConnectionError, RuntimeError):
                await writer.wait_closed()

    async def _tick_loop(self) -> None:
        await self._running.wait()
        dt = 1.0 / TICK_RATE
        next_tick = time.perf_counter()
        while True:
            now = time.perf_counter()
            if now < next_tick:
                await asyncio.sleep(next_tick - now)
                continue
            self.world.update(dt)
            next_tick += dt

    async def _snapshot_loop(self) -> None:
        await self._running.wait()
        delay = 1.0 / SNAPSHOT_RATE
        while True:
            await asyncio.sleep(delay)
            if not self.clients:
                continue
            payload = encode_message("snapshot", snapshot=self.world.snapshot().to_dict())
            dead: list[str] = []
            for player_id, session in list(self.clients.items()):
                try:
                    session.writer.write(payload)
                    await session.writer.drain()
                except ConnectionError:
                    dead.append(player_id)
            for player_id in dead:
                self.clients.pop(player_id, None)
                self.world.remove_player(player_id)
