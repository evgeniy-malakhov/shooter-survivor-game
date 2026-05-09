from __future__ import annotations

from shared.maps.core.map_types import MapZone
from shared.maps.presets.raven_district.districts import RAVEN_DISTRICTS


RAVEN_DISTRICT_ZONES = [
    MapZone(
        district.id,
        "district",
        district.center,
        district.radius,
        floor=district.floor,
        tags=district.tags,
    )
    for district in RAVEN_DISTRICTS
]
