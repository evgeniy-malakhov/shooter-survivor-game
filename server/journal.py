from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque


@dataclass(slots=True)
class JournalEntry:
    created_at: float
    tick: int
    payload: dict[str, Any]


class ServerJournal:
    def __init__(self, retention_seconds: float = 10.0, max_entries: int = 2048) -> None:
        self.retention_seconds = retention_seconds
        self.max_entries = max_entries
        self.command_results: Deque[JournalEntry] = deque()
        self.domain_events: Deque[JournalEntry] = deque()
        self.snapshot_meta: Deque[JournalEntry] = deque()

    def append_command_result(self, result: dict[str, Any]) -> None:
        self._append(self.command_results, int(result.get("server_tick", 0)), result)

    def append_event(self, event: dict[str, Any], tick: int) -> None:
        self._append(self.domain_events, tick, event)

    def append_snapshot_meta(self, tick: int, payload: dict[str, Any]) -> None:
        self._append(self.snapshot_meta, tick, payload)

    def replay_for_player(self, player_id: str, since_tick: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        self._trim()
        results = [
            dict(entry.payload)
            for entry in self.command_results
            if entry.tick >= since_tick and entry.payload.get("player_id") == player_id
        ]
        events = [
            dict(entry.payload)
            for entry in self.domain_events
            if entry.tick >= since_tick and _event_matches_player(entry.payload, player_id)
        ]
        return results, events

    def _append(self, target: Deque[JournalEntry], tick: int, payload: dict[str, Any]) -> None:
        target.append(JournalEntry(time.monotonic(), tick, dict(payload)))
        self._trim()

    def _trim(self) -> None:
        cutoff = time.monotonic() - self.retention_seconds
        for target in (self.command_results, self.domain_events, self.snapshot_meta):
            while target and (target[0].created_at < cutoff or len(target) > self.max_entries):
                target.popleft()


def _event_matches_player(event: dict[str, Any], player_id: str) -> bool:
    if event.get("player_id") == player_id or event.get("owner_id") == player_id:
        return True
    return player_id in {
        str(event.get("entity_id", "")),
        str(event.get("target_id", "")),
        str(event.get("source_id", "")),
    }
