from __future__ import annotations

from typing import Any

import pygame

from shared.constants import SLOTS
from shared.weapon_modules import WEAPON_MODULES


class WeaponCustomController:
    def __init__(self, app: Any) -> None:
        self.app = app

    def handle_event(self, event: pygame.event.Event) -> bool:
        overlay = self.app.overlay_state
        if not overlay.weapon_custom_open:
            return False
        pos = self.app._display_to_screen(event.pos) if hasattr(event, "pos") else self.app._mouse_pos()
        snapshot = self.app._snapshot()
        player = self.app._local_player(snapshot) if snapshot else None
        if event.type == pygame.MOUSEWHEEL:
            if self.app._weapon_module_viewport_rect().collidepoint(self.app._mouse_pos()):
                self.app._scroll_weapon_modules(-event.y)
                return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            if self.app._weapon_module_viewport_rect().collidepoint(pos):
                self.app._scroll_weapon_modules(-1 if event.button == 4 else 1)
                return True
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return event.type in {pygame.MOUSEBUTTONDOWN, pygame.MOUSEWHEEL}
        if self.app._weapon_custom_close_rect().collidepoint(pos):
            overlay.weapon_custom_open = False
            overlay.drag_source = None
            return True
        if not player:
            return True
        for index, slot in enumerate(SLOTS):
            if self.app._weapon_custom_slot_rect(index).collidepoint(pos) and player.weapons.get(slot):
                overlay.custom_weapon_slot = slot
                return True
        weapon_slot = self.app._custom_weapon_slot(player)
        viewport = self.app._weapon_module_viewport_rect()
        for module_key, indices in self.app._available_module_groups(player):
            rect = self.app._available_module_rect(module_key)
            module = WEAPON_MODULES.get(module_key)
            if viewport.collidepoint(pos) and rect.collidepoint(pos) and module and indices and player.weapons.get(weapon_slot):
                self.app.actions.push(
                    "inventory_action",
                    {
                        "type": "move",
                        "src": "backpack",
                        "dst": "weapon_module",
                        "src_index": indices[0],
                        "dst_slot": weapon_slot,
                        "dst_module": module.slot,
                    },
                )
                return True
        return True
