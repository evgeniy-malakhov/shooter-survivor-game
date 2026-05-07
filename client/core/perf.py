from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ClientPerfStats:
    frame_ms: float = 0.0
    update_ms: float = 0.0
    render_prepare_ms: float = 0.0
    draw_world_ms: float = 0.0
    draw_ui_ms: float = 0.0
    scene_update_ms: float = 0.0
    scene_render_ms: float = 0.0
    controller_ms: float = 0.0
    ui_render_ms: float = 0.0
    hud_ms: float = 0.0
    minimap_ms: float = 0.0
    overlay_ms: float = 0.0
    render_frame_build_ms: float = 0.0
    culling_ms: float = 0.0
    spatial_query_ms: float = 0.0
    world_static_ms: float = 0.0
    world_dynamic_ms: float = 0.0
    actors_ms: float = 0.0
    projectiles_ms: float = 0.0
    effects_ms: float = 0.0
    map_ms: float = 0.0
    text_cache_hits: int = 0
    text_cache_misses: int = 0
    icon_cache_hits: int = 0
    icon_cache_misses: int = 0
    snapshot_total_players: int = 0
    snapshot_total_zombies: int = 0
    snapshot_total_soldiers: int = 0
    snapshot_total_loot: int = 0
    visible_players: int = 0
    visible_zombies: int = 0
    visible_soldiers: int = 0
    visible_loot: int = 0
    visible_chunks: int = 0
    static_chunk_hits: int = 0
    static_chunk_misses: int = 0
    minimap_cache_hits: int = 0
    minimap_cache_misses: int = 0
    gc_count_0: int = 0
    gc_count_1: int = 0
    gc_count_2: int = 0
    gc_time_ms: float = 0.0
    frame_alloc_estimate: int = 0
    effect_pool_active: int = 0
    effect_pool_free: int = 0
    frame_p95_ms: float = 0.0
    frame_p99_ms: float = 0.0
    over_budget_frames: int = 0
    suggested_lod_bias: float = 1.0
    suggested_render_radius_scale: float = 1.0

    def reset_visible_counts(self) -> None:
        self.visible_players = 0
        self.visible_zombies = 0
        self.visible_soldiers = 0
        self.visible_loot = 0
        self.visible_chunks = 0
