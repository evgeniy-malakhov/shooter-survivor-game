from __future__ import annotations

from shared.constants import MAP_HEIGHT, MAP_WIDTH
from shared.maps.core.map_types import MapSpawnPoint
from shared.models import Vec2


FOREST_OUTPOST_SPAWN_POINTS = [
    MapSpawnPoint("player_center", "player", Vec2(MAP_WIDTH * 0.5, MAP_HEIGHT * 0.5), radius=360.0),
    MapSpawnPoint("zombie_north", "zombie", Vec2(MAP_WIDTH * 0.5, 220.0), radius=620.0),
    MapSpawnPoint("zombie_south", "zombie", Vec2(MAP_WIDTH * 0.5, MAP_HEIGHT - 220.0), radius=620.0),
    MapSpawnPoint("soldier_checkpoint", "soldier", Vec2(1200.0, 500.0), radius=260.0),
]
