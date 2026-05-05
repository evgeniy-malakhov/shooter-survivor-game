from __future__ import annotations

from shared.maps.core.map_manifest import MapManifest
from shared.maps.presets.forest_outpost.config import FOREST_OUTPOST_CONFIG


FOREST_OUTPOST_MANIFEST = MapManifest(
    id="forest_outpost",
    title="Forest Outpost",
    description="Small survival zone with abandoned posts, interiors and basement tunnels.",
    preview_image="images/screen/load.png",
    difficulty="normal",
    size=(FOREST_OUTPOST_CONFIG.width, FOREST_OUTPOST_CONFIG.height),
    builder_path="shared.maps.presets.forest_outpost.builder.ForestOutpostBuilder",
    config_path="shared.maps.presets.forest_outpost.config.FOREST_OUTPOST_CONFIG",
)
