from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "server.json"


@dataclass(frozen=True, slots=True)
class NetworkTuning:
    max_clients: int = 50
    listen_backlog: int = 256
    interest_radius: float = 900.0
    building_interest_radius: float = 1400.0
    grid_cell_size: float = 512.0
    output_queue_packets: int = 96
    command_queue_limit: int = 128
    snapshot_send_batch_size: int = 10
    max_pending_snapshots_per_client: int = 1
    adaptive_snapshot_medium_clients: int = 16
    adaptive_snapshot_medium_rate: int = 20
    adaptive_snapshot_high_clients: int = 33
    adaptive_snapshot_high_rate: int = 15
    adaptive_snapshot_extreme_clients: int = 45
    adaptive_snapshot_extreme_rate: int = 12
    slow_client_snapshot_stride: int = 3
    slow_client_outbox_wait_ms: float = 750.0
    slow_client_recovery_seconds: float = 3.0
    connection_burst_window_seconds: float = 2.0
    connection_burst_threshold: int = 24
    connection_burst_snapshot_rate: int = 12
    state_hash_sample_seconds: float = 1.0
    full_snapshot_interval_seconds: float = 5.0
    resume_timeout_seconds: float = 30.0
    journal_seconds: float = 10.0
    write_buffer_high_water: int = 262_144
    write_buffer_low_water: int = 65_536


@dataclass(frozen=True, slots=True)
class SimulationTuning:
    tick_rate: int = 30
    snapshot_rate: int = 24
    zombie_ai_decision_rate: float = 6.0
    zombie_ai_far_decision_rate: float = 2.0
    zombie_ai_active_radius: float = 1800.0
    zombie_ai_far_radius: float = 3200.0
    zombie_ai_batch_size: int = 8
    zombie_ai_process_workers: int = 2


@dataclass(frozen=True, slots=True)
class RateLimitTuning:
    input_per_second: int = 45
    command_per_second: int = 16
    inbound_bytes_per_second: int = 256_000


@dataclass(frozen=True, slots=True)
class ObservabilityTuning:
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8766


@dataclass(frozen=True, slots=True)
class ProfilingTuning:
    log_interval_seconds: float = 5.0
    slow_tick_ms: float = 12.0
    slow_snapshot_ms: float = 8.0


@dataclass(frozen=True, slots=True)
class ServerTuning:
    simulation: SimulationTuning = SimulationTuning()
    network: NetworkTuning = NetworkTuning()
    rate_limits: RateLimitTuning = RateLimitTuning()
    observability: ObservabilityTuning = ObservabilityTuning()
    profiling: ProfilingTuning = ProfilingTuning()


def load_server_tuning() -> ServerTuning:
    if not CONFIG_PATH.exists():
        return ServerTuning()
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ServerTuning()
    if not isinstance(raw, dict):
        return ServerTuning()
    return ServerTuning(
        simulation=_load_simulation(raw.get("simulation", {})),
        network=_load_network(raw.get("network", {})),
        rate_limits=_load_rate_limits(raw.get("rate_limits", {})),
        observability=_load_observability(raw.get("observability", {})),
        profiling=_load_profiling(raw.get("profiling", {})),
    )


def _load_simulation(raw: Any) -> SimulationTuning:
    data = raw if isinstance(raw, dict) else {}
    fallback = SimulationTuning()
    return SimulationTuning(
        tick_rate=_int(data, "tick_rate", fallback.tick_rate, minimum=5),
        snapshot_rate=_int(data, "snapshot_rate", fallback.snapshot_rate, minimum=1),
        zombie_ai_decision_rate=_float(
            data,
            "zombie_ai_decision_rate",
            fallback.zombie_ai_decision_rate,
            minimum=0.25,
        ),
        zombie_ai_far_decision_rate=_float(
            data,
            "zombie_ai_far_decision_rate",
            fallback.zombie_ai_far_decision_rate,
            minimum=0.1,
        ),
        zombie_ai_active_radius=_float(
            data,
            "zombie_ai_active_radius",
            fallback.zombie_ai_active_radius,
            minimum=240.0,
        ),
        zombie_ai_far_radius=_float(
            data,
            "zombie_ai_far_radius",
            fallback.zombie_ai_far_radius,
            minimum=240.0,
        ),
        zombie_ai_batch_size=_int(data, "zombie_ai_batch_size", fallback.zombie_ai_batch_size, minimum=1),
        zombie_ai_process_workers=_int(
            data,
            "zombie_ai_process_workers",
            fallback.zombie_ai_process_workers,
            minimum=0,
        ),
    )


