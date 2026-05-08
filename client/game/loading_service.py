from __future__ import annotations

import threading
import time

from client.game.loading_jobs import LoadingJob, LoadingJobRunner
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
                if app.loading_state is None:
                    return
                loaded: dict[str, object] = {}

                def prepare_session() -> None:
                    world, player_id = app._build_single_player_world(app.loading_state)
                    loaded["world"] = world
                    loaded["player_id"] = player_id
                    loaded["snapshot"] = world.snapshot()

                def build_chunks() -> None:
                    snapshot = loaded["snapshot"]
                    quality_key = f"r{app.render_quality.render_radius_multiplier:.2f}:lod{app.render_quality.actor_lod_bias}:fx{app.render_quality.effects_quality:.2f}"
                    app.static_world_cache.warm_snapshot(snapshot, quality_profile=quality_key, theme=str(app.settings.get("theme", "default")))

                def prepare_minimap() -> None:
                    app.minimap_static_cache.key = None
                    app.minimap_static_cache.surface = None

                def warm_assets() -> None:
                    app.assets.warm_scaled_icons()

                def warm_sprites() -> None:
                    if hasattr(app, "actor_sprite_cache"):
                        app.actor_sprite_cache.warm_defaults()

                def warm_ui_surfaces() -> None:
                    app.ui_surface_cache.rounded_rect("button", (180, 46), (19, 25, 42), (53, 68, 98), outline_width=2, radius=10)
                    app.ui_surface_cache.rounded_rect("panel", (520, 680), (19, 25, 42), (76, 225, 255), outline_width=2, radius=12)

                runner = LoadingJobRunner(app.loading_state)
                runner.run(
                    [
                        LoadingJob(LoadingStage.LOAD_ASSETS, "Loading configs", 0.12, lambda: None),
                        LoadingJob(LoadingStage.LOAD_ASSETS, "Loading assets", 0.22, lambda: None),
                        LoadingJob(LoadingStage.COMPOSE_WORLD, "Preparing session", 0.90, prepare_session),
                        LoadingJob(LoadingStage.BUILD_CHUNKS, "Building static world chunks", 0.965, build_chunks),
                        LoadingJob(LoadingStage.PREPARE_MINIMAP, "Preparing minimap cache", 0.975, prepare_minimap),
                        LoadingJob(LoadingStage.WARM_ASSETS, "Warming icon cache", 0.982, warm_assets),
                        LoadingJob(LoadingStage.WARM_ASSETS, "Warming actor sprites", 0.988, warm_sprites),
                        LoadingJob(LoadingStage.WARM_ASSETS, "Warming UI surfaces", 0.992, warm_ui_surfaces),
                        LoadingJob(LoadingStage.START_SESSION, "Starting session", 0.995, lambda: None),
                    ]
                )
                world = loaded["world"]
                player_id = loaded["player_id"]
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
