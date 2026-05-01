from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pygame

from client.audio import AudioManager
from client.audio_config import load_audio_tuning
from client.death_effects import load_death_effect_tuning
from client.network import OnlineClient, ping_server
from client.settings_schema import (
    SETTINGS_TABS,
    tab_has_audio_sliders,
    tab_has_camera_distance,
    tab_has_language,
    tab_is_stub,
    tab_toggle_keys,
)
from client.single_setup_schema import DENSITY_ORDER, MAP_OPTIONS
from shared.constants import ARMORS, MAP_HEIGHT, MAP_WIDTH, SLOTS, WEAPONS, ZOMBIES
from shared.crafting import craft_rarity_chances
from shared.difficulty import DIFFICULTY_KEYS, load_difficulty
from shared.explosives import GRENADE_SPECS, MINE_SPECS, DEFAULT_GRENADE, DEFAULT_MINE
from shared.items import EQUIPMENT_SLOTS, ITEMS, RECIPES
from shared.level import tunnel_segments
from shared.models import BuildingState, ClientCommand, InputCommand, LootState, PlayerState, RectState, Vec2, WorldSnapshot
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
MINE_MAP_COLOR = (196, 96, 255)
ONLINE_MINIMAP_MIN_RADIUS = 1400.0
ONLINE_MINIMAP_MAX_RADIUS = 4200.0

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


