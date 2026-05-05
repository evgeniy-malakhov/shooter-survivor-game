from __future__ import annotations

from shared.maps.core.map_id import DEFAULT_MAP_ID
from shared.maps.core.map_manifest import MapManifest


class MapRegistry:
    def __init__(self) -> None:
        self._maps: dict[str, MapManifest] = {}

    def register(self, manifest: MapManifest) -> None:
        self._maps[manifest.id] = manifest

    def get(self, map_id: str | None) -> MapManifest:
        key = str(map_id or DEFAULT_MAP_ID)
        return self._maps.get(key) or self._maps[str(DEFAULT_MAP_ID)]

    def list_maps(self) -> list[MapManifest]:
        return list(self._maps.values())
