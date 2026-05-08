from __future__ import annotations

from typing import Any

import pygame

from shared.items import RECIPES


class CraftingController:
    def __init__(self, app: Any) -> None:
        self.app = app

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.app.overlay_state.craft_open:
            return False
        pos = self.app._display_to_screen(event.pos) if hasattr(event, "pos") else self.app._mouse_pos()
        if event.type == pygame.MOUSEWHEEL:
            self.app._scroll_crafting(-event.y)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            self.app._scroll_crafting(-1 if event.button == 4 else 1)
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.app._craft_scroll_track_rect().collidepoint(pos):
                self.app._set_craft_scroll_from_pointer(pos[1])
                return True
            if self.app._craft_viewport_rect().collidepoint(pos):
                for index, recipe_key in enumerate(RECIPES):
                    if self.app._craft_recipe_rect(index).collidepoint(pos):
                        self.app.actions.push("craft", {"key": recipe_key})
                        return True
            return True
        return event.type in {pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP}

