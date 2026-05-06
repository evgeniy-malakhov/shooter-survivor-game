from __future__ import annotations

import time
from typing import Any

import pygame

from client.controllers.scoreboard_controller import ScoreboardController
from client.render.ui.context_prompt_renderer import ContextPromptRenderer
from client.render.render_context import RenderContext
from client.render.ui.crafting_renderer import CraftingRenderer
from client.render.ui.death_overlay_renderer import DeathOverlayRenderer
from client.render.ui.hud_renderer import HudRenderer
from client.render.ui.inventory_renderer import InventoryRenderer
from client.render.ui.minimap_renderer import MinimapRenderer
from client.render.ui.overlay_router import OverlayRouter
from client.render.ui.scoreboard_renderer import ScoreboardRenderer
from client.render.ui.settings_overlay_renderer import SettingsOverlayRenderer
from client.render.ui.status_renderer import StatusRenderer
from client.render.ui.weapon_custom_renderer import WeaponCustomRenderer
from client.render.world.world_renderer import WorldRenderer


class GameplayScene:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.world_renderer = WorldRenderer()
        self.hud_renderer = HudRenderer()
        self.minimap_renderer = MinimapRenderer()
        self.status_renderer = StatusRenderer(self.minimap_renderer)
        self.context_prompt_renderer = ContextPromptRenderer()
        self.death_overlay_renderer = DeathOverlayRenderer()
        self.scoreboard_renderer = ScoreboardRenderer()
        self.inventory_renderer = InventoryRenderer()
        self.crafting_renderer = CraftingRenderer()
        self.settings_renderer = SettingsOverlayRenderer()
        self.weapon_custom_renderer = WeaponCustomRenderer()
        self.overlay_router = OverlayRouter(
            self.inventory_renderer,
            self.crafting_renderer,
            self.settings_renderer,
            self.weapon_custom_renderer,
        )
        self.scoreboard_controller = ScoreboardController(app)

    def handle_events(self, events: list[pygame.event.Event]) -> None:
        for event in events:
            if self.scoreboard_controller.handle_event(event):
                continue
            if event.type == pygame.KEYDOWN:
                self.app._handle_keydown(event)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self.app._handle_mouse_down(event)
            elif event.type == pygame.MOUSEBUTTONUP:
                self.app._handle_mouse_up(event)
            elif event.type == pygame.MOUSEMOTION:
                self.app._handle_mouse_motion(event)
            elif event.type == pygame.MOUSEWHEEL:
                self.app._handle_mouse_wheel(event)

    def update(self, dt: float) -> None:
        self.app._update(dt)

    def render(self, ctx: RenderContext) -> None:
        if ctx.snapshot:
            self.app._update_explosion_effects(ctx.snapshot, ctx.local_player)
            self.app._update_death_effects(ctx.snapshot)
            self.app._update_weapon_audio_from_snapshot(ctx.snapshot)
            ctx.effects = self.app._sync_visual_effect_state()
        self.world_renderer.render(ctx)
        started = time.perf_counter()
        if ctx.snapshot:
            self.hud_renderer.render(ctx)
            self.minimap_renderer.render(ctx)
            self.status_renderer.render(
                ctx,
                connection_quality=self.app.online.connection_quality(),
                error=self.app.online.error or "",
            )
            self.context_prompt_renderer.render(ctx)
            if pygame.key.get_pressed()[pygame.K_TAB]:
                self.scoreboard_renderer.render(ctx)
            self.death_overlay_renderer.render(ctx, online=self.app.state == "online_game")
            self.overlay_router.render(ctx)
        if ctx.perf:
            if ctx.text_cache:
                ctx.perf.text_cache_hits = ctx.text_cache.hits
            ctx.perf.draw_ui_ms = (time.perf_counter() - started) * 1000.0
