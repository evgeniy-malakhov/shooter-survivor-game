from __future__ import annotations

from typing import Any

import pygame

from shared.constants import WEAPONS


class InventoryController:
    def __init__(self, app: Any) -> None:
        self.app = app

    def handle_event(self, event: pygame.event.Event) -> bool:
        overlay = self.app.overlay_state
        if not overlay.backpack_open:
            return False
        pos = self.app._display_to_screen(event.pos) if hasattr(event, "pos") else self.app._mouse_pos()
        snapshot = self.app._snapshot()
        player = self.app._local_player(snapshot) if snapshot else None
        if event.type == pygame.MOUSEBUTTONDOWN:
            if overlay.weapon_custom_open:
                return False
            if event.button == 1 and self.app._customize_button_rect().collidepoint(pos):
                overlay.custom_weapon_slot = self.app._custom_weapon_slot(player)
                overlay.weapon_custom_open = True
                overlay.weapon_modules_scroll = 0
                overlay.drag_source = None
                return True
            repair_slot = self.app._repair_slot_at(pos)
            if repair_slot:
                self.app.actions.push("repair", {"slot": repair_slot})
                return True
            if event.button == 1:
                overlay.drag_source = self.app._inventory_target_at(pos, player)
                return True
            if event.button == 3:
                target = self.app._inventory_target_at(pos, player)
                if target and target.get("source") == "backpack":
                    self.app.actions.push("inventory_action", {"type": "use", "index": target["index"]})
                    return True
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and overlay.drag_source:
            target = self.app._inventory_target_at(pos, player)
            drop_rect = self.app._drop_rect()
            outside_panel = not self.app._backpack_panel_rect().collidepoint(pos)
            should_drop = bool(self.app._dragged_payload(player) and (drop_rect.collidepoint(pos) or outside_panel))
            if target:
                action = self.move_action(player, overlay.drag_source, target)
                if action:
                    self.app.actions.push("inventory_action", action)
            elif should_drop:
                action = {"type": "drop", "source": overlay.drag_source["source"]}
                if overlay.drag_source["source"] == "backpack":
                    action["index"] = overlay.drag_source["index"]
                elif overlay.drag_source["source"] == "weapon_module":
                    action["slot"] = overlay.drag_source["slot"]
                    action["module_slot"] = overlay.drag_source["module_slot"]
                else:
                    action["slot"] = overlay.drag_source["slot"]
                self.app.actions.push("inventory_action", action)
            overlay.drag_source = None
            return True
        return event.type in {pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION}

    def move_action(self, player: Any, source: dict[str, object], target: dict[str, object]) -> dict[str, object] | None:
        if target["source"] == "module_return" and source["source"] == "weapon_module":
            return {"type": "unequip_module", "slot": source["slot"], "module_slot": source["module_slot"]}
        if target["source"] == "module_return":
            return None
        if self.app._is_repair_drag(player, source):
            return self.app._repair_drag_action(source, target)
        if source["source"] == "weapon_slot" and target["source"] == "weapon_slot":
            return {"type": "quick_swap", "a": source["slot"], "b": target["slot"]}
        payload = self.app._dragged_payload(player)
        payload_key = payload[0] if payload else ""
        dst = "weapon_slot" if target["source"] == "weapon_slot" and payload_key in WEAPONS else "quick_item" if target["source"] == "weapon_slot" else target["source"]
        action: dict[str, object] = {"type": "move", "src": source["source"], "dst": dst}
        if source["source"] == "backpack":
            action["src_index"] = source["index"]
        elif source["source"] == "weapon_module":
            action["src_slot"] = source["slot"]
            action["src_module"] = source["module_slot"]
        else:
            action["src_slot"] = source["slot"]
        if dst == "backpack":
            action["dst_index"] = target["index"]
        elif dst == "weapon_module":
            action["dst_slot"] = target["slot"]
            action["dst_module"] = target["module_slot"]
        elif dst in {"equipment", "quick_item"}:
            action["dst_slot"] = target["slot"]
        return action
