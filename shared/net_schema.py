from __future__ import annotations

from typing import Any


SNAPSHOT_SCHEMA = "compact-v1"

_COLLECTION_TO_WIRE = {
    "players": "p",
    "zombies": "z",
    "projectiles": "s",
    "grenades": "g",
    "mines": "m",
    "poison_projectiles": "pp",
    "poison_pools": "pl",
    "loot": "l",
    "buildings": "b",
}
_WIRE_TO_COLLECTION = {wire: collection for collection, wire in _COLLECTION_TO_WIRE.items()}


def compact_snapshot(snapshot: dict[str, Any], local_player_id: str | None) -> dict[str, Any]:
    players = _collection(snapshot, "players")
    local_player = players.get(local_player_id or "")
    compact: dict[str, Any] = {
        "v": 1,
        "t": snapshot.get("time", 0.0),
        "mw": snapshot.get("map_width", 1),
        "mh": snapshot.get("map_height", 1),
        "p": [_pack_player(entity) for entity_id, entity in players.items() if entity_id != local_player_id],
        "z": [_pack_zombie(entity) for entity in _collection(snapshot, "zombies").values()],
        "s": [_pack_projectile(entity) for entity in _collection(snapshot, "projectiles").values()],
        "g": [_pack_grenade(entity) for entity in _collection(snapshot, "grenades").values()],
        "m": [_pack_mine(entity) for entity in _collection(snapshot, "mines").values()],
        "pp": [_pack_poison_projectile(entity) for entity in _collection(snapshot, "poison_projectiles").values()],
        "pl": [_pack_poison_pool(entity) for entity in _collection(snapshot, "poison_pools").values()],
        "l": [_pack_loot(entity) for entity in _collection(snapshot, "loot").values()],
        "b": _collection(snapshot, "buildings"),
    }
    if isinstance(local_player, dict):
        compact["lp"] = local_player
    return compact


def expand_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("v") != 1:
        return payload
    players = {}
    local_player = payload.get("lp")
    if isinstance(local_player, dict) and "id" in local_player:
        players[str(local_player["id"])] = local_player
    for row in payload.get("p", []):
        player = _unpack_player(row)
        players[player["id"]] = player
    return {
        "time": float(payload.get("t", 0.0)),
        "map_width": int(payload.get("mw", 1)),
        "map_height": int(payload.get("mh", 1)),
        "players": players,
        "zombies": _unpack_rows(payload.get("z", []), _unpack_zombie),
        "projectiles": _unpack_rows(payload.get("s", []), _unpack_projectile),
        "grenades": _unpack_rows(payload.get("g", []), _unpack_grenade),
        "mines": _unpack_rows(payload.get("m", []), _unpack_mine),
        "poison_projectiles": _unpack_rows(payload.get("pp", []), _unpack_poison_projectile),
        "poison_pools": _unpack_rows(payload.get("pl", []), _unpack_poison_pool),
        "loot": _unpack_rows(payload.get("l", []), _unpack_loot),
        "buildings": _collection(payload, "b"),
    }


def compact_delta(delta: dict[str, Any], local_player_id: str | None) -> dict[str, Any]:
    compact: dict[str, Any] = {"v": 1}
    if "time" in delta:
        compact["t"] = delta["time"]
    if "map_width" in delta:
        compact["mw"] = delta["map_width"]
    if "map_height" in delta:
        compact["mh"] = delta["map_height"]
    for collection, wire_key in _COLLECTION_TO_WIRE.items():
        patch = delta.get(collection)
        if not isinstance(patch, dict):
            continue
        upserts = _collection(patch, "u")
        removals = list(patch.get("r", []))
        if collection == "players":
            full_players = {
                entity_id: entity
                for entity_id, entity in upserts.items()
                if entity_id == local_player_id or _is_full_player(entity)
            }
            rows = [_pack_player(entity) for entity_id, entity in upserts.items() if entity_id not in full_players]
            compact_patch: dict[str, Any] = {"u": rows, "r": removals}
            if full_players:
                compact_patch["f"] = full_players
        elif collection == "buildings":
            compact_patch = {"u": upserts, "r": removals}
        else:
            compact_patch = {"u": [_pack_entity(collection, entity) for entity in upserts.values()], "r": removals}
        if compact_patch.get("u") or compact_patch.get("f") or compact_patch.get("r"):
            compact[wire_key] = compact_patch
    return compact


