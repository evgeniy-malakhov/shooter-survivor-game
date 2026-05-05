from __future__ import annotations

from shared.constants import MAP_HEIGHT, MAP_WIDTH
from shared.maps.core.map_config import MapConfig


FOREST_OUTPOST_CONFIG = MapConfig(
    width=int(MAP_WIDTH),
    height=int(MAP_HEIGHT),
    player_spawn_count=4,
    zombie_spawn_count=80,
    soldier_spawn_count=12,
    building_density=0.12,
    obstacle_density=0.35,
    loot_density=0.18,
    enable_soldiers=True,
    enable_zombies=True,
    enable_weather=False,
)
