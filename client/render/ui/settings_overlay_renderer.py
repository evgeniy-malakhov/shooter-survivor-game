from __future__ import annotations

from typing import Any

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.ui.components.button import draw_button
from client.render.world.render_utils import draw_text_fit
from client.settings_schema import (
    SETTINGS_TABS,
    tab_has_camera_distance,
    tab_has_graphics_quality,
    tab_has_language,
    tab_is_stub,
    tab_toggle_keys,
)


class SettingsOverlayRenderer:
    def __init__(self, app: Any) -> None:
        self.app = app

    def render(self, ctx: RenderContext) -> None:
        app = self.app
        if not ctx.fonts or not ctx.text:
            return
        overlay = pygame.Surface(ctx.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((1, 3, 8, 166))
        ctx.screen.blit(overlay, (0, 0))
        self._render_settings_panel(ctx, in_game=True)

    def _render_settings_panel(self, ctx: RenderContext, *, in_game: bool) -> None:
        app = self.app
        panel = app._settings_panel_rect()
        pygame.draw.rect(ctx.screen, palette.PANEL, panel, border_radius=12)
        pygame.draw.rect(ctx.screen, palette.CYAN, panel, 2, border_radius=12)
        draw_text_fit(ctx, ctx.text.tr("settings.pause" if in_game else "settings.title"), pygame.Rect(panel.x + 32, panel.y + 26, panel.w - 64, 44), palette.TEXT, ctx.fonts.big, center=True)

        for index, tab in enumerate(app.settings_tabs):
            rect = pygame.Rect(panel.x + 32 + index * 112, panel.y + 106, 102, 36)
            active = tab == app.settings_tab
            pygame.draw.rect(ctx.screen, palette.PANEL_2 if active else (16, 22, 34), rect, border_radius=9)
            pygame.draw.rect(ctx.screen, palette.CYAN if active else (68, 86, 120), rect, 2, border_radius=9)
            locale_key = next((tab_item.locale_key for tab_item in SETTINGS_TABS if tab_item.key == tab), f"settings.tab.{tab}")
            draw_text_fit(ctx, ctx.text.tr(locale_key), rect.inflate(-8, -8), palette.TEXT if active else palette.MUTED, ctx.fonts.small, center=True)

        if tab_is_stub(app.settings_tab):
            stub = pygame.Rect(panel.x + 40, panel.y + 168, panel.w - 80, panel.h - 250)
            pygame.draw.rect(ctx.screen, (12, 18, 30), stub, border_radius=10)
            pygame.draw.rect(ctx.screen, palette.PURPLE, stub, 2, border_radius=10)
            draw_text_fit(ctx, ctx.text.tr("settings.audio.stub"), stub.inflate(-20, -30), palette.CYAN, ctx.fonts.big, center=True)
            self._footer(ctx, in_game)
            return

        viewport = pygame.Rect(panel.x + 36, panel.y + 162, panel.w - 72, panel.h - 238)
        pygame.draw.rect(ctx.screen, (10, 16, 28), viewport.inflate(8, 8), border_radius=10)
        pygame.draw.rect(ctx.screen, (56, 74, 108), viewport.inflate(8, 8), 1, border_radius=10)
        previous_clip = ctx.screen.get_clip()
        ctx.screen.set_clip(viewport)
        if app.settings_tab == "audio":
            self._render_audio_stub(ctx, viewport)
        else:
            self._render_option_rows(ctx, viewport)
        ctx.screen.set_clip(previous_clip)
        self._footer(ctx, in_game)

    def _render_option_rows(self, ctx: RenderContext, viewport: pygame.Rect) -> None:
        app = self.app
        labels = {
            "bot_vision": ctx.text.tr("settings.bot_vision"),
            "bot_vision_range": ctx.text.tr("settings.bot_vision_range"),
            "ai_reactions": ctx.text.tr("settings.ai_reactions"),
            "health_bars": ctx.text.tr("settings.health_bars"),
            "noise_radius": ctx.text.tr("settings.noise_radius"),
            "show_zombie_count": ctx.text.tr("settings.show_zombie_count"),
            "fullscreen": ctx.text.tr("settings.fullscreen"),
        }
        step_y = 56
        option_x = viewport.x + 6
        option_w = viewport.w - 24
        row_index = 0
        for key in tab_toggle_keys(app.settings_tab):
            y = viewport.y + row_index * step_y - app.options_scroll
            rect = pygame.Rect(option_x, y, option_w, 44)
            if rect.colliderect(viewport):
                value = bool(app.settings.get(key, False))
                hovered = rect.collidepoint(ctx.mouse_pos)
                pygame.draw.rect(ctx.screen, palette.PANEL_2 if hovered else palette.PANEL, rect, border_radius=9)
                pygame.draw.rect(ctx.screen, palette.GREEN if value else palette.MUTED, rect, 2, border_radius=9)
                draw_text_fit(ctx, labels.get(key, key), pygame.Rect(rect.x + 14, rect.y + 12, rect.w - 120, 20), palette.TEXT, ctx.fonts.normal)
                draw_text_fit(ctx, ctx.text.tr("state.on") if value else ctx.text.tr("state.off"), pygame.Rect(rect.right - 88, rect.y + 10, 76, 22), palette.GREEN if value else palette.RED, ctx.fonts.emphasis, center=True)
            row_index += 1
        if tab_has_camera_distance(app.settings_tab):
            rect = pygame.Rect(option_x, viewport.y + row_index * step_y - app.options_scroll, option_w, 44)
            self._render_value_row(ctx, rect, ctx.text.tr("settings.camera_distance"), self._camera_mode_label(ctx), palette.CYAN, viewport)
            row_index += 1
        if tab_has_graphics_quality(app.settings_tab):
            rect = pygame.Rect(option_x, viewport.y + row_index * step_y - app.options_scroll, option_w, 44)
            label = ctx.text.tr("settings.graphics_quality")
            if label == "settings.graphics_quality":
                label = "Graphics quality"
            self._render_value_row(ctx, rect, label, app.graphics_quality.upper(), palette.PURPLE, viewport)
            row_index += 1
        if tab_has_language(app.settings_tab):
            rect = pygame.Rect(option_x, viewport.y + row_index * step_y - app.options_scroll, option_w, 44)
            self._render_value_row(ctx, rect, ctx.text.tr("settings.language"), app.language.upper(), palette.PURPLE, viewport)

    def _render_value_row(self, ctx: RenderContext, rect: pygame.Rect, label: str, value: str, color: tuple[int, int, int], viewport: pygame.Rect) -> None:
        if not rect.colliderect(viewport):
            return
        pygame.draw.rect(ctx.screen, palette.PANEL_2, rect, border_radius=9)
        pygame.draw.rect(ctx.screen, color, rect, 2, border_radius=9)
        draw_text_fit(ctx, label, pygame.Rect(rect.x + 14, rect.y + 12, rect.w - 180, 20), palette.TEXT, ctx.fonts.normal)
        draw_text_fit(ctx, value, pygame.Rect(rect.right - 154, rect.y + 12, 140, 20), color, ctx.fonts.hud_title, center=True)

    def _render_audio_stub(self, ctx: RenderContext, viewport: pygame.Rect) -> None:
        colors = {
            "master": palette.CYAN,
            "music": palette.PURPLE,
            "effects": palette.YELLOW,
        }
        values = {
            "master": self.app.master_volume,
            "music": self.app.music_volume,
            "effects": self.app.effects_volume,
        }
        for _index, (key, card, track) in enumerate(self.app._audio_slider_layout(viewport)):
            if not card.colliderect(viewport):
                continue
            value = values[key]
            color = colors[key]
            hovered = card.collidepoint(ctx.mouse_pos) or track.inflate(18, 30).collidepoint(ctx.mouse_pos)
            active = self.app._dragging_audio_slider == key
            pygame.draw.rect(ctx.screen, palette.PANEL_2 if hovered or active else palette.PANEL, card, border_radius=12)
            pygame.draw.rect(ctx.screen, color if hovered or active else (66, 82, 118), card, 2, border_radius=12)
            draw_text_fit(ctx, ctx.text.tr(f"settings.audio.{key}"), pygame.Rect(card.x + 20, card.y + 12, card.w - 150, 22), palette.TEXT, ctx.fonts.hud_title)
            draw_text_fit(ctx, f"{int(round(value * 100)):>3}%", pygame.Rect(card.right - 104, card.y + 12, 82, 24), color, ctx.fonts.hud_value, center=True)
            draw_text_fit(ctx, ctx.text.tr(f"settings.audio.{key}.desc"), pygame.Rect(card.x + 20, card.y + 38, card.w - 42, 20), palette.MUTED, ctx.fonts.small)
            pygame.draw.rect(ctx.screen, (8, 12, 22), track.inflate(0, 8), border_radius=8)
            pygame.draw.rect(ctx.screen, (48, 62, 92), track, border_radius=5)
            fill_w = int(track.w * value)
            if fill_w > 0:
                pygame.draw.rect(ctx.screen, color, pygame.Rect(track.x, track.y, fill_w, track.h), border_radius=5)
            knob_x = track.x + fill_w
            pygame.draw.circle(ctx.screen, (6, 10, 18), (knob_x, track.centery), 15)
            pygame.draw.circle(ctx.screen, color, (knob_x, track.centery), 11)

    def _camera_mode_label(self, ctx: RenderContext) -> str:
        if self.app.camera_distance >= 0.97:
            return ctx.text.tr("settings.camera_distance.near")
        if self.app.camera_distance <= 0.86:
            return ctx.text.tr("settings.camera_distance.far")
        return ctx.text.tr("settings.camera_distance.normal")

    def _footer(self, ctx: RenderContext, in_game: bool) -> None:
        if in_game:
            resume = self.app._settings_resume_rect()
            menu = self.app._settings_main_menu_rect()
            draw_button(ctx, resume, ctx.text.tr("settings.resume"), resume.collidepoint(ctx.mouse_pos))
            draw_button(ctx, menu, ctx.text.tr("settings.main_menu"), menu.collidepoint(ctx.mouse_pos))
        else:
            back = self.app._settings_back_rect()
            draw_button(ctx, back, ctx.text.tr("settings.back"), back.collidepoint(ctx.mouse_pos))

