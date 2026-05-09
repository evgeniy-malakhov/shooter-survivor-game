from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * pct)))
    return ordered[index]


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def streaks(values: list[float], threshold: float) -> tuple[int, int]:
    longest = 0
    current = 0
    count = 0
    for value in values:
        if value > threshold:
            current += 1
            count += 1
            longest = max(longest, current)
        else:
            current = 0
    return count, longest


def avg(rows: list[dict[str, Any]], key: str) -> float:
    values = [float(row.get(key, 0.0) or 0.0) for row in rows]
    return statistics.fmean(values) if values else 0.0


def analyze(path: Path) -> str:
    rows = load_rows(path)
    frames = [float(row.get("frame_ms", 0.0) or 0.0) for row in rows]
    over_count, over_longest = streaks(frames, 16.67)
    heavy_online = [row for row in rows if float(row.get("online_ms", 0.0) or 0.0) > 4.0]
    gc_spikes = [row for row in rows if float(row.get("gc_ms", row.get("gc_time_ms", 0.0)) or 0.0) > 1.0]
    quality_changes = 0
    previous_quality = None
    for row in rows:
        quality = (
            row.get("quality_profile"),
            row.get("quality_radius"),
            row.get("quality_lod"),
            row.get("quality_effects"),
        )
        if previous_quality is not None and quality != previous_quality:
            quality_changes += 1
        previous_quality = quality
    bottlenecks = {
        "world": avg(rows, "world_ms"),
        "actors": avg(rows, "actors_ms"),
        "minimap": avg(rows, "minimap_ms"),
        "online": avg(rows, "online_ms"),
    }
    top = sorted(bottlenecks.items(), key=lambda item: item[1], reverse=True)
    return "\n".join(
        [
            f"file: {path}",
            f"samples: {len(rows)}",
            f"frame avg/p95/p99/max: {avg(rows, 'frame_ms'):.2f}/{percentile(frames, 0.95):.2f}/{percentile(frames, 0.99):.2f}/{(max(frames) if frames else 0.0):.2f} ms",
            f"over-budget frames/streak: {over_count}/{over_longest}",
            "top bottlenecks: " + ", ".join(f"{name}={value:.2f}ms" for name, value in top),
            f"online spikes >4ms: {len(heavy_online)}",
            f"GC spikes >1ms: {len(gc_spikes)}",
            f"quality changes: {quality_changes}",
            f"payload avg snapshot/delta/events: {avg(rows, 'snapshot_bytes'):.0f}/{avg(rows, 'delta_bytes'):.0f}/{avg(rows, 'events_bytes'):.0f} bytes",
            f"LOD avg full/simple/dot: {avg(rows, 'actors_full'):.1f}/{avg(rows, 'actors_simple'):.1f}/{avg(rows, 'actors_dot'):.1f}",
            f"compression ratio avg: {avg(rows, 'compression_ratio'):.2f}",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Neon Outbreak client perf JSONL logs.")
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    for index, path in enumerate(args.paths):
        if index:
            print()
        print(analyze(path))


if __name__ == "__main__":
    main()
