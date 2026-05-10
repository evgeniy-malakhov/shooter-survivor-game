from __future__ import annotations

import pygame

from client.game.loading_service import LoadingService
from client.single_setup_schema import DENSITY_ORDER
from shared.game_modes import get_game_mode


class SingleSetupController:
    def __init__(self, app) -> None:
        self.app = app
        self.loading = LoadingService(app)

    def update(self, dt: float) -> None:
        target = 1.0 if self.app.single_map_dropdown_open else 0.0
        self.app.single_map_dropdown_alpha += (target - self.app.single_map_dropdown_alpha) * min(1.0, dt * 8.0)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.single_map_dropdown_open = False
            self.app.navigation.go_menu()
            return True
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return False
        self.click(self.app._display_to_screen(event.pos))
        return True

    def click(self, pos: tuple[int, int]) -> None:
        app = self.app
        panel = pygame.Rect((1280 - 700) // 2, 90, 700, 590)
        back_rect = pygame.Rect(panel.x + 56, panel.bottom - 72, 230, 46)
        start_rect = pygame.Rect(panel.right - 286, panel.bottom - 72, 230, 46)
        if back_rect.collidepoint(pos):
            app.single_map_dropdown_open = False
            app.navigation.go_menu()
            return
        if start_rect.collidepoint(pos):
            app.single_map_dropdown_open = False
            self.loading.start_single_player()
            return
        rows = [pygame.Rect(panel.x + 56, panel.y + 120 + index * 58, panel.w - 112, 46) for index in range(6)]
        if rows[0].collidepoint(pos):
            app.single_map_dropdown_open = not app.single_map_dropdown_open
            return
        if app.single_map_dropdown_open:
            options = list(app.single_map_options)
            popup = pygame.Rect(rows[0].x, rows[0].bottom + 6, rows[0].w, max(58, 20 + len(options) * 32))
            for index, option in enumerate(options):
                if pygame.Rect(popup.x + 10, popup.y + 10 + index * 32, popup.w - 30, 26).collidepoint(pos):
                    app.single_map_key = option
                    app._save_client_settings()
                    break
            app.single_map_dropdown_open = False
            if popup.collidepoint(pos):
                return
        if rows[1].collidepoint(pos):
            options = list(app.single_game_mode_options)
            idx = options.index(app.single_game_mode_key)
            app.single_game_mode_key = options[(idx + 1) % len(options)]
            mode = get_game_mode(app.single_game_mode_key)
            if app.single_player_faction not in mode.player_factions:
                app.single_player_faction = mode.default_player_faction
        elif rows[2].collidepoint(pos):
            mode = get_game_mode(app.single_game_mode_key)
            factions = list(mode.player_factions)
            if len(factions) > 1:
                idx = factions.index(app.single_player_faction)
                app.single_player_faction = factions[(idx + 1) % len(factions)]
        elif rows[3].collidepoint(pos) and app.single_bots_enabled:
            idx = app.difficulty_options.index(app.difficulty_key)
            app.difficulty_key = app.difficulty_options[(idx + 1) % len(app.difficulty_options)]
        elif rows[4].collidepoint(pos):
            app.single_bots_enabled = not app.single_bots_enabled
        elif rows[5].collidepoint(pos) and app.single_bots_enabled:
            app.bot_density = DENSITY_ORDER[(DENSITY_ORDER.index(app.bot_density) + 1) % len(DENSITY_ORDER)]
        app._save_client_settings()


