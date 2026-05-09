from __future__ import annotations

from shared.maps.core.map_config import MapConfig


RAVEN_DISTRICT_CONFIG = MapConfig(
    width=12000,
    height=9000,
    player_spawn_count=6,
    zombie_spawn_count=180,
    soldier_spawn_count=34,
    building_density=0.46,
    obstacle_density=0.58,
    loot_density=0.34,
    enable_soldiers=True,
    enable_zombies=True,
    enable_weather=True,
)
