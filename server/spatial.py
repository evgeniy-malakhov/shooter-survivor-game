from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


POSITION_COLLECTIONS = (
    "zombies",
    "projectiles",
    "grenades",
    "mines",
    "poison_projectiles",
    "poison_pools",
    "loot",
)


@dataclass(slots=True)
class SpatialHashGrid:
    cell_size: float
    _cells: dict[tuple[int, int, int], set[str]] = field(default_factory=lambda: defaultdict(set))

    def insert(self, entity_id: str, x: float, y: float, floor: int = 0) -> None:
        self._cells[self._cell(x, y, floor)].add(entity_id)

    def query(self, x: float, y: float, radius: float, floor: int = 0) -> set[str]:
        if radius <= 0:
            return set()
        min_x = math.floor((x - radius) / self.cell_size)
        max_x = math.floor((x + radius) / self.cell_size)
        min_y = math.floor((y - radius) / self.cell_size)
        max_y = math.floor((y + radius) / self.cell_size)
        found: set[str] = set()
        for cx in range(min_x, max_x + 1):
            for cy in range(min_y, max_y + 1):
                found.update(self._cells.get((floor, cx, cy), ()))
        return found

    def _cell(self, x: float, y: float, floor: int) -> tuple[int, int, int]:
        return (floor, math.floor(x / self.cell_size), math.floor(y / self.cell_size))


class SnapshotInterestIndex:
    def __init__(self, snapshot: dict[str, Any], cell_size: float) -> None:
        self._grids: dict[str, SpatialHashGrid] = {}
        for collection in POSITION_COLLECTIONS:
            grid = SpatialHashGrid(cell_size)
            for entity_id, entity in _collection(snapshot, collection).items():
                pos = entity.get("pos") if isinstance(entity, dict) else None
                if not isinstance(pos, dict):
                    continue
                grid.insert(
                    str(entity_id),
                    float(pos.get("x", 0.0)),
                    float(pos.get("y", 0.0)),
                    int(entity.get("floor", 0)),
                )
            self._grids[collection] = grid

    def query(self, collection: str, x: float, y: float, radius: float, floor: int) -> set[str]:
        grid = self._grids.get(collection)
        return grid.query(x, y, radius, floor) if grid else set()


def filter_snapshot_for_player(
    snapshot: dict[str, Any],
    player_id: str,
    index: SnapshotInterestIndex,
    interest_radius: float,
    building_radius: float,
) -> dict[str, Any]:
    players = _collection(snapshot, "players")
    player = players.get(player_id)
    if not isinstance(player, dict):
        return snapshot

    pos = player.get("pos") if isinstance(player.get("pos"), dict) else {"x": 0.0, "y": 0.0}
    x = float(pos.get("x", 0.0))
    y = float(pos.get("y", 0.0))
    floor = int(player.get("floor", 0))
    filtered: dict[str, Any] = {
        "time": snapshot.get("time", 0.0),
        "map_width": snapshot.get("map_width", 1),
        "map_height": snapshot.get("map_height", 1),
        "players": _filter_players(players, player_id, interest_radius, x, y, floor),
        "buildings": _filter_buildings(_collection(snapshot, "buildings"), x, y, player.get("inside_building"), building_radius),
    }

    for collection in POSITION_COLLECTIONS:
        source = _collection(snapshot, collection)
        entity_ids = index.query(collection, x, y, interest_radius, floor)
        owned = {
            entity_id
            for entity_id, entity in source.items()
            if isinstance(entity, dict) and entity.get("owner_id") == player_id
        }
        selected = entity_ids | owned
        filtered[collection] = {entity_id: source[entity_id] for entity_id in selected if entity_id in source}
    return filtered


def filter_snapshot_area(
    snapshot: dict[str, Any],
    index: SnapshotInterestIndex,
    x: float,
    y: float,
    floor: int,
    inside_building: object,
    interest_radius: float,
    building_radius: float,
) -> dict[str, Any]:
    filtered: dict[str, Any] = {
        "time": snapshot.get("time", 0.0),
        "map_width": snapshot.get("map_width", 1),
        "map_height": snapshot.get("map_height", 1),
        "players": _filter_players(_collection(snapshot, "players"), "", interest_radius, x, y, floor),
        "buildings": _filter_buildings(_collection(snapshot, "buildings"), x, y, inside_building, building_radius),
    }
    for collection in POSITION_COLLECTIONS:
        source = _collection(snapshot, collection)
        entity_ids = index.query(collection, x, y, interest_radius, floor)
        filtered[collection] = {entity_id: source[entity_id] for entity_id in entity_ids if entity_id in source}
    return filtered


def snapshot_with_local_player(area_snapshot: dict[str, Any], full_snapshot: dict[str, Any], player_id: str) -> dict[str, Any]:
    filtered = dict(area_snapshot)
    players = dict(_collection(area_snapshot, "players"))
    local = _collection(full_snapshot, "players").get(player_id)
    if isinstance(local, dict):
        players[player_id] = local
    filtered["players"] = players
    return filtered


def _filter_players(
    players: dict[str, Any],
    local_id: str,
    interest_radius: float,
    x: float,
    y: float,
    floor: int,
) -> dict[str, Any]:
    filtered: dict[str, Any] = {}
    for player_id, player in players.items():
        if not isinstance(player, dict):
            continue
        if player_id == local_id:
            filtered[player_id] = player
            continue
        player_pos = player.get("pos") if isinstance(player.get("pos"), dict) else {"x": 0.0, "y": 0.0}
        distance = math.hypot(float(player_pos.get("x", 0.0)) - x, float(player_pos.get("y", 0.0)) - y)
        nearby = int(player.get("floor", 0)) == floor and distance <= interest_radius
        filtered[player_id] = _public_player(player, include_weapon=nearby)
    return filtered


def _public_player(player: dict[str, Any], include_weapon: bool) -> dict[str, Any]:
    keys = (
        "id",
        "name",
        "pos",
        "angle",
        "health",
        "armor",
        "armor_key",
        "active_slot",
        "alive",
        "score",
        "kills_by_kind",
        "noise",
        "sprinting",
        "floor",
        "inside_building",
        "sneaking",
        "poison_left",
        "ping_ms",
        "connection_quality",
    )
    public = {key: player[key] for key in keys if key in player}
    if include_weapon:
        active_slot = str(player.get("active_slot", "1"))
        weapons = player.get("weapons", {})
        if isinstance(weapons, dict) and active_slot in weapons:
            public["weapons"] = {active_slot: weapons[active_slot]}
    return public


def _filter_buildings(
    buildings: dict[str, Any],
    x: float,
    y: float,
    inside_building: object,
    radius: float,
) -> dict[str, Any]:
    filtered: dict[str, Any] = {}
    for building_id, building in buildings.items():
        if not isinstance(building, dict):
            continue
        bounds = building.get("bounds") if isinstance(building.get("bounds"), dict) else None
        if not bounds:
            continue
        center_x = float(bounds.get("x", 0.0)) + float(bounds.get("w", 0.0)) * 0.5
        center_y = float(bounds.get("y", 0.0)) + float(bounds.get("h", 0.0)) * 0.5
        if building_id == inside_building or math.hypot(center_x - x, center_y - y) <= radius:
            filtered[building_id] = building
    return filtered


def _collection(snapshot: dict[str, Any], key: str) -> dict[str, Any]:
    value = snapshot.get(key, {})
    return value if isinstance(value, dict) else {}
