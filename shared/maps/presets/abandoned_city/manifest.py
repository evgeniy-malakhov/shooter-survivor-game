from __future__ import annotations

from shared.maps.core.map_manifest import MapManifest
from shared.maps.presets.forest_outpost.config import FOREST_OUTPOST_CONFIG


ABANDONED_CITY_MANIFEST = MapManifest(
    id="abandoned_city",
    title="Abandoned City",
    description="Future urban preset reserved for denser streets and interiors.",
    preview_image=None,
    difficulty="hard",
    size=(FOREST_OUTPOST_CONFIG.width, FOREST_OUTPOST_CONFIG.height),
    builder_path="shared.maps.presets.abandoned_city.builder.AbandonedCityBuilder",
    config_path="shared.maps.presets.abandoned_city.config.ABANDONED_CITY_CONFIG",
)
