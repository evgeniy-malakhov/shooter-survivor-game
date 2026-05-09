from __future__ import annotations

from shared.level import _make_building
from shared.maps.core.map_config import MapConfig
from shared.maps.core.map_types import MapBuildResult
from shared.maps.presets.raven_district.districts import RAVEN_DISTRICTS
from shared.maps.presets.raven_district.spawn_points import RAVEN_DISTRICT_SPAWN_POINTS
from shared.maps.presets.raven_district.zones import RAVEN_DISTRICT_ZONES


class RavenDistrictBuilder:
    def build(self, config: MapConfig) -> MapBuildResult:
        buildings = {
            building.id: building
            for building in (
                _make_building("rd_clinic", "Raven Hospital Wing", 3800.0, 6250.0, 980.0, 720.0),
                _make_building("rd_police", "Police Station", 6900.0, 6860.0, 980.0, 760.0),
                _make_building("rd_blockade_a", "North Checkpoint", 9300.0, 1640.0, 860.0, 520.0),
                _make_building("rd_blockade_b", "Bunker Command", 10100.0, 2300.0, 720.0, 560.0),
                _make_building("rd_factory_a", "Toxic Factory", 8800.0, 5600.0, 1020.0, 720.0),
                _make_building("rd_factory_b", "Rail Depot", 10000.0, 6500.0, 920.0, 620.0),
                _make_building("rd_apartment_a", "Residential Block A", 2100.0, 3560.0, 820.0, 680.0),
                _make_building("rd_apartment_b", "Residential Block B", 3000.0, 4420.0, 820.0, 680.0),
                _make_building("rd_downtown_a", "Raven Plaza", 5200.0, 2180.0, 900.0, 760.0),
                _make_building("rd_downtown_b", "Quarantine Mall", 6200.0, 2920.0, 1180.0, 760.0),
                _make_building("rd_metro", "Metro Hub", 5560.0, 4300.0, 960.0, 620.0),
            )
        }

        return MapBuildResult(
            map_id="raven_district",
            width=config.width,
            height=config.height,
            buildings=buildings,
            terrain={
                "kind": "abandoned_quarantine_city",
                "persistent": True,
                "districts": list(RAVEN_DISTRICTS),
                "style": "abandoned_quarantined_city",
            },
            spawn_points=list(RAVEN_DISTRICT_SPAWN_POINTS),
            zones=list(RAVEN_DISTRICT_ZONES),
            static_objects=list(buildings.values()),
            decorations=[],
            loot_points=[district.center for district in RAVEN_DISTRICTS if district.loot_remaining > 0.65],
        )
