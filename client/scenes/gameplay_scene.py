from __future__ import annotations

import time
from typing import Any

import pygame

from client.controllers.crafting_controller import CraftingController
from client.controllers.gameplay_input_controller import GameplayInputController
from client.controllers.inventory_controller import InventoryController
from client.controllers.pause_settings_controller import PauseSettingsController
from client.controllers.scoreboard_controller import ScoreboardController
from client.controllers.weapon_custom_controller import WeaponCustomController
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
        self.world_renderer = WorldRenderer(app.static_world_cache)
        self.hud_renderer = HudRenderer()
        self.minimap_renderer = MinimapRenderer(app.minimap_static_cache)
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
        self.pause_settings_controller = PauseSettingsController(app)
        self.weapon_custom_controller = WeaponCustomController(app)
        self.inventory_controller = InventoryController(app)
        self.crafting_controller = CraftingController(app)
        self.input_controller = GameplayInputController(app)

    def handle_events(self, events: list[pygame.event.Event]) -> None:
        started = time.perf_counter()
        for event in events:
            if self.scoreboard_controller.handle_event(event):
                continue
            if self.pause_settings_controller.handle_event(event):
                continue
            if self.weapon_custom_controller.handle_event(event):
                continue
            if self.inventory_controller.handle_event(event):
                continue
            if self.crafting_controller.handle_event(event):
                continue
            self.input_controller.handle_event(event)
        if hasattr(self.app, "perf_stats"):
            self.app.perf_stats.controller_ms = (time.perf_counter() - started) * 1000.0

    def update(self, dt: float) -> None:
        app = self.app
        app._sync_menu_music()
        if app.state == "single" and app.world and app.local_player_id:
            app._dispatch_action_buffer(app.local_player_id)
            command = self.input_controller.build_input_command(app.local_player_id)
            app.world.set_input(command)
            blocked = app.settings_open or app.backpack_open or app.craft_open or app.weapon_custom_open
            app.world.update(0.0 if blocked else dt)
        elif app.state == "online_game" and app.online.player_id:
            app._dispatch_action_buffer(app.online.player_id)
            command = self.input_controller.build_input_command(app.online.player_id)
            app.online.send_input(command)
            app._process_online_events()
        app._update_camera_zoom(dt)
        app._update_damage_feedback(dt)

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
                ctx.perf.text_cache_misses = ctx.text_cache.misses
            if ctx.assets:
                ctx.perf.icon_cache_hits = ctx.assets.scale_cache.hits
                ctx.perf.icon_cache_misses = ctx.assets.scale_cache.misses
            ctx.perf.draw_ui_ms = (time.perf_counter() - started) * 1000.0
            ctx.perf.ui_render_ms = ctx.perf.draw_ui_ms
