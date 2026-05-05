from __future__ import annotations

from shared.level import make_buildings
from shared.maps.core.map_config import MapConfig
from shared.maps.core.map_types import MapBuildResult
from shared.maps.presets.forest_outpost.spawn_points import FOREST_OUTPOST_SPAWN_POINTS
from shared.maps.presets.forest_outpost.zones import FOREST_OUTPOST_ZONES


class ForestOutpostBuilder:
    def build(self, config: MapConfig) -> MapBuildResult:
        buildings = make_buildings()

        return MapBuildResult(
            map_id="forest_outpost",
            width=config.width,
            height=config.height,
            buildings=buildings,
            terrain={"kind": "procedural_outpost"},
            spawn_points=list(FOREST_OUTPOST_SPAWN_POINTS),
            zones=list(FOREST_OUTPOST_ZONES),
            static_objects=list(buildings.values()),
            decorations=[],
            loot_points=[],
        )
