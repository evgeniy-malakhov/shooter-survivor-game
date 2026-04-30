from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.constants import MAP_HEIGHT, MAP_WIDTH, SLOTS
from shared.net_schema import SNAPSHOT_SCHEMA
from shared.protocol import FrameDecoder, SERIALIZER_NAME, encode_message
from shared.protocol_meta import CLIENT_FEATURES, CLIENT_VERSION, PROTOCOL_VERSION

PROFILES_PATH = Path(__file__).with_name("profiles.json")
READ_CHUNK = 65_536


@dataclass(slots=True)
class LoadConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    clients: int = 50
    duration_seconds: float = 90.0
    ramp_up_seconds: float = 20.0
    input_hz: float = 15.0
    command_rate_per_minute: float = 6.0
    disconnect_rate_per_minute: float = 0.1
    reconnect_delay_min: float = 0.4
    reconnect_delay_max: float = 2.5
    packet_delay_ms: float = 0.0
    packet_jitter_ms: float = 0.0
    input_drop_percent: float = 0.0
    shooting_chance: float = 0.06
    ping_interval_seconds: float = 1.0
    connect_timeout_seconds: float = 5.0
    report_interval_seconds: float = 5.0
    seed: int = 1337


@dataclass(slots=True)
class Metrics:
    started_at: float = field(default_factory=time.perf_counter)
    finished_at: float = 0.0
    clients_started: int = 0
    connect_success: int = 0
    connect_failures: int = 0
    reconnect_attempts: int = 0
    reconnect_success: int = 0
    reconnect_failures: int = 0
    disconnects: int = 0
    inputs_sent: int = 0
    inputs_dropped_locally: int = 0
    commands_sent: int = 0
    commands_acked: int = 0
    command_results: int = 0
    command_replays: int = 0
    commands_rejected: int = 0
    command_timeouts: int = 0
    snapshots: int = 0
    full_snapshots: int = 0
    delta_snapshots: int = 0
    estimated_dropped_snapshots: int = 0
    events: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    protocol_errors: int = 0
    tick_ms: list[float] = field(default_factory=list)
    ping_ms: list[float] = field(default_factory=list)
    snapshot_interval_ms: list[float] = field(default_factory=list)
    command_ack_ms: list[float] = field(default_factory=list)
    cpu_percent: list[float] = field(default_factory=list)
    rss_mb: list[float] = field(default_factory=list)
    process_note: str = ""

    def elapsed(self) -> float:
        end = self.finished_at or time.perf_counter()
        return max(0.001, end - self.started_at)

    def to_dict(self) -> dict[str, Any]:
        elapsed = self.elapsed()
        reconnect_total = max(1, self.reconnect_attempts)
        return {
            "elapsed_seconds": round(elapsed, 3),
            "clients_started": self.clients_started,
            "connect_success": self.connect_success,
            "connect_failures": self.connect_failures,
            "reconnect_attempts": self.reconnect_attempts,
            "reconnect_success": self.reconnect_success,
            "reconnect_failures": self.reconnect_failures,
            "reconnect_success_rate": round(self.reconnect_success / reconnect_total, 4),
            "disconnects": self.disconnects,
            "inputs_sent": self.inputs_sent,
            "inputs_dropped_locally": self.inputs_dropped_locally,
            "commands_sent": self.commands_sent,
            "commands_acked": self.commands_acked,
            "command_results": self.command_results,
            "command_replays": self.command_replays,
            "commands_rejected": self.commands_rejected,
            "command_timeouts": self.command_timeouts,
            "snapshots": self.snapshots,
            "full_snapshots": self.full_snapshots,
            "delta_snapshots": self.delta_snapshots,
            "estimated_dropped_snapshots": self.estimated_dropped_snapshots,
            "events": self.events,
            "bytes_in_per_sec": round(self.bytes_in / elapsed, 1),
            "bytes_out_per_sec": round(self.bytes_out / elapsed, 1),
            "protocol_errors": self.protocol_errors,
            "tick_ms": _series(self.tick_ms),
            "snapshot_interval_ms": _series(self.snapshot_interval_ms),
            "command_ack_ms": _series(self.command_ack_ms),
            "ping_ms": _series(self.ping_ms),
            "server_cpu_percent": _series(self.cpu_percent),
            "server_rss_mb": _series(self.rss_mb),
            "process_note": self.process_note,
        }


