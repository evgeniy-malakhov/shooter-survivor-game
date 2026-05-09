from __future__ import annotations

from shared.maps.core.map_types import MapSpawnPoint
from shared.models import Vec2


RAVEN_DISTRICT_SPAWN_POINTS = [
    MapSpawnPoint("rd_player_residential", "player", Vec2(2100.0, 4200.0), radius=460.0),
    MapSpawnPoint("rd_player_police", "player", Vec2(7050.0, 7350.0), radius=360.0),
    MapSpawnPoint("rd_zombie_downtown", "zombie", Vec2(5700.0, 2550.0), radius=1500.0, weight=1.4),
    MapSpawnPoint("rd_zombie_hospital", "zombie", Vec2(4200.0, 6750.0), radius=1200.0, weight=1.2),
    MapSpawnPoint("rd_zombie_metro", "zombie", Vec2(6000.0, 4600.0), floor=-1, radius=1900.0, weight=1.6),
    MapSpawnPoint("rd_soldier_blockade", "soldier", Vec2(9800.0, 2050.0), radius=620.0, weight=1.2),
    MapSpawnPoint("rd_soldier_police", "soldier", Vec2(7150.0, 7100.0), radius=420.0),
]