def _load_network(raw: Any) -> NetworkTuning:
    data = raw if isinstance(raw, dict) else {}
    fallback = NetworkTuning()
    return NetworkTuning(
        max_clients=_int(data, "max_clients", fallback.max_clients, minimum=1),
        listen_backlog=_int(data, "listen_backlog", fallback.listen_backlog, minimum=16),
        interest_radius=_float(data, "interest_radius", fallback.interest_radius, minimum=320.0),
        building_interest_radius=_float(data, "building_interest_radius", fallback.building_interest_radius, minimum=320.0),
        grid_cell_size=_float(data, "grid_cell_size", fallback.grid_cell_size, minimum=64.0),
        output_queue_packets=_int(data, "output_queue_packets", fallback.output_queue_packets, minimum=8),
        command_queue_limit=_int(data, "command_queue_limit", fallback.command_queue_limit, minimum=8),
        snapshot_send_batch_size=_int(data, "snapshot_send_batch_size", fallback.snapshot_send_batch_size, minimum=1),
        max_pending_snapshots_per_client=_int(
            data,
            "max_pending_snapshots_per_client",
            fallback.max_pending_snapshots_per_client,
            minimum=1,
        ),
        adaptive_snapshot_medium_clients=_int(
            data,
            "adaptive_snapshot_medium_clients",
            fallback.adaptive_snapshot_medium_clients,
            minimum=1,
        ),
        adaptive_snapshot_medium_rate=_int(
            data,
            "adaptive_snapshot_medium_rate",
            fallback.adaptive_snapshot_medium_rate,
            minimum=1,
        ),
        adaptive_snapshot_high_clients=_int(
            data,
            "adaptive_snapshot_high_clients",
            fallback.adaptive_snapshot_high_clients,
            minimum=1,
        ),
        adaptive_snapshot_high_rate=_int(
            data,
            "adaptive_snapshot_high_rate",
            fallback.adaptive_snapshot_high_rate,
            minimum=1,
        ),
        adaptive_snapshot_extreme_clients=_int(
            data,
            "adaptive_snapshot_extreme_clients",
            fallback.adaptive_snapshot_extreme_clients,
            minimum=1,
        ),
        adaptive_snapshot_extreme_rate=_int(
            data,
            "adaptive_snapshot_extreme_rate",
            fallback.adaptive_snapshot_extreme_rate,
            minimum=1,
        ),
        slow_client_snapshot_stride=_int(
            data,
            "slow_client_snapshot_stride",
            fallback.slow_client_snapshot_stride,
            minimum=1,
        ),
        slow_client_outbox_wait_ms=_float(
            data,
            "slow_client_outbox_wait_ms",
            fallback.slow_client_outbox_wait_ms,
            minimum=1.0,
        ),
        slow_client_recovery_seconds=_float(
            data,
            "slow_client_recovery_seconds",
            fallback.slow_client_recovery_seconds,
            minimum=0.1,
        ),
        connection_burst_window_seconds=_float(
            data,
            "connection_burst_window_seconds",
            fallback.connection_burst_window_seconds,
            minimum=0.1,
        ),
        connection_burst_threshold=_int(
            data,
            "connection_burst_threshold",
            fallback.connection_burst_threshold,
            minimum=1,
        ),
        connection_burst_snapshot_rate=_int(
            data,
            "connection_burst_snapshot_rate",
            fallback.connection_burst_snapshot_rate,
            minimum=1,
        ),
        state_hash_sample_seconds=_float(
            data,
            "state_hash_sample_seconds",
            fallback.state_hash_sample_seconds,
            minimum=0.1,
        ),
        full_snapshot_interval_seconds=_float(
            data,
            "full_snapshot_interval_seconds",
            fallback.full_snapshot_interval_seconds,
            minimum=1.0,
        ),
        resume_timeout_seconds=_float(data, "resume_timeout_seconds", fallback.resume_timeout_seconds, minimum=5.0),
        journal_seconds=_float(data, "journal_seconds", fallback.journal_seconds, minimum=3.0),
        write_buffer_high_water=_int(data, "write_buffer_high_water", fallback.write_buffer_high_water, minimum=32_768),
        write_buffer_low_water=_int(data, "write_buffer_low_water", fallback.write_buffer_low_water, minimum=16_384),
    )


def _load_rate_limits(raw: Any) -> RateLimitTuning:
    data = raw if isinstance(raw, dict) else {}
    fallback = RateLimitTuning()
    return RateLimitTuning(
        input_per_second=_int(data, "input_per_second", fallback.input_per_second, minimum=1),
        command_per_second=_int(data, "command_per_second", fallback.command_per_second, minimum=1),
        inbound_bytes_per_second=_int(data, "inbound_bytes_per_second", fallback.inbound_bytes_per_second, minimum=4096),
    )


def _load_observability(raw: Any) -> ObservabilityTuning:
    data = raw if isinstance(raw, dict) else {}
    fallback = ObservabilityTuning()
    return ObservabilityTuning(
        enabled=bool(data.get("enabled", fallback.enabled)),
        host=str(data.get("host", fallback.host)),
        port=_int(data, "port", fallback.port, minimum=1),
    )


def _load_profiling(raw: Any) -> ProfilingTuning:
    data = raw if isinstance(raw, dict) else {}
    fallback = ProfilingTuning()
    return ProfilingTuning(
        log_interval_seconds=_float(data, "log_interval_seconds", fallback.log_interval_seconds, minimum=1.0),
        slow_tick_ms=_float(data, "slow_tick_ms", fallback.slow_tick_ms, minimum=0.0),
        slow_snapshot_ms=_float(data, "slow_snapshot_ms", fallback.slow_snapshot_ms, minimum=0.0),
    )


def _float(data: dict[str, Any], key: str, fallback: float, minimum: float) -> float:
    try:
        return max(minimum, float(data.get(key, fallback)))
    except (TypeError, ValueError):
        return fallback


def _int(data: dict[str, Any], key: str, fallback: int, minimum: int) -> int:
    try:
        return max(minimum, int(data.get(key, fallback)))
    except (TypeError, ValueError):
        return fallback
