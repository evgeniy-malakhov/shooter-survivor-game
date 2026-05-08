from __future__ import annotations

import threading
import time

import pygame

from client.network import ping_server


class ServerBrowserController:
    def __init__(self, app) -> None:
        self.app = app

    def refresh_initial(self) -> None:
        self.app.server_entries = self.app._load_servers()
        self.app.selected_server = 0
        self.refresh_pings()

    def update(self, dt: float) -> None:
        if time.time() - self.app._last_ping_refresh > 4.0:
            self.refresh_pings()

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.navigation.go_menu()
            return True
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return False
        self.click(self.app._display_to_screen(event.pos))
        return True

    def click(self, pos: tuple[int, int]) -> None:
        app = self.app
        if pygame.Rect(72, 632, 180, 46).collidepoint(pos):
            app.navigation.go_menu()
            return
        if pygame.Rect(270, 632, 180, 46).collidepoint(pos):
            self.refresh_pings()
            return
        if pygame.Rect(470, 632, 180, 46).collidepoint(pos):
            self.connect_selected()
            return
        for index, _entry in enumerate(app.server_entries):
            if pygame.Rect(72, 190 + index * 72, 720, 56).collidepoint(pos):
                app.selected_server = index

    def connect_selected(self) -> None:
        app = self.app
        if not app.server_entries:
            return
        entry = app.server_entries[app.selected_server]
        try:
            app.online.connect(entry.host, entry.port, app.player_name)
            if app.world:
                app.world.close()
            app.world = None
            app.overlay_state.close_gameplay_overlays()
            app._reset_death_effect_tracking()
            app.navigation.go_gameplay("online")
        except OSError as exc:
            entry.status = f"error: {exc}"

    def refresh_pings(self) -> None:
        app = self.app
        if app._pinging:
            return
        app._pinging = True
        app._last_ping_refresh = time.time()

        def worker() -> None:
            try:
                for entry in app.server_entries:
                    entry.status = "checking"
                    ping, meta = ping_server(entry.host, entry.port)
                    entry.ping_ms = ping
                    entry.players = int(meta.get("players", 0)) if meta else 0
                    entry.max_players = int(meta.get("max_players", 0)) if meta else 0
                    entry.ready = bool(meta.get("ready", False)) if meta else False
                    entry.difficulty = str(meta.get("difficulty", entry.difficulty)) if meta else entry.difficulty
                    entry.mode = str(meta.get("mode", entry.mode)) if meta else entry.mode
                    entry.pvp = bool(meta.get("pvp", entry.pvp) or entry.mode == "pvp") if meta else entry.pvp
                    entry.status = "ready" if ping is not None and entry.ready else "online" if ping is not None else "offline"
            finally:
                app._pinging = False

        threading.Thread(target=worker, name="server-ping", daemon=True).start()

