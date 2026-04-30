from __future__ import annotations

import gc
import os
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque


@dataclass(slots=True)
class RollingSeries:
    maxlen: int = 2048
    values: Deque[float] = field(default_factory=deque)

    def observe(self, value: float) -> None:
        if len(self.values) >= self.maxlen:
            self.values.popleft()
        self.values.append(float(value))

    def summary(self) -> dict[str, float | int]:
        if not self.values:
            return {"count": 0, "avg": 0.0, "p95": 0.0, "p99": 0.0}
        ordered = sorted(self.values)
        return {
            "count": len(ordered),
            "avg": sum(ordered) / len(ordered),
            "p95": _percentile(ordered, 95.0),
            "p99": _percentile(ordered, 99.0),
        }


@dataclass(slots=True)
class ServerMetrics:
    started_at: float = field(default_factory=time.time)
    tick_ms: RollingSeries = field(default_factory=RollingSeries)
    snapshot_ms: RollingSeries = field(default_factory=RollingSeries)
    command_ack_ms: RollingSeries = field(default_factory=RollingSeries)
    commands_rejected_total: int = 0
    reconnect_total: int = 0
    dropped_snapshots_total: int = 0
    bytes_sent_total: int = 0
    bytes_received_total: int = 0
    desync_reports_total: int = 0
    desync_mismatch_total: int = 0
    desync_forced_full_total: int = 0
    rate_limited_inputs_total: int = 0
    rate_limited_commands_total: int = 0
    rate_limited_bytes_total: int = 0
    accepted_connections_total: int = 0

    def observe_tick(self, seconds: float) -> None:
        self.tick_ms.observe(seconds * 1000.0)

    def observe_snapshot(self, seconds: float) -> None:
        self.snapshot_ms.observe(seconds * 1000.0)

    def observe_command_ack(self, milliseconds: float | int | None) -> None:
        if milliseconds is not None:
            self.command_ack_ms.observe(float(milliseconds))

    def prometheus_text(self, runtime: dict[str, Any]) -> str:
        tick = self.tick_ms.summary()
        snapshot = self.snapshot_ms.summary()
        command_ack = self.command_ack_ms.summary()
        lines = [
            "# HELP neon_connected_players Active connected players.",
            "# TYPE neon_connected_players gauge",
            f"neon_connected_players {runtime['connected_players']}",
            "# HELP neon_tick_ms Server simulation tick duration in milliseconds.",
            "# TYPE neon_tick_ms summary",
            *_summary_lines("neon_tick_ms", tick),
            "# TYPE neon_tick_ms_avg gauge",
            f"neon_tick_ms_avg {float(tick['avg']):.6f}",
            "# TYPE neon_tick_ms_p95 gauge",
            f"neon_tick_ms_p95 {float(tick['p95']):.6f}",
            "# TYPE neon_tick_ms_p99 gauge",
            f"neon_tick_ms_p99 {float(tick['p99']):.6f}",
            "# HELP neon_snapshot_ms Snapshot build/filter/send loop duration in milliseconds.",
            "# TYPE neon_snapshot_ms summary",
            *_summary_lines("neon_snapshot_ms", snapshot),
            "# TYPE neon_snapshot_ms_avg gauge",
            f"neon_snapshot_ms_avg {float(snapshot['avg']):.6f}",
            "# TYPE neon_snapshot_ms_p95 gauge",
            f"neon_snapshot_ms_p95 {float(snapshot['p95']):.6f}",
            "# TYPE neon_snapshot_ms_p99 gauge",
            f"neon_snapshot_ms_p99 {float(snapshot['p99']):.6f}",
            "# HELP neon_command_ack_ms Server-side reliable command processing latency in milliseconds.",
            "# TYPE neon_command_ack_ms summary",
            *_summary_lines("neon_command_ack_ms", command_ack),
            "# TYPE neon_command_ack_ms_avg gauge",
            f"neon_command_ack_ms_avg {float(command_ack['avg']):.6f}",
            "# TYPE neon_command_ack_ms_p95 gauge",
            f"neon_command_ack_ms_p95 {float(command_ack['p95']):.6f}",
            "# TYPE neon_command_ack_ms_p99 gauge",
            f"neon_command_ack_ms_p99 {float(command_ack['p99']):.6f}",
            "# HELP neon_commands_rejected_total Rejected reliable commands.",
            "# TYPE neon_commands_rejected_total counter",
            f"neon_commands_rejected_total {self.commands_rejected_total}",
            "# HELP neon_reconnect_total Successful session resumes.",
            "# TYPE neon_reconnect_total counter",
            f"neon_reconnect_total {self.reconnect_total}",
            "# HELP neon_dropped_snapshots_total Snapshot packets dropped from slow client queues.",
            "# TYPE neon_dropped_snapshots_total counter",
            f"neon_dropped_snapshots_total {self.dropped_snapshots_total}",
            "# HELP neon_bytes_sent_total Bytes written by the game protocol.",
            "# TYPE neon_bytes_sent_total counter",
            f"neon_bytes_sent_total {self.bytes_sent_total}",
            "# HELP neon_bytes_received_total Bytes read by the game protocol.",
            "# TYPE neon_bytes_received_total counter",
            f"neon_bytes_received_total {self.bytes_received_total}",
            "# HELP neon_desync_reports_total Client state hash reports received.",
            "# TYPE neon_desync_reports_total counter",
            f"neon_desync_reports_total {self.desync_reports_total}",
            "# HELP neon_desync_mismatch_total Client/server snapshot hash mismatches.",
            "# TYPE neon_desync_mismatch_total counter",
            f"neon_desync_mismatch_total {self.desync_mismatch_total}",
            "# HELP neon_desync_forced_full_total Full snapshots forced after desync detection.",
            "# TYPE neon_desync_forced_full_total counter",
            f"neon_desync_forced_full_total {self.desync_forced_full_total}",
            "# HELP neon_rate_limited_inputs_total Input messages dropped by rate limit.",
            "# TYPE neon_rate_limited_inputs_total counter",
            f"neon_rate_limited_inputs_total {self.rate_limited_inputs_total}",
            "# HELP neon_rate_limited_commands_total Commands rejected by rate limit.",
            "# TYPE neon_rate_limited_commands_total counter",
            f"neon_rate_limited_commands_total {self.rate_limited_commands_total}",
            "# HELP neon_rate_limited_bytes_total Connections closed by inbound byte rate limit.",
            "# TYPE neon_rate_limited_bytes_total counter",
            f"neon_rate_limited_bytes_total {self.rate_limited_bytes_total}",
            "# HELP neon_resume_tickets Players waiting in reconnect window.",
            "# TYPE neon_resume_tickets gauge",
            f"neon_resume_tickets {runtime['resume_tickets']}",
            "# HELP neon_output_queue_packets Queued outbound packets across all clients.",
            "# TYPE neon_output_queue_packets gauge",
            f"neon_output_queue_packets {runtime['output_queue_packets']}",
            "# HELP neon_persistence_queue_size Pending persistence records.",
            "# TYPE neon_persistence_queue_size gauge",
            f"neon_persistence_queue_size {runtime['persistence_queue_size']}",
            "# HELP neon_process_uptime_seconds Server process uptime.",
            "# TYPE neon_process_uptime_seconds gauge",
            f"neon_process_uptime_seconds {time.time() - self.started_at:.3f}",
            "# HELP neon_process_cpu_seconds_total CPU time consumed by this Python process.",
            "# TYPE neon_process_cpu_seconds_total counter",
            f"neon_process_cpu_seconds_total {time.process_time():.6f}",
            "# HELP neon_python_threads Active Python threads.",
            "# TYPE neon_python_threads gauge",
            f"neon_python_threads {threading.active_count()}",
            "# HELP neon_python_gc_count Objects tracked by Python GC generations since last collection.",
            "# TYPE neon_python_gc_count gauge",
        ]
        for generation, count in enumerate(gc.get_count()):
            lines.append(f'neon_python_gc_count{{generation="{generation}"}} {count}')
        lines.extend(
            [
                "# HELP neon_asyncio_tasks Active asyncio tasks in the server loop.",
                "# TYPE neon_asyncio_tasks gauge",
                f"neon_asyncio_tasks {runtime['asyncio_tasks']}",
                "# HELP neon_python_allocated_blocks CPython allocated memory blocks if available.",
                "# TYPE neon_python_allocated_blocks gauge",
                f"neon_python_allocated_blocks {getattr(sys, 'getallocatedblocks', lambda: 0)()}",
                "# HELP neon_process_pid Operating system process id.",
                "# TYPE neon_process_pid gauge",
                f"neon_process_pid {os.getpid()}",
            ]
        )
        return "\n".join(lines) + "\n"


def _summary_lines(name: str, summary: dict[str, float | int]) -> list[str]:
    return [
        f'{name}{{quantile="avg"}} {float(summary["avg"]):.6f}',
        f'{name}{{quantile="p95"}} {float(summary["p95"]):.6f}',
        f'{name}{{quantile="p99"}} {float(summary["p99"]):.6f}',
        f"{name}_count {int(summary['count'])}",
    ]


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    rank = (len(values) - 1) * percentile / 100.0
    low = int(rank)
    high = min(len(values) - 1, low + 1)
    blend = rank - low
    return values[low] * (1.0 - blend) + values[high] * blend
