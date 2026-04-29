from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque


class AsyncLogWorker:
    def __init__(self, max_queue: int = 1024) -> None:
        self._queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=max_queue)
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if not self._task:
            self._task = asyncio.create_task(self._run(), name="server-log-worker")

    async def stop(self) -> None:
        if not self._task:
            return
        await self._queue.put(None)
        await self._task
        self._task = None

    def info(self, message: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {message}"
        try:
            self._queue.put_nowait(line)
        except asyncio.QueueFull:
            pass

    async def _run(self) -> None:
        while True:
            line = await self._queue.get()
            if line is None:
                break
            print(line)


@dataclass(slots=True)
class ServerProfiler:
    enabled: bool = False
    max_samples: int = 180
    samples: dict[str, Deque[float]] = field(default_factory=lambda: defaultdict(deque))

    def record(self, key: str, seconds: float) -> None:
        if not self.enabled:
            return
        bucket = self.samples[key]
        bucket.append(seconds)
        while len(bucket) > self.max_samples:
            bucket.popleft()

    def summary(self) -> str:
        parts: list[str] = []
        for key in sorted(self.samples):
            bucket = self.samples[key]
            if not bucket:
                continue
            values = sorted(bucket)
            avg = sum(values) / len(values)
            p95 = values[min(len(values) - 1, int(len(values) * 0.95))]
            parts.append(f"{key}: avg={avg * 1000:.2f}ms p95={p95 * 1000:.2f}ms")
        return " | ".join(parts)
