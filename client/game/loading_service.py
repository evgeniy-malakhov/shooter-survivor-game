from __future__ import annotations

import threading
import time

from shared.maps.loading import LoadingScreenState, LoadingStage


class LoadingService:
    def __init__(self, app) -> None:
        self.app = app

    def start_single_player(self) -> None:
        app = self.app
        app.online.close()
        if app.world:
            app.world.close()
        app.world = None
        app.local_player_id = None
        app._loaded_world = None
        app._loaded_player_id = None
        app.loading_error = None
        app.loading_state = LoadingScreenState(app.single_map_key)
        app._loading_started_at = time.time()
        app._set_state("single_loading")
        app._save_client_settings()

        def worker() -> None:
            try:
                world, player_id = app._build_single_player_world(app.loading_state)
                snapshot = world.snapshot()
                if app.loading_state is not None:
                    app.loading_state.update(LoadingStage.BUILD_CHUNKS, "Building static world chunks", 0.965)
                app.static_world_cache.warm_snapshot(snapshot)
                if app.loading_state is not None:
                    app.loading_state.update(LoadingStage.PREPARE_MINIMAP, "Preparing minimap cache", 0.975)
                app.minimap_static_cache.key = None
                app.minimap_static_cache.surface = None
                if app.loading_state is not None:
                    app.loading_state.update(LoadingStage.WARM_ASSETS, "Warming asset cache", 0.985)
                app.assets.warm_scaled_icons()
                if app.loading_state is not None:
                    app.loading_state.update(LoadingStage.START_SESSION, "Starting session", 0.995)
                app._loaded_world = world
                app._loaded_player_id = player_id
                if app.loading_state is not None:
                    app.loading_state.update(LoadingStage.READY, "Entering operation zone", 1.0)
            except Exception as exc:
                app.loading_error = str(exc)
                if app.loading_state is not None:
                    app.loading_state.fail(str(exc))

        app.loading_thread = threading.Thread(target=worker, name="single-map-loader", daemon=True)
        app.loading_thread.start()

    def finish_single_loading_if_ready(self) -> None:
        app = self.app
        if app.state != "single_loading":
            return
        thread_done = app.loading_thread is not None and not app.loading_thread.is_alive()
        ready = app.loading_state and app.loading_state.snapshot().stage == LoadingStage.READY
        if app.loading_error or not thread_done or not ready or app._loaded_world is None or app._loaded_player_id is None:
            return
        app.world = app._loaded_world
        app.local_player_id = app._loaded_player_id
        app._loaded_world = None
        app._loaded_player_id = None
        app.overlay_state.close_gameplay_overlays()
        app._reset_death_effect_tracking()
        app._set_state("single")
