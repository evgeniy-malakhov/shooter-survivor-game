from __future__ import annotations

import json
import time
from pathlib import Path

from client.core.perf import ClientPerfStats


class PerfLogRecorder:
    def __init__(self, root: Path, *, interval_seconds: float = 1.0) -> None:
        self.root = root
        self.interval_seconds = max(0.1, interval_seconds)
        self.enabled = False
        self._path: Path | None = None
        self._last_write_at = 0.0

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if not self.enabled:
            return
        logs_dir = self.root / "logs" / "perf"
        logs_dir.mkdir(parents=True, exist_ok=True)
        if self._path is None:
            stamp = time.strftime("%Y-%m-%d-%H%M%S")
            self._path = logs_dir / f"{stamp}-session.jsonl"

    @property
    def path(self) -> Path | None:
        return self._path

    def observe(self, stats: ClientPerfStats, *, state: str, fps: float, quality_profile: str, online: object | None = None) -> None:
        if not self.enabled:
            return
        now = time.time()
        if now - self._last_write_at < self.interval_seconds:
            return
        self._last_write_at = now
        self.set_enabled(True)
        if self._path is None:
            return
        row = {
            "time": now,
            "state": state,
            "fps": fps,
            "frame_ms": stats.frame_ms,
            "p95_ms": stats.frame_p95_ms,
            "p99_ms": stats.frame_p99_ms,
            "world_ms": stats.draw_world_ms,
            "actors_ms": stats.actors_ms,
            "minimap_ms": stats.minimap_ms,
            "online_ms": stats.render_prepare_ms,
            "visible_players": stats.visible_players,
            "visible_zombies": stats.visible_zombies,
            "visible_soldiers": stats.visible_soldiers,
            "visible_loot": stats.visible_loot,
            "quality_profile": quality_profile,
            "quality_radius": stats.quality_render_radius_multiplier,
            "quality_lod": stats.quality_actor_lod_bias,
            "quality_effects": stats.quality_effects_quality,
        }
        if online is not None:
            row.update(
                {
                    "snapshot_bytes": int(getattr(online, "snapshot_bytes", 0)),
                    "delta_bytes": int(getattr(online, "delta_bytes", 0)),
                    "events_bytes": int(getattr(online, "events_bytes", 0)),
                    "actors_full": int(getattr(online, "actors_full", 0)),
                    "actors_simple": int(getattr(online, "actors_simple", 0)),
                    "actors_dot": int(getattr(online, "actors_dot", 0)),
                    "compression_ratio": float(getattr(online, "compression_ratio", 1.0)),
                }
            )
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
