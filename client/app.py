from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pygame

from client.network import OnlineClient, ping_server
from shared.constants import ARMORS, MAP_HEIGHT, MAP_WIDTH, SLOTS, WEAPONS, ZOMBIES
from shared.crafting import craft_rarity_chances
from shared.difficulty import DIFFICULTY_KEYS, load_difficulty
from shared.explosives import GRENADE_SPECS, DEFAULT_GRENADE
from shared.items import EQUIPMENT_SLOTS, ITEMS, RECIPES
from shared.level import tunnel_segments
from shared.models import BuildingState, InputCommand, LootState, PlayerState, RectState, Vec2, WorldSnapshot
from shared.rarities import RARITY_KEYS, rarity_color, rarity_rank, rarity_spec
from shared.simulation import GameWorld
from shared.weapon_modules import WEAPON_MODULES, WEAPON_MODULE_SLOTS


SCREEN_W = 1280
SCREEN_H = 760
MIN_WINDOW_W = 960
MIN_WINDOW_H = 570
FPS = 60
ROOT = Path(__file__).resolve().parents[1]
ICON_MAPPING_PATH = ROOT / "configs" / "icon_mapping.json"
CLIENT_SETTINGS_PATH = ROOT / "client_settings.json"

BG = (9, 12, 22)
PANEL = (19, 25, 42)
PANEL_2 = (28, 37, 62)
TEXT = (232, 239, 255)
MUTED = (139, 156, 188)
CYAN = (76, 225, 255)
GREEN = (120, 240, 164)
RED = (255, 91, 111)
YELLOW = (255, 210, 112)
PURPLE = (177, 132, 255)

DEFAULT_ICON_MAPPING = {
    "grenade": "granade",
    "gunpowder": "gun_powder",
    "duct_tape": "dust_type",
    "medicine": "medkit",
    "medkit": "medkit",
    "ammo": "ammo_pack",
    "armor": "light_torso",
    "light_head": "light_helmet",
    "light": "light_torso",
    "medium": "medium_torso",
    "tactical": "tactical_vest",
    "heavy": "heavy_torso",
}


@dataclass(slots=True)
class Button:
    rect: pygame.Rect
    label: str
    action: str

    def hovered(self, mouse: tuple[int, int]) -> bool:
        return self.rect.collidepoint(mouse)


@dataclass(slots=True)
class ServerEntry:
    name: str
    host: str
    port: int
    ping_ms: float | None = None
    players: int = 0
    status: str = "checking"
    difficulty: str = "medium"


