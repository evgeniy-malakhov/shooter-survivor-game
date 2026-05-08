from __future__ import annotations

from typing import Any

import pygame

from client.settings_schema import (
    tab_has_audio_sliders,
    tab_has_camera_distance,
    tab_has_graphics_quality,
    tab_has_language,
    tab_is_stub,
    tab_toggle_keys,
)


class PauseSettingsController:
    def __init__(self, app: Any) -> None:
        self.app = app

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.app.overlay_state.settings_open:
            return False
        pos = self.app._display_to_screen(event.pos) if hasattr(event, "pos") else self.app._mouse_pos()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.app._settings_audio_active():
            if self.app._begin_audio_slider_drag(pos):
                return True
        if event.type == pygame.MOUSEMOTION and self.app._dragging_audio_slider:
            self.app._update_audio_slider_from_pos(self.app._dragging_audio_slider, pos, save=False)
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.app._dragging_audio_slider:
                self.app._update_audio_slider_from_pos(self.app._dragging_audio_slider, pos, save=True)
                self.app._dragging_audio_slider = None
                return True
            self.click(pos)
            return True
        if event.type == pygame.MOUSEWHEEL:
            self.app._scroll_options(-event.y)
            return True
        return event.type in {pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION}

    def click(self, pos: tuple[int, int]) -> None:
        if self.app._settings_resume_rect().collidepoint(pos):
            self.app.overlay_state.settings_open = False
            return
        if self.app._settings_main_menu_rect().collidepoint(pos):
            self.app._back_to_menu()
            return
        panel = self.app._settings_panel_rect()
        for index, tab in enumerate(self.app.settings_tabs):
            rect = pygame.Rect(panel.x + 32 + index * 112, panel.y + 106, 102, 36)
            if rect.collidepoint(pos):
                self.app.settings_tab = tab
                self.app.options_scroll = 0
                return
        self.options_click(pos)

    def options_click(self, pos: tuple[int, int]) -> None:
        panel = self.app._settings_panel_rect()
        if self.app._settings_back_rect().collidepoint(pos):
            if self.app.name_editing:
                self.app._commit_player_name()
            self.app._set_state("menu")
            return
        if tab_is_stub(self.app.settings_tab):
            return
        viewport = pygame.Rect(panel.x + 36, panel.y + 162, panel.w - 72, panel.h - 238)
        if not viewport.collidepoint(pos):
            return
        if tab_has_audio_sliders(self.app.settings_tab):
            self.app._begin_audio_slider_drag(pos)
            return
        options = tab_toggle_keys(self.app.settings_tab)
        option_x = viewport.x + 6
        option_width = viewport.w - 24
        for index, key in enumerate(options):
            rect = pygame.Rect(option_x, viewport.y + index * 56 - self.app.options_scroll, option_width, 44)
            if rect.collidepoint(pos):
                if key == "fullscreen":
                    self.app._toggle_fullscreen()
                else:
                    self.app.settings[key] = not self.app.settings[key]
                    self.app._save_client_settings()
                return
        row_index = len(options)
        if tab_has_camera_distance(self.app.settings_tab):
            camera_rect = pygame.Rect(option_x, viewport.y + row_index * 56 - self.app.options_scroll, option_width, 44)
            if camera_rect.collidepoint(pos):
                cycle = [1.0, 0.92, 0.84]
                nearest = min(cycle, key=lambda value: abs(value - self.app.camera_distance))
                self.app.camera_distance = cycle[(cycle.index(nearest) + 1) % len(cycle)]
                self.app._save_client_settings()
                return
            row_index += 1
        if tab_has_graphics_quality(self.app.settings_tab):
            quality_rect = pygame.Rect(option_x, viewport.y + row_index * 56 - self.app.options_scroll, option_width, 44)
            if quality_rect.collidepoint(pos):
                self.app._cycle_graphics_quality()
                return
            row_index += 1
        if tab_has_language(self.app.settings_tab):
            language_rect = pygame.Rect(option_x, viewport.y + row_index * 56 - self.app.options_scroll, option_width, 44)
            if language_rect.collidepoint(pos):
                languages = sorted(self.app.locales)
                self.app.language = languages[(languages.index(self.app.language) + 1) % len(languages)]
                self.app._save_client_settings()

