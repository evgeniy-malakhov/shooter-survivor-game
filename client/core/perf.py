from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ClientPerfStats:
    frame_ms: float = 0.0
    update_ms: float = 0.0
    render_prepare_ms: float = 0.0
    draw_world_ms: float = 0.0
    draw_ui_ms: float = 0.0
    hud_ms: float = 0.0
    minimap_ms: float = 0.0
    overlay_ms: float = 0.0
    text_cache_hits: int = 0
    icon_cache_hits: int = 0
    visible_players: int = 0
    visible_zombies: int = 0
    visible_soldiers: int = 0
    visible_loot: int = 0

    def reset_visible_counts(self) -> None:
        self.visible_players = 0
        self.visible_zombies = 0
        self.visible_soldiers = 0
        self.visible_loot = 0