class GameApp:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Neon Outbreak")
        self.fullscreen = False
        self.windowed_size = (SCREEN_W, SCREEN_H)
        self.display = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        self.screen = pygame.Surface((SCREEN_W, SCREEN_H)).convert()
        self.render_rect = pygame.Rect(0, 0, SCREEN_W, SCREEN_H)
        self.render_scale = 1.0
        self._update_display_transform()
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("segoeui", 18)
        self.small = pygame.font.SysFont("segoeui", 14)
        self.big = pygame.font.SysFont("segoeui", 56, bold=True)
        self.mid = pygame.font.SysFont("segoeui", 26, bold=True)
        self.language = "en"
        self.locales = self._load_locales()
        self.icon_mapping = self._load_icon_mapping()
        self.item_images = self._load_item_images()
        self._icon_cache: dict[tuple[str, int, int], pygame.Surface] = {}
        self.damage_flash = 0.0
        self._last_local_health: float | None = None
        self.camera_zoom = 1.0
        self.state = "menu"
        saved_settings = self._load_client_settings()
        self.player_name = self._clean_player_name(str(saved_settings.get("player_name", "Operator")))
        self.name_editing = False
        self.name_input = self.player_name
        self.world: GameWorld | None = None
        self.local_player_id: str | None = None
        self.online = OnlineClient()
        self.inventory_open = False
        self.backpack_open = False
        self.settings_open = False
        self.craft_open = False
        self.weapon_custom_open = False
        self.minimap_big = False
        self.craft_scroll = 0
        self.running = True
        self.pending_reload = False
        self.pending_pickup = False
        self.pending_medkit = False
        self.pending_interact = False
        self.pending_respawn = False
        self.pending_throw_grenade = False
        self.pending_toggle_utility = False
        self.pending_inventory_action: dict[str, object] | None = None
        self.pending_craft_key: str | None = None
        self.pending_repair_slot: str | None = None
        self.pending_slot: str | None = None
        self.pending_equip_armor: str | None = None
        self.drag_source: dict[str, object] | None = None
        self.custom_weapon_slot = "1"
        self.settings = {
            "bot_vision": True,
            "bot_vision_range": True,
            "ai_reactions": True,
            "health_bars": True,
            "noise_radius": True,
            "show_zombie_count": bool(saved_settings.get("show_zombie_count", False)),
            "fullscreen": False,
        }
        self.bot_density = "normal"
        self.bot_density_profiles = {
            "low": 0.65,
            "normal": 1.0,
            "high": 1.42,
        }
        self.difficulty_key = "medium"
        self.difficulty_options = list(DIFFICULTY_KEYS)
        self.server_entries: list[ServerEntry] = []
        self.selected_server = 0
        self._last_ping_refresh = 0.0
        self._pinging = False
        # Create responsive menu buttons with proper centering
        self._menu_buttons = self._create_menu_buttons()

    def _create_menu_buttons(self) -> list[Button]:
        """Create menu buttons with responsive positioning"""
        button_width = 320
        button_height = 56
        button_spacing = 20
        panel_width = 420
        panel_height = 580
        panel_x = 48
        panel_y = (SCREEN_H - panel_height) // 2

        button_x = panel_x + (panel_width - button_width) // 2  # Center buttons in panel
        start_y = panel_y + 200  # Start below title and subtitle

        return [
            Button(pygame.Rect(button_x, start_y, button_width, button_height), "menu.single", "single"),
            Button(pygame.Rect(button_x, start_y + (button_height + button_spacing), button_width, button_height), "menu.online", "online"),
            Button(pygame.Rect(button_x, start_y + 2 * (button_height + button_spacing), button_width, button_height), "menu.settings", "options"),
            Button(pygame.Rect(button_x, start_y + 3 * (button_height + button_spacing), button_width, button_height), "menu.quit", "quit"),
        ]

    def _load_locales(self) -> dict[str, dict[str, str]]:
        locales: dict[str, dict[str, str]] = {}
        for path in (ROOT / "locales").glob("*.json"):
            locales[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        return locales or {"en": {}}

    def _load_client_settings(self) -> dict[str, object]:
        if not CLIENT_SETTINGS_PATH.exists():
            return {}
        try:
            data = json.loads(CLIENT_SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save_client_settings(self) -> None:
        data = {
            "player_name": self.player_name,
            "show_zombie_count": bool(self.settings.get("show_zombie_count", False)),
        }
        try:
            CLIENT_SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _clean_player_name(self, name: str) -> str:
        cleaned = " ".join(name.strip().split())
        return (cleaned or "Operator")[:18]

    def _commit_player_name(self) -> None:
        self.player_name = self._clean_player_name(self.name_input)
        self.name_input = self.player_name
        self.name_editing = False
        if self.state == "single" and self.world and self.local_player_id:
            self.world.rename_player(self.local_player_id, self.player_name)
        elif self.state == "online_game" and self.online.player_id:
            self.online.send_profile_name(self.player_name)
        self._save_client_settings()

    def tr(self, key: str, **values: object) -> str:
        text = self.locales.get(self.language, {}).get(key) or self.locales.get("en", {}).get(key) or key
        return text.format(**values) if values else text

    def _load_icon_mapping(self) -> dict[str, str]:
        mapping = dict(DEFAULT_ICON_MAPPING)
        if not ICON_MAPPING_PATH.exists():
            return mapping
        try:
            raw = json.loads(ICON_MAPPING_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return mapping
        if not isinstance(raw, dict):
            return mapping
        for key, value in raw.items():
            image_key = Path(str(value)).stem
            if image_key:
                mapping[str(key)] = image_key
        return mapping

    def _load_item_images(self) -> dict[str, pygame.Surface]:
        images: dict[str, pygame.Surface] = {}
        image_dir = ROOT / "images"
        for path in image_dir.glob("*.png"):
            if path.exists():
                try:
                    images[path.stem] = self._load_alpha_image(path)
                except pygame.error:
                    pass
        for key, image_key in self.icon_mapping.items():
            path = image_dir / f"{image_key}.png"
            if not path.exists():
                continue
            try:
                images[key] = self._load_alpha_image(path)
            except pygame.error:
                pass
        return images

    def _load_alpha_image(self, path: Path) -> pygame.Surface:
        image = pygame.image.load(str(path))
        return image.convert_alpha()

    def item_title(self, key: str) -> str:
        if key in WEAPONS:
            return self.weapon_title(key)
        return self.tr(f"item.{key}") if self.tr(f"item.{key}") != f"item.{key}" else ITEMS.get(key).title if key in ITEMS else key

    def weapon_title(self, key: str) -> str:
        return self.tr(f"weapon.{key}") if self.tr(f"weapon.{key}") != f"weapon.{key}" else WEAPONS.get(key).title if key in WEAPONS else key

    def recipe_title(self, key: str) -> str:
        return self.tr(f"recipe.{key}") if self.tr(f"recipe.{key}") != f"recipe.{key}" else RECIPES[key].title

    def rarity_title(self, key: str) -> str:
        localized = self.tr(f"rarity.{key}")
        return localized if localized != f"rarity.{key}" else rarity_spec(key).title

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self._handle_events()
            self._update(dt)
            self._draw()
        if self.world:
            self.world.close()
        self.online.close()
        pygame.quit()

    def _set_display_mode(self, fullscreen: bool) -> None:
        if fullscreen:
            desktop_sizes = pygame.display.get_desktop_sizes() if hasattr(pygame.display, "get_desktop_sizes") else []
            if desktop_sizes:
                size = desktop_sizes[0]
            else:
                info = pygame.display.Info()
                size = (max(1, info.current_w), max(1, info.current_h))
            self.display = pygame.display.set_mode(size, pygame.FULLSCREEN)
        else:
            width = max(MIN_WINDOW_W, int(self.windowed_size[0]))
            height = max(MIN_WINDOW_H, int(self.windowed_size[1]))
            self.windowed_size = (width, height)
            self.display = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        self.fullscreen = fullscreen
        self.settings["fullscreen"] = fullscreen
        self._update_display_transform()

    def _toggle_fullscreen(self) -> None:
        self._set_display_mode(not self.fullscreen)

    def _update_display_transform(self) -> None:
        display_w, display_h = self.display.get_size()
        scale = min(display_w / SCREEN_W, display_h / SCREEN_H)
        self.render_scale = max(0.1, scale)
        render_w = max(1, int(SCREEN_W * self.render_scale))
        render_h = max(1, int(SCREEN_H * self.render_scale))
        self.render_rect = pygame.Rect((display_w - render_w) // 2, (display_h - render_h) // 2, render_w, render_h)

    def _display_to_screen(self, pos: tuple[int, int]) -> tuple[int, int]:
        x = int((pos[0] - self.render_rect.x) / self.render_scale)
        y = int((pos[1] - self.render_rect.y) / self.render_scale)
        return x, y

    def _mouse_pos(self) -> tuple[int, int]:
        return self._display_to_screen(pygame.mouse.get_pos())

    def _present(self) -> None:
        self.display.fill((0, 0, 0))
        if self.render_rect.size == (SCREEN_W, SCREEN_H):
            self.display.blit(self.screen, self.render_rect)
        else:
            scaled = pygame.transform.smoothscale(self.screen, self.render_rect.size)
            self.display.blit(scaled, self.render_rect)
        pygame.display.flip()

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.VIDEORESIZE and not self.fullscreen:
                width = max(MIN_WINDOW_W, int(event.w))
                height = max(MIN_WINDOW_H, int(event.h))
                self.windowed_size = (width, height)
                self.display = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
                self._update_display_transform()
            elif event.type == pygame.KEYDOWN:
                self._handle_keydown(event)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self._handle_mouse_down(event)
            elif event.type == pygame.MOUSEBUTTONUP:
                self._handle_mouse_up(event)
            elif event.type == pygame.MOUSEWHEEL:
                self._handle_mouse_wheel(event)

    def _handle_keydown(self, event: pygame.event.Event) -> None:
        key = event.key
        if self.name_editing:
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._commit_player_name()
            elif key == pygame.K_ESCAPE:
                self.name_input = self.player_name
                self.name_editing = False
            elif key == pygame.K_BACKSPACE:
                self.name_input = self.name_input[:-1]
            elif len(self.name_input) < 18 and event.unicode and event.unicode.isprintable():
                self.name_input += event.unicode
            return
        if key == pygame.K_ESCAPE:
            if self.weapon_custom_open:
                self.weapon_custom_open = False
            elif self.backpack_open or self.inventory_open or self.settings_open or self.craft_open:
                self.backpack_open = False
                self.inventory_open = False
                self.settings_open = False
                self.craft_open = False
            elif self.state == "servers":
                self._back_to_menu()
            elif self.state == "options":
                self.state = "menu"
            elif self.state in {"single", "online_game"}:
                self.settings_open = True
            return
        if self.state not in {"single", "online_game"}:
            return
        if key in (pygame.K_i, pygame.K_b):
            opening = not self.backpack_open
            self.backpack_open = opening
            self.inventory_open = opening
            if opening:
                self.craft_open = False
                self.weapon_custom_open = False
                self.drag_source = None
        elif key == pygame.K_o:
            self.settings_open = not self.settings_open
        elif key == pygame.K_c:
            if self.weapon_custom_open:
                return
            opening = not self.craft_open
            self.craft_open = opening
            if opening:
                self.backpack_open = False
                self.inventory_open = False
                self.drag_source = None
        elif key == pygame.K_r:
            self.pending_reload = True
        elif key == pygame.K_e:
            self.pending_pickup = True
        elif key == pygame.K_f:
            self.pending_interact = True
        elif key == pygame.K_q:
            self.pending_toggle_utility = True
        elif key == pygame.K_SPACE:
            self.pending_respawn = True
        elif key == pygame.K_g:
            self.pending_throw_grenade = True
        elif key == pygame.K_m:
            self.minimap_big = not self.minimap_big
        elif key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6, pygame.K_7, pygame.K_8, pygame.K_9):
            self.pending_slot = str(key - pygame.K_0)
        elif key == pygame.K_0:
            self.pending_slot = "0"

    def _handle_mouse_down(self, event: pygame.event.Event) -> None:
        pos = self._display_to_screen(event.pos)
        if self.craft_open and event.button in (4, 5):
            self._scroll_crafting(-1 if event.button == 4 else 1)
            return
        if self.backpack_open and self.state in {"single", "online_game"}:
            snapshot = self._snapshot()
            player = self._local_player(snapshot) if snapshot else None
            if self.weapon_custom_open:
                if event.button == 1 and self._handle_weapon_custom_click(pos, player):
                    return
                if event.button == 1:
                    self.drag_source = self._inventory_target_at(pos, player)
                return
            elif event.button == 1 and self._customize_button_rect().collidepoint(pos):
                self.custom_weapon_slot = self._custom_weapon_slot(player)
                self.weapon_custom_open = True
                self.drag_source = None
                return
            repair_slot = self._repair_slot_at(pos)
            if repair_slot:
                self.pending_repair_slot = repair_slot
                return
            if event.button == 1:
                self.drag_source = self._inventory_target_at(pos, player)
            elif event.button == 3:
                target = self._inventory_target_at(pos, player)
                if target and target.get("source") == "backpack":
                    self.pending_inventory_action = {"type": "use", "index": target["index"]}
            return
        if event.button == 1:
            self._handle_click(pos)

    def _handle_mouse_up(self, event: pygame.event.Event) -> None:
        if event.button != 1:
            return
        pos = self._display_to_screen(event.pos)
        if self.settings_open:
            self._handle_settings_click(pos)
            return
        if self.craft_open:
            self._handle_craft_click(pos)
            return
        if self.backpack_open and self.drag_source:
            snapshot = self._snapshot()
            player = self._local_player(snapshot) if snapshot else None
            target = self._inventory_target_at(pos, player)
            drop_rect = self._drop_rect()
            outside_panel = not self._backpack_panel_rect().collidepoint(pos)
            should_drop = bool(self._dragged_payload(player) and (drop_rect.collidepoint(pos) or outside_panel))
            if target:
                if target["source"] == "module_return" and self.drag_source["source"] == "weapon_module":
                    self.pending_inventory_action = {
                        "type": "unequip_module",
                        "slot": self.drag_source["slot"],
                        "module_slot": self.drag_source["module_slot"],
                    }
                elif target["source"] == "module_return":
                    pass
                elif self._is_repair_drag(player, self.drag_source):
                    self.pending_inventory_action = self._repair_drag_action(self.drag_source, target)
                elif self.drag_source["source"] == "weapon_slot" and target["source"] == "weapon_slot":
                    self.pending_inventory_action = {"type": "quick_swap", "a": self.drag_source["slot"], "b": target["slot"]}
                else:
                    payload = self._dragged_payload(player)
                    payload_key = payload[0] if payload else ""
                    dst = "weapon_slot" if target["source"] == "weapon_slot" and payload_key in WEAPONS else "quick_item" if target["source"] == "weapon_slot" else target["source"]
                    action = {"type": "move", "src": self.drag_source["source"], "dst": dst}
                    if self.drag_source["source"] == "backpack":
                        action["src_index"] = self.drag_source["index"]
                    elif self.drag_source["source"] == "weapon_module":
                        action["src_slot"] = self.drag_source["slot"]
                        action["src_module"] = self.drag_source["module_slot"]
                    else:
                        action["src_slot"] = self.drag_source["slot"]
                    if dst == "backpack":
                        action["dst_index"] = target["index"]
                    elif dst == "weapon_module":
                        action["dst_slot"] = target["slot"]
                        action["dst_module"] = target["module_slot"]
                    elif dst in {"equipment", "quick_item"}:
                        action["dst_slot"] = target["slot"]
                    self.pending_inventory_action = action
            elif should_drop:
                action = {"type": "drop", "source": self.drag_source["source"]}
                if self.drag_source["source"] == "backpack":
                    action["index"] = self.drag_source["index"]
                elif self.drag_source["source"] == "weapon_module":
                    action["slot"] = self.drag_source["slot"]
                    action["module_slot"] = self.drag_source["module_slot"]
                else:
                    action["slot"] = self.drag_source["slot"]
                self.pending_inventory_action = action
            self.drag_source = None

    def _handle_mouse_wheel(self, event: pygame.event.Event) -> None:
        if self.craft_open:
            self._scroll_crafting(-event.y)

    def _handle_click(self, pos: tuple[int, int]) -> None:
        if self.state == "menu":
            for button in self._menu_buttons:
                if button.hovered(pos):
                    if button.action == "single":
                        self._start_single_player()
                    elif button.action == "online":
                        self._show_servers()
                    elif button.action == "options":
                        self.state = "options"
                    elif button.action == "quit":
                        self.running = False
        elif self.state == "options":
            self._handle_settings_click(pos)
        elif self.state == "servers":
            self._handle_server_click(pos)
        elif self.inventory_open and self.state in {"single", "online_game"}:
            self._handle_inventory_click(pos)

    def _handle_settings_click(self, pos: tuple[int, int]) -> None:
        if self.state == "options" and self._settings_back_rect().collidepoint(pos):
            if self.name_editing:
                self._commit_player_name()
            self.state = "menu"
            return
        if self.state in {"single", "online_game"}:
            if self._settings_resume_rect().collidepoint(pos):
                if self.name_editing:
                    self._commit_player_name()
                self.settings_open = False
                return
            if self._settings_main_menu_rect().collidepoint(pos):
                if self.name_editing:
                    self._commit_player_name()
                self._back_to_menu()
                return
        if self._settings_name_rect().collidepoint(pos):
            self.name_editing = True
            self.name_input = self.player_name
            return
        if self.name_editing:
            self._commit_player_name()
        options = list(self.settings)
        start_y, step_y = self._settings_grid()
        panel = self._settings_panel_rect()
        option_width = 400
        option_height = 40
        option_x = panel.x + (panel.w - option_width) // 2
        for index, key in enumerate(options):
            rect = pygame.Rect(option_x, start_y + index * step_y, option_width, option_height)
            if rect.collidepoint(pos):
                if key == "fullscreen":
                    self._toggle_fullscreen()
                else:
                    self.settings[key] = not self.settings[key]
                    if key == "show_zombie_count":
                        self._save_client_settings()
                return
        density_rect = pygame.Rect(option_x, start_y + len(options) * step_y, option_width, option_height)
        if density_rect.collidepoint(pos):
            order = ["low", "normal", "high"]
            self.bot_density = order[(order.index(self.bot_density) + 1) % len(order)]
            return
        difficulty_rect = pygame.Rect(option_x, start_y + (len(options) + 1) * step_y, option_width, option_height)
        if difficulty_rect.collidepoint(pos):
            index = self.difficulty_options.index(self.difficulty_key)
            self.difficulty_key = self.difficulty_options[(index + 1) % len(self.difficulty_options)]
            return
        language_rect = pygame.Rect(option_x, start_y + (len(options) + 2) * step_y, option_width, option_height)
        if language_rect.collidepoint(pos):
            languages = sorted(self.locales)
            self.language = languages[(languages.index(self.language) + 1) % len(languages)]

    def _handle_craft_click(self, pos: tuple[int, int]) -> None:
        if self._craft_scroll_track_rect().collidepoint(pos):
            self._set_craft_scroll_from_pointer(pos[1])
            return
        if not self._craft_viewport_rect().collidepoint(pos):
            return
        for index, recipe_key in enumerate(RECIPES):
            if self._craft_recipe_rect(index).collidepoint(pos):
                self.pending_craft_key = recipe_key

    def _handle_weapon_custom_click(self, pos: tuple[int, int], player: PlayerState | None) -> bool:
        if self._weapon_custom_close_rect().collidepoint(pos):
            self.weapon_custom_open = False
            self.drag_source = None
            return True
        if not player:
            return False
        for index, slot in enumerate(SLOTS):
            rect = self._weapon_custom_slot_rect(index)
            if rect.collidepoint(pos) and player.weapons.get(slot):
                self.custom_weapon_slot = slot
                return True
        weapon_slot = self._custom_weapon_slot(player)
        for module_key, indices in self._available_module_groups(player):
            rect = self._available_module_rect(module_key)
            module = WEAPON_MODULES.get(module_key)
            if rect.collidepoint(pos) and module and indices and player.weapons.get(weapon_slot):
                self.pending_inventory_action = {
                    "type": "move",
                    "src": "backpack",
                    "dst": "weapon_module",
                    "src_index": indices[0],
                    "dst_slot": weapon_slot,
                    "dst_module": module.slot,
                }
                return True
        return False

    def _handle_server_click(self, pos: tuple[int, int]) -> None:
        if pygame.Rect(72, 632, 180, 46).collidepoint(pos):
            self._back_to_menu()
        if pygame.Rect(270, 632, 180, 46).collidepoint(pos):
            self._refresh_pings()
        if pygame.Rect(470, 632, 180, 46).collidepoint(pos):
            self._connect_selected_server()
        for index, _entry in enumerate(self.server_entries):
            row = pygame.Rect(72, 190 + index * 72, 720, 56)
            if row.collidepoint(pos):
                self.selected_server = index

    def _handle_inventory_click(self, pos: tuple[int, int]) -> None:
        snapshot = self._snapshot()
        player = self._local_player(snapshot) if snapshot else None
        if not player:
            return
        panel = pygame.Rect(260, 110, 760, 540)
        if not panel.collidepoint(pos):
            return
        armor_y = panel.y + 292
        for index, armor_key in enumerate(player.owned_armors):
            rect = pygame.Rect(panel.x + 42 + index * 172, armor_y, 152, 46)
            if rect.collidepoint(pos):
                self.pending_equip_armor = armor_key
        if pygame.Rect(panel.x + 42, panel.y + 442, 158, 46).collidepoint(pos):
            self.pending_medkit = True

    def _update(self, dt: float) -> None:
        if self.state == "servers" and time.time() - self._last_ping_refresh > 4.0:
            self._refresh_pings()

        if self.state == "single" and self.world and self.local_player_id:
            if self.settings_open or self.backpack_open or self.craft_open or self.weapon_custom_open:
                if self.pending_inventory_action or self.pending_craft_key or self.pending_repair_slot:
                    command = self._build_input(self.local_player_id)
                    self.world.set_input(command)
                    self.world.update(0.0)
                    self._clear_transient_inputs()
                self._update_camera_zoom(dt)
                self._update_damage_feedback(dt)
                return
            command = self._build_input(self.local_player_id)
            self.world.set_input(command)
            self.world.update(dt)
            self._clear_transient_inputs()
        elif self.state == "online_game" and self.online.player_id:
            command = self._build_input(self.online.player_id)
            self.online.send_input(command)
            self._clear_transient_inputs()
        self._update_camera_zoom(dt)
        self._update_damage_feedback(dt)

    def _update_camera_zoom(self, dt: float) -> None:
        snapshot = self._snapshot()
        player = self._local_player(snapshot) if snapshot else None
        target = 0.84 if player and player.alive and player.sprinting else 1.0
        speed = 3.1 if target < self.camera_zoom else 4.8
        blend = 1.0 - math.exp(-speed * max(0.0, dt))
        self.camera_zoom += (target - self.camera_zoom) * blend
        if abs(self.camera_zoom - target) < 0.002:
            self.camera_zoom = target

    def _update_damage_feedback(self, dt: float) -> None:
        self.damage_flash = max(0.0, self.damage_flash - dt * 1.9)
        snapshot = self._snapshot()
        player = self._local_player(snapshot) if snapshot else None
        if not player:
            self._last_local_health = None
            return
        previous = self._last_local_health
        if previous is not None and player.alive and player.health < previous - 0.1:
            loss = previous - player.health
            self.damage_flash = min(1.0, max(self.damage_flash, 0.25 + min(0.55, loss / 55.0)))
        self._last_local_health = player.health

    def _build_input(self, player_id: str) -> InputCommand:
        keys = pygame.key.get_pressed()
        move_x = float(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - float(keys[pygame.K_a] or keys[pygame.K_LEFT])
        move_y = float(keys[pygame.K_s] or keys[pygame.K_DOWN]) - float(keys[pygame.K_w] or keys[pygame.K_UP])
        ui_open = self.backpack_open or self.settings_open or self.craft_open or self.weapon_custom_open
        if ui_open:
            move_x = 0.0
            move_y = 0.0
        snapshot = self._snapshot()
        player = self._local_player(snapshot) if snapshot else None
        mouse_world = self._mouse_world(player)
        if player and pygame.mouse.get_pressed(num_buttons=3)[2]:
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
            shooting=pygame.mouse.get_pressed(num_buttons=3)[0] and not ui_open,
            reload=self.pending_reload,
            pickup=self.pending_pickup,
            interact=self.pending_interact,
            use_medkit=self.pending_medkit,
            sprint=keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT],
            sneak=keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL],
            respawn=self.pending_respawn,
            throw_grenade=self.pending_throw_grenade,
            toggle_utility=self.pending_toggle_utility,
            inventory_action=self.pending_inventory_action,
            craft_key=self.pending_craft_key,
            repair_slot=self.pending_repair_slot,
            active_slot=self.pending_slot,
            equip_armor=self.pending_equip_armor,
        )

    def _clear_transient_inputs(self) -> None:
        self.pending_reload = False
        self.pending_pickup = False
        self.pending_medkit = False
        self.pending_interact = False
        self.pending_respawn = False
        self.pending_throw_grenade = False
        self.pending_toggle_utility = False
        self.pending_inventory_action = None
        self.pending_craft_key = None
        self.pending_repair_slot = None
        self.pending_slot = None
        self.pending_equip_armor = None

    def _start_single_player(self) -> None:
        self.online.close()
        if self.world:
            self.world.close()
        difficulty = load_difficulty(self.difficulty_key)
        density = self.bot_density_profiles[self.bot_density]
        initial_zombies = max(1, int(round(difficulty.initial_zombies * density)))
        max_zombies = max(initial_zombies, int(round(difficulty.max_zombies * density)))
        self.world = GameWorld(
            seed=int(time.time()),
            initial_zombies=initial_zombies,
            max_zombies=max_zombies,
            difficulty_key=self.difficulty_key,
        )
        player = self.world.add_player(self.player_name, "local")
        self.local_player_id = player.id
        self.inventory_open = False
        self.backpack_open = False
        self.settings_open = False
        self.craft_open = False
        self.weapon_custom_open = False
        self.state = "single"

    def _show_servers(self) -> None:
        self.state = "servers"
        self.server_entries = self._load_servers()
        self.selected_server = 0
        self._refresh_pings()

    def _connect_selected_server(self) -> None:
        if not self.server_entries:
            return
        entry = self.server_entries[self.selected_server]
        try:
            self.online.connect(entry.host, entry.port, self.player_name)
            if self.world:
                self.world.close()
            self.world = None
            self.inventory_open = False
            self.backpack_open = False
            self.weapon_custom_open = False
            self.state = "online_game"
        except OSError as exc:
            entry.status = f"error: {exc}"

    def _back_to_menu(self) -> None:
        self.online.close()
        if self.world:
            self.world.close()
            self.world = None
        self.state = "menu"
        self.inventory_open = False
        self.backpack_open = False
        self.settings_open = False
        self.craft_open = False
        self.weapon_custom_open = False

    def _load_servers(self) -> list[ServerEntry]:
        path = ROOT / "servers.json"
        if not path.exists():
            return [ServerEntry("Local Dev", "127.0.0.1", 8765)]
        data = json.loads(path.read_text(encoding="utf-8"))
        return [ServerEntry(str(row["name"]), str(row["host"]), int(row["port"])) for row in data]

    def _refresh_pings(self) -> None:
        if self._pinging:
            return
        self._pinging = True
        self._last_ping_refresh = time.time()

        def worker() -> None:
            try:
                for entry in self.server_entries:
                    entry.status = "checking"
                    ping, meta = ping_server(entry.host, entry.port)
                    entry.ping_ms = ping
                    entry.players = int(meta.get("players", 0)) if meta else 0
                    entry.difficulty = str(meta.get("difficulty", entry.difficulty)) if meta else entry.difficulty
                    entry.status = "online" if ping is not None else "offline"
            finally:
                self._pinging = False

        threading.Thread(target=worker, name="server-ping", daemon=True).start()

    def _snapshot(self) -> WorldSnapshot | None:
        if self.state == "single" and self.world:
            return self.world.snapshot()
        if self.state == "online_game":
            return self.online.snapshot()
        return None

    def _local_player(self, snapshot: WorldSnapshot | None) -> PlayerState | None:
        if not snapshot:
            return None
        player_id = self.local_player_id if self.state == "single" else self.online.player_id
        return snapshot.players.get(player_id or "")

    def _camera(self, player: PlayerState | None) -> Vec2:
        if not player:
            return Vec2(0, 0)
        viewport_w = SCREEN_W / max(0.1, self.camera_zoom)
        viewport_h = SCREEN_H / max(0.1, self.camera_zoom)
        return Vec2(
            max(0, min(max(0.0, MAP_WIDTH - viewport_w), player.pos.x - viewport_w * 0.5)),
            max(0, min(max(0.0, MAP_HEIGHT - viewport_h), player.pos.y - viewport_h * 0.5)),
        )

    def _mouse_world(self, player: PlayerState | None) -> Vec2:
        mx, my = self._mouse_pos()
        camera = self._camera(player)
        zoom = max(0.1, self.camera_zoom)
        return Vec2(mx / zoom + camera.x, my / zoom + camera.y)

    def _world_to_screen(self, pos: Vec2, camera: Vec2) -> tuple[int, int]:
        zoom = max(0.1, self.camera_zoom)
        return int((pos.x - camera.x) * zoom), int((pos.y - camera.y) * zoom)

    def _world_rect_to_screen(self, rect: RectState, camera: Vec2) -> pygame.Rect:
        zoom = max(0.1, self.camera_zoom)
        return pygame.Rect(
            int((rect.x - camera.x) * zoom),
            int((rect.y - camera.y) * zoom),
            max(1, int(rect.w * zoom)),
            max(1, int(rect.h * zoom)),
        )

    def _world_size(self, value: float, minimum: int = 1) -> int:
        return max(minimum, int(value * max(0.1, self.camera_zoom)))

    def _draw(self) -> None:
        if self.state == "menu":
            self._draw_menu()
        elif self.state == "options":
            self._draw_options_menu()
        elif self.state == "servers":
            self._draw_servers()
        elif self.state in {"single", "online_game"}:
            self._draw_game()
        self._present()

    def _draw_menu(self) -> None:
        self.screen.fill(BG)
        self._draw_neon_background()

        # Create responsive main menu panel
        panel_width = 420
        panel_height = 580
        panel_x = 48
        panel_y = (SCREEN_H - panel_height) // 2
        panel = pygame.Rect(panel_x, panel_y, panel_width, panel_height)

        pygame.draw.rect(self.screen, (10, 15, 25), panel, border_radius=12)
        pygame.draw.rect(self.screen, CYAN, panel, 2, border_radius=12)

        # Improved text positioning
        self._draw_text_fit(self.tr("app.title"), pygame.Rect(panel.x + 28, panel.y + 32, panel.w - 56, 64), TEXT, self.big, center=True)
        self._draw_text_fit(self.tr("menu.subtitle"), pygame.Rect(panel.x + 30, panel.y + 110, panel.w - 60, 24), CYAN, self.font, center=True)
        self._draw_text_fit(self.tr("menu.caption"), pygame.Rect(panel.x + 30, panel.y + 140, panel.w - 60, 20), MUTED, self.small, center=True)

        for button in self._menu_buttons:
            self._draw_button(button.rect, self.tr(button.label), button.hovered(self._mouse_pos()))
        self._draw_menu_showcase()

    def _draw_menu_showcase(self) -> None:
        pygame.draw.rect(self.screen, (12, 18, 28), pygame.Rect(492, 96, 662, 500), border_radius=10)
        pygame.draw.rect(self.screen, (58, 78, 108), pygame.Rect(492, 96, 662, 500), 2, border_radius=10)
        for i in range(7):
            pygame.draw.line(self.screen, (25, 38, 58), (530 + i * 88, 128), (460 + i * 118, 562), 2)
        self._draw_text(self.tr("menu.systems"), 536, 132, TEXT, self.big)
        cards = [
            (self.tr("menu.card.stealth.title"), self.tr("menu.card.stealth.body"), CYAN),
            (self.tr("menu.card.ai.title"), self.tr("menu.card.ai.body"), YELLOW),
            (self.tr("menu.card.craft.title"), self.tr("menu.card.craft.body"), GREEN),
        ]
        for index, (title, body, color) in enumerate(cards):
            rect = pygame.Rect(540, 226 + index * 94, 520, 72)
            pygame.draw.rect(self.screen, PANEL, rect, border_radius=8)
            pygame.draw.rect(self.screen, (54, 74, 104), rect, 1, border_radius=8)
            pygame.draw.circle(self.screen, color, (rect.x + 34, rect.y + 36), 13)
            pygame.draw.circle(self.screen, TEXT, (rect.x + 34, rect.y + 36), 13, 1)
            self._draw_text(title, rect.x + 62, rect.y + 12, TEXT, self.mid)
            self._draw_text(body, rect.x + 64, rect.y + 44, MUTED, self.small)

    def _draw_options_menu(self) -> None:
        self.screen.fill(BG)
        self._draw_neon_background()
        self._draw_settings(panel_only=True)

    def _draw_servers(self) -> None:
        self.screen.fill(BG)
        self._draw_neon_background()
        self._draw_text(self.tr("servers.title"), 72, 90, TEXT, self.big)
        self._draw_text(self.tr("servers.caption"), 76, 150, MUTED)
        for index, entry in enumerate(self.server_entries):
            rect = pygame.Rect(72, 190 + index * 72, 720, 56)
            selected = index == self.selected_server
            pygame.draw.rect(self.screen, PANEL_2 if selected else PANEL, rect, border_radius=8)
            pygame.draw.rect(self.screen, CYAN if selected else (45, 59, 91), rect, 2, border_radius=8)
            self._draw_text(entry.name, rect.x + 18, rect.y + 9, TEXT, self.mid)
            endpoint = f"{entry.host}:{entry.port}"
            ping = "offline" if entry.ping_ms is None else f"{entry.ping_ms:.0f} ms"
            difficulty = self.tr(f"difficulty.{entry.difficulty}") if entry.difficulty in self.difficulty_options else entry.difficulty
            self._draw_text(endpoint, rect.x + 260, rect.y + 18, MUTED)
            status = f"{ping}  {self.tr('servers.players')}: {entry.players}  {self.tr('servers.difficulty')}: {difficulty}"
            self._draw_text_fit(status, pygame.Rect(rect.x + 485, rect.y + 18, 210, 22), GREEN if entry.ping_ms else RED, self.small)
        self._draw_button(pygame.Rect(72, 632, 180, 46), self.tr("servers.back"), False)
        self._draw_button(pygame.Rect(270, 632, 180, 46), self.tr("servers.refresh"), False)
        self._draw_button(pygame.Rect(470, 632, 180, 46), self.tr("servers.connect"), False)

    def _draw_game(self) -> None:
        snapshot = self._snapshot()
        player = self._local_player(snapshot)
        camera = self._camera(player)
        self.screen.fill(BG)
        self._draw_world_background(camera)
        if snapshot:
            self._draw_tunnels(snapshot, camera, player)
            self._draw_buildings(snapshot, camera, player)
            if player and self.settings["noise_radius"]:
                self._draw_noise_radius(player, camera)
            self._draw_loot(snapshot, camera)
            self._draw_projectiles(snapshot, camera)
            self._draw_grenades(snapshot, camera)
            self._draw_mines(snapshot, camera)
            self._draw_poison(snapshot, camera)
            self._draw_zombies(snapshot, camera)
            self._draw_players(snapshot, camera)
            self._draw_weapon_utilities(snapshot, camera, player)
            if player:
                self._draw_tunnel_darkness(player, camera)
            if player:
                self._draw_damage_feedback(player)
            self._draw_hud(snapshot, player)
            self._draw_minimap(snapshot, player)
            if self.settings.get("show_zombie_count", False):
                self._draw_zombie_counter(snapshot)
            self._draw_context_prompt(snapshot, player, camera)
            if pygame.key.get_pressed()[pygame.K_TAB]:
                self._draw_scoreboard(snapshot)
            if player and not player.alive:
                self._draw_death_overlay()
            if self.backpack_open and player:
                self._draw_backpack(player)
            if self.craft_open and player:
                self._draw_crafting(player)
            if self.settings_open:
                self._draw_settings()
        if self.state == "online_game" and self.online.error:
            self._draw_text(self.online.error, 26, SCREEN_H - 34, RED)

    def _draw_neon_background(self) -> None:
        for i in range(18):
            x = 680 + i * 42
            color = (18, 36 + i * 3 % 50, 58 + i * 4 % 90)
            pygame.draw.line(self.screen, color, (x, 0), (x - 360, SCREEN_H), 2)
        pygame.draw.circle(self.screen, (20, 62, 92), (1050, 180), 210, 2)
        pygame.draw.circle(self.screen, (54, 31, 91), (1040, 180), 140, 2)

    def _draw_world_background(self, camera: Vec2) -> None:
        grid = 80
        zoom = max(0.1, self.camera_zoom)
        visible_w = SCREEN_W / zoom
        visible_h = SCREEN_H / zoom
        start_world_x = math.floor(camera.x / grid) * grid
        start_world_y = math.floor(camera.y / grid) * grid
        end_world_x = camera.x + visible_w + grid
        end_world_y = camera.y + visible_h + grid
        x = start_world_x
        while x <= end_world_x:
            sx = int((x - camera.x) * zoom)
            pygame.draw.line(self.screen, (18, 25, 41), (sx, 0), (sx, SCREEN_H))
            x += grid
        y = start_world_y
        while y <= end_world_y:
            sy = int((y - camera.y) * zoom)
            pygame.draw.line(self.screen, (18, 25, 41), (0, sy), (SCREEN_W, sy))
            y += grid
        pygame.draw.rect(
            self.screen,
            (34, 55, 76),
            pygame.Rect(int(-camera.x * zoom), int(-camera.y * zoom), int(MAP_WIDTH * zoom), int(MAP_HEIGHT * zoom)),
            3,
        )

    def _draw_tunnels(self, snapshot: WorldSnapshot, camera: Vec2, player: PlayerState | None) -> None:
        if not player or player.floor >= 0:
            return
        for tunnel in tunnel_segments(snapshot.buildings):
            rect = self._world_rect_to_screen(tunnel, camera)
            if not rect.colliderect(pygame.Rect(-120, -120, SCREEN_W + 240, SCREEN_H + 240)):
                continue
            pygame.draw.rect(self.screen, (10, 14, 20), rect, border_radius=10)
            pygame.draw.rect(self.screen, (38, 52, 68), rect, 2, border_radius=10)

    def _draw_buildings(self, snapshot: WorldSnapshot, camera: Vec2, player: PlayerState | None) -> None:
        for building in snapshot.buildings.values():
            rect = self._world_rect_to_screen(building.bounds, camera)
            bx, by = rect.x, rect.y
            if not rect.colliderect(pygame.Rect(-120, -120, SCREEN_W + 240, SCREEN_H + 240)):
                continue
            player_inside = bool(player and player.inside_building == building.id)
            fill = (18, 26, 34) if player_inside else (15, 20, 30)
            outline = CYAN if player_inside else (55, 72, 94)
            pygame.draw.rect(self.screen, fill, rect, border_radius=3)
            pygame.draw.rect(self.screen, outline, rect, 2, border_radius=3)
            if player_inside:
                floor_label = f"{building.name} {self._floor_label(player.floor)}"
                self._draw_text(floor_label, bx + 18, by + 14, CYAN, self.small)
            for wall in building.walls:
                self._draw_rect_world(wall, camera, (77, 91, 117))
            for prop in building.props:
                if prop.floor != (player.floor if player_inside and player else 0):
                    continue
                if not player_inside and prop.kind not in {"shelf", "crate", "barrel", "pallet", "roadblock"}:
                    continue
                color = (111, 92, 72) if prop.kind in {"desk", "table", "pallet"} else (110, 74, 54) if prop.kind == "barrel" else (82, 96, 124)
                self._draw_rect_world(prop.rect, camera, color)
            for stairs in building.stairs:
                if player_inside or not player:
                    self._draw_rect_world(stairs, camera, (86, 126, 164))
                    sx, sy = self._world_to_screen(stairs.center, camera)
                    self._draw_text("stairs", sx - 22, sy - 8, TEXT, self.small)
            for door in building.doors:
                if player_inside and player and door.floor != player.floor:
                    continue
                if not player_inside and door.floor != 0:
                    continue
                color = GREEN if door.open else YELLOW
                self._draw_rect_world(door.rect, camera, color)

    def _draw_noise_radius(self, player: PlayerState, camera: Vec2) -> None:
        if player.noise <= 0.0 or not player.alive:
            return
        sx, sy = self._world_to_screen(player.pos, camera)
        radius = self._world_size(max(12, min(460, player.noise)), 8)
        surface = pygame.Surface((radius * 2 + 8, radius * 2 + 8), pygame.SRCALPHA)
        color = (76, 225, 255, 30) if player.sneaking else (255, 210, 112, 34)
        pygame.draw.circle(surface, color, (radius + 4, radius + 4), radius)
        pygame.draw.circle(surface, (255, 255, 255, 48), (radius + 4, radius + 4), radius, 1)
        self.screen.blit(surface, (sx - radius - 4, sy - radius - 4))

    def _draw_rect_world(self, rect: RectState, camera: Vec2, color: tuple[int, int, int]) -> None:
        screen_rect = self._world_rect_to_screen(rect, camera)
        pygame.draw.rect(self.screen, color, screen_rect, border_radius=2)

    def _loot_icon_key(self, item: LootState) -> str:
        if item.kind == "ammo":
            ammo_key = f"{item.payload}_ammo"
            return ammo_key if ammo_key in self.item_images else "ammo_pack"
        if item.kind == "medkit":
            return "medicine"
        if item.kind == "armor":
            armor_key = f"{item.payload}_torso"
            return armor_key if armor_key in ITEMS or armor_key in self.item_images else item.payload
        return item.payload if item.kind in {"item", "weapon"} else self.icon_mapping.get(item.kind, item.kind)

    def _draw_world_item_frame(
        self,
        center: tuple[int, int],
        rarity: str,
        accent: tuple[int, int, int],
        world_time: float,
    ) -> pygame.Rect:
        rank = rarity_rank(rarity)
        rarity_accent = rarity_color(rarity) if rank > 0 else accent
        pulse = (math.sin(world_time * 4.6 + center[0] * 0.017) + 1.0) * 0.5
        size = 42 + min(rank, 3) * 3
        rect = pygame.Rect(0, 0, size, size)
        rect.center = center
        glow_rect = rect.inflate(22 + rank * 6, 22 + rank * 6)
        glow = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
        for layer in range(3 + min(rank, 2)):
            inset = layer * 5
            alpha = max(8, int(42 + rank * 22 + pulse * 26) - layer * 18)
            layer_rect = glow.get_rect().inflate(-inset, -inset)
            pygame.draw.rect(glow, (*rarity_accent, alpha), layer_rect, 2, border_radius=10)
        pygame.draw.rect(glow, (*accent, 24 + rank * 8), glow.get_rect().inflate(-12, -12), border_radius=9)
        self.screen.blit(glow, glow_rect)

        pygame.draw.rect(self.screen, (7, 11, 19), rect, border_radius=7)
        pygame.draw.rect(self.screen, accent, rect, 1, border_radius=7)
        pygame.draw.rect(self.screen, rarity_accent, rect.inflate(4, 4), 2 + (1 if rank >= 2 else 0), border_radius=8)
        corner = 8 + rank * 2
        width = 2 + (1 if rank >= 3 else 0)
        for sx, sy in ((rect.left, rect.top), (rect.right, rect.top), (rect.left, rect.bottom), (rect.right, rect.bottom)):
            x_dir = 1 if sx == rect.left else -1
            y_dir = 1 if sy == rect.top else -1
            pygame.draw.line(self.screen, rarity_accent, (sx, sy), (sx + corner * x_dir, sy), width)
            pygame.draw.line(self.screen, rarity_accent, (sx, sy), (sx, sy + corner * y_dir), width)
        return rect

    def _draw_loot(self, snapshot: WorldSnapshot, camera: Vec2) -> None:
        player = self._local_player(snapshot)
        colors = {"weapon": CYAN, "ammo": YELLOW, "armor": PURPLE, "medkit": GREEN, "item": TEXT}
        for item in snapshot.loot.values():
            if player and item.floor != player.floor:
                continue
            if player and player.floor < 0 and not self._point_lit_by_flashlight(player, item.pos):
                continue
            sx, sy = self._world_to_screen(item.pos, camera)
            if -30 <= sx <= SCREEN_W + 30 and -30 <= sy <= SCREEN_H + 30:
                color = colors.get(item.kind, TEXT)
                icon_key = self._loot_icon_key(item)
                if item.kind == "item" and item.payload in ITEMS:
                    color = ITEMS[item.payload].color
                spec = ITEMS.get(item.payload)
                rare_visual = item.kind in {"weapon", "armor"} or bool(spec and spec.kind == "armor")
                if rare_visual and rarity_rank(item.rarity) > 0:
                    color = rarity_color(item.rarity)
                glow_rect = self._draw_world_item_frame((sx, sy), item.rarity, color, snapshot.time)
                if rare_visual:
                    self._draw_rarity_badge(glow_rect, item.rarity, compact=True)
                if not self._draw_item_icon(icon_key, pygame.Rect(sx - 14, sy - 14, 28, 28), aura=False):
                    pygame.draw.circle(self.screen, color, (sx, sy), 10)
                label = self._loot_label(item)
                self._draw_text(label, sx + 14, sy - 11, color, self.small)

    def _draw_projectiles(self, snapshot: WorldSnapshot, camera: Vec2) -> None:
        player = self._local_player(snapshot)
        for projectile in snapshot.projectiles.values():
            if player and projectile.floor != player.floor:
                continue
            sx, sy = self._world_to_screen(projectile.pos, camera)
            tail = Vec2(projectile.pos.x - projectile.velocity.x * 0.025, projectile.pos.y - projectile.velocity.y * 0.025)
            tx, ty = self._world_to_screen(tail, camera)
            pygame.draw.line(self.screen, (255, 244, 170), (tx, ty), (sx, sy), self._world_size(4, 2))
            pygame.draw.circle(self.screen, (255, 255, 255), (sx, sy), self._world_size(3, 2))

    def _draw_grenades(self, snapshot: WorldSnapshot, camera: Vec2) -> None:
        player = self._local_player(snapshot)
        for grenade in snapshot.grenades.values():
            if player and grenade.floor != player.floor:
                continue
            spec = GRENADE_SPECS.get(grenade.kind, DEFAULT_GRENADE)
            sx, sy = self._world_to_screen(grenade.pos, camera)
            progress = max(0.0, min(1.0, 1.0 - grenade.timer / max(0.05, spec.timer)))
            pulse = int(7 + progress * 10)
            color = (103, 236, 190) if grenade.kind == "contact_grenade" else (255, 128, 92) if grenade.kind == "heavy_grenade" else GREEN
            warning = RED if grenade.timer <= 0.55 else color
            pygame.draw.circle(self.screen, (10, 16, 12), (sx, sy), pulse + 5)
            pygame.draw.circle(self.screen, warning, (sx, sy), pulse)
            pygame.draw.circle(self.screen, (255, 255, 255), (sx, sy), max(3, pulse - 5), 1)
            if spec.contact:
                pygame.draw.circle(self.screen, CYAN, (sx, sy), pulse + 4, 1)
            pygame.draw.circle(self.screen, YELLOW, (sx, sy), self._world_size(spec.blast_radius * progress, 1), 1)

    def _draw_mines(self, snapshot: WorldSnapshot, camera: Vec2) -> None:
        player = self._local_player(snapshot)
        for mine in snapshot.mines.values():
            if player and mine.floor != player.floor:
                continue
            sx, sy = self._world_to_screen(mine.pos, camera)
            if not (-180 <= sx <= SCREEN_W + 180 and -180 <= sy <= SCREEN_H + 180):
                continue
            base_color = (120, 225, 255) if mine.kind == "mine_light" else RED if mine.kind == "mine_heavy" else YELLOW
            blink = 0.5 + 0.5 * math.sin(snapshot.time * 7.2 + mine.rotation)
            alpha = int((72 if mine.armed else 42) + blink * (70 if mine.armed else 18))
            self._draw_dashed_circle((sx, sy), self._world_size(mine.trigger_radius, 8), base_color, mine.rotation, alpha)
            glow = pygame.Surface((58, 58), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*base_color, 44 if mine.armed else 24), (29, 29), 28)
            self.screen.blit(glow, (sx - 29, sy - 29))
            pygame.draw.circle(self.screen, (8, 11, 16), (sx, sy), 18)
            pygame.draw.circle(self.screen, base_color if mine.armed else MUTED, (sx, sy), 13)
            pygame.draw.circle(self.screen, TEXT, (sx, sy), 13, 1)
            if mine.armed and blink > 0.55:
                pygame.draw.circle(self.screen, RED, (sx, sy), 5)
            if not self._draw_item_icon(mine.kind, pygame.Rect(sx - 12, sy - 12, 24, 24)):
                pygame.draw.line(self.screen, BG, (sx - 8, sy), (sx + 8, sy), 2)
                pygame.draw.line(self.screen, BG, (sx, sy - 8), (sx, sy + 8), 2)

    def _draw_dashed_circle(
        self,
        center: tuple[int, int],
        radius: int,
        color: tuple[int, int, int],
        phase: float,
        alpha: int,
    ) -> None:
        if radius <= 0:
            return
        surface = pygame.Surface((radius * 2 + 16, radius * 2 + 16), pygame.SRCALPHA)
        local_center = (radius + 8, radius + 8)
        segments = 40
        for index in range(segments):
            if index % 2:
                continue
            a1 = phase + math.tau * index / segments
            a2 = phase + math.tau * (index + 0.62) / segments
            p1 = (int(local_center[0] + math.cos(a1) * radius), int(local_center[1] + math.sin(a1) * radius))
            p2 = (int(local_center[0] + math.cos(a2) * radius), int(local_center[1] + math.sin(a2) * radius))
            pygame.draw.line(surface, (*color, alpha), p1, p2, 2)
        self.screen.blit(surface, (center[0] - radius - 8, center[1] - radius - 8))

    def _draw_poison(self, snapshot: WorldSnapshot, camera: Vec2) -> None:
        player = self._local_player(snapshot)
        for pool in snapshot.poison_pools.values():
            if player and pool.floor != player.floor:
                continue
            sx, sy = self._world_to_screen(pool.pos, camera)
            radius = self._world_size(pool.radius * (0.72 + 0.12 * math.sin(snapshot.time * 6.0 + sx)), 8)
            pool_surface = pygame.Surface((radius * 2 + 20, radius * 2 + 20), pygame.SRCALPHA)
            center = (pool_surface.get_width() // 2, pool_surface.get_height() // 2)
            pygame.draw.circle(pool_surface, (64, 255, 106, 64), center, radius)
            pygame.draw.circle(pool_surface, (170, 255, 140, 92), center, max(8, radius // 2), 2)
            self.screen.blit(pool_surface, (sx - center[0], sy - center[1]))
        for spit in snapshot.poison_projectiles.values():
            if player and spit.floor != player.floor:
                continue
            sx, sy = self._world_to_screen(spit.pos, camera)
            pygame.draw.circle(self.screen, (28, 68, 24), (sx, sy), self._world_size(13, 6))
            pygame.draw.circle(self.screen, (104, 255, 112), (sx, sy), self._world_size(8, 4))
            pygame.draw.circle(self.screen, (220, 255, 180), (sx - 2, sy - 2), self._world_size(3, 2))

    def _draw_zombies(self, snapshot: WorldSnapshot, camera: Vec2) -> None:
        player = self._local_player(snapshot)
        for zombie in snapshot.zombies.values():
            if player and zombie.floor != player.floor:
                continue
            spec = ZOMBIES[zombie.kind]
            sx, sy = self._world_to_screen(zombie.pos, camera)
            if -80 <= sx <= SCREEN_W + 80 and -80 <= sy <= SCREEN_H + 80:
                if self.settings["bot_vision"] and (self.settings["bot_vision_range"] or zombie.mode in {"chase", "investigate", "search"}):
                    cone_len = spec.sight_range if self.settings["bot_vision_range"] else min(spec.sight_range, 160)
                    cone_len_screen = self._world_size(cone_len, 1)
                    left = zombie.facing - math.radians(spec.fov_degrees * 0.5)
                    right = zombie.facing + math.radians(spec.fov_degrees * 0.5)
                    points = [
                        (sx, sy),
                        (int(sx + math.cos(left) * cone_len_screen), int(sy + math.sin(left) * cone_len_screen)),
                        (int(sx + math.cos(right) * cone_len_screen), int(sy + math.sin(right) * cone_len_screen)),
                    ]
                    cone = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                    alpha = 18 if self.settings["bot_vision_range"] else 34
                    pygame.draw.polygon(cone, (*spec.color, alpha), points)
                    pygame.draw.arc(
                        cone,
                        (*spec.color, 68),
                        pygame.Rect(sx - cone_len_screen, sy - cone_len_screen, cone_len_screen * 2, cone_len_screen * 2),
                        -right,
                        -left,
                        1,
                    )
                    self.screen.blit(cone, (0, 0))
                radius = self._world_size(spec.radius, 8)
                pygame.draw.circle(self.screen, (12, 18, 28), (sx, sy), self._world_size(spec.radius + 8, radius + 4))
                pygame.draw.circle(self.screen, spec.color, (sx, sy), radius)
                pygame.draw.circle(self.screen, (255, 255, 255), (sx, sy), radius, 2)
                nose_len = self._world_size(spec.radius + 12, radius + 4)
                nose = (int(sx + math.cos(zombie.facing) * nose_len), int(sy + math.sin(zombie.facing) * nose_len))
                pygame.draw.line(self.screen, TEXT, (sx, sy), nose, 2)
                if self.settings["health_bars"]:
                    self._bar(sx - 24, sy - radius - 15, 48, 5, zombie.health / max(1, spec.health), RED)
                if self.settings["health_bars"] and zombie.armor > 0:
                    self._bar(sx - 24, sy - radius - 8, 48, 4, zombie.armor / max(1, spec.armor), CYAN)
                if self.settings["ai_reactions"]:
                    mode_color = RED if zombie.mode == "chase" else YELLOW if zombie.mode in {"investigate", "search"} else MUTED
                    self._draw_text(zombie.mode, sx - 22, sy + radius + 8, mode_color, self.small)

    def _draw_players(self, snapshot: WorldSnapshot, camera: Vec2) -> None:
        local = self._local_player(snapshot)
        for player in snapshot.players.values():
            if local and player.floor != local.floor:
                continue
            sx, sy = self._world_to_screen(player.pos, camera)
            color = CYAN if player.id == (self.local_player_id or self.online.player_id) else GREEN
            body_radius = self._world_size(24, 12)
            pygame.draw.circle(self.screen, (4, 8, 14), (sx, sy), self._world_size(31, body_radius + 4))
            pygame.draw.circle(self.screen, color, (sx, sy), body_radius)
            pygame.draw.circle(self.screen, TEXT, (sx, sy), body_radius, 2)
            muzzle_len = self._world_size(42, 22)
            muzzle = (int(sx + math.cos(player.angle) * muzzle_len), int(sy + math.sin(player.angle) * muzzle_len))
            pygame.draw.line(self.screen, TEXT, (sx, sy), muzzle, self._world_size(5, 2))
            self._draw_text(player.name, sx - 28, sy - 48, TEXT, self.small)

    def _draw_weapon_utilities(self, snapshot: WorldSnapshot, camera: Vec2, local: PlayerState | None) -> None:
        for player in snapshot.players.values():
            if local and player.floor != local.floor:
                continue
            weapon = player.active_weapon()
            if not weapon or not weapon.utility_on:
                continue
            utility = weapon.modules.get("utility")
            sx, sy = self._world_to_screen(player.pos, camera)
            if utility == "laser_module":
                module = WEAPON_MODULES.get(utility)
                length = self._world_size(module.beam_length if module else 720, 1)
                end = (int(sx + math.cos(player.angle) * length), int(sy + math.sin(player.angle) * length))
                laser = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                pygame.draw.line(laser, (255, 64, 88, 76), (sx, sy), end, self._world_size(5, 2))
                pygame.draw.line(laser, (255, 210, 220, 138), (sx, sy), end, 1)
                pygame.draw.circle(laser, (255, 68, 92, 150), end, self._world_size(4, 2))
                self.screen.blit(laser, (0, 0))
            elif utility == "flashlight_module":
                self._draw_flashlight_cone(player, camera, soft=True)

    def _draw_flashlight_cone(self, player: PlayerState, camera: Vec2, soft: bool) -> None:
        module = WEAPON_MODULES.get("flashlight_module")
        cone_range = self._world_size(module.cone_range if module else 620, 1)
        half_angle = math.radians((module.cone_degrees if module else 58) * 0.5)
        sx, sy = self._world_to_screen(player.pos, camera)
        points = [
            (sx, sy),
            (int(sx + math.cos(player.angle - half_angle) * cone_range), int(sy + math.sin(player.angle - half_angle) * cone_range)),
            (int(sx + math.cos(player.angle + half_angle) * cone_range), int(sy + math.sin(player.angle + half_angle) * cone_range)),
        ]
        cone = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        color = (255, 238, 168, 38 if soft else 118)
        pygame.draw.polygon(cone, color, points)
        pygame.draw.circle(cone, (255, 244, 184, 24), (sx, sy), self._world_size(120, 24))
        self.screen.blit(cone, (0, 0))

    def _draw_tunnel_darkness(self, player: PlayerState, camera: Vec2) -> None:
        if player.floor >= 0:
            return
        has_flashlight = self._has_active_flashlight(player)
        darkness = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        darkness.fill((0, 0, 0, 232 if not has_flashlight else 206))
        if has_flashlight:
            module = WEAPON_MODULES.get("flashlight_module")
            cone_range = self._world_size(module.cone_range if module else 620, 1)
            half_angle = math.radians((module.cone_degrees if module else 58) * 0.5)
            sx, sy = self._world_to_screen(player.pos, camera)
            points = [
                (sx, sy),
                (int(sx + math.cos(player.angle - half_angle) * cone_range), int(sy + math.sin(player.angle - half_angle) * cone_range)),
                (int(sx + math.cos(player.angle + half_angle) * cone_range), int(sy + math.sin(player.angle + half_angle) * cone_range)),
            ]
            pygame.draw.polygon(darkness, (0, 0, 0, 58), points)
            pygame.draw.circle(darkness, (0, 0, 0, 70), (sx, sy), self._world_size(112, 24))
        self.screen.blit(darkness, (0, 0))
        label = self.tr("hud.dark_flashlight" if not has_flashlight else "hud.dark")
        badge = pygame.Rect(SCREEN_W - 288, SCREEN_H - 126, 260, 34)
        pygame.draw.rect(self.screen, PANEL, badge, border_radius=7)
        pygame.draw.rect(self.screen, YELLOW if not has_flashlight else CYAN, badge, 1, border_radius=7)
        self._draw_text_fit(label, badge.inflate(-16, -8), TEXT, self.small, center=True)

    def _has_active_flashlight(self, player: PlayerState | None) -> bool:
        weapon = player.active_weapon() if player else None
        return bool(weapon and weapon.utility_on and weapon.modules.get("utility") == "flashlight_module")

    def _point_lit_by_flashlight(self, player: PlayerState, pos: Vec2) -> bool:
        if player.floor >= 0:
            return True
        if not self._has_active_flashlight(player):
            return False
        distance = player.pos.distance_to(pos)
        if distance < 100:
            return True
        module = WEAPON_MODULES.get("flashlight_module")
        if distance > (module.cone_range if module else 620):
            return False
        angle_to = player.pos.angle_to(pos)
        half_angle = math.radians((module.cone_degrees if module else 58) * 0.5)
        return abs((angle_to - player.angle + math.pi) % math.tau - math.pi) <= half_angle

    def _draw_damage_feedback(self, player: PlayerState) -> None:
        if not player.alive:
            return
        critical = max(0.0, (25.0 - player.health) / 25.0)
        pulse = (math.sin(time.time() * 7.4) + 1.0) * 0.5
        hit = self.damage_flash
        if hit <= 0.01 and critical <= 0.01:
            return

        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        if hit > 0.01:
            overlay.fill((120, 0, 8, int(44 * hit)))
            edge_alpha = int(108 * hit)
            for index in range(18):
                alpha = max(0, edge_alpha - index * 6)
                color = (150, 0, 10, alpha)
                pygame.draw.rect(overlay, color, pygame.Rect(index * 7, 0, 7, SCREEN_H))
                pygame.draw.rect(overlay, color, pygame.Rect(SCREEN_W - (index + 1) * 7, 0, 7, SCREEN_H))
        if critical > 0.01:
            alpha = int((20 + 44 * pulse) * critical)
            overlay.fill((60, 0, 8, alpha), special_flags=pygame.BLEND_RGBA_ADD)
            for index in range(20):
                band_alpha = int((64 - index * 3) * critical * (0.55 + pulse * 0.45))
                pygame.draw.rect(overlay, (90, 0, 10, band_alpha), pygame.Rect(0, index * 6, SCREEN_W, 6))
                pygame.draw.rect(overlay, (90, 0, 10, band_alpha), pygame.Rect(0, SCREEN_H - (index + 1) * 6, SCREEN_W, 6))
            center_band = pygame.Rect(0, SCREEN_H // 2 - 34, SCREEN_W, 68)
            pygame.draw.rect(overlay, (0, 0, 0, int(32 * critical * pulse)), center_band)
        self.screen.blit(overlay, (0, 0))

    def _draw_hud(self, snapshot: WorldSnapshot, player: PlayerState | None) -> None:
        if not player:
            return
        pygame.draw.rect(self.screen, PANEL, pygame.Rect(18, 18, 348, 132), border_radius=8)
        self._draw_text(player.name, 74, 30, TEXT, self.mid)
        critical = player.alive and player.health < 25
        pulse = (math.sin(time.time() * 8.0) + 1.0) * 0.5 if critical else 0.0
        heart_size = 24 + int(7 * pulse if critical else 0)
        heart_rect = pygame.Rect(43 - heart_size // 2, 79 - heart_size // 2, heart_size, heart_size)
        if critical:
            glow = pygame.Surface((58, 58), pygame.SRCALPHA)
            pygame.draw.circle(glow, (255, 42, 58, int(72 + pulse * 70)), (29, 29), int(18 + pulse * 10))
            self.screen.blit(glow, (14, 50))
        if not self._draw_item_icon("heart", heart_rect):
            pygame.draw.circle(self.screen, RED, (42, 78), 9)
        health_color = (255, int(72 + pulse * 72), int(82 + pulse * 28)) if critical else RED
        if critical:
            pygame.draw.rect(self.screen, (122, 0, 18), pygame.Rect(58, 66, 278, 24), 2, border_radius=7)
        self._bar(62, 70, 270, 16, player.health / 100.0, health_color)
        if player.poison_left > 0:
            poison_alpha = int(90 + 70 * ((math.sin(time.time() * 5.5) + 1.0) * 0.5))
            pygame.draw.rect(self.screen, (92, 255, 114), pygame.Rect(58, 66, 278, 24), 2, border_radius=7)
            pygame.draw.circle(self.screen, (30, 92, 34), (342, 78), 12)
            pygame.draw.circle(self.screen, (110, 255, 118, poison_alpha), (342, 78), 8)
        armor_max = self._client_armor_max(player)
        if not self._draw_item_icon("shield", pygame.Rect(31, 92, 24, 24)):
            pygame.draw.rect(self.screen, CYAN, pygame.Rect(34, 91, 18, 18), 2, border_radius=3)
        self._bar(62, 97, 270, 12, player.armor / armor_max, CYAN)
        self._draw_text(f"{self.tr('hud.score')} {player.score}   {self.tr('hud.medkits')} {player.medkits}", 34, 116, MUTED, self.small)
        if player.poison_left > 0:
            self._draw_text_fit(self.tr("hud.poisoned"), pygame.Rect(242, 116, 96, 18), GREEN, self.small, center=True)
            badge = pygame.Rect(SCREEN_W - 86, 150, 58, 58)
            pygame.draw.rect(self.screen, PANEL, badge, border_radius=10)
            pygame.draw.rect(self.screen, GREEN, badge, 2, border_radius=10)
            pygame.draw.circle(self.screen, (42, 124, 44), badge.center, 16)
            pygame.draw.circle(self.screen, (130, 255, 124), badge.center, 9)
        noise_w = min(270, int(player.noise / 900 * 270))
        pygame.draw.rect(self.screen, (33, 40, 58), pygame.Rect(62, 134, 270, 5), border_radius=2)
        pygame.draw.rect(self.screen, YELLOW if player.sprinting else GREEN, pygame.Rect(62, 134, noise_w, 5), border_radius=2)

        weapon = player.active_weapon()
        active_quick_item = player.quick_items.get(player.active_slot)
        weapon_title = self.tr("hud.unarmed")
        ammo = "--"
        reload_text = ""
        if weapon:
            spec = WEAPONS[weapon.key]
            weapon_title = f"{self.rarity_title(weapon.rarity)} {self.weapon_title(spec.key)}"
            ammo = f"{weapon.ammo_in_mag}/{weapon.reserve_ammo}"
            if weapon.reload_left > 0:
                reload_text = f" {self.tr('hud.reloading')} {weapon.reload_left:.1f}s"
        elif active_quick_item:
            weapon_title = self.item_title(active_quick_item.key)
            ammo = f"x{active_quick_item.amount}"
        pygame.draw.circle(self.screen, YELLOW, (398, 44), 10)
        self._draw_text(f"{weapon_title}  {ammo}{reload_text}", 426, 32, TEXT, self.mid)

        start_x = 380
        y = SCREEN_H - 72
        for index, slot in enumerate(SLOTS):
            rect = pygame.Rect(start_x + index * 82, y, 72, 50)
            active = slot == player.active_slot
            pygame.draw.rect(self.screen, PANEL_2 if active else PANEL, rect, border_radius=8)
            pygame.draw.rect(self.screen, CYAN if active else (47, 61, 91), rect, 2, border_radius=8)
            label = slot
            weapon = player.weapons.get(slot)
            quick_item = player.quick_items.get(slot)
            if weapon:
                label = f"{slot} {self.weapon_title(weapon.key).split()[0]}"
                self._draw_rarity_frame(rect, weapon.rarity)
                self._draw_rarity_badge(rect, weapon.rarity, compact=True)
                self._mini_durability(rect, weapon.durability)
            elif quick_item:
                label = f"{slot} {self.item_title(quick_item.key).split()[0]}"
                self._draw_rarity_badge(rect, quick_item.rarity, compact=True)
                self._draw_item_icon(quick_item.key, pygame.Rect(rect.x + 22, rect.y + 6, 28, 28))
            self._draw_text_fit(label, rect.inflate(-10, -12), TEXT if weapon or quick_item else MUTED, self.small, center=True)
        self._draw_notice(player)

    def _draw_minimap(self, snapshot: WorldSnapshot, player: PlayerState | None) -> None:
        size = 226 if self.minimap_big else 156
        rect = pygame.Rect(SCREEN_W - size - 18, 18, size, int(size * MAP_HEIGHT / MAP_WIDTH))
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=8)
        pygame.draw.rect(self.screen, CYAN, rect, 2, border_radius=8)

        def mp(pos: Vec2) -> tuple[int, int]:
            return int(rect.x + pos.x / MAP_WIDTH * rect.w), int(rect.y + pos.y / MAP_HEIGHT * rect.h)

        for item in snapshot.loot.values():
            if player and item.floor != player.floor:
                continue
            pygame.draw.circle(self.screen, YELLOW, mp(item.pos), 2)
        for mine in snapshot.mines.values():
            if player and mine.floor != player.floor:
                continue
            pygame.draw.circle(self.screen, RED if mine.armed else YELLOW, mp(mine.pos), 3)
        for zombie in snapshot.zombies.values():
            if player and zombie.floor != player.floor:
                continue
            pygame.draw.circle(self.screen, RED, mp(zombie.pos), 3)
        for other in snapshot.players.values():
            pygame.draw.circle(self.screen, CYAN if player and other.id == player.id else GREEN, mp(other.pos), 4)
        for building in snapshot.buildings.values():
            mini = pygame.Rect(
                int(rect.x + building.bounds.x / MAP_WIDTH * rect.w),
                int(rect.y + building.bounds.y / MAP_HEIGHT * rect.h),
                max(2, int(building.bounds.w / MAP_WIDTH * rect.w)),
                max(2, int(building.bounds.h / MAP_HEIGHT * rect.h)),
            )
            pygame.draw.rect(self.screen, (84, 95, 118), mini, 1)

    def _draw_zombie_counter(self, snapshot: WorldSnapshot) -> None:
        size = 226 if self.minimap_big else 156
        minimap_h = int(size * MAP_HEIGHT / MAP_WIDTH)
        rect = pygame.Rect(SCREEN_W - size - 18, 18 + minimap_h + 12, size, 42)
        count = len(snapshot.zombies)
        pulse = (math.sin(time.time() * 3.6) + 1.0) * 0.5
        bg = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (20, 13, 24, 220), bg.get_rect(), border_radius=9)
        pygame.draw.rect(bg, (255, 91, 111, int(110 + pulse * 70)), bg.get_rect(), 2, border_radius=9)
        self.screen.blit(bg, rect)
        icon_rect = pygame.Rect(rect.x + 12, rect.y + 8, 26, 26)
        if not self._draw_item_icon("dead", icon_rect, aura=False, shadow=False):
            pygame.draw.circle(self.screen, RED, icon_rect.center, 10)
        self._draw_text_fit(self.tr("hud.zombies"), pygame.Rect(rect.x + 44, rect.y + 7, rect.w - 96, 15), MUTED, self.small)
        self._draw_text_fit(str(count), pygame.Rect(rect.right - 58, rect.y + 5, 42, 30), RED, self.mid, center=True)

    def _draw_notice(self, player: PlayerState) -> None:
        if not player.notice or player.notice_timer <= 0.0:
            return
        text = self.tr(player.notice)
        alpha = int(90 + min(1.0, player.notice_timer / 0.5) * 120)
        rect = pygame.Rect(0, 0, 430, 42)
        rect.center = (SCREEN_W // 2, 92)
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(surface, (20, 24, 36, alpha), surface.get_rect(), border_radius=10)
        pygame.draw.rect(surface, (*YELLOW, min(255, alpha + 30)), surface.get_rect(), 2, border_radius=10)
        self.screen.blit(surface, rect)
        self._draw_text_fit(text, rect.inflate(-24, -10), TEXT, self.font, center=True)

    def _draw_context_prompt(self, snapshot: WorldSnapshot, player: PlayerState | None, camera: Vec2) -> None:
        if not player or not player.alive:
            return
        prompt = ""
        for building in snapshot.buildings.values():
            for door in building.doors:
                if door.rect.center.distance_to(player.pos) <= 86:
                    prompt = self.tr("prompt.close_door") if door.open else self.tr("prompt.open_door")
            for stairs in building.stairs:
                if stairs.inflated(60).contains(player.pos):
                    prompt = f"{self.tr('prompt.stairs')} ({self._floor_label(player.floor)})"
            for prop in building.props:
                if prop.floor != player.floor:
                    continue
                if prop.rect.center.distance_to(player.pos) <= 92 and prop.kind == "work_bench":
                    prompt = self.tr("prompt.craft")
                elif prop.rect.center.distance_to(player.pos) <= 92 and prop.kind == "repair_table":
                    prompt = self.tr("prompt.repair")
        for item in snapshot.loot.values():
            if item.floor != player.floor:
                continue
            if item.pos.distance_to(player.pos) <= 72:
                prompt = self.tr("prompt.pickup", item=self._loot_label(item))
                break
        if prompt:
            sx, sy = self._world_to_screen(player.pos, camera)
            label = self.font.render(prompt, True, TEXT)
            bg = label.get_rect(center=(sx, sy - 72)).inflate(22, 12)
            pygame.draw.rect(self.screen, PANEL, bg, border_radius=7)
            pygame.draw.rect(self.screen, CYAN, bg, 1, border_radius=7)
            self.screen.blit(label, label.get_rect(center=bg.center))

    def _draw_scoreboard(self, snapshot: WorldSnapshot) -> None:
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((4, 7, 18, 206))
        self.screen.blit(overlay, (0, 0))
        panel = pygame.Rect(250, 96, 780, 520)
        glow = pygame.Surface(panel.inflate(26, 26).size, pygame.SRCALPHA)
        pygame.draw.rect(glow, (76, 225, 255, 34), glow.get_rect(), border_radius=16)
        pygame.draw.rect(glow, (255, 91, 111, 24), glow.get_rect().inflate(-10, -10), 2, border_radius=14)
        self.screen.blit(glow, panel.inflate(26, 26))
        pygame.draw.rect(self.screen, (15, 20, 38), panel, border_radius=10)
        pygame.draw.rect(self.screen, CYAN, panel, 2, border_radius=10)
        pygame.draw.line(self.screen, PURPLE, (panel.x + 24, panel.y + 92), (panel.right - 24, panel.y + 92), 2)
        self._draw_text(self.tr("scoreboard.title"), panel.x + 34, panel.y + 24, TEXT, self.big)
        headers = [
            self.tr("scoreboard.player"),
            self.tr("scoreboard.total"),
            self.tr("scoreboard.walker"),
            self.tr("scoreboard.runner"),
            self.tr("scoreboard.brute"),
            self.tr("scoreboard.leaper"),
            self.tr("scoreboard.status"),
        ]
        xs = [panel.x + 42, panel.x + 286, panel.x + 365, panel.x + 452, panel.x + 535, panel.x + 618, panel.x + 700]
        for x, header in zip(xs, headers):
            self._draw_text(header, x, panel.y + 112, CYAN if header == self.tr("scoreboard.total") else MUTED, self.small)
        y = panel.y + 150
        for player in sorted(snapshot.players.values(), key=lambda p: p.score, reverse=True):
            row = pygame.Rect(panel.x + 30, y - 8, 720, 42)
            row_color = (28, 42, 66) if player.alive else (48, 20, 31)
            border = GREEN if player.alive else RED
            if player.id == (self.local_player_id or self.online.player_id):
                border = CYAN
            pygame.draw.rect(self.screen, row_color, row, border_radius=7)
            pygame.draw.rect(self.screen, border, row, 1, border_radius=7)
            if not player.alive:
                self._draw_item_icon("dead", pygame.Rect(xs[0], y - 3, 24, 24), aura=False, shadow=False)
                name_x = xs[0] + 30
            else:
                pygame.draw.circle(self.screen, GREEN, (xs[0] + 10, y + 9), 6)
                name_x = xs[0] + 22
            values = [
                str(player.score),
                str(player.kills_by_kind.get("walker", 0)),
                str(player.kills_by_kind.get("runner", 0)),
                str(player.kills_by_kind.get("brute", 0)),
                str(player.kills_by_kind.get("leaper", 0)),
                self.tr("state.alive") if player.alive else self.tr("state.dead"),
            ]
            self._draw_text_fit(
                f"{player.name}{'' if player.alive else ' - ' + self.tr('state.dead')}",
                pygame.Rect(name_x, y, xs[1] - name_x - 12, 22),
                TEXT if player.alive else RED,
                self.font,
            )
            for x, value in zip(xs[1:], values):
                color = RED if value == self.tr("state.dead") else YELLOW if x == xs[1] else TEXT
                self._draw_text(value, x, y, color, self.font)
            y += 52

    def _draw_death_overlay(self) -> None:
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((60, 4, 10, 126))
        self.screen.blit(overlay, (0, 0))
        text = self.big.render(self.tr("death.title"), True, TEXT)
        self.screen.blit(text, text.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 - 44)))
        if self.state == "online_game":
            hint = self.mid.render(self.tr("death.online"), True, CYAN)
        else:
            hint = self.mid.render(self.tr("death.single"), True, CYAN)
        self.screen.blit(hint, hint.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 + 22)))

    def _draw_backpack(self, player: PlayerState) -> None:
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((2, 5, 12, 184))
        self.screen.blit(overlay, (0, 0))
        panel = self._backpack_panel_rect()
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=10)
        pygame.draw.rect(self.screen, CYAN, panel, 2, border_radius=10)
        self._draw_text(self.tr("backpack.title"), panel.x + 34, panel.y + 24, TEXT, self.big)
        self._draw_text(self.tr("backpack.body"), panel.x + 54, panel.y + 116, PURPLE, self.mid)
        self._draw_text(self.tr("backpack.help"), panel.x + 358, panel.y + 46, MUTED, self.small)

        self._draw_text(self.tr("backpack.quickbar"), 390, 106, CYAN, self.mid)
        for index, slot in enumerate(SLOTS):
            rect = self._quick_rect(index)
            active = player.active_slot == slot
            pygame.draw.rect(self.screen, PANEL_2 if active else BG, rect, border_radius=8)
            pygame.draw.rect(self.screen, CYAN if active else (52, 68, 98), rect, 2 if active else 1, border_radius=8)
            self._draw_text(slot, rect.x + 6, rect.y + 5, MUTED, self.small)
            weapon = player.weapons.get(slot)
            quick_item = player.quick_items.get(slot)
            if weapon and not self._is_dragging("weapon_slot", slot=slot):
                self._draw_rarity_frame(rect, weapon.rarity)
                self._draw_rarity_badge(rect, weapon.rarity, compact=True)
                self._draw_item_icon(weapon.key, pygame.Rect(rect.x + 16, rect.y + 11, 34, 34))
                self._mini_durability(rect, weapon.durability)
            elif quick_item and not self._is_dragging("quick_item", slot=slot):
                self._draw_item(quick_item.key, quick_item.amount, rect, quick_item.rarity)

        for slot in EQUIPMENT_SLOTS:
            rect = self._equipment_rect(slot)
            item = player.equipment.get(slot)
            pygame.draw.rect(self.screen, BG, rect, border_radius=8)
            pygame.draw.rect(self.screen, PURPLE if item else (58, 58, 88), rect, 2, border_radius=8)
            self._draw_text(self.tr(f"slot.{slot}"), rect.x + 12, rect.y + 10, MUTED, self.small)
            if item and not self._is_dragging("equipment", slot=slot):
                self._draw_item(item.key, item.amount, rect, item.rarity)
                self._mini_durability(rect, item.durability)
            repair = pygame.Rect(rect.right + 12, rect.y + 12, 70, 34)
            pygame.draw.rect(self.screen, PANEL_2, repair, border_radius=6)
            pygame.draw.rect(self.screen, YELLOW, repair, 1, border_radius=6)
            self._draw_text(self.tr("backpack.repair"), repair.x + 10, repair.y + 8, TEXT, self.small)

        for index in range(30):
            rect = self._backpack_rect(index)
            pygame.draw.rect(self.screen, BG, rect, border_radius=8)
            pygame.draw.rect(self.screen, (52, 68, 98), rect, 1, border_radius=8)
            item = player.backpack[index] if index < len(player.backpack) else None
            if item and not self._is_dragging("backpack", index=index):
                self._draw_item(item.key, item.amount, rect, item.rarity)

        drop = self._drop_rect()
        drop_hovered = bool(self.drag_source and drop.collidepoint(self._mouse_pos()))
        customize = self._customize_button_rect()
        pygame.draw.rect(self.screen, (60, 22, 30), drop, border_radius=8)
        pygame.draw.rect(self.screen, YELLOW if drop_hovered else RED, drop, 2, border_radius=8)
        self._draw_text(self.tr("backpack.drop"), drop.x + 44, drop.y + 20, TEXT, self.font)
        pygame.draw.rect(self.screen, PANEL_2, customize, border_radius=8)
        pygame.draw.rect(self.screen, PURPLE if self.weapon_custom_open else CYAN, customize, 2, border_radius=8)
        self._draw_text_fit(self.tr("backpack.customize"), customize.inflate(-18, -8), TEXT, self.font, center=True)
        if self.weapon_custom_open:
            self._draw_weapon_customization(player)
        self._draw_drag_preview(player)

    def _draw_item(self, key: str, amount: int, rect: pygame.Rect, rarity: str = "common") -> None:
        spec = ITEMS.get(key)
        color = YELLOW if key in WEAPONS else spec.color if spec else TEXT
        rarity_highlight = key in WEAPONS or bool(spec and spec.kind == "armor") or rarity != "common"
        if rarity_highlight:
            color = rarity_color(rarity)
            self._draw_rarity_frame(rect, rarity)
        icon_rect = pygame.Rect(rect.x + 12, rect.y + 8, min(36, rect.w - 18), min(36, rect.h - 20))
        if not self._draw_item_icon(key, icon_rect):
            pygame.draw.circle(self.screen, color, rect.center, min(rect.w, rect.h) // 4)
            pygame.draw.circle(self.screen, (255, 255, 255), rect.center, min(rect.w, rect.h) // 4, 1)
        self._draw_rarity_badge(rect, rarity)
        title = self.weapon_title(key) if key in WEAPONS else self.item_title(key)
        self._draw_text(title[:12], rect.x + 6, rect.y + rect.h - 20, color if rarity_highlight else TEXT, self.small)
        if amount > 1:
            self._draw_text(str(amount), rect.right - 26, rect.bottom - 36, YELLOW, self.small)

    def _craft_panel_rect(self) -> pygame.Rect:
        return pygame.Rect(126, 56, 1028, 648)

    def _craft_viewport_rect(self) -> pygame.Rect:
        panel = self._craft_panel_rect()
        return pygame.Rect(panel.x + 34, panel.y + 126, panel.w - 86, panel.h - 164)

    def _craft_scroll_track_rect(self) -> pygame.Rect:
        viewport = self._craft_viewport_rect()
        return pygame.Rect(viewport.right + 14, viewport.y, 10, viewport.h)

    def _craft_card_metrics(self) -> tuple[int, int, int, int]:
        return 294, 112, 18, 3

    def _craft_content_height(self) -> int:
        card_w, card_h, gap, cols = self._craft_card_metrics()
        rows = max(1, math.ceil(len(RECIPES) / cols))
        return rows * card_h + max(0, rows - 1) * gap

    def _craft_max_scroll(self) -> int:
        return max(0, self._craft_content_height() - self._craft_viewport_rect().h)

    def _scroll_crafting(self, direction: int) -> None:
        self.craft_scroll = max(0, min(self._craft_max_scroll(), self.craft_scroll + direction * 78))

    def _set_craft_scroll_from_pointer(self, y: int) -> None:
        track = self._craft_scroll_track_rect()
        max_scroll = self._craft_max_scroll()
        if max_scroll <= 0:
            self.craft_scroll = 0
            return
        knob_h = max(42, int(track.h * track.h / max(track.h, self._craft_content_height())))
        ratio = (y - track.y - knob_h * 0.5) / max(1, track.h - knob_h)
        self.craft_scroll = max(0, min(max_scroll, int(max_scroll * ratio)))

    def _craft_recipe_rect(self, index: int) -> pygame.Rect:
        viewport = self._craft_viewport_rect()
        card_w, card_h, gap, cols = self._craft_card_metrics()
        col = index % cols
        row = index // cols
        return pygame.Rect(viewport.x + col * (card_w + gap), viewport.y + row * (card_h + gap) - self.craft_scroll, card_w, card_h)

    def _recipe_result_kind(self, recipe_key: str) -> str:
        recipe = RECIPES[recipe_key]
        result_key, _ = recipe.result
        if result_key in WEAPONS:
            return "weapon"
        spec = ITEMS.get(result_key)
        return spec.kind if spec else "item"

    def _draw_crafting(self, player: PlayerState) -> None:
        self.craft_scroll = max(0, min(self._craft_max_scroll(), self.craft_scroll))
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((2, 5, 12, 190))
        self.screen.blit(overlay, (0, 0))
        panel = self._craft_panel_rect()
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=10)
        pygame.draw.rect(self.screen, (44, 68, 77), panel.inflate(8, 8), 1, border_radius=12)
        pygame.draw.rect(self.screen, GREEN, panel, 2, border_radius=10)
        self._draw_text(self.tr("craft.title"), panel.x + 34, panel.y + 24, TEXT, self.big)
        self._draw_text(self.tr("craft.caption"), panel.x + 38, panel.y + 90, MUTED, self.small)
        odds = pygame.Rect(panel.right - 438, panel.y + 28, 392, 64)
        pygame.draw.rect(self.screen, (12, 18, 30), odds, border_radius=9)
        pygame.draw.rect(self.screen, (55, 74, 102), odds, 1, border_radius=9)
        self._draw_text_fit(self.tr("craft.rarity_odds"), pygame.Rect(odds.x + 14, odds.y + 10, 138, 18), MUTED, self.small)
        self._draw_craft_rarity_odds(odds.x + 156, odds.y + 11, "preview", "item", large=True)

        mouse = self._mouse_pos()
        viewport = self._craft_viewport_rect()
        pygame.draw.rect(self.screen, (9, 13, 23), viewport.inflate(12, 12), border_radius=10)
        pygame.draw.rect(self.screen, (42, 57, 82), viewport.inflate(12, 12), 1, border_radius=10)
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(viewport)
        for index, recipe in enumerate(RECIPES.values()):
            rect = self._craft_recipe_rect(index)
            if rect.colliderect(viewport.inflate(18, 18)):
                self._draw_craft_card(player, recipe.key, rect, mouse)
        self.screen.set_clip(previous_clip)
        self._draw_craft_scrollbar()

    def _draw_craft_scrollbar(self) -> None:
        track = self._craft_scroll_track_rect()
        pygame.draw.rect(self.screen, (8, 12, 20), track, border_radius=5)
        pygame.draw.rect(self.screen, (52, 68, 98), track, 1, border_radius=5)
        max_scroll = self._craft_max_scroll()
        if max_scroll <= 0:
            pygame.draw.rect(self.screen, GREEN, track.inflate(-2, -2), border_radius=4)
            return
        knob_h = max(42, int(track.h * track.h / max(track.h, self._craft_content_height())))
        knob_y = track.y + int((track.h - knob_h) * (self.craft_scroll / max_scroll))
        knob = pygame.Rect(track.x + 2, knob_y, track.w - 4, knob_h)
        pygame.draw.rect(self.screen, GREEN, knob, border_radius=4)
        pygame.draw.rect(self.screen, (202, 255, 218), knob, 1, border_radius=4)

    def _draw_craft_card(self, player: PlayerState, recipe_key: str, rect: pygame.Rect, mouse: tuple[int, int]) -> None:
        recipe = RECIPES[recipe_key]
        result_key, result_amount = recipe.result
        result_kind = self._recipe_result_kind(recipe_key)
        can_craft = all(self._inventory_count(player, key) >= amount for key, amount in recipe.requires.items())
        hovered = rect.collidepoint(mouse)
        accent = GREEN if can_craft else (96, 108, 132)
        if can_craft or hovered:
            pulse = (math.sin(time.time() * 5.0) + 1.0) * 0.5
            glow_rect = rect.inflate(14, 14)
            glow = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(glow, (*accent, int(26 + pulse * 30)), glow.get_rect(), border_radius=12)
            self.screen.blit(glow, glow_rect)
        pygame.draw.rect(self.screen, PANEL_2 if can_craft else (15, 19, 30), rect, border_radius=9)
        pygame.draw.rect(self.screen, accent, rect, 2 if can_craft else 1, border_radius=9)
        pygame.draw.rect(self.screen, (255, 255, 255, 16 if can_craft else 6), rect.inflate(-8, -8), 1, border_radius=7)
        if not can_craft:
            shade = pygame.Surface(rect.size, pygame.SRCALPHA)
            shade.fill((0, 0, 0, 46))
            self.screen.blit(shade, rect)

        result_rect = pygame.Rect(rect.x + 14, rect.y + 18, 68, 68)
        result_color = rarity_color("uncommon") if result_kind in {"armor", "weapon_module"} else self._icon_color(result_key)
        pygame.draw.rect(self.screen, (7, 11, 19), result_rect, border_radius=8)
        pygame.draw.rect(self.screen, result_color, result_rect, 2, border_radius=8)
        if not self._draw_item_icon(result_key, result_rect.inflate(-10, -10), aura=False):
            pygame.draw.circle(self.screen, result_color, result_rect.center, 18)
        if result_amount > 1:
            self._draw_text(str(result_amount), result_rect.right - 14, result_rect.bottom - 18, YELLOW, self.small)

        title_color = TEXT if can_craft else MUTED
        self._draw_text_fit(self.recipe_title(recipe.key), pygame.Rect(rect.x + 96, rect.y + 12, rect.w - 110, 20), title_color, self.font)
        self._draw_craft_rarity_odds(rect.x + 96, rect.y + 39, recipe.key, result_kind)

        req_x = rect.x + 96
        req_y = rect.y + 72
        for index, (key, amount) in enumerate(recipe.requires.items()):
            have = self._inventory_count(player, key)
            filled = have >= amount
            req_rect = pygame.Rect(req_x + index * 42, req_y, 36, 32)
            pygame.draw.rect(self.screen, (7, 11, 19), req_rect, border_radius=6)
            pygame.draw.rect(self.screen, GREEN if filled else RED, req_rect, 1, border_radius=6)
            if not self._draw_item_icon(key, pygame.Rect(req_rect.x + 5, req_rect.y + 3, 22, 22), aura=False, shadow=False):
                pygame.draw.circle(self.screen, GREEN if filled else RED, (req_rect.x + 16, req_rect.y + 14), 8)
            count_color = GREEN if filled else RED
            self._draw_text_fit(f"{min(have, 99)}/{amount}", pygame.Rect(req_rect.x + 1, req_rect.bottom - 11, req_rect.w - 2, 10), count_color, self.small, center=True)

    def _draw_craft_rarity_odds(self, x: int, y: int, recipe_key: str, result_kind: str, large: bool = False) -> None:
        chances = craft_rarity_chances(recipe_key, result_kind)
        cursor = x
        for rarity in RARITY_KEYS:
            chance = chances.get(rarity, 0.0)
            if chance <= 0:
                continue
            color = rarity_color(rarity)
            icon_size = 18 if large else 12
            chip_w = 52 if large else 42
            chip_h = 36 if large else 16
            chip = pygame.Rect(cursor, y, chip_w, chip_h)
            pygame.draw.rect(self.screen, (8, 12, 20), chip, border_radius=6)
            pygame.draw.rect(self.screen, color, chip, 1, border_radius=6)
            self._draw_item_icon(rarity, pygame.Rect(chip.x + 5, chip.y + 4, icon_size, icon_size), aura=False, shadow=False)
            percent = f"{chance:.0f}%"
            if large:
                self._draw_text_fit(percent, pygame.Rect(chip.x + 4, chip.bottom - 13, chip.w - 8, 10), color, self.small, center=True)
            else:
                self._draw_text_fit(percent, pygame.Rect(chip.x + 17, chip.y + 3, chip.w - 19, 10), color, self.small)
            cursor += chip_w + (7 if large else 3)

    def _draw_weapon_customization(self, player: PlayerState) -> None:
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((3, 6, 14, 148))
        self.screen.blit(overlay, (0, 0))
        panel = self._weapon_custom_panel_rect()
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=10)
        pygame.draw.rect(self.screen, (55, 38, 88), panel.inflate(8, 8), 1, border_radius=12)
        pygame.draw.rect(self.screen, PURPLE, panel, 2, border_radius=10)
        self._draw_text_fit(self.tr("weaponmods.title"), pygame.Rect(panel.x + 28, panel.y + 18, 420, 44), TEXT, self.mid)
        self._draw_text_fit(self.tr("weaponmods.click_install"), pygame.Rect(panel.x + 32, panel.y + 54, 560, 20), MUTED, self.small)
        self._draw_button(self._weapon_custom_close_rect(), self.tr("weaponmods.close"), False)

        self._draw_text(self.tr("weaponmods.weapon"), panel.x + 34, panel.y + 76, MUTED, self.small)
        for index, slot in enumerate(SLOTS):
            rect = self._weapon_custom_slot_rect(index)
            weapon = player.weapons.get(slot)
            selected = slot == self._custom_weapon_slot(player)
            pygame.draw.rect(self.screen, PANEL_2 if selected else BG, rect, border_radius=8)
            pygame.draw.rect(self.screen, CYAN if selected else (52, 68, 98), rect, 2 if selected else 1, border_radius=8)
            self._draw_text(slot, rect.x + 6, rect.y + 5, MUTED, self.small)
            if weapon:
                if selected:
                    self._draw_rarity_frame(rect, weapon.rarity)
                self._draw_item_icon(weapon.key, pygame.Rect(rect.x + 28, rect.y + 7, 38, 28), aura=False)
                self._draw_text_fit(self.weapon_title(weapon.key).split()[0], pygame.Rect(rect.x + 8, rect.bottom - 18, rect.w - 16, 14), TEXT, self.small, center=True)
            else:
                self._draw_text_fit(slot, rect.inflate(-8, -10), MUTED, self.small, center=True)

        weapon_slot = self._custom_weapon_slot(player)
        weapon = player.weapons.get(weapon_slot)
        if not weapon:
            empty = pygame.Rect(panel.x + 34, panel.y + 168, panel.w - 68, 180)
            pygame.draw.rect(self.screen, BG, empty, border_radius=10)
            pygame.draw.rect(self.screen, (58, 68, 92), empty, 1, border_radius=10)
            self._draw_text_fit(self.tr("weaponmods.empty"), empty.inflate(-40, -40), MUTED, self.font, center=True)
            return
        mag_size = self._client_weapon_magazine_size(weapon)
        info = pygame.Rect(panel.x + 34, panel.y + 164, 292, 210)
        pygame.draw.rect(self.screen, (12, 17, 29), info, border_radius=10)
        pygame.draw.rect(self.screen, rarity_color(weapon.rarity), info, 2, border_radius=10)
        weapon_rect = pygame.Rect(info.x + 18, info.y + 34, 104, 88)
        self._draw_rarity_frame(weapon_rect, weapon.rarity)
        self._draw_rarity_badge(weapon_rect, weapon.rarity, compact=True)
        self._draw_item_icon(weapon.key, weapon_rect.inflate(-14, -18))
        self._draw_text_fit(
            f"{self.rarity_title(weapon.rarity)} {self.weapon_title(weapon.key)}",
            pygame.Rect(info.x + 136, info.y + 34, 138, 34),
            rarity_color(weapon.rarity),
            self.font,
        )
        self._draw_text_fit(f"{self.tr('weaponmods.magazine')}: {mag_size}", pygame.Rect(info.x + 136, info.y + 78, 130, 18), MUTED, self.small)
        utility_title = self.item_title(weapon.modules["utility"]) if weapon.modules.get("utility") else self.tr("weaponmods.empty_slot")
        magazine_title = self.item_title(weapon.modules["magazine"]) if weapon.modules.get("magazine") else self.tr("weaponmods.empty_slot")
        self._draw_text_fit(f"{self.tr('weaponmods.slot.utility')}: {utility_title}", pygame.Rect(info.x + 20, info.y + 142, 250, 18), TEXT, self.small)
        self._draw_text_fit(f"{self.tr('weaponmods.slot.magazine')}: {magazine_title}", pygame.Rect(info.x + 20, info.y + 166, 250, 18), TEXT, self.small)

        for module_slot in WEAPON_MODULE_SLOTS:
            rect = self._weapon_module_rect(module_slot)
            module_key = weapon.modules.get(module_slot)
            pygame.draw.rect(self.screen, PANEL_2 if module_key else BG, rect, border_radius=10)
            pygame.draw.rect(self.screen, GREEN if module_key else (58, 68, 92), rect, 2, border_radius=10)
            self._draw_text_fit(self.tr(f"weaponmods.slot.{module_slot}"), pygame.Rect(rect.x + 14, rect.y + 12, rect.w - 28, 18), MUTED, self.small)
            dragging_this_module = (
                self.drag_source
                and self.drag_source.get("source") == "weapon_module"
                and self.drag_source.get("slot") == weapon_slot
                and self.drag_source.get("module_slot") == module_slot
            )
            if module_key and not dragging_this_module:
                self._draw_item_icon(module_key, pygame.Rect(rect.x + 18, rect.y + 38, 58, 54))
                self._draw_text_fit(self.item_title(module_key), pygame.Rect(rect.x + 86, rect.y + 42, rect.w - 100, 20), TEXT, self.font)
                self._draw_text_fit(self._module_effect_text(module_key), pygame.Rect(rect.x + 86, rect.y + 70, rect.w - 100, 18), GREEN, self.small)
                self._draw_text_fit(self.tr("weaponmods.drag_remove"), pygame.Rect(rect.x + 18, rect.bottom - 24, rect.w - 36, 16), MUTED, self.small)
            else:
                self._draw_text_fit(self.tr("weaponmods.empty_slot"), pygame.Rect(rect.x + 18, rect.y + 48, rect.w - 36, 28), MUTED, self.font, center=True)

        return_rect = self._weapon_module_return_rect()
        return_hot = bool(self.drag_source and self.drag_source.get("source") == "weapon_module")
        pygame.draw.rect(self.screen, (12, 17, 29), return_rect, border_radius=9)
        pygame.draw.rect(self.screen, CYAN if return_hot else (58, 68, 92), return_rect, 2 if return_hot else 1, border_radius=9)
        self._draw_text_fit(self.tr("weaponmods.return_bay"), return_rect.inflate(-24, -12), CYAN if return_hot else MUTED, self.small, center=True)

        self._draw_text(self.tr("weaponmods.available"), panel.x + 34, panel.y + 388, TEXT, self.mid)
        self._draw_text_fit(self.tr("weaponmods.click_install"), pygame.Rect(panel.x + 250, panel.y + 396, 490, 18), MUTED, self.small)
        for module_key, indices in self._available_module_groups(player):
            rect = self._available_module_rect(module_key)
            module = WEAPON_MODULES[module_key]
            available = len(indices)
            installed_here = weapon.modules.get(module.slot) == module_key
            accent = GREEN if available else MUTED
            if installed_here:
                accent = CYAN
            if available:
                glow_rect = rect.inflate(10, 10)
                glow = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
                pygame.draw.rect(glow, (*accent, 28), glow.get_rect(), border_radius=12)
                self.screen.blit(glow, glow_rect)
            pygame.draw.rect(self.screen, PANEL_2 if available else BG, rect, border_radius=10)
            pygame.draw.rect(self.screen, accent, rect, 2 if available or installed_here else 1, border_radius=10)
            self._draw_item_icon(module_key, pygame.Rect(rect.x + 14, rect.y + 22, 54, 50), aura=False)
            self._draw_text_fit(self.item_title(module_key), pygame.Rect(rect.x + 76, rect.y + 18, rect.w - 88, 20), TEXT if available else MUTED, self.font)
            self._draw_text_fit(self._module_effect_text(module_key), pygame.Rect(rect.x + 76, rect.y + 44, rect.w - 88, 18), GREEN if available else MUTED, self.small)
            count_text = self.tr("weaponmods.installed") if installed_here and not available else f"x{available}"
            self._draw_text_fit(count_text, pygame.Rect(rect.x + 76, rect.y + 68, rect.w - 88, 18), CYAN if installed_here else YELLOW if available else MUTED, self.small)

    def _client_weapon_magazine_size(self, weapon: object) -> int:
        base = WEAPONS[weapon.key].magazine_size
        module_key = weapon.modules.get("magazine")
        module = WEAPON_MODULES.get(module_key or "")
        return max(base, int(math.ceil(base * (module.magazine_multiplier if module else 1.0))))

    def _client_armor_max(self, player: PlayerState) -> int:
        best = max(1, ARMORS.get(player.armor_key, ARMORS["none"]).armor_points)
        for item in player.equipment.values():
            spec = ITEMS.get(item.key) if item else None
            if not item or not spec or not spec.armor_key or item.durability <= 0:
                continue
            armor = ARMORS.get(spec.armor_key, ARMORS["none"])
            rarity = rarity_spec(item.rarity)
            best = max(best, int(round(armor.armor_points * rarity.armor_points_multiplier)))
        return max(1, best)

    def _draw_settings(self, panel_only: bool = False) -> None:
        if not panel_only:
            overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            overlay.fill((1, 3, 8, 166))
            self.screen.blit(overlay, (0, 0))
        panel = self._settings_panel_rect()
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=10)
        pygame.draw.rect(self.screen, CYAN, panel, 2, border_radius=10)
        title = self.tr("settings.title") if panel_only else self.tr("settings.pause")
        self._draw_text_fit(title, pygame.Rect(panel.x + 34, panel.y + 24, panel.w - 68, 58), TEXT, self.big)
        self._draw_text(self.tr("settings.caption"), panel.x + 38, panel.y + 88, MUTED, self.small)
        labels = {
            "bot_vision": self.tr("settings.bot_vision"),
            "bot_vision_range": self.tr("settings.bot_vision_range"),
            "ai_reactions": self.tr("settings.ai_reactions"),
            "health_bars": self.tr("settings.health_bars"),
            "noise_radius": self.tr("settings.noise_radius"),
            "show_zombie_count": self.tr("settings.show_zombie_count"),
            "fullscreen": self.tr("settings.fullscreen"),
        }
        start_y, step_y = self._settings_grid()

        # Calculate centered positioning for settings options
        option_width = 400
        option_height = 40
        option_x = panel.x + (panel.w - option_width) // 2

        name_rect = self._settings_name_rect()
        pygame.draw.rect(self.screen, (12, 18, 30), name_rect, border_radius=8)
        pygame.draw.rect(self.screen, CYAN if self.name_editing else (58, 78, 108), name_rect, 2, border_radius=8)
        self._draw_text_fit(self.tr("settings.player_name"), pygame.Rect(name_rect.x + 16, name_rect.y + 11, 142, 20), MUTED, self.font)
        display_name = self.name_input if self.name_editing else self.player_name
        if self.name_editing and int(time.time() * 2) % 2 == 0:
            display_name += "|"
        self._draw_text_fit(display_name, pygame.Rect(name_rect.x + 168, name_rect.y + 11, name_rect.w - 184, 20), TEXT, self.font)

        for index, key in enumerate(self.settings):
            rect = pygame.Rect(option_x, start_y + index * step_y, option_width, option_height)
            pygame.draw.rect(self.screen, PANEL_2, rect, border_radius=8)
            pygame.draw.rect(self.screen, GREEN if self.settings[key] else MUTED, rect, 2, border_radius=8)
            marker = self.tr("state.on") if self.settings[key] else self.tr("state.off")
            self._draw_text_fit(labels[key], pygame.Rect(rect.x + 16, rect.y + 12, rect.w - 100, 20), TEXT, self.font)
            self._draw_text(marker, rect.right - 70, rect.y + 12, GREEN if self.settings[key] else RED, self.font)

        density_rect = pygame.Rect(option_x, start_y + len(self.settings) * step_y, option_width, option_height)
        pygame.draw.rect(self.screen, PANEL_2, density_rect, border_radius=8)
        pygame.draw.rect(self.screen, YELLOW, density_rect, 2, border_radius=8)
        self._draw_text_fit(self.tr("settings.bot_density"), pygame.Rect(density_rect.x + 16, density_rect.y + 12, density_rect.w - 140, 20), TEXT, self.font)
        self._draw_text_fit(self.tr(f"density.{self.bot_density}"), pygame.Rect(density_rect.right - 130, density_rect.y + 12, 114, 20), YELLOW, self.font)

        difficulty_rect = pygame.Rect(option_x, start_y + (len(self.settings) + 1) * step_y, option_width, option_height)
        pygame.draw.rect(self.screen, PANEL_2, difficulty_rect, border_radius=8)
        pygame.draw.rect(self.screen, PURPLE, difficulty_rect, 2, border_radius=8)
        self._draw_text_fit(self.tr("settings.difficulty"), pygame.Rect(difficulty_rect.x + 16, difficulty_rect.y + 12, difficulty_rect.w - 150, 20), TEXT, self.font)
        self._draw_text_fit(self.tr(f"difficulty.{self.difficulty_key}"), pygame.Rect(difficulty_rect.right - 140, difficulty_rect.y + 12, 124, 20), PURPLE, self.font)

        language_rect = pygame.Rect(option_x, start_y + (len(self.settings) + 2) * step_y, option_width, option_height)
        pygame.draw.rect(self.screen, PANEL_2, language_rect, border_radius=8)
        pygame.draw.rect(self.screen, CYAN, language_rect, 2, border_radius=8)
        self._draw_text_fit(self.tr("settings.language"), pygame.Rect(language_rect.x + 16, language_rect.y + 12, language_rect.w - 90, 20), TEXT, self.font)
        self._draw_text(self.language.upper(), language_rect.right - 70, language_rect.y + 12, CYAN, self.font)
        if panel_only:
            self._draw_button(self._settings_back_rect(), self.tr("settings.back"), False)
        else:
            self._draw_button(self._settings_resume_rect(), self.tr("settings.resume"), False)
            self._draw_button(self._settings_main_menu_rect(), self.tr("settings.main_menu"), False)

    def _backpack_rect(self, index: int) -> pygame.Rect:
        col = index % 6
        row = index // 6
        return pygame.Rect(390 + col * 92, 210 + row * 78, 74, 62)

    def _quick_rect(self, index: int) -> pygame.Rect:
        return pygame.Rect(390 + index * 72, 142, 58, 54)

    def _backpack_panel_rect(self) -> pygame.Rect:
        return pygame.Rect(76, 58, 1128, 642)

    def _drop_rect(self) -> pygame.Rect:
        return pygame.Rect(1020, 590, 190, 64)

    def _customize_button_rect(self) -> pygame.Rect:
        return pygame.Rect(1020, 514, 190, 54)

    def _weapon_custom_panel_rect(self) -> pygame.Rect:
        return pygame.Rect(138, 92, 1004, 578)

    def _weapon_custom_close_rect(self) -> pygame.Rect:
        panel = self._weapon_custom_panel_rect()
        return pygame.Rect(panel.right - 112, panel.y + 24, 82, 34)

    def _weapon_custom_slot_rect(self, index: int) -> pygame.Rect:
        panel = self._weapon_custom_panel_rect()
        return pygame.Rect(panel.x + 32 + index * 94, panel.y + 82, 84, 54)

    def _weapon_module_rect(self, module_slot: str) -> pygame.Rect:
        order = {"utility": 0, "magazine": 1}
        panel = self._weapon_custom_panel_rect()
        return pygame.Rect(panel.x + 360 + order.get(module_slot, 0) * 260, panel.y + 168, 236, 126)

    def _weapon_module_return_rect(self) -> pygame.Rect:
        panel = self._weapon_custom_panel_rect()
        return pygame.Rect(panel.x + 360, panel.y + 316, 496, 58)

    def _available_module_rect(self, module_key: str) -> pygame.Rect:
        panel = self._weapon_custom_panel_rect()
        order = {key: index for index, key in enumerate(WEAPON_MODULES)}
        index = order.get(module_key, 0)
        return pygame.Rect(panel.x + 34 + index * 226, panel.y + 414, 210, 96)

    def _equipment_rect(self, slot: str) -> pygame.Rect:
        order = {"head": 0, "torso": 1, "arms": 2, "legs": 3}
        return pygame.Rect(126, 170 + order[slot] * 94, 134, 72)

    def _repair_slot_at(self, pos: tuple[int, int]) -> str | None:
        for slot in EQUIPMENT_SLOTS:
            rect = self._equipment_rect(slot)
            if pygame.Rect(rect.right + 12, rect.y + 12, 70, 34).collidepoint(pos):
                return slot
        return None

    def _inventory_target_at(self, pos: tuple[int, int], player: PlayerState | None = None) -> dict[str, object] | None:
        if self.weapon_custom_open and player:
            weapon_slot = self._custom_weapon_slot(player)
            for module_slot in WEAPON_MODULE_SLOTS:
                if self._weapon_module_rect(module_slot).collidepoint(pos):
                    return {"source": "weapon_module", "slot": weapon_slot, "module_slot": module_slot}
            if self._weapon_module_return_rect().collidepoint(pos):
                return {"source": "module_return"}
            for module_key, indices in self._available_module_groups(player):
                if indices and self._available_module_rect(module_key).collidepoint(pos):
                    return {"source": "backpack", "index": indices[0]}
        for index, slot in enumerate(SLOTS):
            if self._quick_rect(index).collidepoint(pos):
                if player and player.weapons.get(slot):
                    return {"source": "weapon_slot", "slot": slot}
                if player and player.quick_items.get(slot):
                    return {"source": "quick_item", "slot": slot}
                return {"source": "weapon_slot", "slot": slot}
        for index in range(30):
            if self._backpack_rect(index).collidepoint(pos):
                return {"source": "backpack", "index": index}
        for slot in EQUIPMENT_SLOTS:
            if self._equipment_rect(slot).collidepoint(pos):
                return {"source": "equipment", "slot": slot}
        return None

    def _inventory_count(self, player: PlayerState, key: str) -> int:
        return sum(item.amount for item in player.backpack if item and item.key == key)

    def _is_repair_drag(self, player: PlayerState | None, source: dict[str, object]) -> bool:
        if not player or source.get("source") != "backpack":
            return False
        index = int(source.get("index", -1))
        return 0 <= index < len(player.backpack) and bool(player.backpack[index] and player.backpack[index].key == "repair_kit")

    def _repair_drag_action(self, source: dict[str, object], target: dict[str, object]) -> dict[str, object]:
        action: dict[str, object] = {"type": "repair_drag", "kit_index": source["index"], "target_source": target["source"]}
        if target["source"] == "backpack":
            action["target_index"] = target["index"]
        else:
            action["target_slot"] = target["slot"]
        return action

    def _settings_panel_rect(self) -> pygame.Rect:
        panel_width = 520
        panel_height = 680
        panel_x = (SCREEN_W - panel_width) // 2
        panel_y = (SCREEN_H - panel_height) // 2
        return pygame.Rect(panel_x, panel_y, panel_width, panel_height)

    def _settings_grid(self) -> tuple[int, int]:
        panel = self._settings_panel_rect()
        start_y = panel.y + 166
        step_y = 40
        return start_y, step_y

    def _settings_name_rect(self) -> pygame.Rect:
        panel = self._settings_panel_rect()
        return pygame.Rect(panel.x + 60, panel.y + 116, panel.w - 120, 40)

    def _settings_back_rect(self) -> pygame.Rect:
        panel = self._settings_panel_rect()
        button_width = 200
        button_height = 48
        button_x = panel.x + (panel.w - button_width) // 2
        button_y = panel.bottom - button_height - 20
        return pygame.Rect(button_x, button_y, button_width, button_height)

    def _settings_resume_rect(self) -> pygame.Rect:
        panel = self._settings_panel_rect()
        button_width = 180
        button_height = 48
        button_spacing = 20
        total_width = button_width * 2 + button_spacing
        start_x = panel.x + (panel.w - total_width) // 2
        button_y = panel.bottom - button_height - 20
        return pygame.Rect(start_x, button_y, button_width, button_height)

    def _settings_main_menu_rect(self) -> pygame.Rect:
        panel = self._settings_panel_rect()
        button_width = 180
        button_height = 48
        button_spacing = 20
        total_width = button_width * 2 + button_spacing
        start_x = panel.x + (panel.w - total_width) // 2
        button_y = panel.bottom - button_height - 20
        return pygame.Rect(start_x + button_width + button_spacing, button_y, button_width, button_height)

    def _is_dragging(self, source: str, index: int | None = None, slot: str | None = None) -> bool:
        if not self.drag_source or self.drag_source.get("source") != source:
            return False
        if index is not None and self.drag_source.get("index") != index:
            return False
        if slot is not None and self.drag_source.get("slot") != slot:
            return False
        return True

    def _dragged_payload(self, player: PlayerState | None) -> tuple[str, int, float | None, str] | None:
        if not player or not self.drag_source:
            return None
        source = str(self.drag_source.get("source", ""))
        if source == "backpack":
            index = int(self.drag_source.get("index", -1))
            item = player.backpack[index] if 0 <= index < len(player.backpack) else None
            return (item.key, item.amount, item.durability, item.rarity) if item else None
        if source == "equipment":
            item = player.equipment.get(str(self.drag_source.get("slot", "")))
            return (item.key, item.amount, item.durability, item.rarity) if item else None
        if source == "quick_item":
            item = player.quick_items.get(str(self.drag_source.get("slot", "")))
            return (item.key, item.amount, item.durability, item.rarity) if item else None
        if source == "weapon_module":
            weapon = player.weapons.get(str(self.drag_source.get("slot", "")))
            module_key = weapon.modules.get(str(self.drag_source.get("module_slot", ""))) if weapon else None
            return (module_key, 1, 100.0, "common") if module_key else None
        if source == "weapon_slot":
            weapon = player.weapons.get(str(self.drag_source.get("slot", "")))
            return (weapon.key, 1, weapon.durability, weapon.rarity) if weapon else None
        return None

    def _custom_weapon_slot(self, player: PlayerState | None) -> str:
        if player and player.weapons.get(self.custom_weapon_slot):
            return self.custom_weapon_slot
        if player and player.weapons.get(player.active_slot):
            return player.active_slot
        if player:
            return next((slot for slot in SLOTS if player.weapons.get(slot)), "1")
        return "1"

    def _available_module_groups(self, player: PlayerState) -> list[tuple[str, list[int]]]:
        groups = {key: [] for key in WEAPON_MODULES}
        for index, item in enumerate(player.backpack):
            if item and item.key in groups:
                groups[item.key].append(index)
        return [(key, groups[key]) for key in WEAPON_MODULES]

    def _module_effect_text(self, module_key: str) -> str:
        module = WEAPON_MODULES.get(module_key)
        if not module:
            return ""
        if module.key == "laser_module":
            return f"{self.tr('weaponmods.accuracy')} x{module.spread_multiplier:.2f}"
        if module.key == "flashlight_module":
            return f"{int(module.cone_range)} {self.tr('weaponmods.light')}"
        if module.key == "extended_mag":
            bonus = int(round((module.magazine_multiplier - 1.0) * 100))
            return f"+{bonus}% {self.tr('weaponmods.magazine')}"
        return self.tr(f"weaponmods.slot.{module.slot}")

    def _draw_drag_preview(self, player: PlayerState) -> None:
        payload = self._dragged_payload(player)
        if not payload:
            return
        key, amount, durability, rarity = payload
        mx, my = self._mouse_pos()
        rect = pygame.Rect(mx - 36, my - 32, 78, 66)
        glow = pygame.Surface((rect.w + 14, rect.h + 14), pygame.SRCALPHA)
        pygame.draw.rect(glow, (*rarity_color(rarity), 54), glow.get_rect(), border_radius=12)
        self.screen.blit(glow, (rect.x - 7, rect.y - 7))
        pygame.draw.rect(self.screen, PANEL_2, rect, border_radius=9)
        pygame.draw.rect(self.screen, rarity_color(rarity), rect, 2, border_radius=9)
        if not self._draw_item_icon(key, pygame.Rect(rect.x + 21, rect.y + 8, 36, 36)):
            pygame.draw.circle(self.screen, YELLOW, (rect.centerx, rect.y + 26), 15)
        self._draw_rarity_badge(rect, rarity)
        title = self.weapon_title(key) if key in WEAPONS else self.item_title(key)
        self._draw_text_fit(title.split()[0], pygame.Rect(rect.x + 6, rect.bottom - 20, rect.w - 12, 16), TEXT, self.small, center=True)
        if amount > 1:
            self._draw_text(str(amount), rect.right - 24, rect.bottom - 36, YELLOW, self.small)
        if durability is not None:
            self._mini_durability(rect, durability)

    def _draw_item_icon(self, key: str, rect: pygame.Rect, aura: bool = True, shadow: bool = True) -> bool:
        icon = self._scaled_icon(key, rect.size)
        if not icon:
            return False
        target = icon.get_rect(center=rect.center)
        color = self._icon_color(key)

        if aura:
            aura_rect = target.inflate(max(10, rect.w // 3), max(10, rect.h // 3))
            aura_surface = pygame.Surface(aura_rect.size, pygame.SRCALPHA)
            pygame.draw.ellipse(aura_surface, (*color, 26), aura_surface.get_rect())
            self.screen.blit(aura_surface, aura_rect)

        if shadow:
            shadow_icon = icon.copy()
            shadow_icon.fill((0, 0, 0, 120), special_flags=pygame.BLEND_RGBA_MULT)
            self.screen.blit(shadow_icon, target.move(2, 3))
        self.screen.blit(icon, target)
        return True

    def _scaled_icon(self, key: str, size: tuple[int, int]) -> pygame.Surface | None:
        source = self.item_images.get(key) or self.item_images.get(self.icon_mapping.get(key, ""))
        if not source:
            return None
        max_w, max_h = max(1, size[0]), max(1, size[1])
        source_w, source_h = source.get_size()
        scale = min(max_w / max(1, source_w), max_h / max(1, source_h))
        width = max(1, int(source_w * scale))
        height = max(1, int(source_h * scale))
        cache_key = (key, width, height)
        icon = self._icon_cache.get(cache_key)
        if icon is None:
            icon = pygame.transform.smoothscale(source, (width, height))
            self._icon_cache[cache_key] = icon
        return icon

    def _icon_color(self, key: str) -> tuple[int, int, int]:
        if key == "heart":
            return RED
        if key == "shield" or key in ARMORS:
            return CYAN
        if key in WEAPONS:
            return YELLOW
        spec = ITEMS.get(key)
        if spec:
            return spec.color
        return TEXT

    def _draw_rarity_frame(self, rect: pygame.Rect, rarity: str, width: int = 2) -> None:
        color = rarity_color(rarity)
        rank = rarity_rank(rarity)
        pulse = (math.sin(time.time() * 4.0) + 1.0) * 0.5
        glow_rect = rect.inflate(10 + rank * 5, 10 + rank * 5)
        glow = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
        for layer in range(2 + min(rank, 3)):
            layer_rect = glow.get_rect().inflate(-layer * 5, -layer * 5)
            alpha = max(10, int(42 + rank * 22 + pulse * 22) - layer * 17)
            pygame.draw.rect(glow, (*color, alpha), layer_rect, 2, border_radius=10)
        self.screen.blit(glow, glow_rect)
        pygame.draw.rect(self.screen, color, rect.inflate(2, 2), width + (1 if rank >= 2 else 0), border_radius=9)
        corner = 10 + rank * 2
        for sx, sy in ((rect.left, rect.top), (rect.right, rect.top), (rect.left, rect.bottom), (rect.right, rect.bottom)):
            x_dir = 1 if sx == rect.left else -1
            y_dir = 1 if sy == rect.top else -1
            pygame.draw.line(self.screen, color, (sx, sy), (sx + corner * x_dir, sy), 2)
            pygame.draw.line(self.screen, color, (sx, sy), (sx, sy + corner * y_dir), 2)

    def _draw_rarity_badge(self, rect: pygame.Rect, rarity: str, compact: bool = False) -> None:
        if rarity not in RARITY_KEYS:
            return
        size = 15 if compact else 18
        inset = 1 if compact else 5
        badge = pygame.Rect(rect.right - size - inset, rect.y + inset, size, size)
        color = rarity_color(rarity)
        glow_rect = badge.inflate(8, 8)
        glow = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
        pygame.draw.ellipse(glow, (*color, 44), glow.get_rect())
        self.screen.blit(glow, glow_rect)
        pygame.draw.rect(self.screen, (8, 12, 20), badge, border_radius=5)
        pygame.draw.rect(self.screen, color, badge, 1, border_radius=5)
        icon_rect = badge.inflate(-4, -4)
        if not self._draw_item_icon(rarity, icon_rect, aura=False, shadow=False):
            points = [(badge.centerx, badge.y + 3), (badge.right - 3, badge.centery), (badge.centerx, badge.bottom - 3), (badge.x + 3, badge.centery)]
            pygame.draw.polygon(self.screen, color, points)

    def _mini_durability(self, rect: pygame.Rect, durability: float) -> None:
        color = GREEN if durability >= 55 else YELLOW if durability >= 25 else RED
        bar = pygame.Rect(rect.x + 8, rect.bottom - 7, rect.w - 16, 4)
        pygame.draw.rect(self.screen, (34, 38, 50), bar, border_radius=2)
        pygame.draw.rect(self.screen, color, pygame.Rect(bar.x, bar.y, int(bar.w * max(0, min(100, durability)) / 100), bar.h), border_radius=2)

    def _floor_label(self, floor: int) -> str:
        if floor < 0:
            return f"B{abs(floor)}"
        return f"F{floor + 1}"

    def _draw_inventory(self, player: PlayerState) -> None:
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((2, 5, 12, 168))
        self.screen.blit(overlay, (0, 0))
        panel = pygame.Rect(260, 110, 760, 540)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=10)
        pygame.draw.rect(self.screen, CYAN, panel, 2, border_radius=10)
        self._draw_text("Inventory", panel.x + 38, panel.y + 26, TEXT, self.big)
        self._draw_text("Weapons", panel.x + 42, panel.y + 118, CYAN, self.mid)
        for index, slot in enumerate(SLOTS):
            x = panel.x + 42 + (index % 5) * 136
            y = panel.y + 158 + (index // 5) * 58
            rect = pygame.Rect(x, y, 120, 42)
            active = player.active_slot == slot
            pygame.draw.rect(self.screen, PANEL_2 if active else BG, rect, border_radius=7)
            pygame.draw.rect(self.screen, CYAN if active else (49, 62, 91), rect, 1, border_radius=7)
            weapon = player.weapons.get(slot)
            text = f"{slot}: empty"
            if weapon:
                text = f"{slot}: {WEAPONS[weapon.key].title.split()[0]}"
            self._draw_text(text, rect.x + 10, rect.y + 12, TEXT if weapon else MUTED, self.small)

        self._draw_text("Armor", panel.x + 42, panel.y + 250, PURPLE, self.mid)
        armor_y = panel.y + 292
        for index, armor_key in enumerate(player.owned_armors):
            rect = pygame.Rect(panel.x + 42 + index * 172, armor_y, 152, 46)
            active = player.armor_key == armor_key
            pygame.draw.rect(self.screen, PANEL_2 if active else BG, rect, border_radius=7)
            pygame.draw.rect(self.screen, PURPLE if active else (58, 58, 88), rect, 2, border_radius=7)
            self._draw_text(ARMORS[armor_key].title, rect.x + 12, rect.y + 13, TEXT, self.small)

        self._draw_text("Supplies", panel.x + 42, panel.y + 400, GREEN, self.mid)
        med_rect = pygame.Rect(panel.x + 42, panel.y + 442, 158, 46)
        pygame.draw.rect(self.screen, BG, med_rect, border_radius=7)
        pygame.draw.rect(self.screen, GREEN, med_rect, 2, border_radius=7)
        self._draw_text(f"Use medkit ({player.medkits})", med_rect.x + 12, med_rect.y + 13, TEXT, self.small)

    def _loot_label(self, item: LootState) -> str:
        if item.kind == "item" and item.payload in ITEMS:
            if ITEMS[item.payload].kind == "armor":
                return f"{self.rarity_title(item.rarity)} {self.item_title(item.payload)} x{item.amount}"
            return f"{self.item_title(item.payload)} x{item.amount}"
        if item.kind == "weapon" and item.payload in WEAPONS:
            return f"{self.rarity_title(item.rarity)} {self.weapon_title(item.payload)}"
        if item.kind == "armor" and item.payload in ARMORS:
            armor_title = self.tr(f"armor.{item.payload}") if self.tr(f"armor.{item.payload}") != f"armor.{item.payload}" else ARMORS[item.payload].title
            return f"{self.rarity_title(item.rarity)} {armor_title}"
        if item.kind == "ammo":
            return f"{self.tr('item.ammo_pack')} +{item.amount}"
        return self.tr("item.medicine")

    def _draw_button(self, rect: pygame.Rect, label: str, hovered: bool) -> None:
        # Create modern button with gradient and shadow effects
        if hovered:
            # Draw shadow for hovered state
            shadow_rect = rect.move(2, 3)
            shadow_surface = pygame.Surface((shadow_rect.w, shadow_rect.h), pygame.SRCALPHA)
            pygame.draw.rect(shadow_surface, (0, 0, 0, 60), shadow_surface.get_rect(), border_radius=10)
            self.screen.blit(shadow_surface, shadow_rect)

            # Draw gradient background for hover
            gradient_surface = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            for i in range(rect.h):
                alpha = 255 - (i * 40 // rect.h)
                color = (35, 45, 70, alpha)
                pygame.draw.line(gradient_surface, color, (0, i), (rect.w, i))
            self.screen.blit(gradient_surface, rect)

            # Draw main button
            pygame.draw.rect(self.screen, (40, 55, 85), rect, border_radius=10)
            pygame.draw.rect(self.screen, CYAN, rect, 3, border_radius=10)

            # Add inner glow
            inner_rect = rect.inflate(-6, -6)
            pygame.draw.rect(self.screen, (76, 225, 255, 30), inner_rect, 2, border_radius=8)
        else:
            # Normal state
            pygame.draw.rect(self.screen, PANEL, rect, border_radius=10)
            pygame.draw.rect(self.screen, (53, 68, 98), rect, 2, border_radius=10)

        # Draw text with better positioning
        text_color = TEXT if hovered else (200, 210, 230)
        font = self.mid if hovered else self.font
        self._draw_text_fit(label, rect.inflate(-24, -12), text_color, font, center=True)

    def _draw_text(
        self,
        text: str,
        x: int,
        y: int,
        color: tuple[int, int, int],
        font: pygame.font.Font | None = None,
    ) -> None:
        surface = (font or self.font).render(text, True, color)
        self.screen.blit(surface, (x, y))

    def _draw_text_fit(
        self,
        text: str,
        rect: pygame.Rect,
        color: tuple[int, int, int],
        font: pygame.font.Font | None = None,
        center: bool = False,
    ) -> None:
        fonts = [font or self.font, self.font, self.small]
        chosen = fonts[-1]
        for candidate in fonts:
            if candidate.size(text)[0] <= rect.w:
                chosen = candidate
                break
        surface = chosen.render(text, True, color)
        target = surface.get_rect(center=rect.center) if center else surface.get_rect(topleft=rect.topleft)
        self.screen.blit(surface, target)

    def _bar(self, x: int, y: int, w: int, h: int, ratio: float, color: tuple[int, int, int]) -> None:
        ratio = max(0.0, min(1.0, ratio))
        pygame.draw.rect(self.screen, (33, 40, 58), pygame.Rect(x, y, w, h), border_radius=4)
        pygame.draw.rect(self.screen, color, pygame.Rect(x, y, int(w * ratio), h), border_radius=4)
        pygame.draw.rect(self.screen, (100, 116, 150), pygame.Rect(x, y, w, h), 1, border_radius=4)
