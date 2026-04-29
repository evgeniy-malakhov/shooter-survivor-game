from __future__ import annotations

import math
from copy import deepcopy
from typing import Any


def interpolate_snapshot(a: dict[str, Any], b: dict[str, Any], alpha: float, local_player_id: str | None) -> dict[str, Any]:
    alpha = max(0.0, min(1.0, alpha))
    result = deepcopy(a)
    result["time"] = _lerp(float(a.get("time", 0.0)), float(b.get("time", a.get("time", 0.0))), alpha)
    for collection in ("players", "zombies", "projectiles", "grenades", "mines", "poison_projectiles", "poison_pools"):
        _interpolate_collection(result, a, b, collection, alpha, local_player_id)
    return result


def _interpolate_collection(
    result: dict[str, Any],
    a: dict[str, Any],
    b: dict[str, Any],
    collection: str,
    alpha: float,
    local_player_id: str | None,
) -> None:
    result_items = result.setdefault(collection, {})
    if not isinstance(result_items, dict):
        return
    a_items = _collection(a, collection)
    b_items = _collection(b, collection)
    for entity_id, start in a_items.items():
        if collection == "players" and entity_id == local_player_id:
            continue
        end = b_items.get(entity_id)
        if not isinstance(start, dict) or not isinstance(end, dict):
            continue
        entity = deepcopy(start)
        if "pos" in start and "pos" in end:
            entity["pos"] = {
                "x": _lerp_pos(start, end, "x", alpha),
                "y": _lerp_pos(start, end, "y", alpha),
            }
        if "angle" in start and "angle" in end:
            entity["angle"] = _lerp_angle(float(start.get("angle", 0.0)), float(end.get("angle", 0.0)), alpha)
        if "facing" in start and "facing" in end:
            entity["facing"] = _lerp_angle(float(start.get("facing", 0.0)), float(end.get("facing", 0.0)), alpha)
        if "rotation" in start and "rotation" in end:
            entity["rotation"] = _lerp_angle(float(start.get("rotation", 0.0)), float(end.get("rotation", 0.0)), alpha)
        result_items[entity_id] = entity


def _collection(snapshot: dict[str, Any], key: str) -> dict[str, Any]:
    value = snapshot.get(key, {})
    return value if isinstance(value, dict) else {}


def _lerp_pos(start: dict[str, Any], end: dict[str, Any], key: str, alpha: float) -> float:
    start_pos = start.get("pos", {}) if isinstance(start.get("pos"), dict) else {}
    end_pos = end.get("pos", {}) if isinstance(end.get("pos"), dict) else {}
    return _lerp(float(start_pos.get(key, 0.0)), float(end_pos.get(key, 0.0)), alpha)


def _lerp(start: float, end: float, alpha: float) -> float:
    return start + (end - start) * alpha


def _lerp_angle(start: float, end: float, alpha: float) -> float:
    delta = (end - start + math.pi) % math.tau - math.pi
    return start + delta * alpha
