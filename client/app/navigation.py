from __future__ import annotations

from typing import Literal


class AppNavigation:
    def __init__(self, app) -> None:
        self.app = app

    def go_menu(self) -> None:
        self.app._set_state("menu")

    def go_options(self) -> None:
        self.app._set_state("options")

    def go_single_setup(self) -> None:
        self.app._set_state("single_setup")

    def go_loading(self) -> None:
        self.app._set_state("single_loading")

    def go_servers(self) -> None:
        self.app._set_state("servers")

    def go_gameplay(self, mode: Literal["single", "online"]) -> None:
        self.app._set_state("single" if mode == "single" else "online_game")

    def quit(self) -> None:
        self.app.running = False
