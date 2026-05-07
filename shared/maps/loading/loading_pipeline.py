from __future__ import annotations

from shared.maps.core.map_loader import MapLoader
from shared.maps.core.map_manifest import MapManifest
from shared.maps.core.map_types import MapBuildResult
from shared.maps.loading.loading_screen_state import LoadingScreenState
from shared.maps.loading.loading_stage import LoadingStage


class MapLoadingPipeline:
    def __init__(self, loader: MapLoader) -> None:
        self._loader = loader

    def run(
        self,
        manifest: MapManifest,
        state: LoadingScreenState | None = None,
    ) -> MapBuildResult:
        self._mark(state, LoadingStage.INIT, "Preparing map manifest", 0.04)
        config = self._loader.load_config(manifest)
        self._mark(state, LoadingStage.LOAD_ASSETS, "Resolving map assets", 0.16)
        self._mark(state, LoadingStage.BUILD_TERRAIN, "Building terrain layout", 0.32)

        builder = self._loader.load_builder(manifest)
        result = builder.build(config)

        self._mark(state, LoadingStage.BUILD_COLLISIONS, "Baking collision data", 0.58)
        self._mark(state, LoadingStage.BUILD_NAVIGATION, "Preparing navigation data", 0.72)
        self._mark(state, LoadingStage.SPAWN_ENTITIES, "Placing spawn zones", 0.82)
        self._mark(state, LoadingStage.COMPOSE_WORLD, "Composing world runtime", 0.92)
        return result

    def mark_ready(self, state: LoadingScreenState | None) -> None:
        self._mark(state, LoadingStage.READY, "Entering operation zone", 1.0)

    def _mark(
        self,
        state: LoadingScreenState | None,
        stage: LoadingStage,
        label: str,
        progress: float,
    ) -> None:
        if state is not None:
            state.update(stage, label, progress)
