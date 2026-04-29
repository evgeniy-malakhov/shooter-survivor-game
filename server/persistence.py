from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parents[1] / "server_data"
_STOP = object()


@dataclass(slots=True)
class PersistenceRecord:
    kind: str
    payload: dict[str, Any]


class PersistenceWorker:
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.data_dir = data_dir
        self._queue: asyncio.Queue[PersistenceRecord | object] = asyncio.Queue(maxsize=2048)
        self._task: asyncio.Task[None] | None = None
        self._profiles: dict[str, dict[str, Any]] = {}
        self._dirty_profiles = False

    async def start(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self._task:
            self._task = asyncio.create_task(self._run(), name="persistence-worker")

    async def stop(self) -> None:
        if not self._task:
            return
        await self._queue.put(_STOP)
        await self._task
        self._task = None
        await self._flush_profiles()

    def record_session(self, event: str, **payload: Any) -> None:
        self._put("session", {"event": event, **payload})

    def record_match_event(self, event: str, **payload: Any) -> None:
        self._put("match_event", {"event": event, **payload})

    def save_player_profile(self, player_id: str, profile: dict[str, Any]) -> None:
        self._put("player_profile", {"player_id": player_id, "profile": profile})

    def _put(self, kind: str, payload: dict[str, Any]) -> None:
        payload = {"saved_at": time.time(), **payload}
        try:
            self._queue.put_nowait(PersistenceRecord(kind, payload))
        except asyncio.QueueFull:
            pass

    async def _run(self) -> None:
        last_profile_flush = time.monotonic()
        while True:
            try:
                record = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                if self._dirty_profiles:
                    await self._flush_profiles()
                continue
            if record is _STOP:
                break
            if not isinstance(record, PersistenceRecord):
                continue
            await self._handle(record)
            if self._dirty_profiles and time.monotonic() - last_profile_flush > 2.0:
                await self._flush_profiles()
                last_profile_flush = time.monotonic()
        await self._flush_profiles()

    async def _handle(self, record: PersistenceRecord) -> None:
        if record.kind == "player_profile":
            player_id = str(record.payload.get("player_id", ""))
            profile = record.payload.get("profile")
            if player_id and isinstance(profile, dict):
                self._profiles[player_id] = {
                    "saved_at": record.payload.get("saved_at"),
                    **profile,
                }
                self._dirty_profiles = True
            return
        filename = "session_history.jsonl" if record.kind == "session" else "match_events.jsonl"
        await asyncio.to_thread(self._append_jsonl, self.data_dir / filename, record.payload)

    def _append_jsonl(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")

    async def _flush_profiles(self) -> None:
        if not self._dirty_profiles:
            return
        payload = json.dumps(self._profiles, ensure_ascii=False, indent=2)
        path = self.data_dir / "player_profiles.json"
        tmp = self.data_dir / "player_profiles.tmp"
        await asyncio.to_thread(self._write_atomic, tmp, path, payload)
        self._dirty_profiles = False

    def _write_atomic(self, tmp: Path, path: Path, payload: str) -> None:
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)
