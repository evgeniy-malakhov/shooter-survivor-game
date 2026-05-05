from __future__ import annotations

from shared.constants import MAP_HEIGHT, MAP_WIDTH
from shared.maps.core.map_types import MapZone
from shared.models import Vec2


FOREST_OUTPOST_ZONES = [
    MapZone("central_loot", "loot", Vec2(MAP_WIDTH * 0.5, MAP_HEIGHT * 0.5), 980.0, tags=("urban",)),
    MapZone("outer_pressure", "danger", Vec2(MAP_WIDTH * 0.5, MAP_HEIGHT * 0.5), max(MAP_WIDTH, MAP_HEIGHT) * 0.48),
]