def _connection_icon_from_state(value: str) -> str:
    if value in {"stable-connection", "unstable-connection", "packet-lost", "lost-connection"}:
        return value
    if value == "stable":
        return "stable-connection"
    if value == "unstable":
        return "unstable-connection"
    if value in {"packet_lost", "packet-lost"}:
        return "packet-lost"
    return "lost-connection" if value == "lost" else "unstable-connection"


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
    max_players: int = 0
    ready: bool = False
    status: str = "checking"
    difficulty: str = "medium"
    mode: str = "survival"
    pvp: bool = False


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
        self.label_font = pygame.font.SysFont("cambria", 19, bold=True)
        self.hud_title_font = pygame.font.SysFont("trebuchetms", 24, bold=True)
        self.hud_value_font = pygame.font.SysFont("consolas", 24, bold=True)
        self.emphasis_font = pygame.font.SysFont("georgia", 16, bold=True, italic=True)
        self.language = "en"
        self.locales = self._load_locales()
        self.icon_mapping = self._load_icon_mapping()
        self.item_images = self._load_item_images()
        self._icon_cache: dict[tuple[str, int, int], pygame.Surface] = {}
        self.damage_flash = 0.0
        self._last_local_health: float | None = None
        self._regen_target_health: float | None = None
        self._prev_grenade_state: dict[str, tuple[Vec2, int, str]] = {}
        self._prev_mine_state: dict[str, tuple[Vec2, int, str]] = {}
        self._explosion_effects: list[dict[str, object]] = []
        self._join_notifications: list[dict[str, object]] = []
        self.death_effects = load_death_effect_tuning()
        self._death_effects: list[dict[str, object]] = []
        self._prev_zombie_death_state: dict[str, dict[str, object]] = {}
        self._prev_player_death_state: dict[str, dict[str, object]] = {}
        self._prev_projectile_audio_state: dict[str, dict[str, object]] = {}
        self._played_projectile_sounds: set[str] = set()
        self._shot_sound_debounce: dict[str, float] = {}
        self._prev_reload_audio_state: dict[str, float] = {}
        self._last_empty_sound_at = 0.0
        self.scoreboard_scroll = 0
        saved_settings = self._load_client_settings()
        self.camera_distance = max(0.78, min(1.08, float(saved_settings.get("camera_distance", 0.92))))
        self.camera_zoom = self.camera_distance
        self.audio_tuning = load_audio_tuning()
        self.master_volume = self._read_volume(saved_settings, "master_volume", 0.8)
        self.music_volume = self._read_volume(saved_settings, "music_volume", 0.55)
        self.effects_volume = self._read_volume(saved_settings, "effects_volume", 0.8)
        self.audio = AudioManager(self.audio_tuning.menu_music_path, self.audio_tuning.actions_dir)
        self.audio.set_master_volume(self.master_volume)
        self.audio.set_music_volume(self.music_volume)
        self.audio.set_effects_volume(self.effects_volume)
        self.state = "menu"
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
        self.weapon_modules_scroll = 0
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
        self._local_command_id = 0
        self.drag_source: dict[str, object] | None = None
        self.custom_weapon_slot = "1"
        self.language = str(saved_settings.get("language", self.language))
        if self.language not in self.locales:
            self.language = "en"
        self.settings = {
            "bot_vision": bool(saved_settings.get("bot_vision", True)),
            "bot_vision_range": bool(saved_settings.get("bot_vision_range", True)),
            "ai_reactions": bool(saved_settings.get("ai_reactions", True)),
            "health_bars": bool(saved_settings.get("health_bars", True)),
            "noise_radius": bool(saved_settings.get("noise_radius", True)),
            "show_zombie_count": bool(saved_settings.get("show_zombie_count", False)),
            "fullscreen": bool(saved_settings.get("fullscreen", False)),
        }
        self.bot_density = str(saved_settings.get("single_bot_density", "normal"))
        self.bot_density_profiles = {
            "low": 0.65,
            "normal": 1.0,
            "high": 1.42,
        }
        if self.bot_density not in self.bot_density_profiles:
            self.bot_density = "normal"
        self.single_bots_enabled = bool(saved_settings.get("single_bots_enabled", True))
        self.single_map_key = str(saved_settings.get("single_map", "city"))
        self.difficulty_key = str(saved_settings.get("single_difficulty", "medium"))
        self.difficulty_options = list(DIFFICULTY_KEYS)
        if self.difficulty_key not in self.difficulty_options:
            self.difficulty_key = "medium"
        self.settings_tab = "general"
        self.settings_tabs = [tab.key for tab in SETTINGS_TABS]
        self.options_scroll = 0
        self.pause_settings_scroll = 0
        self.single_map_dropdown_open = False
        self.single_map_dropdown_alpha = 0.0
        self.single_map_scroll = 0
        self._dragging_audio_slider: str | None = None
        self.server_entries: list[ServerEntry] = []
        self.selected_server = 0
        self._last_ping_refresh = 0.0
        self._pinging = False
        # Create responsive menu buttons with proper centering
        self._menu_buttons = self._create_menu_buttons()
        if self.settings["fullscreen"]:
            self._set_display_mode(True)
        self._sync_menu_music()

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

    def _read_volume(self, settings: dict[str, object], key: str, default: float) -> float:
        try:
            value = float(settings.get(key, default))
        except (TypeError, ValueError):
            value = default
        if value > 1.0:
            value /= 100.0
        return max(0.0, min(1.0, value))

    def _save_client_settings(self) -> None:
        data = {
            "player_name": self.player_name,
            "language": self.language,
            "camera_distance": round(self.camera_distance, 3),
            "master_volume": round(self.master_volume, 3),
            "music_volume": round(self.music_volume, 3),
            "effects_volume": round(self.effects_volume, 3),
            "single_difficulty": self.difficulty_key,
            "single_bot_density": self.bot_density,
            "single_bots_enabled": self.single_bots_enabled,
            "single_map": self.single_map_key,
        }
        data.update({key: bool(value) for key, value in self.settings.items()})
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
        for path in image_dir.rglob("*.png"):
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
        self.audio.close()
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
            elif event.type == pygame.MOUSEMOTION:
                self._handle_mouse_motion(event)
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
            elif self.state in {"options", "single_setup"}:
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
        if event.button == 1 and self._settings_audio_active():
            if self._begin_audio_slider_drag(pos):
                return
        if self.weapon_custom_open and event.button in (4, 5):
            if self._weapon_module_viewport_rect().collidepoint(pos):
                self._scroll_weapon_modules(-1 if event.button == 4 else 1)
                return
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
                self.weapon_modules_scroll = 0
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
        if self._dragging_audio_slider:
            self._update_audio_slider_from_pos(self._dragging_audio_slider, pos, save=True)
            self._dragging_audio_slider = None
            return
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

    def _handle_mouse_motion(self, event: pygame.event.Event) -> None:
        if not self._dragging_audio_slider:
            return
        pos = self._display_to_screen(event.pos)
        self._update_audio_slider_from_pos(self._dragging_audio_slider, pos, save=False)

    def _handle_mouse_wheel(self, event: pygame.event.Event) -> None:
        if self.weapon_custom_open and self.backpack_open and self._weapon_module_viewport_rect().collidepoint(self._mouse_pos()):
            self._scroll_weapon_modules(-event.y)
            return
        if self.craft_open:
            self._scroll_crafting(-event.y)
            return
        if self.state == "options":
            self._scroll_options(-event.y)
            return
        if self.settings_open and self.state in {"single", "online_game"}:
            self._scroll_options(-event.y)
            return
        if self.backpack_open:
            return
        if self.state in {"single", "online_game"} and pygame.key.get_pressed()[pygame.K_TAB]:
            self._scroll_scoreboard(-event.y)

    def _handle_click(self, pos: tuple[int, int]) -> None:
        if self.state == "menu":
            for button in self._menu_buttons:
                if button.hovered(pos):
                    if button.action == "single":
                        self.state = "single_setup"
                    elif button.action == "online":
                        self._show_servers()
                    elif button.action == "options":
                        self.settings_tab = "general"
                        self.options_scroll = 0
                        self.state = "options"
                    elif button.action == "quit":
                        self.running = False
        elif self.state == "options":
            self._handle_settings_click(pos)
        elif self.state == "single_setup":
            self._handle_single_setup_click(pos)
        elif self.state == "servers":
            self._handle_server_click(pos)
        elif self.inventory_open and self.state in {"single", "online_game"}:
            self._handle_inventory_click(pos)

    def _handle_settings_click(self, pos: tuple[int, int]) -> None:
        if self.state == "options":
            self._handle_options_click(pos)
            return
        if self.state in {"single", "online_game"}:
            self._handle_pause_settings_click(pos)
            return

    def _handle_pause_settings_click(self, pos: tuple[int, int]) -> None:
        if self._settings_resume_rect().collidepoint(pos):
            self.settings_open = False
            return
        if self._settings_main_menu_rect().collidepoint(pos):
            self._back_to_menu()
            return
        panel = self._settings_panel_rect()
        for index, tab in enumerate(self.settings_tabs):
            rect = pygame.Rect(panel.x + 32 + index * 112, panel.y + 106, 102, 36)
            if rect.collidepoint(pos):
                self.settings_tab = tab
                self.options_scroll = 0
                return
        self._handle_options_click(pos)

    def _handle_options_click(self, pos: tuple[int, int]) -> None:
        panel = self._settings_panel_rect()
        if self._settings_back_rect().collidepoint(pos):
            if self.name_editing:
                self._commit_player_name()
            self.state = "menu"
            return
        for index, tab in enumerate(self.settings_tabs):
            rect = pygame.Rect(panel.x + 32 + index * 112, panel.y + 106, 102, 36)
            if rect.collidepoint(pos):
                self.settings_tab = tab
                self.options_scroll = 0
                return
        if tab_is_stub(self.settings_tab):
            return
        viewport = pygame.Rect(panel.x + 36, panel.y + 162, panel.w - 72, panel.h - 238)
        if not viewport.collidepoint(pos):
            return
        if tab_has_audio_sliders(self.settings_tab):
            self._begin_audio_slider_drag(pos)
            return
        options = tab_toggle_keys(self.settings_tab)
        step_y = 56
        option_height = 44
        option_x = viewport.x + 6
        option_width = viewport.w - 24
        for index, key in enumerate(options):
            y = viewport.y + index * step_y - self.options_scroll
            rect = pygame.Rect(option_x, y, option_width, option_height)
            if rect.collidepoint(pos):
                if key == "fullscreen":
                    self._toggle_fullscreen()
                else:
                    self.settings[key] = not self.settings[key]
                    if key == "show_zombie_count":
                        self._save_client_settings()
                return
        row_index = len(options)
        if tab_has_camera_distance(self.settings_tab):
            camera_rect = pygame.Rect(option_x, viewport.y + row_index * step_y - self.options_scroll, option_width, option_height)
            if camera_rect.collidepoint(pos):
                cycle = [1.0, 0.92, 0.84]
                nearest = min(cycle, key=lambda value: abs(value - self.camera_distance))
                self.camera_distance = cycle[(cycle.index(nearest) + 1) % len(cycle)]
                self._save_client_settings()
                return
            row_index += 1
        if tab_has_language(self.settings_tab):
            language_rect = pygame.Rect(option_x, viewport.y + row_index * step_y - self.options_scroll, option_width, option_height)
            if not language_rect.collidepoint(pos):
                return
            languages = sorted(self.locales)
            self.language = languages[(languages.index(self.language) + 1) % len(languages)]
            self._save_client_settings()

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
        viewport = self._weapon_module_viewport_rect()
        for module_key, indices in self._available_module_groups(player):
            rect = self._available_module_rect(module_key)
            module = WEAPON_MODULES.get(module_key)
            if viewport.collidepoint(pos) and rect.collidepoint(pos) and module and indices and player.weapons.get(weapon_slot):
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
        self._sync_menu_music()
        target_dropdown = 1.0 if self.single_map_dropdown_open and self.state == "single_setup" else 0.0
        self.single_map_dropdown_alpha += (target_dropdown - self.single_map_dropdown_alpha) * min(1.0, dt * 8.0)
        if self.state == "servers" and time.time() - self._last_ping_refresh > 4.0:
            self._refresh_pings()

        if self.state == "single" and self.world and self.local_player_id:
            if self.settings_open or self.backpack_open or self.craft_open or self.weapon_custom_open:
                self._dispatch_pending_commands(self.local_player_id)
                command = self._build_input(self.local_player_id)
                self.world.set_input(command)
                self.world.update(0.0)
                self._update_camera_zoom(dt)
                self._update_damage_feedback(dt)
                return
            self._dispatch_pending_commands(self.local_player_id)
            command = self._build_input(self.local_player_id)
            self.world.set_input(command)
            self.world.update(dt)
        elif self.state == "online_game" and self.online.player_id:
            self._dispatch_pending_commands(self.online.player_id)
            command = self._build_input(self.online.player_id)
            self.online.send_input(command)
            self._handle_online_events()
        self._update_camera_zoom(dt)
        self._update_damage_feedback(dt)

    def _sync_menu_music(self) -> None:
        self.audio.set_menu_music_active(self.state in {"menu", "options", "single_setup", "servers"})

    def _maybe_play_empty_weapon_sound(self, player: PlayerState) -> None:
        weapon = player.active_weapon()
        if not weapon or weapon.ammo_in_mag > 0 or weapon.reserve_ammo > 0:
            return
        now = time.time()
        if now - self._last_empty_sound_at < 0.34:
            return
        self._last_empty_sound_at = now
        self._play_weapon_action_sound(weapon.key, "empty", player.pos, player.floor, local=True)

    def _update_weapon_audio_from_snapshot(self, snapshot: WorldSnapshot) -> None:
        current_projectiles: dict[str, dict[str, object]] = {}
        for projectile in snapshot.projectiles.values():
            current_projectiles[projectile.id] = {
                "owner_id": projectile.owner_id,
                "weapon_key": projectile.weapon_key,
                "pos": projectile.pos.copy(),
                "floor": projectile.floor,
            }
            if projectile.id not in self._prev_projectile_audio_state:
                weapon_key = projectile.weapon_key or self._active_weapon_key(snapshot, projectile.owner_id)
                self._play_shot_sound(projectile.owner_id, weapon_key, projectile.pos, projectile.floor, projectile.id)
        self._prev_projectile_audio_state = current_projectiles
        if len(self._played_projectile_sounds) > 2048:
            self._played_projectile_sounds.clear()

        current_reload: dict[str, float] = {}
        for player in snapshot.players.values():
            weapon = player.active_weapon()
            reload_left = float(weapon.reload_left if weapon else 0.0)
            current_reload[player.id] = reload_left
            if weapon and reload_left > 0.0 and self._prev_reload_audio_state.get(player.id, 0.0) <= 0.0:
                self._play_weapon_action_sound(weapon.key, "reload", player.pos, player.floor, local=player.id == (self.local_player_id or self.online.player_id))
        self._prev_reload_audio_state = current_reload

    def _play_shot_event(self, event: dict[str, object]) -> None:
        projectile_id = str(event.get("projectile_id") or "")
        owner_id = str(event.get("owner_id") or "")
        weapon_key = str(event.get("weapon_key") or "")
        if not weapon_key:
            snapshot = self._snapshot()
            weapon_key = self._active_weapon_key(snapshot, owner_id) if snapshot else "pistol"
        try:
            pos = Vec2(float(event.get("x", 0.0)), float(event.get("y", 0.0)))
            floor = int(event.get("floor", 0))
        except (TypeError, ValueError):
            return
        self._play_shot_sound(owner_id, weapon_key, pos, floor, projectile_id)

    def _play_shot_sound(self, owner_id: str, weapon_key: str, pos: Vec2, floor: int, projectile_id: str = "") -> None:
        if projectile_id and projectile_id in self._played_projectile_sounds:
            return
        if projectile_id:
            self._played_projectile_sounds.add(projectile_id)
        weapon_key = weapon_key if weapon_key in WEAPONS else "pistol"
        now = time.time()
        debounce_key = f"{owner_id}:{weapon_key}"
        if now - self._shot_sound_debounce.get(debounce_key, -999.0) < 0.045:
            return
        self._shot_sound_debounce[debounce_key] = now
        self._play_weapon_action_sound(weapon_key, "shot", pos, floor, local=owner_id == (self.local_player_id or self.online.player_id))

    def _active_weapon_key(self, snapshot: WorldSnapshot | None, player_id: str) -> str:
        player = snapshot.players.get(player_id) if snapshot else None
        weapon = player.active_weapon() if player else None
        return weapon.key if weapon else "pistol"

    def _play_weapon_action_sound(self, weapon_key: str, action: str, pos: Vec2 | None, floor: int, *, local: bool = False) -> None:
        sound_key = self._weapon_sound_key(weapon_key, action)
        if not sound_key:
            return
        volume, pan = (1.0, 0.0) if local else self._spatial_sound_params(pos, floor)
        if volume <= 0.0:
            return
        self.audio.play_action_sound(sound_key, volume=volume, pan=pan)

    def _weapon_sound_key(self, weapon_key: str, action: str) -> str:
        spec = self.audio_tuning.weapon_sounds.get(weapon_key)
        if spec:
            return getattr(spec, action, "")
        if action == "shot":
            return weapon_key if weapon_key else "pistol"
        if action == "reload":
            return "reload"
        return "empty"

    def _spatial_sound_params(self, pos: Vec2 | None, floor: int) -> tuple[float, float]:
        if not pos:
            return 1.0, 0.0
        snapshot = self._snapshot()
        listener = self._local_player(snapshot) if snapshot else None
        if not listener:
            return 1.0, 0.0
        dx = pos.x - listener.pos.x
        dy = pos.y - listener.pos.y
        distance = math.hypot(dx, dy)
        max_distance = max(1.0, float(self.audio_tuning.shot_hearing_distance))
        full_distance = min(max_distance, max(0.0, float(self.audio_tuning.shot_full_volume_distance)))
        if distance >= max_distance:
            return 0.0, 0.0
        if distance <= full_distance:
            volume = 1.0
        else:
            ratio = (distance - full_distance) / max(1.0, max_distance - full_distance)
            volume = max(0.0, (1.0 - ratio) ** 1.35)
        if int(floor) != listener.floor:
            volume *= max(0.0, float(self.audio_tuning.different_floor_volume_multiplier))
        if volume < float(self.audio_tuning.min_spatial_volume):
            return 0.0, 0.0
        pan = max(-1.0, min(1.0, dx / max(240.0, max_distance * 0.42)))
        return volume, pan

    def _handle_online_events(self) -> None:
        if self.state != "online_game":
            return
        for event in self.online.poll_events():
            kind = event.get("kind")
            if kind == "server_shutdown":
                self.online.error = self.tr("online.server_shutdown")
                continue
            if kind == "player_joined":
                if str(event.get("player_id", "")) != str(self.online.player_id or ""):
                    self._add_join_notification(str(event.get("name") or "Player"))
                continue
            if kind == "shot":
                self._play_shot_event(event)
                continue
            if kind == "zombie_killed":
                self._add_zombie_death_from_event(event)
                continue
            if kind == "player_died":
                self._add_player_death_from_event(event)
                if event.get("player_id") == self.online.player_id:
                    self.damage_flash = min(1.0, max(self.damage_flash, 0.35))
                continue
            if kind == "hit" and event.get("target_id") == self.online.player_id:
                self.damage_flash = min(1.0, max(self.damage_flash, 0.35))

    def _add_join_notification(self, name: str) -> None:
        clean_name = self._clean_player_name(name)
        self._join_notifications.append(
            {
                "name": clean_name,
                "started": time.time(),
                "duration": 4.2,
            }
        )
        self._join_notifications = self._join_notifications[-4:]

    def _add_zombie_death_from_event(self, event: dict[str, object]) -> None:
        entity_id = str(event.get("entity_id") or "")
        if not entity_id:
            return
        kind = str(event.get("entity_kind") or "walker")
        if kind not in ZOMBIES:
            kind = "walker"
        try:
            pos = Vec2(float(event.get("x", 0.0)), float(event.get("y", 0.0)))
            floor = int(event.get("floor", 0))
            facing = float(event.get("facing", 0.0))
        except (TypeError, ValueError):
            return
        self._add_death_effect("zombie", entity_id, pos, floor, kind=kind, facing=facing)

    def _add_player_death_from_event(self, event: dict[str, object]) -> None:
        player_id = str(event.get("player_id") or "")
        if not player_id:
            return
        snapshot = self._snapshot()
        player = snapshot.players.get(player_id) if snapshot else None
        try:
            x_value = event.get("x", player.pos.x if player else 0.0)
            y_value = event.get("y", player.pos.y if player else 0.0)
            pos = Vec2(float(x_value), float(y_value))
            floor = int(event.get("floor", player.floor if player else 0))
            facing = float(event.get("angle", player.angle if player else 0.0))
        except (TypeError, ValueError):
            return
        name = str(event.get("name") or (player.name if player else "Player"))
        self._add_death_effect("player", player_id, pos, floor, name=name, facing=facing)

    def _add_death_effect(
        self,
        entity_type: str,
        entity_id: str,
        pos: Vec2,
        floor: int,
        *,
        kind: str = "",
        name: str = "",
        facing: float = 0.0,
    ) -> None:
        now = time.time()
        self._prune_death_effects(now)
        key = f"{entity_type}:{entity_id}"
        if any(str(effect.get("key", "")) == key for effect in self._death_effects):
            return
        seed_text = f"{key}:{kind}:{name}"
        seed = sum((index + 1) * ord(char) for index, char in enumerate(seed_text))
        self._death_effects.append(
            {
                "key": key,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "kind": kind,
                "name": name,
                "pos": pos.copy(),
                "floor": int(floor),
                "facing": float(facing),
                "started": now,
                "seed": seed,
            }
        )
        max_effects = max(1, int(self.death_effects.max_effects))
        if len(self._death_effects) > max_effects:
            self._death_effects = self._death_effects[-max_effects:]

    def _update_death_effects(self, snapshot: WorldSnapshot) -> None:
        now = time.time()
        current_zombies: dict[str, dict[str, object]] = {
            zombie.id: {
                "kind": zombie.kind,
                "pos": zombie.pos.copy(),
                "floor": zombie.floor,
                "facing": zombie.facing,
            }
            for zombie in snapshot.zombies.values()
        }
        if self.state == "single":
            for zombie_id, previous in self._prev_zombie_death_state.items():
                if zombie_id in current_zombies:
                    continue
                previous_pos = previous.get("pos")
                if isinstance(previous_pos, Vec2):
                    self._add_death_effect(
                        "zombie",
                        zombie_id,
                        previous_pos,
                        int(previous.get("floor", 0)),
                        kind=str(previous.get("kind", "walker")),
                        facing=float(previous.get("facing", 0.0)),
                    )
        self._prev_zombie_death_state = current_zombies

        current_players: dict[str, dict[str, object]] = {
            player.id: {
                "alive": player.alive,
                "pos": player.pos.copy(),
                "floor": player.floor,
                "name": player.name,
                "angle": player.angle,
            }
            for player in snapshot.players.values()
        }
        for player_id, current in current_players.items():
            previous = self._prev_player_death_state.get(player_id)
            if current.get("alive", True) or (previous and not previous.get("alive", True)):
                continue
            current_pos = current.get("pos")
            if isinstance(current_pos, Vec2):
                self._add_death_effect(
                    "player",
                    player_id,
                    current_pos,
                    int(current.get("floor", 0)),
                    name=str(current.get("name", "Player")),
                    facing=float(current.get("angle", 0.0)),
                )
        self._prev_player_death_state = current_players
        self._prune_death_effects(now)

    def _prune_death_effects(self, now: float) -> None:
        lifetime = max(float(self.death_effects.corpse_seconds), float(self.death_effects.blood_seconds))
        self._death_effects = [
            effect for effect in self._death_effects if now - float(effect.get("started", now)) <= lifetime + 0.08
        ]

    def _has_death_effect(self, entity_type: str, entity_id: str) -> bool:
        key = f"{entity_type}:{entity_id}"
        now = time.time()
        return any(
            str(effect.get("key", "")) == key
            and now - float(effect.get("started", now)) <= float(self.death_effects.corpse_seconds)
            for effect in self._death_effects
        )

    def _update_camera_zoom(self, dt: float) -> None:
        snapshot = self._snapshot()
        player = self._local_player(snapshot) if snapshot else None
        sprint_target = self.camera_distance * 0.9
        target = sprint_target if player and player.alive and player.sprinting else self.camera_distance
        target = max(0.72, min(1.12, target))
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
            self._regen_target_health = None
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
        mouse_buttons = pygame.mouse.get_pressed(num_buttons=3)
        right_pressed = bool(mouse_buttons[2])
        left_pressed = bool(mouse_buttons[0])
        has_weapon = bool(player and player.active_weapon())
        if player and left_pressed and not ui_open:
            self._maybe_play_empty_weapon_sound(player)
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

    def _dispatch_pending_commands(self, player_id: str) -> None:
        commands = self._pending_command_specs()
        if not commands:
            return
        if self.state == "online_game":
            if self.online.has_pending_commands():
                return
            sent_all = True
            for kind, payload in commands:
                sent_all = self.online.send_command(kind, payload) is not None and sent_all
            if sent_all:
                self._clear_transient_inputs()
            return
        if self.world:
            for kind, payload in commands:
                self._local_command_id += 1
                self.world.apply_client_command(ClientCommand(player_id, self._local_command_id, kind, payload))
            self._clear_transient_inputs()

    def _pending_command_specs(self) -> list[tuple[str, dict[str, object]]]:
        commands: list[tuple[str, dict[str, object]]] = []
        if self.pending_slot:
            commands.append(("select_slot", {"slot": self.pending_slot}))
        if self.pending_reload:
            commands.append(("reload", {}))
        if self.pending_pickup:
            commands.append(("pickup", {}))
        if self.pending_interact:
            commands.append(("interact", {}))
        if self.pending_toggle_utility:
            commands.append(("toggle_utility", {}))
        if self.pending_respawn:
            commands.append(("respawn", {}))
        if self.pending_throw_grenade:
            commands.append(("throw_grenade", {}))
        if self.pending_medkit:
            commands.append(("use_medkit", {}))
        if self.pending_inventory_action:
            commands.append(("inventory_action", dict(self.pending_inventory_action)))
        if self.pending_craft_key:
            commands.append(("craft", {"key": self.pending_craft_key}))
        if self.pending_repair_slot:
            commands.append(("repair", {"slot": self.pending_repair_slot}))
        if self.pending_equip_armor:
            commands.append(("equip_armor", {"armor_key": self.pending_equip_armor}))
        return commands

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

    def _reset_death_effect_tracking(self) -> None:
        self._death_effects.clear()
        self._prev_zombie_death_state.clear()
        self._prev_player_death_state.clear()
        self._prev_projectile_audio_state.clear()
        self._played_projectile_sounds.clear()
        self._shot_sound_debounce.clear()
        self._prev_reload_audio_state.clear()
        self._last_empty_sound_at = 0.0

    def _start_single_player(self) -> None:
        self.online.close()
        if self.world:
            self.world.close()
        difficulty = load_difficulty(self.difficulty_key)
        density = self.bot_density_profiles[self.bot_density]
        if self.single_bots_enabled:
            initial_zombies = max(1, int(round(difficulty.initial_zombies * density)))
            max_zombies = max(initial_zombies, int(round(difficulty.max_zombies * density)))
        else:
            initial_zombies = 0
            max_zombies = 0
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
        self._reset_death_effect_tracking()
        self.state = "single"
        self._save_client_settings()

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
            self._reset_death_effect_tracking()
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
        self._reset_death_effect_tracking()

    def _load_servers(self) -> list[ServerEntry]:
        path = ROOT / "servers.json"
        if not path.exists():
            return [ServerEntry("Local Dev", "127.0.0.1", 8765)]
        data = json.loads(path.read_text(encoding="utf-8"))
        entries: list[ServerEntry] = []
        for row in data:
            if not isinstance(row, dict):
                continue
            mode = str(row.get("mode", "survival"))
            entries.append(
                ServerEntry(
                    str(row["name"]),
                    str(row["host"]),
                    int(row["port"]),
                    mode=mode,
                    pvp=bool(row.get("pvp", False) or mode == "pvp"),
                )
            )
        return entries

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
                    entry.max_players = int(meta.get("max_players", 0)) if meta else 0
                    entry.ready = bool(meta.get("ready", False)) if meta else False
                    entry.difficulty = str(meta.get("difficulty", entry.difficulty)) if meta else entry.difficulty
                    entry.mode = str(meta.get("mode", entry.mode)) if meta else entry.mode
                    entry.pvp = bool(meta.get("pvp", entry.pvp) or entry.mode == "pvp") if meta else entry.pvp
                    entry.status = "ready" if ping is not None and entry.ready else "online" if ping is not None else "offline"
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
        elif self.state == "single_setup":
            self._draw_single_setup()
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
        pulse = (math.sin(time.time() * 2.8) + 1.0) * 0.5

        # Create responsive main menu panel
        panel_width = 420
        panel_height = 580
        panel_x = 48
        panel_y = (SCREEN_H - panel_height) // 2
        panel = pygame.Rect(panel_x, panel_y, panel_width, panel_height)

        pygame.draw.rect(self.screen, (10, 15, 25), panel, border_radius=12)
        pygame.draw.rect(self.screen, CYAN, panel, 2, border_radius=12)
        glow = pygame.Surface(panel.inflate(26, 26).size, pygame.SRCALPHA)
        pygame.draw.rect(glow, (76, 225, 255, int(22 + pulse * 34)), glow.get_rect(), 2, border_radius=16)
        self.screen.blit(glow, panel.inflate(26, 26))

        # Improved text positioning
        self._draw_text_fit(self.tr("app.title"), pygame.Rect(panel.x + 28, panel.y + 32, panel.w - 56, 64), TEXT, self.big, center=True)
        self._draw_text_fit(self.tr("menu.subtitle"), pygame.Rect(panel.x + 30, panel.y + 110, panel.w - 60, 24), CYAN, self.font, center=True)
        self._draw_text_fit(self.tr("menu.caption"), pygame.Rect(panel.x + 30, panel.y + 140, panel.w - 60, 20), MUTED, self.small, center=True)

        for button in self._menu_buttons:
            self._draw_button(button.rect, self.tr(button.label), button.hovered(self._mouse_pos()))
        self._draw_menu_showcase()

    def _draw_menu_showcase(self) -> None:
        pulse = (math.sin(time.time() * 3.3) + 1.0) * 0.5
        showcase = pygame.Rect(492, 96, 662, 548)
        pygame.draw.rect(self.screen, (12, 18, 28), showcase, border_radius=10)
        pygame.draw.rect(self.screen, (58, 78, 108), showcase, 2, border_radius=10)
        pulse_outline = pygame.Surface((676, 562), pygame.SRCALPHA)
        pygame.draw.rect(pulse_outline, (104, 198, 255, int(16 + pulse * 48)), pulse_outline.get_rect(), 1, border_radius=12)
        self.screen.blit(pulse_outline, (485, 89))
        for i in range(7):
            pygame.draw.line(self.screen, (25, 38, 58), (530 + i * 88, 128), (460 + i * 118, 562), 2)
        self._draw_text(self.tr("menu.systems"), 536, 132, TEXT, self.big)
        cards = [
            (self.tr("menu.card.stealth.title"), self.tr("menu.card.stealth.body"), CYAN, "silence"),
            (self.tr("menu.card.ai.title"), self.tr("menu.card.ai.body"), YELLOW, "ai"),
            (self.tr("menu.card.craft.title"), self.tr("menu.card.craft.body"), GREEN, "loot"),
            (self.tr("menu.card.online.title"), self.tr("menu.card.online.body"), PURPLE, "online"),
        ]
        for index, (title, body, color, image_key) in enumerate(cards):
            rect = pygame.Rect(530, 226 + index * 92, 556, 74)
            hover_pulse = 0.5 + 0.5 * math.sin(time.time() * 4.8 + index)
            pygame.draw.rect(self.screen, PANEL, rect, border_radius=8)
            pygame.draw.rect(self.screen, (54, 74, 104), rect, 1, border_radius=8)
            glow = pygame.Surface(rect.inflate(10, 10).size, pygame.SRCALPHA)
            pygame.draw.rect(glow, (*color, int(18 + hover_pulse * 38)), glow.get_rect(), 1, border_radius=10)
            self.screen.blit(glow, rect.inflate(10, 10))
            image_rect = pygame.Rect(rect.x + 14, rect.y + 11, 52, 52)
            pygame.draw.rect(self.screen, (10, 16, 28), image_rect, border_radius=9)
            pygame.draw.rect(self.screen, color, image_rect, 2, border_radius=9)
            if not self._draw_item_icon(image_key, image_rect.inflate(-8, -8), aura=False, shadow=False):
                pygame.draw.circle(self.screen, color, image_rect.center, 12)
            self._draw_text(title, rect.x + 80, rect.y + 10, TEXT, self.mid)
            self._draw_text(body, rect.x + 82, rect.y + 44, MUTED, self.small)

    def _draw_options_menu(self) -> None:
        self.screen.fill(BG)
        self._draw_neon_background()
        self._draw_settings_hub()

    def _draw_single_setup(self) -> None:
        self.screen.fill(BG)
        self._draw_neon_background()
        panel = pygame.Rect((SCREEN_W - 660) // 2, 120, 660, 500)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=12)
        pygame.draw.rect(self.screen, CYAN, panel, 2, border_radius=12)
        self._draw_text_fit(self.tr("single.setup.title"), pygame.Rect(panel.x + 24, panel.y + 28, panel.w - 48, 42), TEXT, self.big, center=True)
        self._draw_text_fit(self.tr("single.setup.caption"), pygame.Rect(panel.x + 28, panel.y + 76, panel.w - 56, 24), MUTED, self.small, center=True)
        mouse = self._mouse_pos()
        rows = [
            (self.tr("single.setup.map"), self.single_map_key.upper()),
            (self.tr("single.setup.difficulty"), self.tr(f"difficulty.{self.difficulty_key}")),
            (self.tr("single.setup.bots"), self.tr("state.on") if self.single_bots_enabled else self.tr("state.off")),
            (self.tr("single.setup.bot_density"), self.tr(f"density.{self.bot_density}")),
        ]
        for index, (left, right) in enumerate(rows):
            rect = pygame.Rect(panel.x + 56, panel.y + 130 + index * 70, panel.w - 112, 50)
            hovered = rect.collidepoint(mouse)
            locked = index in {1, 3} and not self.single_bots_enabled
            pulse = (math.sin(time.time() * 6.0 + index) + 1.0) * 0.5
            bg_color = (24, 30, 46) if locked else PANEL_2 if hovered else PANEL
            border_color = (92, 124, 172) if not locked else (82, 86, 102)
            pygame.draw.rect(self.screen, bg_color, rect, border_radius=10)
            pygame.draw.rect(self.screen, border_color, rect, 2, border_radius=10)
            if hovered and not locked:
                glow = pygame.Surface(rect.inflate(12, 12).size, pygame.SRCALPHA)
                pygame.draw.rect(glow, (96, 206, 255, int(20 + pulse * 52)), glow.get_rect(), 1, border_radius=12)
                self.screen.blit(glow, rect.inflate(12, 12))
            self._draw_text_fit(left, pygame.Rect(rect.x + 16, rect.y + 14, rect.w - 180, 22), TEXT, self.font)
            value_color = CYAN
            if index == 1:
                value_color = GREEN if self.difficulty_key == "easy" else YELLOW if self.difficulty_key == "medium" else RED if self.difficulty_key == "hard" else PURPLE
            elif index == 3:
                value_color = GREEN if self.bot_density == "low" else YELLOW if self.bot_density == "normal" else RED
            if locked:
                value_color = MUTED
            self._draw_text_fit(right, pygame.Rect(rect.right - 170, rect.y + 14, 154, 22), value_color, self.hud_title_font, center=True)
            if index == 0:
                caret = "v" if self.single_map_dropdown_open else ">"
                self._draw_text_fit(caret, pygame.Rect(rect.right - 32, rect.y + 16, 16, 18), CYAN, self.font, center=True)
        self._draw_single_map_dropdown(panel)
        back_rect = pygame.Rect(panel.x + 56, panel.bottom - 72, 230, 46)
        start_rect = pygame.Rect(panel.right - 286, panel.bottom - 72, 230, 46)
        self._draw_button(back_rect, self.tr("settings.back"), back_rect.collidepoint(mouse))
        self._draw_button(start_rect, self.tr("single.setup.start"), start_rect.collidepoint(mouse))

    def _draw_single_map_dropdown(self, panel: pygame.Rect) -> None:
        if self.single_map_dropdown_alpha <= 0.01:
            return
        row = pygame.Rect(panel.x + 56, panel.y + 130, panel.w - 112, 50)
        popup = pygame.Rect(row.x, row.bottom + 6, row.w, 120)
        surface = pygame.Surface(popup.size, pygame.SRCALPHA)
        alpha = int(220 * self.single_map_dropdown_alpha)
        pygame.draw.rect(surface, (14, 20, 32, alpha), surface.get_rect(), border_radius=10)
        pygame.draw.rect(surface, (98, 176, 255, int(180 * self.single_map_dropdown_alpha)), surface.get_rect(), 2, border_radius=10)
        self.screen.blit(surface, popup)
        options = list(MAP_OPTIONS)
        for index, option in enumerate(options):
            item = pygame.Rect(popup.x + 10, popup.y + 10 + index * 36, popup.w - 30, 30)
            hovered = item.collidepoint(self._mouse_pos())
            pygame.draw.rect(self.screen, PANEL_2 if hovered else BG, item, border_radius=7)
            pygame.draw.rect(self.screen, CYAN if option == self.single_map_key else (64, 84, 116), item, 1, border_radius=7)
            self._draw_text_fit(option.upper(), item.inflate(-10, -6), CYAN if option == self.single_map_key else TEXT, self.font)
        track = pygame.Rect(popup.right - 14, popup.y + 10, 6, popup.h - 20)
        pygame.draw.rect(self.screen, (18, 25, 40), track, border_radius=4)
        pygame.draw.rect(self.screen, (88, 160, 224), track, 1, border_radius=4)
        knob = pygame.Rect(track.x + 1, track.y + 1, track.w - 2, max(18, track.h - 2))
        pygame.draw.rect(self.screen, CYAN, knob, border_radius=4)

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
            self._draw_text_fit(entry.name, pygame.Rect(rect.x + 18, rect.y + 8, 160, 26), TEXT, self.mid)
            mode_label = self.tr("servers.mode.pvp") if entry.pvp else self.tr("servers.mode.survival")
            mode_color = RED if entry.pvp else GREEN
            mode_rect = pygame.Rect(rect.x + 186, rect.y + 16, 62, 24)
            pygame.draw.rect(self.screen, (12, 18, 30), mode_rect, border_radius=7)
            pygame.draw.rect(self.screen, mode_color, mode_rect, 1, border_radius=7)
            self._draw_text_fit(mode_label, mode_rect.inflate(-8, -4), mode_color, self.small, center=True)
            endpoint = f"{entry.host}:{entry.port}"
            ping = "offline" if entry.ping_ms is None else f"{entry.ping_ms:.0f} ms"
            difficulty = self.tr(f"difficulty.{entry.difficulty}") if entry.difficulty in self.difficulty_options else entry.difficulty
            self._draw_text(endpoint, rect.x + 260, rect.y + 18, MUTED)
            players = f"{entry.players}/{entry.max_players}" if entry.max_players else str(entry.players)
            readiness = self.tr("servers.ready") if entry.ready else self.tr("servers.not_ready") if entry.ping_ms is not None else self.tr("servers.offline")
            status = f"{ping}  {players}  {readiness}" if entry.pvp else f"{ping}  {players}  {readiness}  {difficulty}"
            self._draw_text_fit(status, pygame.Rect(rect.x + 485, rect.y + 18, 210, 22), GREEN if entry.ready else YELLOW if entry.ping_ms else RED, self.small)
        back_rect = pygame.Rect(72, 632, 180, 46)
        refresh_rect = pygame.Rect(270, 632, 180, 46)
        connect_rect = pygame.Rect(470, 632, 180, 46)
        mouse = self._mouse_pos()
        self._draw_button(back_rect, self.tr("servers.back"), back_rect.collidepoint(mouse))
        self._draw_button(refresh_rect, self.tr("servers.refresh"), refresh_rect.collidepoint(mouse))
        self._draw_button(connect_rect, self.tr("servers.connect"), connect_rect.collidepoint(mouse))

    def _draw_game(self) -> None:
        snapshot = self._snapshot()
        player = self._local_player(snapshot)
        camera = self._camera(player)
        self.screen.fill(BG)
        self._draw_world_background(camera)
        if snapshot:
            self._update_explosion_effects(snapshot, player)
            self._update_death_effects(snapshot)
            self._update_weapon_audio_from_snapshot(snapshot)
            self._draw_tunnels(snapshot, camera, player)
            self._draw_buildings(snapshot, camera, player)
            if player and self.settings["noise_radius"]:
                self._draw_noise_radius(player, camera)
            self._draw_loot(snapshot, camera)
            self._draw_projectiles(snapshot, camera)
            self._draw_grenades(snapshot, camera)
            self._draw_mines(snapshot, camera)
            self._draw_poison(snapshot, camera)
            self._draw_death_blood_effects(camera, player)
            self._draw_zombies(snapshot, camera)
            self._draw_players(snapshot, camera)
            self._draw_death_body_effects(camera, player)
            self._draw_weapon_utilities(snapshot, camera, player)
            self._draw_explosion_effects(camera, player)
            if player:
                self._draw_tunnel_darkness(player, camera)
            if player:
                self._draw_damage_feedback(player)
            self._draw_hud(snapshot, player)
            if self.state == "online_game":
                self._draw_join_notifications()
            self._draw_minimap(snapshot, player)
            if self.state == "online_game":
                self._draw_connection_status()
                self._draw_network_notice()
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
                self._draw_settings_hub(in_game=True)

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
        segments = tunnel_segments(snapshot.buildings)
        for index, tunnel in enumerate(segments):
            rect = self._world_rect_to_screen(tunnel, camera)
            if not rect.colliderect(pygame.Rect(-120, -120, SCREEN_W + 240, SCREEN_H + 240)):
                continue
            pulse = 0.5 + 0.5 * math.sin(snapshot.time * 2.6 + index * 0.33)
            pygame.draw.rect(self.screen, (8, 12, 18), rect, border_radius=10)
            pygame.draw.rect(self.screen, (34, 49, 66), rect, 2, border_radius=10)
            center_line = rect.inflate(-max(8, rect.w // 7), -max(8, rect.h // 7))
            if center_line.w > 6 and center_line.h > 6:
                glow = pygame.Surface(center_line.size, pygame.SRCALPHA)
                pygame.draw.rect(glow, (34, 52, 78, int(42 + pulse * 24)), glow.get_rect(), border_radius=7)
                pygame.draw.rect(glow, (66, 106, 146, int(28 + pulse * 36)), glow.get_rect(), 1, border_radius=7)
                self.screen.blit(glow, center_line)
            node = self._world_to_screen(tunnel.center, camera)
            pygame.draw.circle(self.screen, (98, 136, 176), node, 2)

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
                label_rect = pygame.Rect(bx + 14, by + 10, max(120, rect.w - 28), 24)
                label_bg = pygame.Surface(label_rect.size, pygame.SRCALPHA)
                pygame.draw.rect(label_bg, (8, 14, 24, 128), label_bg.get_rect(), border_radius=8)
                pygame.draw.rect(label_bg, (78, 114, 150, 84), label_bg.get_rect(), 1, border_radius=8)
                self.screen.blit(label_bg, label_rect)
                self._draw_text_fit(floor_label, label_rect.inflate(-10, -4), CYAN, self.label_font)
            for wall in building.walls:
                self._draw_rect_world(wall, camera, (77, 91, 117))
            for prop in building.props:
                if prop.floor != (player.floor if player_inside and player else 0):
                    continue
                if not player_inside and prop.kind not in {"shelf", "crate", "barrel", "pallet", "roadblock"}:
                    continue
                if prop.kind == "glass_wall":
                    prop_rect = self._world_rect_to_screen(prop.rect, camera)
                    glass = pygame.Surface(prop_rect.size, pygame.SRCALPHA)
                    pygame.draw.rect(glass, (136, 220, 255, 76), glass.get_rect(), border_radius=3)
                    pygame.draw.rect(glass, (196, 246, 255, 122), glass.get_rect(), 2, border_radius=3)
                    self.screen.blit(glass, prop_rect)
                else:
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
        pulse = 0.5 + 0.5 * math.sin(time.time() * (8.2 if player.sprinting else 6.1))
        surface = pygame.Surface((radius * 2 + 24, radius * 2 + 24), pygame.SRCALPHA)
        center = (radius + 12, radius + 12)
        base = (82, 232, 255) if player.sneaking else (255, 198, 102)
        for layer in range(4, 0, -1):
            layer_radius = int(radius * (0.48 + layer * 0.16 + pulse * 0.04))
            alpha = max(10, int((42 if player.sneaking else 50) - layer * 8 + pulse * 18))
            pygame.draw.circle(surface, (*base, alpha), center, max(8, layer_radius), 2)
        pygame.draw.circle(surface, (*base, 24), center, radius)
        pygame.draw.circle(surface, (255, 255, 255, 56), center, radius, 1)
        self.screen.blit(surface, (sx - center[0], sy - center[1]))

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
            glow = pygame.Surface((84, 84), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*warning, int(44 + progress * 56)), (42, 42), 20 + int(progress * 14))
            self.screen.blit(glow, (sx - 42, sy - 42))
            pygame.draw.circle(self.screen, (10, 16, 12), (sx, sy), pulse + 6)
            pygame.draw.circle(self.screen, warning, (sx, sy), pulse + 1)
            pygame.draw.circle(self.screen, (255, 255, 255), (sx, sy), max(3, pulse - 4), 1)
            if spec.contact:
                pygame.draw.circle(self.screen, CYAN, (sx, sy), pulse + 4, 1)
            blast_px = self._world_size(spec.blast_radius, 1)
            phase = snapshot.time * 5.2 + progress * 3.4
            ring_alpha = int(36 + progress * 64)
            ring = pygame.Surface((blast_px * 2 + 20, blast_px * 2 + 20), pygame.SRCALPHA)
            center = (blast_px + 10, blast_px + 10)
            pygame.draw.circle(ring, (255, 214, 122, ring_alpha), center, blast_px, 1)
            pygame.draw.circle(ring, (255, 145, 96, max(10, ring_alpha - 24)), center, int(blast_px * (0.55 + 0.35 * progress)), 1)
            self.screen.blit(ring, (sx - center[0], sy - center[1]))
            shard_count = 10 if grenade.kind == "heavy_grenade" else 7 if grenade.kind == "grenade" else 5
            for index in range(shard_count):
                angle = phase + math.tau * index / shard_count
                inner = blast_px * (0.42 + 0.08 * math.sin(phase + index * 0.7))
                outer = blast_px * (0.92 + 0.09 * math.cos(phase * 1.2 + index))
                x1 = int(sx + math.cos(angle) * inner)
                y1 = int(sy + math.sin(angle) * inner)
                x2 = int(sx + math.cos(angle) * outer)
                y2 = int(sy + math.sin(angle) * outer)
                shard_color = (255, 196, 124) if grenade.kind != "heavy_grenade" else (255, 154, 108)
                pygame.draw.line(self.screen, shard_color, (x1, y1), (x2, y2), 2 if grenade.kind == "heavy_grenade" else 1)

    def _draw_mines(self, snapshot: WorldSnapshot, camera: Vec2) -> None:
        player = self._local_player(snapshot)
        for mine in snapshot.mines.values():
            if player and mine.floor != player.floor:
                continue
            sx, sy = self._world_to_screen(mine.pos, camera)
            if not (-180 <= sx <= SCREEN_W + 180 and -180 <= sy <= SCREEN_H + 180):
                continue
            tier = self._mine_tier(mine.kind)
            tier_name = self._mine_tier_label(tier)
            base_color = self._mine_tier_color(tier, mine.armed)
            blink = 0.5 + 0.5 * math.sin(snapshot.time * 7.2 + mine.rotation)
            alpha = int((72 if mine.armed else 42) + blink * (70 if mine.armed else 18))
            self._draw_dashed_circle((sx, sy), self._world_size(mine.trigger_radius, 8), base_color, mine.rotation, alpha)
            glow = pygame.Surface((74, 74), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*base_color, 54 if mine.armed else 26), (37, 37), 34)
            self.screen.blit(glow, (sx - 37, sy - 37))
            radius = self._world_size(17 + tier * 2, 10)
            points = [
                (int(sx + math.cos(mine.rotation - math.pi / 2) * radius), int(sy + math.sin(mine.rotation - math.pi / 2) * radius)),
                (int(sx + math.cos(mine.rotation + math.pi * 0.16) * radius), int(sy + math.sin(mine.rotation + math.pi * 0.16) * radius)),
                (int(sx + math.cos(mine.rotation + math.pi * 0.84) * radius), int(sy + math.sin(mine.rotation + math.pi * 0.84) * radius)),
            ]
            pygame.draw.polygon(self.screen, (8, 11, 16), [(x + 2, y + 2) for x, y in points])
            pygame.draw.polygon(self.screen, base_color if mine.armed else MUTED, points)
            pygame.draw.polygon(self.screen, TEXT, points, 1)
            if mine.armed and blink > 0.55:
                pygame.draw.circle(self.screen, RED, (sx, sy), 5)
            if not self._draw_item_icon(mine.kind, pygame.Rect(sx - 12, sy - 12, 24, 24)):
                pygame.draw.circle(self.screen, BG, (sx, sy), 4)
            level_rect = pygame.Rect(sx - 14, sy + self._world_size(24, 16), 28, 14)
            pygame.draw.rect(self.screen, (8, 12, 20), level_rect, border_radius=4)
            pygame.draw.rect(self.screen, base_color, level_rect, 1, border_radius=4)
            self._draw_text_fit(tier_name, level_rect.inflate(-2, -2), base_color, self.small, center=True)

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
            if not player.alive:
                if not self._has_death_effect("player", player.id):
                    self._draw_dead_player_cross((sx, sy), 1.0, 210)
                continue
            color = CYAN if player.id == (self.local_player_id or self.online.player_id) else GREEN
            body_radius = self._world_size(24, 12)
            pygame.draw.circle(self.screen, (4, 8, 14), (sx, sy), self._world_size(31, body_radius + 4))
            pygame.draw.circle(self.screen, color, (sx, sy), body_radius)
            pygame.draw.circle(self.screen, TEXT, (sx, sy), body_radius, 2)
            muzzle_len = self._world_size(42, 22)
            muzzle = (int(sx + math.cos(player.angle) * muzzle_len), int(sy + math.sin(player.angle) * muzzle_len))
            pygame.draw.line(self.screen, TEXT, (sx, sy), muzzle, self._world_size(5, 2))
            self._draw_text(player.name, sx - 28, sy - 48, TEXT, self.small)

    def _draw_death_blood_effects(self, camera: Vec2, local: PlayerState | None) -> None:
        now = time.time()
        for effect in self._death_effects:
            if local and int(effect.get("floor", 0)) != local.floor:
                continue
            started = float(effect.get("started", now))
            age = now - started
            if age < 0.0 or age > float(self.death_effects.blood_seconds):
                continue
            pos = effect.get("pos")
            if not isinstance(pos, Vec2):
                continue
            sx, sy = self._world_to_screen(pos, camera)
            self._draw_blood_pool((sx, sy), effect, age)

    def _draw_death_body_effects(self, camera: Vec2, local: PlayerState | None) -> None:
        now = time.time()
        for effect in self._death_effects:
            if local and int(effect.get("floor", 0)) != local.floor:
                continue
            started = float(effect.get("started", now))
            age = now - started
            alpha_ratio = self._corpse_alpha_ratio(age)
            if alpha_ratio <= 0.0:
                continue
            pos = effect.get("pos")
            if not isinstance(pos, Vec2):
                continue
            sx, sy = self._world_to_screen(pos, camera)
            if str(effect.get("entity_type", "")) == "player":
                self._draw_dead_player_cross((sx, sy), alpha_ratio, int(225 * alpha_ratio))
            else:
                self._draw_dead_zombie_body((sx, sy), effect, alpha_ratio)

    def _draw_blood_pool(self, center: tuple[int, int], effect: dict[str, object], age: float) -> None:
        tuning = self.death_effects
        spread = min(1.0, age / max(0.01, float(tuning.blood_spread_seconds)))
        spread = spread * spread * (3.0 - 2.0 * spread)
        fade_start = max(0.01, float(tuning.blood_seconds) - float(tuning.blood_fade_seconds))
        fade = 1.0 if age <= fade_start else max(0.0, (float(tuning.blood_seconds) - age) / max(0.01, float(tuning.blood_fade_seconds)))
        alpha = int(float(tuning.blood_alpha) * fade)
        if alpha <= 0:
            return
        radius_world = float(tuning.blood_start_radius) + (float(tuning.blood_end_radius) - float(tuning.blood_start_radius)) * spread
        radius = self._world_size(radius_world, 8)
        size = radius * 2 + 34
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        cx = cy = size // 2
        seed = int(effect.get("seed", 1))
        base_rect = pygame.Rect(cx - radius, cy - int(radius * 0.62), radius * 2, max(2, int(radius * 1.24)))
        pygame.draw.ellipse(surface, (68, 3, 12, int(alpha * 0.64)), base_rect)
        pygame.draw.ellipse(surface, (132, 12, 22, int(alpha * 0.68)), base_rect.inflate(-int(radius * 0.3), -int(radius * 0.2)))
        for index in range(7):
            wave = 0.5 + 0.5 * math.sin(seed * 0.037 + index * 2.17)
            angle = seed * 0.011 + index * 0.93
            distance = radius * (0.14 + 0.22 * wave) * spread
            lobe_radius = max(3, int(radius * (0.16 + 0.14 * (1.0 - wave))))
            lx = int(cx + math.cos(angle) * distance)
            ly = int(cy + math.sin(angle) * distance * 0.72)
            lobe = pygame.Rect(lx - lobe_radius, ly - int(lobe_radius * 0.65), lobe_radius * 2, max(2, int(lobe_radius * 1.3)))
            pygame.draw.ellipse(surface, (114, 4, 18, int(alpha * (0.42 + 0.3 * wave))), lobe)
        pygame.draw.ellipse(surface, (218, 32, 38, int(alpha * 0.18)), base_rect.inflate(-int(radius * 0.75), -int(radius * 0.72)))
        self.screen.blit(surface, (center[0] - cx, center[1] - cy))

    def _draw_dead_zombie_body(self, center: tuple[int, int], effect: dict[str, object], alpha_ratio: float) -> None:
        kind = str(effect.get("kind", "walker"))
        spec = ZOMBIES.get(kind, ZOMBIES["walker"])
        radius = self._world_size(spec.radius, 8)
        size = radius * 3 + 28
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        cx = cy = size // 2
        alpha = int(255 * alpha_ratio)
        dark_alpha = int(float(self.death_effects.corpse_dark_alpha) * alpha_ratio)
        outline_alpha = int(float(self.death_effects.corpse_outline_alpha) * alpha_ratio)
        pygame.draw.ellipse(
            surface,
            (0, 0, 0, int(86 * alpha_ratio)),
            pygame.Rect(cx - radius - 8, cy - int(radius * 0.62), radius * 2 + 16, int(radius * 1.24)),
        )
        pygame.draw.circle(surface, (*spec.color, int(96 * alpha_ratio)), (cx, cy), radius)
        pygame.draw.circle(surface, (2, 4, 8, dark_alpha), (cx, cy), radius)
        pygame.draw.circle(surface, (0, 0, 0, outline_alpha), (cx, cy), radius, max(1, self._world_size(3, 1)))
        facing = float(effect.get("facing", 0.0))
        nose = (int(cx + math.cos(facing) * radius * 0.78), int(cy + math.sin(facing) * radius * 0.78))
        pygame.draw.line(surface, (18, 0, 4, alpha), (cx, cy), nose, max(2, self._world_size(5, 2)))
        self.screen.blit(surface, (center[0] - cx, center[1] - cy))

    def _draw_dead_player_cross(self, center: tuple[int, int], alpha_ratio: float, alpha: int) -> None:
        size = self._world_size(float(self.death_effects.player_cross_size), 18)
        width = self._world_size(float(self.death_effects.player_cross_width), 3)
        surface_size = size * 2 + 18
        surface = pygame.Surface((surface_size, surface_size), pygame.SRCALPHA)
        cx = cy = surface_size // 2
        shadow_alpha = int(90 * alpha_ratio)
        pygame.draw.circle(surface, (80, 0, 8, shadow_alpha), (cx, cy), max(10, int(size * 0.62)))
        pygame.draw.line(surface, (10, 10, 14, alpha), (cx - size, cy - size), (cx + size, cy + size), width)
        pygame.draw.line(surface, (10, 10, 14, alpha), (cx - size, cy + size), (cx + size, cy - size), width)
        pygame.draw.line(surface, (0, 0, 0, min(255, alpha + 24)), (cx - size, cy - size), (cx + size, cy + size), max(1, width // 2))
        pygame.draw.line(surface, (0, 0, 0, min(255, alpha + 24)), (cx - size, cy + size), (cx + size, cy - size), max(1, width // 2))
        self.screen.blit(surface, (center[0] - cx, center[1] - cy))

    def _corpse_alpha_ratio(self, age: float) -> float:
        lifetime = float(self.death_effects.corpse_seconds)
        if age < 0.0 or age > lifetime:
            return 0.0
        fade_seconds = max(0.01, float(self.death_effects.corpse_fade_seconds))
        fade_start = max(0.0, lifetime - fade_seconds)
        if age <= fade_start:
            return 1.0
        return max(0.0, (lifetime - age) / fade_seconds)

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
        cone = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        flicker = 0.95 + 0.05 * math.sin(time.time() * 33.0 + player.pos.x * 0.0017)
        layers = 13 if soft else 6
        for index in range(layers, 0, -1):
            ratio = index / layers
            distance = int(cone_range * ratio * flicker)
            spread = half_angle * (0.68 + 0.32 * ratio)
            alpha = int((56 if soft else 124) * (1.0 - ratio * 0.58) * flicker)
            points = [
                (sx, sy),
                (int(sx + math.cos(player.angle - spread) * distance), int(sy + math.sin(player.angle - spread) * distance)),
                (int(sx + math.cos(player.angle + spread) * distance), int(sy + math.sin(player.angle + spread) * distance)),
            ]
            pygame.draw.polygon(cone, (255, 236, 164, max(8, alpha)), points)
        hot_radius = self._world_size(108, 22)
        pygame.draw.circle(cone, (255, 248, 196, 62), (sx, sy), hot_radius)
        pygame.draw.circle(cone, (255, 255, 236, 36), (sx, sy), max(12, int(hot_radius * 0.46)))
        self.screen.blit(cone, (0, 0))

    def _draw_tunnel_darkness(self, player: PlayerState, camera: Vec2) -> None:
        if player.floor >= 0:
            return
        has_flashlight = self._has_active_flashlight(player)
        darkness = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        darkness.fill((0, 0, 0, 228 if not has_flashlight else 198))
        if has_flashlight:
            module = WEAPON_MODULES.get("flashlight_module")
            cone_range = self._world_size(module.cone_range if module else 620, 1)
            half_angle = math.radians((module.cone_degrees if module else 58) * 0.5)
            sx, sy = self._world_to_screen(player.pos, camera)
            light = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            flicker = 0.94 + 0.06 * math.sin(time.time() * 32.0 + player.pos.y * 0.0021)
            layers = 14
            for index in range(layers, 0, -1):
                ratio = index / layers
                distance = int(cone_range * ratio * flicker)
                spread = half_angle * (0.66 + 0.34 * ratio)
                alpha = int(170 * (1.0 - ratio * 0.68) * flicker)
                points = [
                    (sx, sy),
                    (int(sx + math.cos(player.angle - spread) * distance), int(sy + math.sin(player.angle - spread) * distance)),
                    (int(sx + math.cos(player.angle + spread) * distance), int(sy + math.sin(player.angle + spread) * distance)),
                ]
                pygame.draw.polygon(light, (0, 0, 0, max(8, alpha)), points)
            pygame.draw.circle(light, (0, 0, 0, 126), (sx, sy), self._world_size(142, 24))
            darkness.blit(light, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
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
        panel = pygame.Rect(18, 18, 348, 132)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=8)
        glow = pygame.Surface((panel.w + 8, panel.h + 8), pygame.SRCALPHA)
        pygame.draw.rect(glow, (66, 118, 182, 28), glow.get_rect(), border_radius=10)
        self.screen.blit(glow, (panel.x - 4, panel.y - 4))
        panel_pulse = 0.5 + 0.5 * math.sin(snapshot.time * 3.1)
        pygame.draw.rect(self.screen, (80, 140, 210), panel, 1, border_radius=8)
        pulse_glow = pygame.Surface((panel.w + 14, panel.h + 14), pygame.SRCALPHA)
        pygame.draw.rect(
            pulse_glow,
            (110, 184, 255, int(58 + panel_pulse * 34)),
            pulse_glow.get_rect(),
            1,
            border_radius=12,
        )
        self.screen.blit(pulse_glow, (panel.x - 7, panel.y - 7))
        self._draw_text(player.name, 74, 30, TEXT, self.hud_title_font)
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
        regen_active = player.healing_left > 0.0 and player.healing_pool > 0.0
        if regen_active:
            self._regen_target_health = min(100.0, player.health + player.healing_pool)
        elif self._regen_target_health is not None and player.health >= self._regen_target_health - 0.15:
            self._regen_target_health = max(player.health, self._regen_target_health)
        health_color = (255, int(72 + pulse * 72), int(82 + pulse * 28)) if critical else RED
        if self._regen_target_health is not None and player.health >= self._regen_target_health - 0.15:
            health_color = (132, 22, 34)
        if critical:
            pygame.draw.rect(self.screen, (122, 0, 18), pygame.Rect(58, 66, 278, 24), 2, border_radius=7)
        if self._regen_target_health is not None and self._regen_target_health > player.health + 0.1:
            start_x = 62 + int(270 * max(0.0, min(1.0, player.health / 100.0)))
            target_w = int(270 * max(0.0, min(1.0, (self._regen_target_health - player.health) / 100.0)))
            if target_w > 0:
                regen_rect = pygame.Rect(start_x, 70, target_w, 16)
                pygame.draw.rect(self.screen, (74, 16, 28), regen_rect, border_radius=4)
                pygame.draw.rect(self.screen, (108, 28, 40), regen_rect, 1, border_radius=4)
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
        noise_w = min(270, int(player.noise / 900 * 270))
        pygame.draw.rect(self.screen, (33, 40, 58), pygame.Rect(62, 134, 270, 5), border_radius=2)
        pygame.draw.rect(self.screen, YELLOW if player.sprinting else GREEN, pygame.Rect(62, 134, noise_w, 5), border_radius=2)
        noise_sheen = pygame.Rect(62, 134, max(0, min(270, noise_w // 3)), 5)
        if noise_sheen.w > 0:
            pygame.draw.rect(self.screen, (245, 248, 255), noise_sheen, 1, border_radius=2)
        self._draw_status_effects_bar(player)

        start_x = 380
        y = SCREEN_H - 72
        for index, slot in enumerate(SLOTS):
            rect = pygame.Rect(start_x + index * 82, y, 72, 50)
            active = slot == player.active_slot
            pygame.draw.rect(self.screen, PANEL_2 if active else PANEL, rect, border_radius=8)
            pygame.draw.rect(self.screen, CYAN if active else (47, 61, 91), rect, 2, border_radius=8)
            if active:
                glow = pygame.Surface((rect.w + 10, rect.h + 10), pygame.SRCALPHA)
                alpha = int(52 + (0.5 + 0.5 * math.sin(snapshot.time * 7.0 + index)) * 66)
                pygame.draw.rect(glow, (86, 226, 255, alpha), glow.get_rect(), 2, border_radius=10)
                self.screen.blit(glow, (rect.x - 5, rect.y - 5))
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
        self._draw_weapon_widget(player)

    def _draw_status_effects_bar(self, player: PlayerState) -> None:
        effects: list[tuple[str, str, tuple[int, int, int], float]] = []
        if player.poison_left > 0.0:
            effects.append(("poisoned", self.tr("hud.poisoned"), (95, 220, 122), player.poison_left))
        if not effects:
            return
        width = max(180, len(effects) * 76 + 24)
        panel = pygame.Rect((SCREEN_W - width) // 2, 16, width, 64)
        pygame.draw.rect(self.screen, (12, 18, 30), panel, border_radius=10)
        pygame.draw.rect(self.screen, (72, 98, 138), panel, 2, border_radius=10)
        pulse = (math.sin(time.time() * 6.2) + 1.0) * 0.5
        for index, (icon_key, title, color, left_seconds) in enumerate(effects):
            icon_cell = pygame.Rect(panel.x + 14 + index * 76, panel.y + 10, 56, 44)
            pygame.draw.rect(self.screen, PANEL, icon_cell, border_radius=9)
            pygame.draw.rect(self.screen, color, icon_cell, 2, border_radius=9)
            glow = pygame.Surface(icon_cell.inflate(10, 10).size, pygame.SRCALPHA)
            pygame.draw.rect(glow, (*color, int(24 + pulse * 58)), glow.get_rect(), 1, border_radius=11)
            self.screen.blit(glow, icon_cell.inflate(10, 10))
            self._draw_item_icon(icon_key, icon_cell.inflate(-11, -8), aura=False, shadow=False)
            self._draw_text_fit(f"{left_seconds:.1f}s", pygame.Rect(icon_cell.x, icon_cell.bottom - 14, icon_cell.w, 12), color, self.small, center=True)
            label_rect = pygame.Rect(icon_cell.right + 8, icon_cell.y + 6, panel.right - icon_cell.right - 16, 30)
            self._draw_text_fit(title, label_rect, color, self.small)
        self._draw_notice(player)

    def _draw_weapon_widget(self, player: PlayerState) -> None:
        weapon = player.active_weapon()
        quick_item = player.quick_items.get(player.active_slot)
        rect = pygame.Rect(22, SCREEN_H - 168, 300, 86)
        rarity = weapon.rarity if weapon else quick_item.rarity if quick_item else "common"
        accent = rarity_color(rarity) if weapon or quick_item else MUTED
        pulse = (math.sin(time.time() * 5.6) + 1.0) * 0.5
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(surface, (10, 16, 28, 224), surface.get_rect(), border_radius=11)
        pygame.draw.rect(surface, (*accent, int(130 + pulse * 60)), surface.get_rect(), 2, border_radius=11)
        self.screen.blit(surface, rect)
        icon_rect = pygame.Rect(rect.x + 16, rect.y + 14, 58, 58)
        pygame.draw.rect(self.screen, (8, 12, 22), icon_rect, border_radius=9)
        if weapon:
            self._draw_rarity_frame(icon_rect, weapon.rarity)
            self._draw_item_icon(weapon.key, icon_rect.inflate(-9, -12), aura=False)
            title = self.weapon_title(weapon.key)
            ammo = f"{weapon.ammo_in_mag}/{weapon.reserve_ammo}"
            subtitle = self.rarity_title(weapon.rarity)
            self._mini_durability(pygame.Rect(rect.x + 88, rect.y + 60, 182, 18), weapon.durability)
            if weapon.reload_left > 0:
                gear_rect = pygame.Rect(rect.right - 44, rect.y + 18, 28, 28)
                self._draw_item_icon("gear", gear_rect, aura=False, shadow=False)
                angle = time.time() * 7.0
                p1 = (int(gear_rect.centerx + math.cos(angle) * 16), int(gear_rect.centery + math.sin(angle) * 16))
                pygame.draw.line(self.screen, YELLOW, gear_rect.center, p1, 2)
                self._draw_text_fit(f"{weapon.reload_left:.1f}s", pygame.Rect(rect.right - 58, rect.y + 50, 44, 18), YELLOW, self.small, center=True)
        elif quick_item:
            self._draw_item_icon(quick_item.key, icon_rect.inflate(-10, -10), aura=False)
            title = self.item_title(quick_item.key)
            ammo = f"x{quick_item.amount}"
            subtitle = self.rarity_title(quick_item.rarity)
        else:
            title = self.tr("hud.unarmed")
            ammo = "--"
            subtitle = self._floor_label(player.floor)
            pygame.draw.circle(self.screen, MUTED, icon_rect.center, 14, 2)
        self._draw_text_fit(title, pygame.Rect(rect.x + 88, rect.y + 14, 160, 22), TEXT, self.hud_title_font)
        self._draw_text_fit(subtitle, pygame.Rect(rect.x + 88, rect.y + 38, 120, 18), accent, self.small)
        self._draw_text_fit(ammo, pygame.Rect(rect.right - 86, rect.y + 52, 64, 24), YELLOW if weapon or quick_item else MUTED, self.hud_value_font, center=True)

    def _draw_join_notifications(self) -> None:
        now = time.time()
        active: list[dict[str, object]] = []
        for notification in self._join_notifications:
            started = float(notification.get("started", now))
            duration = float(notification.get("duration", 4.2))
            age = now - started
            if age < duration:
                active.append(notification)
        self._join_notifications = active
        for index, notification in enumerate(reversed(active[-3:])):
            started = float(notification.get("started", now))
            duration = float(notification.get("duration", 4.2))
            age = max(0.0, now - started)
            appear = min(1.0, age / 0.38)
            fade = min(1.0, max(0.0, (duration - age) / 0.95))
            alpha = int(225 * min(appear, fade))
            if alpha <= 0:
                continue
            pulse = math.sin(age * 8.0) * 0.035
            scale = 0.92 + 0.13 * appear + pulse * fade
            rect = pygame.Rect(22, SCREEN_H - 234 - index * 58, 300, 48)
            slide = int((1.0 - appear) * -34)
            rect.x += slide
            surface = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(surface, (9, 14, 26, int(172 * min(appear, fade))), surface.get_rect(), border_radius=11)
            pygame.draw.rect(surface, (76, 225, 255, int(112 * min(appear, fade))), surface.get_rect(), 1, border_radius=11)
            self.screen.blit(surface, rect)
            icon_size = max(24, int(34 * scale))
            icon = self._scaled_icon("joined", (icon_size, icon_size))
            icon_center = (rect.x + 31, rect.centery)
            if icon:
                icon = icon.copy()
                icon.set_alpha(alpha)
                glow = pygame.Surface((54, 54), pygame.SRCALPHA)
                pygame.draw.circle(glow, (76, 225, 255, int(42 * min(appear, fade))), (27, 27), int(18 * scale))
                self.screen.blit(glow, (icon_center[0] - 27, icon_center[1] - 27))
                self.screen.blit(icon, icon.get_rect(center=icon_center))
            else:
                pygame.draw.circle(self.screen, (76, 225, 255), icon_center, int(12 * scale))
            name = str(notification.get("name", "Player"))
            label = self.tr("online.player_joined", name=name)
            text_rect = pygame.Rect(rect.x + 58, rect.y + 11, rect.w - 70, 24)
            text_font = self.emphasis_font
            for candidate in (self.emphasis_font, self.hud_value_font, self.small):
                if candidate.size(label)[0] <= text_rect.w:
                    text_font = candidate
                    break
            display_label = label
            if text_font.size(display_label)[0] > text_rect.w:
                while len(display_label) > 4 and text_font.size(display_label.rstrip() + "...")[0] > text_rect.w:
                    display_label = display_label[:-1]
                display_label = display_label.rstrip() + "..."
            text = text_font.render(display_label, True, TEXT)
            text.set_alpha(alpha)
            self.screen.blit(text, text.get_rect(midleft=(text_rect.x, rect.centery)))

    def _mine_tier(self, mine_kind: str) -> int:
        if "heavy" in mine_kind:
            return 3
        if "light" in mine_kind:
            return 1
        return 2

    def _mine_tier_label(self, tier: int) -> str:
        return "I" if tier <= 1 else "II" if tier == 2 else "III"

    def _mine_tier_color(self, tier: int, armed: bool) -> tuple[int, int, int]:
        if tier <= 1:
            return (86, 208, 172) if armed else (88, 136, 124)
        if tier == 2:
            return (145, 116, 228) if armed else (122, 112, 160)
        return (255, 128, 98) if armed else (164, 118, 108)

    def _update_explosion_effects(self, snapshot: WorldSnapshot, player: PlayerState | None) -> None:
        now = time.time()
        current_grenades: dict[str, tuple[Vec2, int, str]] = {
            grenade.id: (grenade.pos.copy(), grenade.floor, grenade.kind) for grenade in snapshot.grenades.values()
        }
        current_mines: dict[str, tuple[Vec2, int, str]] = {
            mine.id: (mine.pos.copy(), mine.floor, mine.kind) for mine in snapshot.mines.values()
        }
        for grenade_id, (pos, floor, kind) in self._prev_grenade_state.items():
            if grenade_id in current_grenades:
                continue
            spec = GRENADE_SPECS.get(kind, DEFAULT_GRENADE)
            self._explosion_effects.append(
                {"pos": pos, "floor": floor, "radius": spec.blast_radius, "color": (255, 168, 118), "start": now, "duration": 0.34},
            )
        for mine_id, (pos, floor, kind) in self._prev_mine_state.items():
            if mine_id in current_mines:
                continue
            spec = MINE_SPECS.get(kind, DEFAULT_MINE)
            self._explosion_effects.append(
                {"pos": pos, "floor": floor, "radius": spec.blast_radius, "color": (212, 140, 255), "start": now, "duration": 0.36},
            )
        self._prev_grenade_state = current_grenades
        self._prev_mine_state = current_mines
        self._explosion_effects = [
            fx for fx in self._explosion_effects if now - float(fx["start"]) <= float(fx["duration"]) + 0.04
        ]

    def _draw_explosion_effects(self, camera: Vec2, player: PlayerState | None) -> None:
        now = time.time()
        for fx in self._explosion_effects:
            if player and int(fx["floor"]) != player.floor:
                continue
            pos = fx["pos"]
            sx, sy = self._world_to_screen(pos, camera)
            radius = self._world_size(float(fx["radius"]), 1)
            age = max(0.0, min(1.0, (now - float(fx["start"])) / max(0.01, float(fx["duration"]))))
            spike = 1.0 - age
            color = fx["color"]
            flash_radius = int(radius * (0.18 + age * 0.86))
            blast = pygame.Surface((flash_radius * 2 + 48, flash_radius * 2 + 48), pygame.SRCALPHA)
            center = (blast.get_width() // 2, blast.get_height() // 2)
            pygame.draw.circle(blast, (*color, int(84 * spike)), center, max(12, flash_radius))
            pygame.draw.circle(blast, (255, 238, 210, int(120 * spike)), center, max(8, int(flash_radius * 0.55)))
            pygame.draw.circle(blast, (*color, int(66 * spike)), center, max(10, int(flash_radius * 1.16)), 2)
            self.screen.blit(blast, (sx - center[0], sy - center[1]))

            ring = pygame.Surface((radius * 2 + 20, radius * 2 + 20), pygame.SRCALPHA)
            rc = (radius + 10, radius + 10)
            ring_r = int(radius * (0.38 + age * 0.8))
            pygame.draw.circle(ring, (*color, int(58 * spike)), rc, max(12, ring_r), 2)
            pygame.draw.circle(ring, (255, 222, 178, int(48 * spike)), rc, max(8, int(ring_r * 0.72)), 1)
            self.screen.blit(ring, (sx - rc[0], sy - rc[1]))

    def _minimap_rect(self) -> pygame.Rect:
        size = 248 if self.minimap_big else 176
        return pygame.Rect(SCREEN_W - size - 18, 18, size, int(size * MAP_HEIGHT / MAP_WIDTH))

    def _draw_minimap(self, snapshot: WorldSnapshot, player: PlayerState | None) -> None:
        rect = self._minimap_rect()
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=8)
        pygame.draw.rect(self.screen, CYAN, rect, 2, border_radius=8)
        bounds = self._minimap_world_bounds(rect, snapshot, player)
        min_x, min_y, max_x, max_y = bounds
        span_x = max(1.0, max_x - min_x)
        span_y = max(1.0, max_y - min_y)

        def mp(pos: Vec2) -> tuple[int, int]:
            return int(rect.x + (pos.x - min_x) / span_x * rect.w), int(rect.y + (pos.y - min_y) / span_y * rect.h)

        def inside(pos: Vec2) -> bool:
            return min_x <= pos.x <= max_x and min_y <= pos.y <= max_y

        for item in snapshot.loot.values():
            if player and item.floor != player.floor:
                continue
            if not inside(item.pos):
                continue
            pygame.draw.circle(self.screen, YELLOW, mp(item.pos), 2)
        for mine in snapshot.mines.values():
            if player and mine.floor != player.floor:
                continue
            if not inside(mine.pos):
                continue
            self._draw_minimap_triangle(mp(mine.pos), MINE_MAP_COLOR if mine.armed else (136, 102, 170), mine.rotation, 5)
        for zombie in snapshot.zombies.values():
            if player and zombie.floor != player.floor:
                continue
            if not inside(zombie.pos):
                continue
            pygame.draw.circle(self.screen, RED, mp(zombie.pos), 3)
        for other in snapshot.players.values():
            if player and other.floor != player.floor:
                continue
            color = CYAN if player and other.id == player.id else GREEN
            if inside(other.pos):
                pygame.draw.circle(self.screen, color, mp(other.pos), 4)
            elif self.state == "online_game" and player and other.id != player.id:
                edge, angle = self._minimap_edge_marker(rect, other.pos, bounds)
                self._draw_minimap_triangle(edge, color, angle, 6)
        for building in snapshot.buildings.values():
            if not self._rect_intersects_bounds(building.bounds, bounds):
                continue
            mini = pygame.Rect(
                int(rect.x + (building.bounds.x - min_x) / span_x * rect.w),
                int(rect.y + (building.bounds.y - min_y) / span_y * rect.h),
                max(2, int(building.bounds.w / span_x * rect.w)),
                max(2, int(building.bounds.h / span_y * rect.h)),
            )
            mini.clamp_ip(rect)
            pygame.draw.rect(self.screen, (84, 95, 118), mini, 1)
        if player:
            floor_badge = pygame.Rect(rect.x + 8, rect.bottom - 22, 44, 16)
            pygame.draw.rect(self.screen, (10, 16, 28), floor_badge, border_radius=5)
            pygame.draw.rect(self.screen, CYAN, floor_badge, 1, border_radius=5)
            self._draw_text_fit(self._floor_label(player.floor), floor_badge.inflate(-4, -2), TEXT, self.small, center=True)

    def _minimap_world_bounds(self, rect: pygame.Rect, snapshot: WorldSnapshot, player: PlayerState | None) -> tuple[float, float, float, float]:
        map_w = float(snapshot.map_width or MAP_WIDTH)
        map_h = float(snapshot.map_height or MAP_HEIGHT)
        if self.state != "online_game" or not player:
            return (0.0, 0.0, map_w, map_h)
        radius_x = max(ONLINE_MINIMAP_MIN_RADIUS, min(ONLINE_MINIMAP_MAX_RADIUS, self.online.server_building_interest_radius))
        radius_y = radius_x * rect.h / max(1, rect.w)
        min_x = max(0.0, player.pos.x - radius_x)
        max_x = min(map_w, player.pos.x + radius_x)
        min_y = max(0.0, player.pos.y - radius_y)
        max_y = min(map_h, player.pos.y + radius_y)
        if max_x - min_x < radius_x:
            if min_x <= 0.0:
                max_x = min(map_w, min_x + radius_x * 2.0)
            elif max_x >= map_w:
                min_x = max(0.0, max_x - radius_x * 2.0)
        if max_y - min_y < radius_y:
            if min_y <= 0.0:
                max_y = min(map_h, min_y + radius_y * 2.0)
            elif max_y >= map_h:
                min_y = max(0.0, max_y - radius_y * 2.0)
        return (min_x, min_y, max_x, max_y)

    def _rect_intersects_bounds(self, rect: RectState, bounds: tuple[float, float, float, float]) -> bool:
        min_x, min_y, max_x, max_y = bounds
        return rect.x <= max_x and rect.x + rect.w >= min_x and rect.y <= max_y and rect.y + rect.h >= min_y

    def _minimap_edge_marker(
        self,
        rect: pygame.Rect,
        pos: Vec2,
        bounds: tuple[float, float, float, float],
    ) -> tuple[tuple[int, int], float]:
        min_x, min_y, max_x, max_y = bounds
        span_x = max(1.0, max_x - min_x)
        span_y = max(1.0, max_y - min_y)
        px = rect.x + (pos.x - min_x) / span_x * rect.w
        py = rect.y + (pos.y - min_y) / span_y * rect.h
        clamped_x = max(rect.x + 8, min(rect.right - 8, int(px)))
        clamped_y = max(rect.y + 8, min(rect.bottom - 8, int(py)))
        angle = math.atan2(py - rect.centery, px - rect.centerx)
        return (clamped_x, clamped_y), angle

    def _draw_minimap_triangle(
        self,
        center: tuple[int, int],
        color: tuple[int, int, int],
        angle: float,
        radius: int,
    ) -> None:
        points = [
            (int(center[0] + math.cos(angle) * radius), int(center[1] + math.sin(angle) * radius)),
            (int(center[0] + math.cos(angle + math.tau * 0.38) * radius), int(center[1] + math.sin(angle + math.tau * 0.38) * radius)),
            (int(center[0] + math.cos(angle - math.tau * 0.38) * radius), int(center[1] + math.sin(angle - math.tau * 0.38) * radius)),
        ]
        pygame.draw.polygon(self.screen, (6, 9, 16), [(x + 1, y + 1) for x, y in points])
        pygame.draw.polygon(self.screen, color, points)

    def _draw_connection_status(self) -> None:
        quality = self.online.connection_quality()
        if quality == "stable-connection":
            return
        minimap = self._minimap_rect()
        rect = pygame.Rect(minimap.x - 54, minimap.y + 8, 38, 38)
        color = {
            "stable-connection": GREEN,
            "unstable-connection": YELLOW,
            "packet-lost": RED,
            "lost-connection": RED,
        }.get(quality, MUTED)
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(surface, (10, 16, 28, 206), surface.get_rect(), border_radius=8)
        pygame.draw.rect(surface, (*color, 170), surface.get_rect(), 1, border_radius=8)
        self.screen.blit(surface, rect)
        icon_rect = pygame.Rect(rect.x + 7, rect.y + 7, 24, 24)
        if not self._draw_item_icon(quality, icon_rect, aura=False, shadow=False):
            pygame.draw.circle(self.screen, color, icon_rect.center, 8)

    def _draw_network_notice(self) -> None:
        quality = self.online.connection_quality()
        if quality == "stable-connection" and not self.online.error:
            return
        color = {
            "unstable-connection": YELLOW,
            "packet-lost": RED,
            "lost-connection": RED,
        }.get(quality, CYAN)
        key = {
            "unstable-connection": "online.notice.unstable",
            "packet-lost": "online.notice.packet_loss",
            "lost-connection": "online.notice.lost",
        }.get(quality, "online.notice.reconnecting")
        text = self.online.error if self.online.error and quality == "lost-connection" else self.tr(key)
        rect = pygame.Rect(0, 0, 420, 38)
        rect.center = (SCREEN_W // 2, 34)
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(surface, (9, 14, 26, 220), surface.get_rect(), border_radius=10)
        pygame.draw.rect(surface, (*color, 180), surface.get_rect(), 1, border_radius=10)
        self.screen.blit(surface, rect)
        icon_rect = pygame.Rect(rect.x + 14, rect.y + 7, 24, 24)
        if not self._draw_item_icon(quality, icon_rect, aura=False, shadow=False):
            pygame.draw.circle(self.screen, color, icon_rect.center, 8)
        self._draw_text_fit(text, pygame.Rect(rect.x + 46, rect.y + 9, rect.w - 62, 18), TEXT, self.small, center=True)

    def _format_ping(self, ping_ms: float | int | None) -> str:
        if ping_ms is None or float(ping_ms) <= 0.0:
            return "--"
        if float(ping_ms) >= 1000.0:
            return "999+"
        return f"{float(ping_ms):.0f} ms"

    def _draw_zombie_counter(self, snapshot: WorldSnapshot) -> None:
        minimap = self._minimap_rect()
        rect = pygame.Rect(minimap.x, minimap.bottom + 12, minimap.w, 42)
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
                if door.floor != player.floor:
                    continue
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
        panel = pygame.Rect((SCREEN_W - 980) // 2, 96, 980, 520)
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
            self.tr("scoreboard.floor"),
            self.tr("scoreboard.total"),
            self.tr("scoreboard.walker"),
            self.tr("scoreboard.runner"),
            self.tr("scoreboard.brute"),
            self.tr("scoreboard.leaper"),
            self.tr("scoreboard.ping"),
            self.tr("scoreboard.status"),
        ]
        xs = [panel.x + 42, panel.x + 286, panel.x + 350, panel.x + 426, panel.x + 506, panel.x + 586, panel.x + 666, panel.x + 746, panel.x + 832]
        for x, header in zip(xs, headers):
            self._draw_text(header, x, panel.y + 112, CYAN if header == self.tr("scoreboard.total") else MUTED, self.small)
        viewport = pygame.Rect(panel.x + 22, panel.y + 146, panel.w - 44, panel.h - 176)
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(viewport)
        y = panel.y + 150 - self.scoreboard_scroll
        for player in sorted(snapshot.players.values(), key=lambda p: p.score, reverse=True):
            row = pygame.Rect(panel.x + 30, y - 8, panel.w - 60, 42)
            if not row.colliderect(viewport.inflate(0, 24)):
                y += 52
                continue
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
                self._floor_label(player.floor),
                str(player.score),
                str(player.kills_by_kind.get("walker", 0)),
                str(player.kills_by_kind.get("runner", 0)),
                str(player.kills_by_kind.get("brute", 0)),
                str(player.kills_by_kind.get("leaper", 0)),
                self._format_ping(player.ping_ms),
                self.tr("state.alive") if player.alive else self.tr("state.dead"),
            ]
            self._draw_text_fit(
                f"{player.name}{'' if player.alive else ' - ' + self.tr('state.dead')}",
                pygame.Rect(name_x, y, xs[1] - name_x - 12, 22),
                TEXT if player.alive else RED,
                self.emphasis_font if player.id == (self.local_player_id or self.online.player_id) else self.font,
            )
            for index, (x, value) in enumerate(zip(xs[1:], values), start=1):
                if index == len(values):
                    quality = _connection_icon_from_state(player.connection_quality)
                    icon_rect = pygame.Rect(x, y - 3, 22, 22)
                    if not self._draw_item_icon(quality, icon_rect, aura=False, shadow=False):
                        pygame.draw.circle(self.screen, RED if not player.alive else GREEN, icon_rect.center, 7)
                    color = RED if value == self.tr("state.dead") else TEXT
                    self._draw_text_fit(value, pygame.Rect(x + 28, y, panel.right - x - 48, 20), color, self.small)
                    continue
                if index == 1:
                    badge = pygame.Rect(x, y - 2, 46, 24)
                    pygame.draw.rect(self.screen, (11, 18, 30), badge, border_radius=7)
                    pygame.draw.rect(self.screen, PURPLE if player.floor < 0 else CYAN, badge, 1, border_radius=7)
                    self._draw_text_fit(value, badge.inflate(-6, -3), TEXT, self.small, center=True)
                    continue
                color = YELLOW if index == 2 else TEXT
                if index == len(values) - 1 and value == "999+":
                    color = RED
                self._draw_text_fit(value, pygame.Rect(x, y, 66, 22), color, self.font)
            y += 52
        self.screen.set_clip(previous_clip)
        self._draw_scoreboard_scrollbar(snapshot, viewport)

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
        pulse = (math.sin(time.time() * 4.0) + 1.0) * 0.5
        highlight = pygame.Surface(panel.inflate(18, 18).size, pygame.SRCALPHA)
        pygame.draw.rect(highlight, (98, 184, 255, int(18 + pulse * 36)), highlight.get_rect(), 1, border_radius=12)
        self.screen.blit(highlight, panel.inflate(18, 18))
        self._draw_text(self.tr("backpack.title"), panel.x + 34, panel.y + 24, TEXT, self.big)
        self._draw_text(self.tr("backpack.body"), panel.x + 54, panel.y + 116, PURPLE, self.mid)
        self._draw_text_fit(self.tr("backpack.help"), pygame.Rect(panel.x + 352, panel.y + 42, panel.w - 390, 40), MUTED, self.small)

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
        self._draw_text_fit(
            title,
            pygame.Rect(rect.x + 4, rect.y + rect.h - 20, rect.w - 8, 16),
            color if rarity_highlight else TEXT,
            self.small,
            center=True,
        )
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
        close_rect = self._weapon_custom_close_rect()
        self._draw_button(close_rect, self.tr("weaponmods.close"), close_rect.collidepoint(self._mouse_pos()))

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
        info = pygame.Rect(panel.x + 34, panel.y + 164, 312, 210)
        pygame.draw.rect(self.screen, (12, 17, 29), info, border_radius=10)
        pygame.draw.rect(self.screen, rarity_color(weapon.rarity), info, 2, border_radius=10)
        weapon_rect = pygame.Rect(info.x + 16, info.y + 34, 94, 88)
        self._draw_rarity_frame(weapon_rect, weapon.rarity)
        self._draw_rarity_badge(weapon_rect, weapon.rarity, compact=True)
        self._draw_item_icon(weapon.key, weapon_rect.inflate(-14, -18))
        self._draw_text_fit(
            f"{self.rarity_title(weapon.rarity)} {self.weapon_title(weapon.key)}",
            pygame.Rect(info.x + 120, info.y + 34, 178, 34),
            rarity_color(weapon.rarity),
            self.font,
        )
        self._draw_text_fit(f"{self.tr('weaponmods.magazine')}: {mag_size}", pygame.Rect(info.x + 120, info.y + 78, 178, 18), MUTED, self.small)
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
        viewport = self._weapon_module_viewport_rect()
        self.weapon_modules_scroll = max(0, min(self._weapon_modules_max_scroll(), self.weapon_modules_scroll))
        pygame.draw.rect(self.screen, (9, 13, 23), viewport.inflate(10, 10), border_radius=10)
        pygame.draw.rect(self.screen, (42, 57, 82), viewport.inflate(10, 10), 1, border_radius=10)
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(viewport)
        for module_key, indices in self._available_module_groups(player):
            rect = self._available_module_rect(module_key)
            if not rect.colliderect(viewport.inflate(20, 20)):
                continue
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
        self.screen.set_clip(previous_clip)
        self._draw_weapon_modules_scrollbar()

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
        pulse = (math.sin(time.time() * 3.0) + 1.0) * 0.5
        glow = pygame.Surface(panel.inflate(20, 20).size, pygame.SRCALPHA)
        pygame.draw.rect(glow, (76, 225, 255, int(20 + pulse * 40)), glow.get_rect(), 1, border_radius=12)
        self.screen.blit(glow, panel.inflate(20, 20))
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

        viewport = pygame.Rect(option_x, start_y, option_width, panel.h - 250)
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(viewport)
        for index, key in enumerate(self.settings):
            rect = pygame.Rect(option_x, start_y + index * step_y - self.pause_settings_scroll, option_width, option_height)
            pygame.draw.rect(self.screen, PANEL_2, rect, border_radius=8)
            pygame.draw.rect(self.screen, GREEN if self.settings[key] else MUTED, rect, 2, border_radius=8)
            marker = self.tr("state.on") if self.settings[key] else self.tr("state.off")
            self._draw_text_fit(labels[key], pygame.Rect(rect.x + 16, rect.y + 12, rect.w - 100, 20), TEXT, self.font)
            self._draw_text(marker, rect.right - 70, rect.y + 12, GREEN if self.settings[key] else RED, self.font)

        camera_rect = pygame.Rect(option_x, start_y + len(self.settings) * step_y - self.pause_settings_scroll, option_width, option_height)
        pygame.draw.rect(self.screen, PANEL_2, camera_rect, border_radius=8)
        pygame.draw.rect(self.screen, (134, 196, 255), camera_rect, 2, border_radius=8)
        self._draw_text_fit(
            self.tr("settings.camera_distance"),
            pygame.Rect(camera_rect.x + 16, camera_rect.y + 12, camera_rect.w - 170, 20),
            TEXT,
            self.font,
        )
        camera_mode = (
            "settings.camera_distance.near"
            if self.camera_distance >= 0.97
            else "settings.camera_distance.far"
            if self.camera_distance <= 0.86
            else "settings.camera_distance.normal"
        )
        self._draw_text_fit(self.tr(camera_mode), pygame.Rect(camera_rect.right - 146, camera_rect.y + 12, 130, 20), CYAN, self.font)

        language_rect = pygame.Rect(option_x, start_y + (len(self.settings) + 1) * step_y - self.pause_settings_scroll, option_width, option_height)
        pygame.draw.rect(self.screen, PANEL_2, language_rect, border_radius=8)
        pygame.draw.rect(self.screen, CYAN, language_rect, 2, border_radius=8)
        self._draw_text_fit(self.tr("settings.language"), pygame.Rect(language_rect.x + 16, language_rect.y + 12, language_rect.w - 90, 20), TEXT, self.font)
        self._draw_text(self.language.upper(), language_rect.right - 70, language_rect.y + 12, CYAN, self.font)
        self.screen.set_clip(previous_clip)
        self._draw_pause_settings_scrollbar(viewport)
        if panel_only:
            back_rect = self._settings_back_rect()
            self._draw_button(back_rect, self.tr("settings.back"), back_rect.collidepoint(self._mouse_pos()))
        else:
            resume_rect = self._settings_resume_rect()
            menu_rect = self._settings_main_menu_rect()
            mouse = self._mouse_pos()
            self._draw_button(resume_rect, self.tr("settings.resume"), resume_rect.collidepoint(mouse))
            self._draw_button(menu_rect, self.tr("settings.main_menu"), menu_rect.collidepoint(mouse))

    def _settings_footer_buttons(self, in_game: bool) -> None:
        mouse = self._mouse_pos()
        if in_game:
            resume_rect = self._settings_resume_rect()
            menu_rect = self._settings_main_menu_rect()
            self._draw_button(resume_rect, self.tr("settings.resume"), resume_rect.collidepoint(mouse))
            self._draw_button(menu_rect, self.tr("settings.main_menu"), menu_rect.collidepoint(mouse))
        else:
            back_rect = self._settings_back_rect()
            self._draw_button(back_rect, self.tr("settings.back"), back_rect.collidepoint(mouse))

    def _settings_audio_active(self) -> bool:
        return self.settings_tab == "audio" and (self.state == "options" or (self.settings_open and self.state in {"single", "online_game"}))

    def _audio_slider_layout(self, viewport: pygame.Rect) -> list[tuple[str, pygame.Rect, pygame.Rect]]:
        option_x = viewport.x + 6
        option_w = viewport.w - 24
        row_h = 122
        rows: list[tuple[str, pygame.Rect, pygame.Rect]] = []
        for index, key in enumerate(("master", "music", "effects")):
            card = pygame.Rect(option_x, viewport.y + index * row_h - self.options_scroll, option_w, 98)
            track = pygame.Rect(card.x + 24, card.y + 68, card.w - 150, 10)
            rows.append((key, card, track))
        return rows

    def _begin_audio_slider_drag(self, pos: tuple[int, int]) -> bool:
        panel = self._settings_panel_rect()
        viewport = pygame.Rect(panel.x + 36, panel.y + 162, panel.w - 72, panel.h - 238)
        if not viewport.collidepoint(pos):
            return False
        for key, card, track in self._audio_slider_layout(viewport):
            if card.collidepoint(pos) or track.inflate(16, 28).collidepoint(pos):
                self._dragging_audio_slider = key
                self._update_audio_slider_from_pos(key, pos, save=False)
                return True
        return False

    def _update_audio_slider_from_pos(self, key: str, pos: tuple[int, int], *, save: bool) -> None:
        panel = self._settings_panel_rect()
        viewport = pygame.Rect(panel.x + 36, panel.y + 162, panel.w - 72, panel.h - 238)
        track = next((track for row_key, _card, track in self._audio_slider_layout(viewport) if row_key == key), None)
        if not track:
            return
        value = (pos[0] - track.x) / max(1, track.w)
        self._set_audio_volume(key, value, save=save)

    def _set_audio_volume(self, key: str, value: float, *, save: bool) -> None:
        volume = max(0.0, min(1.0, float(value)))
        if key == "master":
            self.master_volume = volume
            self.audio.set_master_volume(volume)
        elif key == "music":
            self.music_volume = volume
            self.audio.set_music_volume(volume)
        elif key == "effects":
            self.effects_volume = volume
            self.audio.set_effects_volume(volume)
        if save:
            self._save_client_settings()

    def _draw_audio_settings(self, viewport: pygame.Rect) -> None:
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(viewport)
        for index, (key, card, track) in enumerate(self._audio_slider_layout(viewport)):
            value = self.master_volume if key == "master" else self.music_volume if key == "music" else self.effects_volume
            title_key = f"settings.audio.{key}"
            desc_key = f"settings.audio.{key}.desc"
            color = CYAN if key == "master" else PURPLE if key == "music" else YELLOW
            self._draw_audio_slider_card(key, card, track, self.tr(title_key), self.tr(desc_key), value, color, index)
        self.screen.set_clip(previous_clip)

    def _draw_audio_slider_card(
        self,
        key: str,
        card: pygame.Rect,
        track: pygame.Rect,
        title: str,
        description: str,
        value: float,
        color: tuple[int, int, int],
        index: int,
    ) -> None:
        mouse = self._mouse_pos()
        hovered = card.collidepoint(mouse) or track.inflate(18, 30).collidepoint(mouse)
        pulse = (math.sin(time.time() * 5.5 + index * 1.7) + 1.0) * 0.5
        pygame.draw.rect(self.screen, PANEL_2 if hovered else PANEL, card, border_radius=12)
        pygame.draw.rect(self.screen, color if hovered else (66, 82, 118), card, 2, border_radius=12)
        if hovered or self._dragging_audio_slider == key:
            glow = pygame.Surface(card.inflate(14, 14).size, pygame.SRCALPHA)
            pygame.draw.rect(glow, (*color, int(20 + pulse * 44)), glow.get_rect(), 1, border_radius=14)
            self.screen.blit(glow, card.inflate(14, 14))
        self._draw_text_fit(title, pygame.Rect(card.x + 20, card.y + 12, card.w - 150, 22), TEXT, self.hud_title_font)
        percent = f"{int(round(value * 100)):>3}%"
        self._draw_text_fit(percent, pygame.Rect(card.right - 104, card.y + 12, 82, 24), color, self.hud_value_font, center=True)
        self._draw_text_fit(description, pygame.Rect(card.x + 20, card.y + 38, card.w - 42, 20), MUTED, self.small)

        pygame.draw.rect(self.screen, (8, 12, 22), track.inflate(0, 8), border_radius=8)
        pygame.draw.rect(self.screen, (48, 62, 92), track, border_radius=5)
        fill_w = int(track.w * value)
        if fill_w > 0:
            fill = pygame.Rect(track.x, track.y, fill_w, track.h)
            for offset in range(fill.w):
                ratio = offset / max(1, fill.w - 1)
                segment_color = (
                    int(72 + (color[0] - 72) * ratio),
                    int(110 + (color[1] - 110) * ratio),
                    int(142 + (color[2] - 142) * ratio),
                )
                pygame.draw.line(self.screen, segment_color, (fill.x + offset, fill.y), (fill.x + offset, fill.bottom - 1))
            pygame.draw.rect(self.screen, color, fill, 1, border_radius=5)
        knob_x = track.x + fill_w
        knob_radius = 11 + (2 if hovered else 0)
        pygame.draw.circle(self.screen, (6, 10, 18), (knob_x, track.centery), knob_radius + 4)
        pygame.draw.circle(self.screen, color, (knob_x, track.centery), knob_radius)
        pygame.draw.circle(self.screen, (236, 248, 255), (knob_x - 3, track.centery - 3), max(2, knob_radius // 3))

        meter_x = card.right - 92
        for bar in range(6):
            bar_h = int(7 + value * (10 + bar * 3) + math.sin(time.time() * 4.0 + bar + index) * 2)
            bar_rect = pygame.Rect(meter_x + bar * 9, track.y - 8 - bar_h, 5, max(3, bar_h))
            alpha_color = color if bar / 6 <= value + 0.08 else (58, 72, 104)
            pygame.draw.rect(self.screen, alpha_color, bar_rect, border_radius=2)

    def _draw_settings_hub(self, in_game: bool = False) -> None:
        if in_game:
            overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            overlay.fill((1, 3, 8, 166))
            self.screen.blit(overlay, (0, 0))
        panel = self._settings_panel_rect()
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=12)
        pygame.draw.rect(self.screen, CYAN, panel, 2, border_radius=12)
        self._draw_text_fit(self.tr("settings.title"), pygame.Rect(panel.x + 32, panel.y + 26, panel.w - 64, 44), TEXT, self.big, center=True)
        tab_y = panel.y + 106
        for index, tab in enumerate(self.settings_tabs):
            rect = pygame.Rect(panel.x + 32 + index * 112, tab_y, 102, 36)
            active = tab == self.settings_tab
            pulse = (math.sin(time.time() * 5.0 + index) + 1.0) * 0.5
            pygame.draw.rect(self.screen, PANEL_2 if active else (16, 22, 34), rect, border_radius=9)
            pygame.draw.rect(self.screen, CYAN if active else (68, 86, 120), rect, 2, border_radius=9)
            if active:
                glow = pygame.Surface(rect.inflate(10, 10).size, pygame.SRCALPHA)
                pygame.draw.rect(glow, (86, 226, 255, int(28 + pulse * 44)), glow.get_rect(), 1, border_radius=11)
                self.screen.blit(glow, rect.inflate(10, 10))
            locale_key = next((tab_item.locale_key for tab_item in SETTINGS_TABS if tab_item.key == tab), f"settings.tab.{tab}")
            self._draw_text_fit(self.tr(locale_key), rect.inflate(-8, -8), TEXT if active else MUTED, self.small, center=True)
        if tab_is_stub(self.settings_tab):
            stub = pygame.Rect(panel.x + 40, panel.y + 168, panel.w - 80, panel.h - 250)
            pygame.draw.rect(self.screen, (12, 18, 30), stub, border_radius=10)
            pygame.draw.rect(self.screen, PURPLE, stub, 2, border_radius=10)
            self._draw_text_fit(self.tr("settings.audio.stub"), stub.inflate(-20, -30), CYAN, self.big, center=True)
            self._settings_footer_buttons(in_game)
            return
        viewport = pygame.Rect(panel.x + 36, panel.y + 162, panel.w - 72, panel.h - 238)
        pygame.draw.rect(self.screen, (10, 16, 28), viewport.inflate(8, 8), border_radius=10)
        pygame.draw.rect(self.screen, (56, 74, 108), viewport.inflate(8, 8), 1, border_radius=10)
        if tab_has_audio_sliders(self.settings_tab):
            self._draw_audio_settings(viewport)
            self._draw_options_scrollbar(viewport, 3, 122)
            self._settings_footer_buttons(in_game)
            return
        options = tab_toggle_keys(self.settings_tab)
        labels = {
            "bot_vision": self.tr("settings.bot_vision"),
            "bot_vision_range": self.tr("settings.bot_vision_range"),
            "ai_reactions": self.tr("settings.ai_reactions"),
            "health_bars": self.tr("settings.health_bars"),
            "noise_radius": self.tr("settings.noise_radius"),
            "show_zombie_count": self.tr("settings.show_zombie_count"),
            "fullscreen": self.tr("settings.fullscreen"),
        }
        step_y = 56
        option_h = 44
        option_x = viewport.x + 6
        option_w = viewport.w - 24
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(viewport)
        for index, key in enumerate(options):
            y = viewport.y + index * step_y - self.options_scroll
            rect = pygame.Rect(option_x, y, option_w, option_h)
            hovered = rect.collidepoint(self._mouse_pos())
            marker = self.tr("state.on") if self.settings[key] else self.tr("state.off")
            pygame.draw.rect(self.screen, PANEL_2 if hovered else PANEL, rect, border_radius=9)
            pygame.draw.rect(self.screen, GREEN if self.settings[key] else MUTED, rect, 2, border_radius=9)
            if hovered:
                glow = pygame.Surface(rect.inflate(12, 12).size, pygame.SRCALPHA)
                pulse = (math.sin(time.time() * 8.0 + index) + 1.0) * 0.5
                pygame.draw.rect(glow, (100, 196, 255, int(18 + pulse * 50)), glow.get_rect(), 1, border_radius=11)
                self.screen.blit(glow, rect.inflate(12, 12))
            self._draw_text_fit(labels[key], pygame.Rect(rect.x + 14, rect.y + 12, rect.w - 120, 20), TEXT, self.font)
            self._draw_text_fit(marker, pygame.Rect(rect.right - 88, rect.y + 10, 76, 22), GREEN if self.settings[key] else RED, self.emphasis_font, center=True)
        row_index = len(options)
        if tab_has_camera_distance(self.settings_tab):
            camera_rect = pygame.Rect(option_x, viewport.y + row_index * step_y - self.options_scroll, option_w, option_h)
            pygame.draw.rect(self.screen, PANEL_2, camera_rect, border_radius=9)
            pygame.draw.rect(self.screen, CYAN, camera_rect, 2, border_radius=9)
            camera_mode = "settings.camera_distance.near" if self.camera_distance >= 0.97 else "settings.camera_distance.far" if self.camera_distance <= 0.86 else "settings.camera_distance.normal"
            self._draw_text_fit(self.tr("settings.camera_distance"), pygame.Rect(camera_rect.x + 14, camera_rect.y + 12, camera_rect.w - 180, 20), TEXT, self.font)
            self._draw_text_fit(self.tr(camera_mode), pygame.Rect(camera_rect.right - 154, camera_rect.y + 12, 140, 20), CYAN, self.hud_title_font, center=True)
            row_index += 1
        if tab_has_language(self.settings_tab):
            language_rect = pygame.Rect(option_x, viewport.y + row_index * step_y - self.options_scroll, option_w, option_h)
            pygame.draw.rect(self.screen, PANEL_2, language_rect, border_radius=9)
            pygame.draw.rect(self.screen, PURPLE, language_rect, 2, border_radius=9)
            self._draw_text_fit(self.tr("settings.language"), pygame.Rect(language_rect.x + 14, language_rect.y + 12, language_rect.w - 180, 20), TEXT, self.font)
            self._draw_text_fit(self.language.upper(), pygame.Rect(language_rect.right - 154, language_rect.y + 12, 140, 20), PURPLE, self.hud_title_font, center=True)
        self.screen.set_clip(previous_clip)
        self._draw_options_scrollbar(viewport, row_index + (1 if tab_has_language(self.settings_tab) else 0), step_y)
        self._settings_footer_buttons(in_game)

    def _draw_options_scrollbar(self, viewport: pygame.Rect, rows: int, step_y: int) -> None:
        content_h = rows * step_y
        max_scroll = max(0, content_h - viewport.h)
        if max_scroll <= 0:
            self.options_scroll = 0
            return
        track = pygame.Rect(viewport.right + 10, viewport.y, 10, viewport.h)
        pygame.draw.rect(self.screen, (10, 16, 28), track, border_radius=5)
        pygame.draw.rect(self.screen, (58, 76, 108), track, 1, border_radius=5)
        knob_h = max(42, int(track.h * track.h / max(track.h, content_h)))
        knob_y = track.y + int((track.h - knob_h) * (self.options_scroll / max_scroll))
        knob = pygame.Rect(track.x + 2, knob_y, track.w - 4, knob_h)
        pygame.draw.rect(self.screen, CYAN, knob, border_radius=4)
        pygame.draw.rect(self.screen, (214, 246, 255), knob, 1, border_radius=4)

    def _scroll_options(self, direction: int) -> None:
        if tab_is_stub(self.settings_tab):
            self.options_scroll = 0
            return
        viewport_h = self._settings_panel_rect().h - 238
        row_count = 3 if tab_has_audio_sliders(self.settings_tab) else len(tab_toggle_keys(self.settings_tab))
        if tab_has_camera_distance(self.settings_tab):
            row_count += 1
        if tab_has_language(self.settings_tab):
            row_count += 1
        content_h = row_count * 56
        max_scroll = max(0, content_h - viewport_h)
        self.options_scroll = max(0, min(max_scroll, self.options_scroll + direction * 34))

    def _scroll_pause_settings(self, direction: int) -> None:
        viewport_h = self._settings_panel_rect().h - 238
        content_h = (len(tab_toggle_keys("video")) + 2) * 56
        max_scroll = max(0, content_h - viewport_h)
        self.pause_settings_scroll = max(0, min(max_scroll, self.pause_settings_scroll + direction * 34))

    def _draw_pause_settings_scrollbar(self, viewport: pygame.Rect) -> None:
        content_h = (len(tab_toggle_keys("video")) + 2) * 56
        max_scroll = max(0, content_h - viewport.h)
        if max_scroll <= 0:
            self.pause_settings_scroll = 0
            return
        track = pygame.Rect(viewport.right + 10, viewport.y, 10, viewport.h)
        pygame.draw.rect(self.screen, (10, 16, 28), track, border_radius=5)
        pygame.draw.rect(self.screen, (58, 76, 108), track, 1, border_radius=5)
        knob_h = max(42, int(track.h * track.h / max(track.h, content_h)))
        knob_y = track.y + int((track.h - knob_h) * (self.pause_settings_scroll / max_scroll))
        knob = pygame.Rect(track.x + 2, knob_y, track.w - 4, knob_h)
        pygame.draw.rect(self.screen, CYAN, knob, border_radius=4)
        pygame.draw.rect(self.screen, (214, 246, 255), knob, 1, border_radius=4)

    def _handle_single_setup_click(self, pos: tuple[int, int]) -> None:
        panel = pygame.Rect((SCREEN_W - 660) // 2, 120, 660, 500)
        back_rect = pygame.Rect(panel.x + 56, panel.bottom - 72, 230, 46)
        start_rect = pygame.Rect(panel.right - 286, panel.bottom - 72, 230, 46)
        if back_rect.collidepoint(pos):
            self.single_map_dropdown_open = False
            self.state = "menu"
            return
        if start_rect.collidepoint(pos):
            self.single_map_dropdown_open = False
            self._start_single_player()
            return
        rows = [
            pygame.Rect(panel.x + 56, panel.y + 130, panel.w - 112, 50),
            pygame.Rect(panel.x + 56, panel.y + 200, panel.w - 112, 50),
            pygame.Rect(panel.x + 56, panel.y + 270, panel.w - 112, 50),
            pygame.Rect(panel.x + 56, panel.y + 340, panel.w - 112, 50),
        ]
        if rows[0].collidepoint(pos):
            self.single_map_dropdown_open = not self.single_map_dropdown_open
            return
        if self.single_map_dropdown_open:
            popup = pygame.Rect(rows[0].x, rows[0].bottom + 6, rows[0].w, 120)
            item = pygame.Rect(popup.x + 10, popup.y + 10, popup.w - 30, 30)
            if item.collidepoint(pos):
                self.single_map_key = MAP_OPTIONS[0]
                self._save_client_settings()
            self.single_map_dropdown_open = False
            if popup.collidepoint(pos):
                return
        else:
            self.single_map_dropdown_open = False
        if rows[1].collidepoint(pos):
            if not self.single_bots_enabled:
                return
            idx = self.difficulty_options.index(self.difficulty_key)
            self.difficulty_key = self.difficulty_options[(idx + 1) % len(self.difficulty_options)]
        elif rows[2].collidepoint(pos):
            self.single_bots_enabled = not self.single_bots_enabled
        elif rows[3].collidepoint(pos):
            if not self.single_bots_enabled:
                return
            self.bot_density = DENSITY_ORDER[(DENSITY_ORDER.index(self.bot_density) + 1) % len(DENSITY_ORDER)]
        self._save_client_settings()

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
        viewport = self._weapon_module_viewport_rect()
        order = {key: index for index, key in enumerate(WEAPON_MODULES)}
        index = order.get(module_key, 0)
        cols = 2
        gap_x = 14
        gap_y = 12
        card_w = (viewport.w - gap_x) // cols
        card_h = 96
        row = index // cols
        col = index % cols
        return pygame.Rect(
            viewport.x + col * (card_w + gap_x),
            viewport.y + row * (card_h + gap_y) - self.weapon_modules_scroll,
            card_w,
            card_h,
        )

    def _weapon_module_viewport_rect(self) -> pygame.Rect:
        panel = self._weapon_custom_panel_rect()
        return pygame.Rect(panel.x + 34, panel.y + 424, panel.w - 86, 126)

    def _weapon_modules_content_height(self) -> int:
        card_h = 96
        gap_y = 12
        rows = max(1, math.ceil(len(WEAPON_MODULES) / 2))
        return rows * card_h + max(0, rows - 1) * gap_y

    def _weapon_modules_max_scroll(self) -> int:
        return max(0, self._weapon_modules_content_height() - self._weapon_module_viewport_rect().h)

    def _scroll_weapon_modules(self, direction: int) -> None:
        self.weapon_modules_scroll = max(0, min(self._weapon_modules_max_scroll(), self.weapon_modules_scroll + direction * 40))

    def _draw_weapon_modules_scrollbar(self) -> None:
        viewport = self._weapon_module_viewport_rect()
        track = pygame.Rect(viewport.right + 8, viewport.y, 10, viewport.h)
        pygame.draw.rect(self.screen, (8, 12, 20), track, border_radius=5)
        pygame.draw.rect(self.screen, (52, 68, 98), track, 1, border_radius=5)
        max_scroll = self._weapon_modules_max_scroll()
        if max_scroll <= 0:
            pygame.draw.rect(self.screen, PURPLE, track.inflate(-2, -2), border_radius=4)
            return
        knob_h = max(38, int(track.h * track.h / max(track.h, self._weapon_modules_content_height())))
        knob_y = track.y + int((track.h - knob_h) * (self.weapon_modules_scroll / max_scroll))
        knob = pygame.Rect(track.x + 2, knob_y, track.w - 4, knob_h)
        pygame.draw.rect(self.screen, PURPLE, knob, border_radius=4)
        pygame.draw.rect(self.screen, (236, 222, 255), knob, 1, border_radius=4)

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
            viewport = self._weapon_module_viewport_rect()
            for module_key, indices in self._available_module_groups(player):
                if indices and viewport.collidepoint(pos) and self._available_module_rect(module_key).collidepoint(pos):
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
        step_y = 56
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
        if module.key == "silencer":
            return "noise 0, spread +8%"
        if module.key == "compensator":
            return "fire rate+, spread -5%, noise +12%"
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
        pulse = (math.sin(time.time() * 5.0 + rect.x * 0.01) + 1.0) * 0.5
        if hovered:
            shadow_rect = rect.move(2, 3)
            shadow_surface = pygame.Surface((shadow_rect.w, shadow_rect.h), pygame.SRCALPHA)
            pygame.draw.rect(shadow_surface, (0, 0, 0, 60), shadow_surface.get_rect(), border_radius=10)
            self.screen.blit(shadow_surface, shadow_rect)

            gradient_surface = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            for i in range(rect.h):
                alpha = 255 - (i * 40 // rect.h)
                color = (35, 45, 70, alpha)
                pygame.draw.line(gradient_surface, color, (0, i), (rect.w, i))
            self.screen.blit(gradient_surface, rect)

            pygame.draw.rect(self.screen, (40, 55, 85), rect, border_radius=10)
            pygame.draw.rect(self.screen, CYAN, rect, 3, border_radius=10)
            inner_rect = rect.inflate(-6, -6)
            pygame.draw.rect(self.screen, (76, 225, 255, 30), inner_rect, 2, border_radius=8)
        else:
            pygame.draw.rect(self.screen, PANEL, rect, border_radius=10)
            pygame.draw.rect(self.screen, (53, 68, 98), rect, 2, border_radius=10)
        pulse_glow = pygame.Surface(rect.inflate(12, 12).size, pygame.SRCALPHA)
        pygame.draw.rect(pulse_glow, (88, 204, 255, int(12 + pulse * 34)), pulse_glow.get_rect(), 1, border_radius=12)
        self.screen.blit(pulse_glow, rect.inflate(12, 12))

        # Draw text with better positioning
        text_color = TEXT if hovered else (200, 210, 230)
        font = self.mid if hovered else self.font
        self._draw_text_fit(label, rect.inflate(-24, -12), text_color, font, center=True)

    def _scoreboard_max_scroll(self, snapshot: WorldSnapshot) -> int:
        rows = len(snapshot.players)
        content_h = rows * 52
        viewport_h = 520 - 176
        return max(0, content_h - viewport_h + 12)

    def _scroll_scoreboard(self, direction: int) -> None:
        snapshot = self._snapshot()
        if not snapshot:
            return
        max_scroll = self._scoreboard_max_scroll(snapshot)
        self.scoreboard_scroll = max(0, min(max_scroll, self.scoreboard_scroll + direction * 36))

    def _draw_scoreboard_scrollbar(self, snapshot: WorldSnapshot, viewport: pygame.Rect) -> None:
        max_scroll = self._scoreboard_max_scroll(snapshot)
        if max_scroll <= 0:
            self.scoreboard_scroll = 0
            return
        track = pygame.Rect(viewport.right + 6, viewport.y, 10, viewport.h)
        pygame.draw.rect(self.screen, (10, 16, 28), track, border_radius=5)
        pygame.draw.rect(self.screen, (58, 76, 108), track, 1, border_radius=5)
        knob_h = max(42, int(track.h * track.h / max(track.h, len(snapshot.players) * 52)))
        knob_y = track.y + int((track.h - knob_h) * (self.scoreboard_scroll / max_scroll))
        knob = pygame.Rect(track.x + 2, knob_y, track.w - 4, knob_h)
        pulse = (math.sin(time.time() * 5.5) + 1.0) * 0.5
        pygame.draw.rect(self.screen, (86, 228, 255), knob, border_radius=4)
        pygame.draw.rect(self.screen, (210, 250, 255, int(110 + pulse * 100)), knob, 1, border_radius=4)

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
