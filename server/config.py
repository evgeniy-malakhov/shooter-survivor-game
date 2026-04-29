from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "server.json"


@dataclass(frozen=True, slots=True)
class NetworkTuning:
    interest_radius: float = 1800.0
    building_interest_radius: float = 2400.0
    grid_cell_size: float = 512.0
    output_queue_packets: int = 64
    full_snapshot_interval_seconds: float = 5.0
    resume_timeout_seconds: float = 30.0
    journal_seconds: float = 10.0
    write_buffer_high_water: int = 262_144
    write_buffer_low_water: int = 65_536


@dataclass(frozen=True, slots=True)
class ProfilingTuning:
    log_interval_seconds: float = 5.0
    slow_tick_ms: float = 12.0
    slow_snapshot_ms: float = 8.0


@dataclass(frozen=True, slots=True)
class ServerTuning:
    network: NetworkTuning = NetworkTuning()
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
        network=_load_network(raw.get("network", {})),
        profiling=_load_profiling(raw.get("profiling", {})),
    )


def _load_network(raw: Any) -> NetworkTuning:
    data = raw if isinstance(raw, dict) else {}
    fallback = NetworkTuning()
    return NetworkTuning(
        interest_radius=_float(data, "interest_radius", fallback.interest_radius, minimum=320.0),
        building_interest_radius=_float(data, "building_interest_radius", fallback.building_interest_radius, minimum=320.0),
        grid_cell_size=_float(data, "grid_cell_size", fallback.grid_cell_size, minimum=64.0),
        output_queue_packets=_int(data, "output_queue_packets", fallback.output_queue_packets, minimum=8),
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
