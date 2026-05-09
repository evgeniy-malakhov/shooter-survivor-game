from __future__ import annotations

from shared.maps.core.map_registry import MapRegistry
from shared.maps.presets.forest_outpost.manifest import FOREST_OUTPOST_MANIFEST
from shared.maps.presets.abandoned_city.manifest import ABANDONED_CITY_MANIFEST
from shared.maps.presets.military_base.manifest import MILITARY_BASE_MANIFEST
from shared.maps.presets.raven_district.manifest import RAVEN_DISTRICT_MANIFEST


def build_default_map_registry() -> MapRegistry:
    registry = MapRegistry()
    registry.register(FOREST_OUTPOST_MANIFEST)
    registry.register(ABANDONED_CITY_MANIFEST)
    registry.register(MILITARY_BASE_MANIFEST)
    registry.register(RAVEN_DISTRICT_MANIFEST)
    return registry


DEFAULT_MAP_REGISTRY = build_default_map_registry()


def list_available_maps():
    return DEFAULT_MAP_REGISTRY.list_maps()
