from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MapConfig:
    width: int
    height: int
    player_spawn_count: int
    zombie_spawn_count: int
    soldier_spawn_count: int
    building_density: float
    obstacle_density: float
    loot_density: float
    enable_soldiers: bool
    enable_zombies: bool
    enable_weather: bool