def expand_delta(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("v") != 1:
        return payload
    delta: dict[str, Any] = {}
    if "t" in payload:
        delta["time"] = payload["t"]
    if "mw" in payload:
        delta["map_width"] = payload["mw"]
    if "mh" in payload:
        delta["map_height"] = payload["mh"]
    for wire_key, collection in _WIRE_TO_COLLECTION.items():
        patch = payload.get(wire_key)
        if not isinstance(patch, dict):
            continue
        upserts: dict[str, Any] = {}
        if collection == "players":
            for row in patch.get("u", []):
                entity = _unpack_player(row)
                upserts[entity["id"]] = entity
            for entity_id, entity in _collection(patch, "f").items():
                upserts[entity_id] = entity
        elif collection == "buildings":
            upserts.update(_collection(patch, "u"))
        else:
            for row in patch.get("u", []):
                entity = _unpack_entity(collection, row)
                upserts[entity["id"]] = entity
        delta[collection] = {"u": upserts, "r": list(patch.get("r", []))}
    return delta


def _pack_entity(collection: str, entity: dict[str, Any]) -> list[Any]:
    if collection == "zombies":
        return _pack_zombie(entity)
    if collection == "projectiles":
        return _pack_projectile(entity)
    if collection == "grenades":
        return _pack_grenade(entity)
    if collection == "mines":
        return _pack_mine(entity)
    if collection == "poison_projectiles":
        return _pack_poison_projectile(entity)
    if collection == "poison_pools":
        return _pack_poison_pool(entity)
    if collection == "loot":
        return _pack_loot(entity)
    return [entity.get("id", "")]


def _unpack_entity(collection: str, row: list[Any]) -> dict[str, Any]:
    if collection == "zombies":
        return _unpack_zombie(row)
    if collection == "projectiles":
        return _unpack_projectile(row)
    if collection == "grenades":
        return _unpack_grenade(row)
    if collection == "mines":
        return _unpack_mine(row)
    if collection == "poison_projectiles":
        return _unpack_poison_projectile(row)
    if collection == "poison_pools":
        return _unpack_poison_pool(row)
    if collection == "loot":
        return _unpack_loot(row)
    return {"id": str(row[0]) if row else ""}


def _pack_player(entity: dict[str, Any]) -> list[Any]:
    pos = _pos(entity)
    return [
        entity.get("id", ""),
        entity.get("name", "Player"),
        _q(pos.get("x")),
        _q(pos.get("y")),
        _q(entity.get("angle"), 1000),
        int(entity.get("health", 100)),
        int(entity.get("armor", 0)),
        entity.get("armor_key", "none"),
        entity.get("active_slot", "1"),
        1 if entity.get("alive", True) else 0,
        int(entity.get("score", 0)),
        entity.get("kills_by_kind", {}),
        _q(entity.get("noise"), 10),
        1 if entity.get("sprinting", False) else 0,
        int(entity.get("floor", 0)),
        entity.get("inside_building"),
        1 if entity.get("sneaking", False) else 0,
        _q(entity.get("poison_left"), 1000),
        _active_weapon_payload(entity),
        int(entity.get("ping_ms", 0)),
        entity.get("connection_quality", "stable"),
    ]


def _unpack_player(row: list[Any]) -> dict[str, Any]:
    active_slot = str(_get(row, 8, "1"))
    weapon = _get(row, 18, None)
    weapons = {active_slot: weapon} if isinstance(weapon, dict) else {}
    return {
        "id": str(_get(row, 0, "")),
        "name": str(_get(row, 1, "Player")),
        "pos": {"x": _uq(_get(row, 2, 0)), "y": _uq(_get(row, 3, 0))},
        "angle": _uq(_get(row, 4, 0), 1000),
        "health": int(_get(row, 5, 100)),
        "armor": int(_get(row, 6, 0)),
        "armor_key": str(_get(row, 7, "none")),
        "active_slot": active_slot,
        "alive": bool(_get(row, 9, 1)),
        "score": int(_get(row, 10, 0)),
        "kills_by_kind": _get(row, 11, {}),
        "noise": _uq(_get(row, 12, 0), 10),
        "sprinting": bool(_get(row, 13, 0)),
        "floor": int(_get(row, 14, 0)),
        "inside_building": _get(row, 15, None),
        "sneaking": bool(_get(row, 16, 0)),
        "poison_left": _uq(_get(row, 17, 0), 1000),
        "weapons": weapons,
        "ping_ms": int(_get(row, 19, 0)),
        "connection_quality": str(_get(row, 20, "stable")),
    }


def _pack_zombie(entity: dict[str, Any]) -> list[Any]:
    pos = _pos(entity)
    return [
        entity.get("id", ""),
        entity.get("kind", "walker"),
        _q(pos.get("x")),
        _q(pos.get("y")),
        int(entity.get("health", 1)),
        int(entity.get("armor", 0)),
        entity.get("mode", "patrol"),
        _q(entity.get("facing"), 1000),
        int(entity.get("floor", 0)),
        entity.get("target_player_id"),
        _q(entity.get("alertness"), 1000),
    ]


def _unpack_zombie(row: list[Any]) -> dict[str, Any]:
    return {
        "id": str(_get(row, 0, "")),
        "kind": str(_get(row, 1, "walker")),
        "pos": {"x": _uq(_get(row, 2, 0)), "y": _uq(_get(row, 3, 0))},
        "health": int(_get(row, 4, 1)),
        "armor": int(_get(row, 5, 0)),
        "mode": str(_get(row, 6, "patrol")),
        "facing": _uq(_get(row, 7, 0), 1000),
        "floor": int(_get(row, 8, 0)),
        "target_player_id": _get(row, 9, None),
        "alertness": _uq(_get(row, 10, 0), 1000),
    }


def _pack_projectile(entity: dict[str, Any]) -> list[Any]:
    pos = _pos(entity)
    vel = _velocity(entity)
    return [
        entity.get("id", ""),
        entity.get("owner_id", ""),
        _q(pos.get("x")),
        _q(pos.get("y")),
        _q(vel.get("x")),
        _q(vel.get("y")),
        int(entity.get("damage", 1)),
        _q(entity.get("life"), 1000),
        _q(entity.get("radius", 5.0)),
        int(entity.get("floor", 0)),
    ]


def _unpack_projectile(row: list[Any]) -> dict[str, Any]:
    return {
        "id": str(_get(row, 0, "")),
        "owner_id": str(_get(row, 1, "")),
        "pos": {"x": _uq(_get(row, 2, 0)), "y": _uq(_get(row, 3, 0))},
        "velocity": {"x": _uq(_get(row, 4, 0)), "y": _uq(_get(row, 5, 0))},
        "damage": int(_get(row, 6, 1)),
        "life": _uq(_get(row, 7, 0), 1000),
        "radius": _uq(_get(row, 8, 50)),
        "floor": int(_get(row, 9, 0)),
    }


def _pack_grenade(entity: dict[str, Any]) -> list[Any]:
    row = _pack_projectile({**entity, "damage": 0, "life": entity.get("timer", 0.0)})
    row.extend([entity.get("kind", "grenade")])
    return row


def _unpack_grenade(row: list[Any]) -> dict[str, Any]:
    projectile = _unpack_projectile(row)
    return {
        "id": projectile["id"],
        "owner_id": projectile["owner_id"],
        "pos": projectile["pos"],
        "velocity": projectile["velocity"],
        "timer": projectile["life"],
        "floor": projectile["floor"],
        "radius": projectile["radius"],
        "kind": str(_get(row, 10, "grenade")),
    }


def _pack_mine(entity: dict[str, Any]) -> list[Any]:
    pos = _pos(entity)
    return [
        entity.get("id", ""),
        entity.get("owner_id", ""),
        entity.get("kind", "mine_standard"),
        _q(pos.get("x")),
        _q(pos.get("y")),
        int(entity.get("floor", 0)),
        1 if entity.get("armed", False) else 0,
        _q(entity.get("trigger_radius", 100.0)),
        _q(entity.get("blast_radius", 220.0)),
        _q(entity.get("rotation", 0.0), 1000),
    ]


def _unpack_mine(row: list[Any]) -> dict[str, Any]:
    return {
        "id": str(_get(row, 0, "")),
        "owner_id": str(_get(row, 1, "")),
        "kind": str(_get(row, 2, "mine_standard")),
        "pos": {"x": _uq(_get(row, 3, 0)), "y": _uq(_get(row, 4, 0))},
        "floor": int(_get(row, 5, 0)),
        "armed": bool(_get(row, 6, 0)),
        "trigger_radius": _uq(_get(row, 7, 1000)),
        "blast_radius": _uq(_get(row, 8, 2200)),
        "rotation": _uq(_get(row, 9, 0), 1000),
    }


def _pack_poison_projectile(entity: dict[str, Any]) -> list[Any]:
    pos = _pos(entity)
    vel = _velocity(entity)
    target = entity.get("target", {}) if isinstance(entity.get("target"), dict) else {}
    return [
        entity.get("id", ""),
        entity.get("owner_id", ""),
        _q(pos.get("x")),
        _q(pos.get("y")),
        _q(vel.get("x")),
        _q(vel.get("y")),
        _q(target.get("x")),
        _q(target.get("y")),
        int(entity.get("floor", 0)),
        _q(entity.get("radius", 9.0)),
        _q(entity.get("life", 2.4), 1000),
    ]


def _unpack_poison_projectile(row: list[Any]) -> dict[str, Any]:
    return {
        "id": str(_get(row, 0, "")),
        "owner_id": str(_get(row, 1, "")),
        "pos": {"x": _uq(_get(row, 2, 0)), "y": _uq(_get(row, 3, 0))},
        "velocity": {"x": _uq(_get(row, 4, 0)), "y": _uq(_get(row, 5, 0))},
        "target": {"x": _uq(_get(row, 6, 0)), "y": _uq(_get(row, 7, 0))},
        "floor": int(_get(row, 8, 0)),
        "radius": _uq(_get(row, 9, 90)),
        "life": _uq(_get(row, 10, 2400), 1000),
    }


def _pack_poison_pool(entity: dict[str, Any]) -> list[Any]:
    pos = _pos(entity)
    return [
        entity.get("id", ""),
        _q(pos.get("x")),
        _q(pos.get("y")),
        int(entity.get("floor", 0)),
        _q(entity.get("timer", 5.0), 1000),
        _q(entity.get("radius", 54.0)),
    ]


def _unpack_poison_pool(row: list[Any]) -> dict[str, Any]:
    return {
        "id": str(_get(row, 0, "")),
        "pos": {"x": _uq(_get(row, 1, 0)), "y": _uq(_get(row, 2, 0))},
        "floor": int(_get(row, 3, 0)),
        "timer": _uq(_get(row, 4, 5000), 1000),
        "radius": _uq(_get(row, 5, 540)),
    }


def _pack_loot(entity: dict[str, Any]) -> list[Any]:
    pos = _pos(entity)
    return [
        entity.get("id", ""),
        entity.get("kind", "item"),
        _q(pos.get("x")),
        _q(pos.get("y")),
        entity.get("payload", ""),
        int(entity.get("amount", 1)),
        int(entity.get("floor", 0)),
        entity.get("rarity", "common"),
    ]


def _unpack_loot(row: list[Any]) -> dict[str, Any]:
    return {
        "id": str(_get(row, 0, "")),
        "kind": str(_get(row, 1, "item")),
        "pos": {"x": _uq(_get(row, 2, 0)), "y": _uq(_get(row, 3, 0))},
        "payload": str(_get(row, 4, "")),
        "amount": int(_get(row, 5, 1)),
        "floor": int(_get(row, 6, 0)),
        "rarity": str(_get(row, 7, "common")),
    }


def _unpack_rows(rows: Any, unpacker: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for row in rows if isinstance(rows, list) else []:
        entity = unpacker(row)
        result[entity["id"]] = entity
    return result


def _active_weapon_payload(entity: dict[str, Any]) -> dict[str, Any] | None:
    active_slot = str(entity.get("active_slot", "1"))
    weapons = entity.get("weapons")
    if not isinstance(weapons, dict):
        return None
    weapon = weapons.get(active_slot)
    return weapon if isinstance(weapon, dict) else None


def _is_full_player(entity: dict[str, Any]) -> bool:
    return any(key in entity for key in ("backpack", "equipment", "quick_items", "owned_armors", "medkits"))


def _collection(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    return value if isinstance(value, dict) else {}


def _pos(entity: dict[str, Any]) -> dict[str, Any]:
    pos = entity.get("pos", {})
    return pos if isinstance(pos, dict) else {}


def _velocity(entity: dict[str, Any]) -> dict[str, Any]:
    velocity = entity.get("velocity", {})
    return velocity if isinstance(velocity, dict) else {}


def _q(value: Any, scale: int = 10) -> int:
    try:
        return int(round(float(value) * scale))
    except (TypeError, ValueError):
        return 0


def _uq(value: Any, scale: int = 10) -> float:
    try:
        return round(float(value) / scale, 3)
    except (TypeError, ValueError):
        return 0.0


def _get(row: list[Any], index: int, fallback: Any) -> Any:
    return row[index] if isinstance(row, list) and index < len(row) else fallback
