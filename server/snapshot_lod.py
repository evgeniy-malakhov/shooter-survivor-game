from __future__ import annotations

import math
from typing import Any

from shared.constants import SOLDIERS, ZOMBIES

SNAPSHOT_LOD_FEATURE = "snapshot_lod_v1"


def apply_snapshot_lod(
    snapshot: dict[str, Any],
    *,
    center_x: float,
    center_y: float,
    floor: int,
    near_radius: float,
    mid_radius: float,
    far_radius: float | None = None,
) -> dict[str, Any]:
    result = dict(snapshot)
    result["zombies"] = _lod_collection(
        _collection(snapshot, "zombies"),
        center_x=center_x,
        center_y=center_y,
        floor=floor,
        near_radius=near_radius,
        mid_radius=mid_radius,
        far_radius=far_radius,
        faction="zombie",
    )
    result["soldiers"] = _lod_collection(
        _collection(snapshot, "soldiers"),
        center_x=center_x,
        center_y=center_y,
        floor=floor,
        near_radius=near_radius,
        mid_radius=mid_radius,
        far_radius=far_radius,
        faction="soldier",
    )
    return result


def _lod_collection(
    source: dict[str, Any],
    *,
    center_x: float,
    center_y: float,
    floor: int,
    near_radius: float,
    mid_radius: float,
    far_radius: float | None,
    faction: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for entity_id, entity in source.items():
        if not isinstance(entity, dict):
            continue
        entity_floor = int(entity.get("floor", 0))
        if entity_floor != floor:
            continue
        pos = entity.get("pos") if isinstance(entity.get("pos"), dict) else {}
        distance = math.hypot(float(pos.get("x", 0.0)) - center_x, float(pos.get("y", 0.0)) - center_y)
        if far_radius is not None and distance > far_radius:
            continue
        if distance <= near_radius:
            result[entity_id] = entity
        elif distance <= mid_radius:
            result[entity_id] = _simple_actor(entity, faction)
        else:
            result[entity_id] = _dot_actor(entity, faction)
    return result


def _simple_actor(entity: dict[str, Any], faction: str) -> dict[str, Any]:
    health_max = _max_health(entity, faction)
    return {
        "_lod": "simple",
        "id": entity.get("id", ""),
        "kind": entity.get("kind", "rifleman" if faction == "soldier" else "walker"),
        "pos": entity.get("pos", {}),
        "hp_ratio": max(0.0, min(1.0, float(entity.get("health", 1)) / max(1.0, health_max))),
        "facing": entity.get("facing", 0.0),
        "floor": int(entity.get("floor", 0)),
        "faction": faction,
    }


def _dot_actor(entity: dict[str, Any], faction: str) -> dict[str, Any]:
    return {
        "_lod": "dot",
        "id": entity.get("id", ""),
        "kind": entity.get("kind", "rifleman" if faction == "soldier" else "walker"),
        "pos": entity.get("pos", {}),
        "floor": int(entity.get("floor", 0)),
        "faction": faction,
    }


def _max_health(entity: dict[str, Any], faction: str) -> float:
    kind = str(entity.get("kind", ""))
    if faction == "soldier":
        spec = SOLDIERS.get(kind)
        return float(spec.health if spec else 100)
    spec = ZOMBIES.get(kind)
    return float(spec.health if spec else 100)


def _collection(snapshot: dict[str, Any], key: str) -> dict[str, Any]:
    value = snapshot.get(key, {})
    return value if isinstance(value, dict) else {}
