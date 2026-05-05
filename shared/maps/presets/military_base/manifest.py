from __future__ import annotations

from shared.maps.core.map_manifest import MapManifest
from shared.maps.presets.forest_outpost.config import FOREST_OUTPOST_CONFIG


MILITARY_BASE_MANIFEST = MapManifest(
    id="military_base",
    title="Military Base",
    description="Future preset reserved for fortified compounds and tactical patrols.",
    preview_image=None,
    difficulty="normal",
    size=(FOREST_OUTPOST_CONFIG.width, FOREST_OUTPOST_CONFIG.height),
    builder_path="shared.maps.presets.military_base.builder.MilitaryBaseBuilder",
    config_path="shared.maps.presets.military_base.config.MILITARY_BASE_CONFIG",
)