class FakeClient:
    def __init__(self, index: int, config: LoadConfig, metrics: Metrics, rng: random.Random) -> None:
        self.index = index
        self.config = config
        self.metrics = metrics
        self.rng = rng
        self.player_id: str | None = None
        self.session_token: str | None = None
        self.last_snapshot_tick = 0
        self.last_snapshot_seq = 0
        self.input_seq = 0
        self.command_id = 0
        self.pending_commands: dict[int, float] = {}
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.decoder = FrameDecoder()
        self.pending_messages: list[dict[str, Any]] = []
        self.write_lock = asyncio.Lock()
        self.connected = False
        self.last_snapshot_at = 0.0
        self.move_angle = self.rng.random() * math.tau
        self.next_turn_at = 0.0

    async def run(self, end_at: float, start_delay: float) -> None:
        await asyncio.sleep(start_delay)
        self.metrics.clients_started += 1
        if not await self._connect(resume=False):
            return
        while time.perf_counter() < end_at:
            segment_end = min(end_at, self._next_disconnect_at())
            await self._run_connected_until(segment_end)
            if time.perf_counter() >= end_at:
                break
            self.metrics.disconnects += 1
            await self._close(abort=True)
            await asyncio.sleep(self.rng.uniform(self.config.reconnect_delay_min, self.config.reconnect_delay_max))
            if not await self._connect(resume=bool(self.player_id and self.session_token)):
                await asyncio.sleep(self.rng.uniform(0.5, 2.0))
        await self._close(abort=False)
        self._count_timed_out_commands()

    async def _connect(self, resume: bool) -> bool:
        if resume:
            self.metrics.reconnect_attempts += 1
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.config.host, self.config.port),
                timeout=self.config.connect_timeout_seconds,
            )
            payload = self._resume_payload() if resume else self._hello_payload()
            await self._write_raw(payload)
            message = await asyncio.wait_for(self._read_one(), timeout=self.config.connect_timeout_seconds)
            if message.get("type") != "welcome":
                raise ConnectionError(str(message.get("message", "server refused connection")))
            self.player_id = str(message["player_id"])
            self.session_token = str(message.get("session_token", self.session_token or ""))
            self.last_snapshot_tick = int(message.get("tick", 0))
            self.last_snapshot_seq = int(message.get("seq", 0))
            self.connected = True
            self.last_snapshot_at = time.perf_counter()
            if resume:
                if not message.get("resumed"):
                    raise ConnectionError("server accepted connection but did not resume session")
                self.metrics.reconnect_success += 1
            else:
                self.metrics.connect_success += 1
            return True
        except (asyncio.TimeoutError, ConnectionError, OSError, ValueError):
            if resume:
                self.metrics.reconnect_failures += 1
            else:
                self.metrics.connect_failures += 1
            await self._close(abort=True)
            return False

    async def _run_connected_until(self, segment_end: float) -> None:
        stop = asyncio.Event()
        tasks = [
            asyncio.create_task(self._reader_loop(stop)),
            asyncio.create_task(self._input_loop(stop)),
            asyncio.create_task(self._command_loop(stop)),
            asyncio.create_task(self._ping_loop(stop)),
        ]
        try:
            while time.perf_counter() < segment_end and self.connected:
                await asyncio.sleep(0.05)
        finally:
            stop.set()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _reader_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set() and self.connected:
            try:
                message = await self._read_one()
                await self._network_delay()
                self._handle_message(message)
            except (asyncio.CancelledError,):
                raise
            except (ConnectionError, OSError, ValueError):
                self.metrics.protocol_errors += 1
                self.connected = False
                return

    async def _input_loop(self, stop: asyncio.Event) -> None:
        delay = 1.0 / max(1.0, self.config.input_hz)
        while not stop.is_set() and self.connected:
            if self.rng.random() * 100.0 < self.config.input_drop_percent:
                self.metrics.inputs_dropped_locally += 1
                await asyncio.sleep(delay)
                continue
            self.input_seq += 1
            payload = encode_message("input", seq=self.input_seq, command=self._movement_command())
            await self._send(payload)
            self.metrics.inputs_sent += 1
            await asyncio.sleep(delay)

    async def _command_loop(self, stop: asyncio.Event) -> None:
        rate = max(0.0, self.config.command_rate_per_minute) / 60.0
        if rate <= 0.0:
            return
        while not stop.is_set() and self.connected:
            await asyncio.sleep(max(0.05, self.rng.expovariate(rate)))
            if stop.is_set() or not self.connected:
                return
            await self._send_command(*self._random_command())

    async def _ping_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set() and self.connected:
            sent = time.time()
            await self._send(encode_message("ping", sent=sent, client_ping_ms=0.0))
            await asyncio.sleep(self.config.ping_interval_seconds)

    async def _send_command(self, kind: str, payload: dict[str, Any]) -> None:
        self.command_id += 1
        command_id = self.command_id
        self.pending_commands[command_id] = time.perf_counter()
        await self._send(encode_message("command", command_id=command_id, kind=kind, payload=payload))
        self.metrics.commands_sent += 1

    async def _send(self, payload: bytes) -> None:
        if not self.writer or self.writer.is_closing():
            self.connected = False
            return
        await self._network_delay()
        async with self.write_lock:
            self.writer.write(payload)
            self.metrics.bytes_out += len(payload)
            await self.writer.drain()

    async def _write_raw(self, payload: bytes) -> None:
        if not self.writer:
            raise ConnectionError("not connected")
        self.writer.write(payload)
        self.metrics.bytes_out += len(payload)
        await self.writer.drain()

    async def _read_one(self) -> dict[str, Any]:
        if self.pending_messages:
            return self.pending_messages.pop(0)
        if not self.reader:
            raise ConnectionError("not connected")
        while True:
            chunk = await self.reader.read(READ_CHUNK)
            if not chunk:
                raise ConnectionError("connection closed")
            self.metrics.bytes_in += len(chunk)
            messages = self.decoder.feed(chunk)
            if messages:
                self.pending_messages.extend(messages[1:])
                return messages[0]

    async def _close(self, abort: bool) -> None:
        self.connected = False
        writer = self.writer
        self.writer = None
        self.reader = None
        self.pending_messages.clear()
        self.decoder = FrameDecoder()
        if not writer:
            return
        try:
            if abort:
                writer.transport.abort()
            else:
                writer.close()
                await writer.wait_closed()
        except (ConnectionError, OSError):
            pass

    async def _network_delay(self) -> None:
        base = self.config.packet_delay_ms
        jitter = self.config.packet_jitter_ms
        if base <= 0.0 and jitter <= 0.0:
            return
        delay_ms = max(0.0, base + self.rng.uniform(0.0, jitter))
        await asyncio.sleep(delay_ms / 1000.0)

    def _handle_message(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        if kind == "snapshot":
            now = time.perf_counter()
            if self.last_snapshot_at > 0.0:
                self.metrics.snapshot_interval_ms.append((now - self.last_snapshot_at) * 1000.0)
            self.last_snapshot_at = now
            seq = int(message.get("seq", self.last_snapshot_seq))
            if self.last_snapshot_seq and seq > self.last_snapshot_seq + 1:
                self.metrics.estimated_dropped_snapshots += seq - self.last_snapshot_seq - 1
            self.last_snapshot_seq = seq
            self.last_snapshot_tick = int(message.get("tick", self.last_snapshot_tick))
            self.metrics.snapshots += 1
            if message.get("full", True):
                self.metrics.full_snapshots += 1
            else:
                self.metrics.delta_snapshots += 1
        elif kind == "command_result":
            command_id = int(message.get("command_id", 0))
            sent_at = self.pending_commands.pop(command_id, None)
            self.metrics.command_results += 1
            if sent_at is not None:
                self.metrics.command_ack_ms.append((time.perf_counter() - sent_at) * 1000.0)
                self.metrics.commands_acked += 1
            else:
                self.metrics.command_replays += 1
            if not message.get("ok", False):
                self.metrics.commands_rejected += 1
        elif kind == "events":
            events = message.get("events", [])
            if isinstance(events, list):
                self.metrics.events += len(events)
        elif kind == "pong":
            sent = message.get("sent")
            try:
                self.metrics.ping_ms.append(max(0.0, (time.time() - float(sent)) * 1000.0))
            except (TypeError, ValueError):
                pass
            try:
                self.metrics.tick_ms.append(float(message.get("tick_ms", 0.0)))
            except (TypeError, ValueError):
                pass
        elif kind == "error":
            self.connected = False

    def _movement_command(self) -> dict[str, Any]:
        now = time.perf_counter()
        if now >= self.next_turn_at:
            self.move_angle = self.rng.random() * math.tau
            self.next_turn_at = now + self.rng.uniform(0.5, 2.5)
        return {
            "move_x": round(math.cos(self.move_angle), 3),
            "move_y": round(math.sin(self.move_angle), 3),
            "aim_x": round(self.rng.uniform(0.0, MAP_WIDTH), 3),
            "aim_y": round(self.rng.uniform(0.0, MAP_HEIGHT), 3),
            "shooting": self.rng.random() < self.config.shooting_chance,
            "sprint": self.rng.random() < 0.18,
            "sneak": self.rng.random() < 0.08,
        }

    def _random_command(self) -> tuple[str, dict[str, Any]]:
        roll = self.rng.random()
        if roll < 0.24:
            return "pickup", {}
        if roll < 0.38:
            return "interact", {}
        if roll < 0.52:
            return "select_slot", {"slot": self.rng.choice(SLOTS)}
        if roll < 0.66:
            return "reload", {}
        if roll < 0.80:
            return "inventory_action", self._random_inventory_action()
        if roll < 0.90:
            return "toggle_utility", {}
        return "respawn", {}

    def _random_inventory_action(self) -> dict[str, Any]:
        action = self.rng.choice(("move", "quick_swap", "drop"))
        if action == "quick_swap":
            return {"type": "quick_swap", "a": self.rng.choice(SLOTS), "b": self.rng.choice(SLOTS)}
        if action == "drop":
            return {"type": "drop", "source": "backpack", "index": self.rng.randrange(0, 30)}
        return {
            "type": "move",
            "src": "backpack",
            "src_index": self.rng.randrange(0, 30),
            "dst": "backpack",
            "dst_index": self.rng.randrange(0, 30),
        }

    def _next_disconnect_at(self) -> float:
        rate = max(0.0, self.config.disconnect_rate_per_minute) / 60.0
        if rate <= 0.0:
            return float("inf")
        return time.perf_counter() + max(2.0, self.rng.expovariate(rate))

    def _hello_payload(self) -> bytes:
        return encode_message(
            "hello",
            name=f"Bot{self.index:04d}",
            client_version=CLIENT_VERSION,
            protocol_version=PROTOCOL_VERSION,
            snapshot_schema=SNAPSHOT_SCHEMA,
            features=CLIENT_FEATURES,
        )

    def _resume_payload(self) -> bytes:
        return encode_message(
            "resume",
            player_id=self.player_id,
            session_token=self.session_token,
            last_snapshot_tick=self.last_snapshot_tick,
            client_version=CLIENT_VERSION,
            protocol_version=PROTOCOL_VERSION,
            snapshot_schema=SNAPSHOT_SCHEMA,
            features=CLIENT_FEATURES,
        )

    def _count_timed_out_commands(self) -> None:
        now = time.perf_counter()
        timed_out = [command_id for command_id, sent_at in self.pending_commands.items() if now - sent_at > 5.0]
        for command_id in timed_out:
            self.pending_commands.pop(command_id, None)
        self.metrics.command_timeouts += len(timed_out)


class ProcessSampler:
    def __init__(self, pid: int | None, metrics: Metrics) -> None:
        self.pid = pid
        self.metrics = metrics
        self._process: Any | None = None

    async def run(self, stop: asyncio.Event) -> None:
        if not self.pid:
            self.metrics.process_note = "server process metrics disabled; pass --server-pid or --server-cmd"
            return
        try:
            import psutil  # type: ignore
        except ImportError:
            self.metrics.process_note = "psutil is not installed; CPU/RAM metrics unavailable"
            return
        try:
            self._process = psutil.Process(self.pid)
            self._process.cpu_percent(interval=None)
        except psutil.Error as exc:  # type: ignore[attr-defined]
            self.metrics.process_note = f"cannot sample process {self.pid}: {exc}"
            return
        while not stop.is_set():
            try:
                self.metrics.cpu_percent.append(float(self._process.cpu_percent(interval=None)))
                self.metrics.rss_mb.append(float(self._process.memory_info().rss) / (1024.0 * 1024.0))
            except psutil.Error as exc:  # type: ignore[attr-defined]
                self.metrics.process_note = f"process sampling stopped: {exc}"
                return
            await asyncio.sleep(1.0)


async def run_load(config: LoadConfig, server_pid: int | None = None) -> Metrics:
    metrics = Metrics()
    rng = random.Random(config.seed)
    stop_sampler = asyncio.Event()
    sampler_task = asyncio.create_task(ProcessSampler(server_pid, metrics).run(stop_sampler))
    end_at = time.perf_counter() + config.duration_seconds
    reporter = asyncio.create_task(_report_loop(config, metrics, end_at))
    clients = [
        FakeClient(i, config, metrics, random.Random(rng.randrange(1, 2**31)))
        for i in range(config.clients)
    ]
    tasks = [
        asyncio.create_task(client.run(end_at, _start_delay(i, config)))
        for i, client in enumerate(clients)
    ]
    await asyncio.gather(*tasks)
    metrics.finished_at = time.perf_counter()
    stop_sampler.set()
    reporter.cancel()
    await asyncio.gather(sampler_task, reporter, return_exceptions=True)
    return metrics


async def _report_loop(config: LoadConfig, metrics: Metrics, end_at: float) -> None:
    while time.perf_counter() < end_at:
        await asyncio.sleep(config.report_interval_seconds)
        elapsed = metrics.elapsed()
        print(
            f"[{elapsed:6.1f}s] clients={metrics.connect_success} "
            f"snapshots={metrics.snapshots} commands={metrics.commands_acked}/{metrics.commands_sent} "
            f"reconnect={metrics.reconnect_success}/{metrics.reconnect_attempts} "
            f"in={_human_bytes(metrics.bytes_in / elapsed)}/s out={_human_bytes(metrics.bytes_out / elapsed)}/s",
            flush=True,
        )


def _start_delay(index: int, config: LoadConfig) -> float:
    if config.clients <= 1 or config.ramp_up_seconds <= 0.0:
        return 0.0
    return config.ramp_up_seconds * (index / max(1, config.clients - 1))


def _series(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    return {
        "count": len(values),
        "avg": round(sum(values) / len(values), 3),
        "p50": round(_percentile_sorted(ordered, 50), 3),
        "p95": round(_percentile_sorted(ordered, 95), 3),
        "p99": round(_percentile_sorted(ordered, 99), 3),
        "max": round(ordered[-1], 3),
    }


def _percentile_sorted(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    rank = (len(values) - 1) * percentile / 100.0
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return values[int(rank)]
    blend = rank - low
    return values[low] * (1.0 - blend) + values[high] * blend


def _human_bytes(value: float) -> str:
    units = ("B", "KB", "MB", "GB")
    size = float(value)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}GB"


def _load_profile(name: str) -> dict[str, Any]:
    profiles = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    if name not in profiles:
        raise SystemExit(f"unknown profile '{name}'. Available: {', '.join(sorted(profiles))}")
    profile = profiles[name]
    if not isinstance(profile, dict):
        raise SystemExit(f"profile '{name}' must be an object")
    return profile


def _config_from_args(args: argparse.Namespace) -> LoadConfig:
    data = _load_profile(args.profile)
    overrides = {
        "host": args.host,
        "port": args.port,
        "clients": args.clients,
        "duration_seconds": args.duration,
        "ramp_up_seconds": args.ramp_up,
        "input_hz": args.input_hz,
        "command_rate_per_minute": args.command_rate,
        "disconnect_rate_per_minute": args.disconnect_rate,
        "packet_delay_ms": args.packet_delay_ms,
        "packet_jitter_ms": args.packet_jitter_ms,
        "input_drop_percent": args.input_drop_percent,
        "seed": args.seed,
    }
    for key, value in overrides.items():
        if value is not None:
            data[key] = value
    return LoadConfig(**data)


def _print_summary(metrics: Metrics, config: LoadConfig) -> None:
    payload = metrics.to_dict()
    print("\n=== Load Test Summary ===")
    print(f"codec: {SERIALIZER_NAME}")
    print(f"clients: {config.clients} duration: {payload['elapsed_seconds']}s")
    print(f"connect: {metrics.connect_success} ok / {metrics.connect_failures} failed")
    print(
        f"reconnect: {metrics.reconnect_success}/{metrics.reconnect_attempts} "
        f"({payload['reconnect_success_rate'] * 100:.1f}%)"
    )
    print(f"bytes: in {_human_bytes(payload['bytes_in_per_sec'])}/s out {_human_bytes(payload['bytes_out_per_sec'])}/s")
    print(f"snapshots: {metrics.snapshots} full={metrics.full_snapshots} delta={metrics.delta_snapshots} dropped~={metrics.estimated_dropped_snapshots}")
    print(
        f"commands: sent={metrics.commands_sent} acked={metrics.commands_acked} "
        f"results={metrics.command_results} replays={metrics.command_replays} "
        f"rejected={metrics.commands_rejected} timeouts={metrics.command_timeouts}"
    )
    _print_series("tick ms", payload["tick_ms"])
    _print_series("snapshot interval ms", payload["snapshot_interval_ms"])
    _print_series("command ack ms", payload["command_ack_ms"])
    _print_series("ping ms", payload["ping_ms"])
    _print_series("server CPU %", payload["server_cpu_percent"])
    _print_series("server RSS MB", payload["server_rss_mb"])
    if metrics.process_note:
        print(f"process metrics: {metrics.process_note}")


def _print_series(label: str, series: object) -> None:
    if not isinstance(series, dict) or not series.get("count"):
        print(f"{label}: n/a")
        return
    print(
        f"{label}: avg={series['avg']} p95={series['p95']} "
        f"p99={series['p99']} max={series['max']} count={series['count']}"
    )


async def _wait_for_port(host: str, port: int, timeout: float) -> None:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        try:
            reader, writer = await asyncio.open_connection(host, port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.1)
    raise TimeoutError(f"server did not open {host}:{port} within {timeout:.1f}s")


def _start_server(command: str) -> subprocess.Popen[bytes]:
    args = shlex.split(command, posix=os.name != "nt")
    return subprocess.Popen(args, cwd=ROOT)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run fake-client load tests against the online server.")
    parser.add_argument("--profile", default="smoke", help="Profile from load_tests/profiles.json: smoke, 50, 100, 300, 500.")
    parser.add_argument("--host", default=None, help="Server host override.")
    parser.add_argument("--port", type=int, default=None, help="Server port override.")
    parser.add_argument("--clients", type=int, default=None, help="Client count override.")
    parser.add_argument("--duration", type=float, default=None, help="Duration in seconds override.")
    parser.add_argument("--ramp-up", type=float, default=None, help="Ramp-up seconds override.")
    parser.add_argument("--input-hz", type=float, default=None, help="Movement input frequency per client.")
    parser.add_argument("--command-rate", type=float, default=None, help="Reliable commands per client per minute.")
    parser.add_argument("--disconnect-rate", type=float, default=None, help="Disconnects per client per minute.")
    parser.add_argument("--packet-delay-ms", type=float, default=None, help="Base simulated client network delay.")
    parser.add_argument("--packet-jitter-ms", type=float, default=None, help="Additional random simulated delay.")
    parser.add_argument("--input-drop-percent", type=float, default=None, help="Locally skip this percent of input frames.")
    parser.add_argument("--seed", type=int, default=None, help="Deterministic random seed.")
    parser.add_argument("--server-pid", type=int, default=None, help="Existing server PID for CPU/RAM sampling.")
    parser.add_argument("--server-cmd", default="", help="Optional command to start the server before the test.")
    parser.add_argument("--spawn-wait", type=float, default=10.0, help="Seconds to wait for --server-cmd to open the port.")
    parser.add_argument("--json-out", default="", help="Write machine-readable summary JSON to this path.")
    return parser.parse_args()


async def async_main() -> None:
    args = parse_args()
    config = _config_from_args(args)
    server_process: subprocess.Popen[bytes] | None = None
    server_pid = args.server_pid
    try:
        if args.server_cmd:
            server_process = _start_server(args.server_cmd)
            server_pid = server_process.pid
            await _wait_for_port(config.host, config.port, args.spawn_wait)
        metrics = await run_load(config, server_pid=server_pid)
        _print_summary(metrics, config)
        if args.json_out:
            path = Path(args.json_out)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(metrics.to_dict(), indent=2), encoding="utf-8")
            print(f"wrote {path}")
    finally:
        if server_process and server_process.poll() is None:
            server_process.terminate()
            try:
                server_process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                server_process.kill()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
