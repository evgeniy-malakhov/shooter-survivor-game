from __future__ import annotations

from shared.maps.core.map_registry import MapRegistry
from shared.maps.presets.forest_outpost.manifest import FOREST_OUTPOST_MANIFEST


def build_default_map_registry() -> MapRegistry:
    registry = MapRegistry()
    registry.register(FOREST_OUTPOST_MANIFEST)
    return registry


DEFAULT_MAP_REGISTRY = build_default_map_registry()


def list_available_maps():
    return DEFAULT_MAP_REGISTRY.list_maps()
