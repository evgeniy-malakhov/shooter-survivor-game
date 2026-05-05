from __future__ import annotations

from shared.maps.core.map_loader import MapLoader
from shared.maps.core.map_registry import MapRegistry
from shared.maps.core.map_types import MapBuildResult
from shared.maps.loading.loading_pipeline import MapLoadingPipeline
from shared.maps.loading.loading_screen_state import LoadingScreenState


class MapRuntime:
    def __init__(
        self,
        registry: MapRegistry,
        loader: MapLoader | None = None,
    ) -> None:
        self.registry = registry
        self.loader = loader or MapLoader()

    def start_map(
        self,
        map_id: str | None,
        loading_state: LoadingScreenState | None = None,
    ) -> MapBuildResult:
        manifest = self.registry.get(map_id)
        pipeline = MapLoadingPipeline(self.loader)
        return pipeline.run(manifest, loading_state)
