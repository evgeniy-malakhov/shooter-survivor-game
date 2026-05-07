from __future__ import annotations

import pygame

from client.settings_schema import (
    tab_has_audio_sliders,
    tab_has_camera_distance,
    tab_has_language,
    tab_is_stub,
    tab_toggle_keys,
)


class OptionsController:
    def __init__(self, app) -> None:
        self.app = app

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.navigation.go_menu()
            return True
        pos = self.app._display_to_screen(event.pos) if hasattr(event, "pos") else self.app._mouse_pos()
        if event.type == pygame.MOUSEWHEEL:
            self.app._scroll_options(-event.y)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.app._settings_audio_active():
            return self.app._begin_audio_slider_drag(pos)
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
        return False

    def click(self, pos: tuple[int, int]) -> None:
        app = self.app
        panel = app._settings_panel_rect()
        if app._settings_back_rect().collidepoint(pos):
            if app.name_editing:
                app._commit_player_name()
            app.navigation.go_menu()
            return
        for index, tab in enumerate(app.settings_tabs):
            rect = pygame.Rect(panel.x + 32 + index * 112, panel.y + 106, 102, 36)
            if rect.collidepoint(pos):
                app.settings_tab = tab
                app.options_scroll = 0
                return
        if tab_is_stub(app.settings_tab):
            return
        viewport = pygame.Rect(panel.x + 36, panel.y + 162, panel.w - 72, panel.h - 238)
        if not viewport.collidepoint(pos):
            return
        if tab_has_audio_sliders(app.settings_tab):
            app._begin_audio_slider_drag(pos)
            return
        options = tab_toggle_keys(app.settings_tab)
        option_x = viewport.x + 6
        option_width = viewport.w - 24
        for index, key in enumerate(options):
            rect = pygame.Rect(option_x, viewport.y + index * 56 - app.options_scroll, option_width, 44)
            if rect.collidepoint(pos):
                if key == "fullscreen":
                    app._toggle_fullscreen()
                else:
                    app.settings[key] = not app.settings[key]
                    app._save_client_settings()
                return
        row_index = len(options)
        if tab_has_camera_distance(app.settings_tab):
            camera_rect = pygame.Rect(option_x, viewport.y + row_index * 56 - app.options_scroll, option_width, 44)
            if camera_rect.collidepoint(pos):
                cycle = [1.0, 0.92, 0.84]
                nearest = min(cycle, key=lambda value: abs(value - app.camera_distance))
                app.camera_distance = cycle[(cycle.index(nearest) + 1) % len(cycle)]
                app._save_client_settings()
                return
            row_index += 1
        if tab_has_language(app.settings_tab):
            language_rect = pygame.Rect(option_x, viewport.y + row_index * 56 - app.options_scroll, option_width, 44)
            if language_rect.collidepoint(pos):
                languages = sorted(app.locales)
                app.language = languages[(languages.index(app.language) + 1) % len(languages)]
                app._save_client_settings()

