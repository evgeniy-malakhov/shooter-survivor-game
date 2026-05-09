from __future__ import annotations

from shared.maps.core.map_manifest import MapManifest
from shared.maps.presets.raven_district.config import RAVEN_DISTRICT_CONFIG


RAVEN_DISTRICT_MANIFEST = MapManifest(
    id="raven_district",
    title="Raven District",
    description="Large abandoned quarantine city with persistent district pressure, metro tunnels and military blockade.",
    preview_image="assets/maps/raven_district/preview.png",
    difficulty="hard",
    size=(RAVEN_DISTRICT_CONFIG.width, RAVEN_DISTRICT_CONFIG.height),
    builder_path="shared.maps.presets.raven_district.builder.RavenDistrictBuilder",
    config_path="shared.maps.presets.raven_district.config.RAVEN_DISTRICT_CONFIG",
)
