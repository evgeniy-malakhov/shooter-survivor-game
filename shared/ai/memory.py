from __future__ import annotations

from typing import Any

from shared.ai.context import SoundEvent
from shared.models import Vec2

MAX_AI_MEMORY_RECORDS = 12
MEMORY_TTL_SECONDS = 16.0
THREAT_MEMORY_TTL_SECONDS = 24.0


def remember_sound(memory: list[dict[str, Any]], sound: SoundEvent, *, now: float, actor_pos: Vec2) -> None:
    danger = _sound_danger(sound, actor_pos)
    remember_threat(
        memory,
        kind="last_heard_sound",
        pos=sound.pos,
        floor=sound.floor,
        now=now,
        danger=danger,
        sound_kind=sound.kind,
        source_actor_id=sound.source_player_id,
    )


def remember_threat(
    memory: list[dict[str, Any]],
    *,
    kind: str,
    pos: Vec2,
    floor: int,
    now: float,
    danger: float,
    actor_id: str | None = None,
    actor_kind: str | None = None,
    sound_kind: str | None = None,
    source_actor_id: str | None = None,
) -> None:
    record: dict[str, Any] = {
        "kind": kind,
        "pos": pos.to_dict(),
        "floor": floor,
        "time": round(now, 3),
        "danger": round(max(0.0, danger), 3),
    }
    if actor_id:
        record["actor_id"] = actor_id
    if actor_kind:
        record["actor_kind"] = actor_kind
    if sound_kind:
        record["sound_kind"] = sound_kind
    if source_actor_id:
        record["source_actor_id"] = source_actor_id

    memory[:] = [
        item
        for item in memory
        if now - float(item.get("time", now)) <= THREAT_MEMORY_TTL_SECONDS
        and not _same_memory_slot(item, kind=kind, pos=pos, actor_id=actor_id)
    ]
    memory.append(record)
    memory.sort(key=lambda item: (float(item.get("danger", 0.0)), float(item.get("time", 0.0))), reverse=True)
    del memory[MAX_AI_MEMORY_RECORDS:]


def remember_seen_enemy(
    memory: list[dict[str, Any]],
    *,
    actor_id: str,
    actor_kind: str,
    pos: Vec2,
    floor: int,
    now: float,
    danger: float,
) -> None:
    remember_threat(
        memory,
        kind="last_seen_enemy",
        actor_id=actor_id,
        actor_kind=actor_kind,
        pos=pos,
        floor=floor,
        now=now,
        danger=danger,
    )


def remember_damage_source(
    memory: list[dict[str, Any]],
    *,
    actor_id: str,
    actor_kind: str,
    pos: Vec2,
    floor: int,
    now: float,
    danger: float = 1.0,
) -> None:
    remember_threat(
        memory,
        kind="last_damage_source",
        actor_id=actor_id,
        actor_kind=actor_kind,
        pos=pos,
        floor=floor,
        now=now,
        danger=danger,
    )


def remember_dead_ally(memory: list[dict[str, Any]], *, pos: Vec2, floor: int, now: float) -> None:
    remember_threat(memory, kind="last_dead_ally_position", pos=pos, floor=floor, now=now, danger=0.8)


def remember_grenade(memory: list[dict[str, Any]], *, pos: Vec2, floor: int, now: float) -> None:
    remember_threat(memory, kind="last_grenade_position", pos=pos, floor=floor, now=now, danger=1.15)


def remember_safe_position(memory: list[dict[str, Any]], *, pos: Vec2, floor: int, now: float) -> None:
    remember_threat(memory, kind="known_safe_position", pos=pos, floor=floor, now=now, danger=0.15)


def remember_danger_position(memory: list[dict[str, Any]], *, pos: Vec2, floor: int, now: float) -> None:
    remember_threat(memory, kind="known_danger_position", pos=pos, floor=floor, now=now, danger=0.75)


def merge_threat_memory(
    target: list[dict[str, Any]],
    source: list[dict[str, Any]],
    *,
    now: float,
    max_records: int = MAX_AI_MEMORY_RECORDS,
) -> None:
    for item in source:
        if now - float(item.get("time", now)) > THREAT_MEMORY_TTL_SECONDS:
            continue
        pos = memory_pos(item)
        if not pos:
            continue
        duplicate = any(_same_memory_slot(existing, kind=str(item.get("kind", "")), pos=pos, actor_id=_actor_id(item)) for existing in target)
        if duplicate:
            continue
        target.append(dict(item))

    target.sort(key=lambda item: (float(item.get("danger", 0.0)), float(item.get("time", 0.0))), reverse=True)
    del target[max_records:]


def most_relevant_threat(
    memory: list[dict[str, Any]],
    *,
    now: float,
    floor: int,
    kinds: set[str] | None = None,
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_score = -1.0
    for item in memory:
        kind = str(item.get("kind", ""))
        if kinds is not None and kind not in kinds:
            continue
        if int(item.get("floor", floor)) != floor:
            continue
        age = max(0.0, now - float(item.get("time", now)))
        if age > THREAT_MEMORY_TTL_SECONDS:
            continue
        score = float(item.get("danger", 0.0)) * max(0.0, 1.0 - age / THREAT_MEMORY_TTL_SECONDS)
        if score > best_score:
            best = item
            best_score = score
    return best


def prune_memory(memory: list[dict[str, Any]], *, now: float, max_age: float = THREAT_MEMORY_TTL_SECONDS) -> None:
    memory[:] = [item for item in memory if now - float(item.get("time", now)) <= max_age]


def legacy_sound_record(sound: SoundEvent, *, now: float, actor_pos: Vec2) -> dict[str, Any]:
    danger = _sound_danger(sound, actor_pos)
    return {
        "kind": "last_heard_sound",
        "sound_kind": sound.kind,
        "pos": sound.pos.to_dict(),
        "floor": sound.floor,
        "time": round(now, 3),
        "danger": round(danger, 3),
    }


def most_dangerous_sound(memory: list[dict[str, Any]], *, now: float, floor: int) -> dict[str, Any] | None:
    return most_relevant_threat(memory, now=now, floor=floor, kinds={"sound", "last_heard_sound"})


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


def _actor_id(item: dict[str, Any]) -> str | None:
    raw = item.get("actor_id") or item.get("source_actor_id")
    return str(raw) if raw else None


def _same_memory_slot(item: dict[str, Any], *, kind: str, pos: Vec2, actor_id: str | None) -> bool:
    if str(item.get("kind", "")) != kind:
        return False
    if actor_id and _actor_id(item) == actor_id:
        return True
    return _distance_to(item, pos) <= 96.0
