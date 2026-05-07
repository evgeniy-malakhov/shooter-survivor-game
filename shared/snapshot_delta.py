from __future__ import annotations

from typing import Any


ENTITY_COLLECTIONS = (
    "players",
    "zombies",
    "projectiles",
    "grenades",
    "mines",
    "poison_projectiles",
    "poison_pools",
    "loot",
    "buildings",
)
SCALAR_KEYS = ("time", "map_width", "map_height")


def make_snapshot_delta(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    delta: dict[str, Any] = {key: current[key] for key in SCALAR_KEYS if key in current}
    for collection in ENTITY_COLLECTIONS:
        current_items = _collection(current, collection)
        previous_items = _collection(previous, collection)
        upserts = {
            entity_id: entity
            for entity_id, entity in current_items.items()
            if previous_items.get(entity_id) != entity
        }
        removals = [entity_id for entity_id in previous_items if entity_id not in current_items]
        if upserts or removals:
            delta[collection] = {"u": upserts, "r": removals}
    return delta


def apply_snapshot_delta(base: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key in SCALAR_KEYS:
        if key in delta:
            merged[key] = delta[key]
    for collection in ENTITY_COLLECTIONS:
        patch = delta.get(collection)
        if not isinstance(patch, dict):
            continue
        target = dict(_collection(base, collection))
        merged[collection] = target
        for entity_id in patch.get("r", []):
            target.pop(str(entity_id), None)
        for entity_id, entity in patch.get("u", {}).items():
            key = str(entity_id)
            if isinstance(entity, dict) and isinstance(target.get(key), dict):
                target[key] = _merge_entity(target[key], entity)
            else:
                target[key] = entity
    return merged


def _collection(snapshot: dict[str, Any], key: str) -> dict[str, Any]:
    value = snapshot.get(key, {})
    return value if isinstance(value, dict) else {}


def _merge_entity(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current)
    for key, value in patch.items():
        if key == "weapons" and isinstance(value, dict) and isinstance(merged.get(key), dict):
            weapons = dict(merged[key])
            weapons.update(value)
            merged[key] = weapons
        else:
            merged[key] = value
    return merged
