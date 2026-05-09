from __future__ import annotations

from typing import Any

from shared.ai.context import SoundEvent
from shared.models import Vec2

MAX_AI_MEMORY_RECORDS = 8
MEMORY_TTL_SECONDS = 16.0


def remember_sound(memory: list[dict[str, Any]], sound: SoundEvent, *, now: float, actor_pos: Vec2) -> None:
    danger = _sound_danger(sound, actor_pos)
    record = {
        "kind": "sound",
        "sound_kind": sound.kind,
        "pos": sound.pos.to_dict(),
        "floor": sound.floor,
        "time": round(now, 3),
        "danger": round(danger, 3),
    }
    memory[:] = [
        item
        for item in memory
        if now - float(item.get("time", now)) <= MEMORY_TTL_SECONDS
        and _distance_to(item, sound.pos) > 96.0
    ]
    memory.append(record)
    memory.sort(key=lambda item: (float(item.get("danger", 0.0)), float(item.get("time", 0.0))), reverse=True)
    del memory[MAX_AI_MEMORY_RECORDS:]


def most_dangerous_sound(memory: list[dict[str, Any]], *, now: float, floor: int) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_score = -1.0
    for item in memory:
        if item.get("kind") != "sound" or int(item.get("floor", floor)) != floor:
            continue
        age = max(0.0, now - float(item.get("time", now)))
        if age > MEMORY_TTL_SECONDS:
            continue
        score = float(item.get("danger", 0.0)) * max(0.0, 1.0 - age / MEMORY_TTL_SECONDS)
        if score > best_score:
            best = item
            best_score = score
    return best


def memory_pos(item: dict[str, Any]) -> Vec2 | None:
    raw = item.get("pos")
    if not isinstance(raw, dict):
        return None
    return Vec2.from_dict(raw)


def _sound_danger(sound: SoundEvent, actor_pos: Vec2) -> float:
    distance = actor_pos.distance_to(sound.pos)
    kind_bonus = {
        "shot": 0.55,
        "explosion": 0.9,
        "grenade": 0.75,
        "movement": 0.15,
    }.get(sound.kind, 0.25)
    radius_score = min(1.0, sound.radius / 1400.0)
    proximity = max(0.0, 1.0 - distance / max(1.0, sound.radius))
    return sound.intensity * 0.5 + kind_bonus + radius_score * 0.35 + proximity * 0.45


def _distance_to(item: dict[str, Any], pos: Vec2) -> float:
    item_pos = memory_pos(item)
    return item_pos.distance_to(pos) if item_pos else float("inf")
