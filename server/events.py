from __future__ import annotations

from typing import Any


MAX_EVENTS_PER_TICK = 96


def derive_events(previous: dict[str, Any] | None, current: dict[str, Any], tick: int) -> list[dict[str, Any]]:
    if not previous:
        return []
    events: list[dict[str, Any]] = []
    _append_new_projectiles(events, previous, current, tick)
    _append_removed_entities(events, previous, current, tick, "zombies", "zombie_killed")
    _append_removed_entities(events, previous, current, tick, "grenades", "grenade_exploded")
    _append_removed_entities(events, previous, current, tick, "mines", "mine_exploded")
    _append_removed_entities(events, previous, current, tick, "loot", "item_picked")
    _append_health_events(events, previous, current, tick)
    return events[:MAX_EVENTS_PER_TICK]


def filter_events_for_snapshot(
    events: list[dict[str, Any]],
    snapshot: dict[str, Any],
    player_id: str,
) -> list[dict[str, Any]]:
    visible_ids: set[str] = {player_id}
    for collection in (
        "players",
        "zombies",
        "projectiles",
        "grenades",
        "mines",
        "poison_projectiles",
        "poison_pools",
        "loot",
    ):
        visible_ids.update(_collection(snapshot, collection).keys())
    filtered: list[dict[str, Any]] = []
    for event in events:
        if event.get("owner_id") == player_id:
            filtered.append(event)
            continue
        ids = {
            str(event.get(key))
            for key in ("entity_id", "target_id", "source_id", "player_id", "projectile_id")
            if event.get(key) is not None
        }
        if ids & visible_ids:
            filtered.append(event)
    return filtered


def _append_new_projectiles(events: list[dict[str, Any]], previous: dict[str, Any], current: dict[str, Any], tick: int) -> None:
    old_projectiles = _collection(previous, "projectiles")
    for projectile_id, projectile in _collection(current, "projectiles").items():
        if projectile_id in old_projectiles or not isinstance(projectile, dict):
            continue
        pos = _pos(projectile)
        events.append(
            {
                "kind": "shot",
                "tick": tick,
                "projectile_id": projectile_id,
                "owner_id": projectile.get("owner_id", ""),
                "x": pos.get("x", 0.0),
                "y": pos.get("y", 0.0),
            }
        )


def _append_removed_entities(
    events: list[dict[str, Any]],
    previous: dict[str, Any],
    current: dict[str, Any],
    tick: int,
    collection: str,
    kind: str,
) -> None:
    current_items = _collection(current, collection)
    for entity_id, entity in _collection(previous, collection).items():
        if entity_id in current_items or not isinstance(entity, dict):
            continue
        pos = _pos(entity)
        event = {
            "kind": kind,
            "tick": tick,
            "entity_id": entity_id,
            "x": pos.get("x", 0.0),
            "y": pos.get("y", 0.0),
            "floor": entity.get("floor", 0),
        }
        if "owner_id" in entity:
            event["owner_id"] = entity.get("owner_id")
        if collection in {"zombies", "loot", "grenades", "mines"}:
            event["entity_kind"] = entity.get("kind", entity.get("payload", ""))
        events.append(event)


def _append_health_events(events: list[dict[str, Any]], previous: dict[str, Any], current: dict[str, Any], tick: int) -> None:
    for collection in ("players", "zombies"):
        for entity_id, current_entity in _collection(current, collection).items():
            previous_entity = _collection(previous, collection).get(entity_id)
            if not isinstance(previous_entity, dict) or not isinstance(current_entity, dict):
                continue
            old_hp = int(previous_entity.get("health", 0))
            new_hp = int(current_entity.get("health", old_hp))
            if new_hp < old_hp:
                events.append(
                    {
                        "kind": "hit",
                        "tick": tick,
                        "target_id": entity_id,
                        "target_type": collection[:-1],
                        "damage": old_hp - new_hp,
                    }
                )
            if previous_entity.get("alive", True) and not current_entity.get("alive", True):
                events.append({"kind": "player_died", "tick": tick, "player_id": entity_id})


def _collection(snapshot: dict[str, Any], key: str) -> dict[str, Any]:
    value = snapshot.get(key, {})
    return value if isinstance(value, dict) else {}


def _pos(entity: dict[str, Any]) -> dict[str, Any]:
    pos = entity.get("pos", {})
    return pos if isinstance(pos, dict) else {}
