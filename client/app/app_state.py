from __future__ import annotations

from enum import Enum


class AppState(str, Enum):
    MENU = "menu"
    SINGLE_SETUP = "single_setup"
    SINGLE_LOADING = "single_loading"
    OPTIONS = "options"
    SERVERS = "servers"
    SINGLE = "single"
    ONLINE_GAME = "online_game"

    @property
    def is_gameplay(self) -> bool:
        return self in {AppState.SINGLE, AppState.ONLINE_GAME}

    @property
    def uses_menu_music(self) -> bool:
        return self in {
            AppState.MENU,
            AppState.OPTIONS,
            AppState.SINGLE_SETUP,
            AppState.SINGLE_LOADING,
            AppState.SERVERS,
        }


def normalize_app_state(value: str | AppState) -> AppState:
    if isinstance(value, AppState):
        return value
    try:
        return AppState(str(value))
    except ValueError:
        return AppState.MENU
