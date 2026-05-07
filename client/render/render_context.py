from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pygame

from client.core.camera import CameraController
from client.core.assets import ClientAssets
from client.core.perf import ClientPerfStats
from client.effects.visual_effects_state import VisualEffectsState
from client.controllers.overlay_state import GameplayOverlayState
from client.render.render_frame import RenderFrame
from client.render.render_resources import RenderFonts, RenderText
from client.render.ui.text_cache import TextCache
from shared.models import PlayerState, Vec2, WorldSnapshot


@dataclass(slots=True)
class RenderContext:
    screen: pygame.Surface
    camera: Vec2
    camera_controller: CameraController
    assets: ClientAssets
    snapshot: WorldSnapshot | None
    local_player: PlayerState | None
    dt: float
    settings: dict[str, object]
    fonts: RenderFonts | None = None
    text: RenderText | None = None
    text_cache: TextCache | None = None
    overlay: GameplayOverlayState | None = None
    local_player_id: str | None = None
    online_player_id: str | None = None
    now: float = 0.0
    render_frame: RenderFrame | None = None
    render_snapshot_view: Any | None = None
    perf: ClientPerfStats | None = None
    effects: VisualEffectsState | None = None
    death_tuning: Any | None = None

    @property
    def visible_rect(self) -> pygame.Rect:
        return self.camera_controller.visible_world_rect(self.camera, margin=320.0)
