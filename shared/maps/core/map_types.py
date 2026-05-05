from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shared.models import BuildingState, Vec2


@dataclass(frozen=True, slots=True)
class MapSpawnPoint:
    id: str
    kind: str
    pos: Vec2
    floor: int = 0
    radius: float = 160.0
    weight: float = 1.0


@dataclass(frozen=True, slots=True)
class MapZone:
    id: str
    kind: str
    center: Vec2
    radius: float
    floor: int = 0
    tags: tuple[str, ...] = ()


@dataclass(slots=True)
class MapBuildResult:
    map_id: str
    width: int
    height: int
    buildings: dict[str, BuildingState]
    terrain: Any = None
    collision_grid: Any = None
    navigation_grid: Any = None
    spawn_points: list[MapSpawnPoint] = field(default_factory=list)
    zones: list[MapZone] = field(default_factory=list)
    static_objects: list[Any] = field(default_factory=list)
    decorations: list[Any] = field(default_factory=list)
    loot_points: list[Vec2] = field(default_factory=list)
