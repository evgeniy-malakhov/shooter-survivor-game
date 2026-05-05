from __future__ import annotations

from typing import Protocol

from shared.maps.core.map_config import MapConfig
from shared.maps.core.map_types import MapBuildResult


class MapBuilder(Protocol):
    def build(self, config: MapConfig) -> MapBuildResult:
        ...
