from __future__ import annotations

from typing import Any

import pygame

from client.controllers.overlay_state import GameplayOverlayState
from shared.models import InputCommand, Vec2


class GameplayInputController:
    def __init__(self, app: Any) -> None:
        self.app = app

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type != pygame.KEYDOWN:
            return False
        key = event.key
        overlay: GameplayOverlayState = self.app.overlay_state
        if key == pygame.K_F3:
            self.app.show_perf_overlay = not self.app.show_perf_overlay
            return True
        if key == pygame.K_F4:
            self.app.detailed_perf_overlay = not self.app.detailed_perf_overlay
            self.app.show_perf_overlay = self.app.detailed_perf_overlay or self.app.show_perf_overlay
            return True
        if key == pygame.K_F8:
            self.app.toggle_gc_pacing()
            return True
        if key == pygame.K_F9:
            self.app.toggle_perf_logging()
            return True
        if key == pygame.K_ESCAPE:
            if overlay.weapon_custom_open:
                overlay.weapon_custom_open = False
            elif overlay.backpack_open or overlay.inventory_open or overlay.settings_open or overlay.craft_open:
                overlay.close_gameplay_overlays()
            else:
                overlay.settings_open = True
            return True
        if key in (pygame.K_i, pygame.K_b):
            opening = not overlay.backpack_open
            overlay.backpack_open = opening
            overlay.inventory_open = opening
            if opening:
                overlay.craft_open = False
                overlay.weapon_custom_open = False
                overlay.drag_source = None
            return True
        if key == pygame.K_o:
            overlay.settings_open = not overlay.settings_open
            return True
        if key == pygame.K_c:
            if overlay.weapon_custom_open:
                return True
            opening = not overlay.craft_open
            overlay.craft_open = opening
            if opening:
                overlay.backpack_open = False
                overlay.inventory_open = False
                overlay.drag_source = None
            return True
        if key == pygame.K_m:
            overlay.minimap_big = not overlay.minimap_big
            return True
        actions = {
            pygame.K_r: ("reload", {}),
            pygame.K_e: ("pickup", {}),
            pygame.K_f: ("interact", {}),
            pygame.K_q: ("toggle_utility", {}),
            pygame.K_SPACE: ("respawn", {}),
            pygame.K_g: ("throw_grenade", {}),
        }
        if key in actions:
            action_type, payload = actions[key]
            self.app.actions.push(action_type, payload)
            return True
        if key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6, pygame.K_7, pygame.K_8, pygame.K_9):
            self.app.actions.push("select_slot", {"slot": str(key - pygame.K_0)})
            return True
        if key == pygame.K_0:
            self.app.actions.push("select_slot", {"slot": "0"})
            return True
        return False

    def build_input_command(self, player_id: str) -> InputCommand:
        keys = pygame.key.get_pressed()
        move_x = float(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - float(keys[pygame.K_a] or keys[pygame.K_LEFT])
        move_y = float(keys[pygame.K_s] or keys[pygame.K_DOWN]) - float(keys[pygame.K_w] or keys[pygame.K_UP])
        overlay: GameplayOverlayState = self.app.overlay_state
        ui_open = overlay.backpack_open or overlay.settings_open or overlay.craft_open or overlay.weapon_custom_open
        if ui_open:
            move_x = 0.0
            move_y = 0.0
        snapshot = self.app._snapshot()
        player = self.app._local_player(snapshot) if snapshot else None
        mouse_world = self.app._mouse_world(player)
        mouse_buttons = pygame.mouse.get_pressed(num_buttons=3)
        right_pressed = bool(mouse_buttons[2])
        left_pressed = bool(mouse_buttons[0])
        has_weapon = bool(player and player.active_weapon())
        if player and left_pressed and not ui_open:
            self.app._maybe_play_empty_weapon_sound(player)
        if player and right_pressed:
            to_mouse = Vec2(mouse_world.x - player.pos.x, mouse_world.y - player.pos.y)
            if to_mouse.length() > 20:
                direction = to_mouse.normalized()
                move_x += direction.x
                move_y += direction.y
        return InputCommand(
            player_id=player_id,
            move_x=move_x,
            move_y=move_y,
            aim_x=mouse_world.x,
            aim_y=mouse_world.y,
            shooting=left_pressed and not ui_open,
            alt_attack=right_pressed and not has_weapon and not ui_open,
            sprint=keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT],
            sneak=keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL],
        )

