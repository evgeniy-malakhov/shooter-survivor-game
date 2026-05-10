from __future__ import annotations

import json
import math
import gc
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pygame

from client.app.app_state import AppState, normalize_app_state
from client.app.navigation import AppNavigation
from client.audio import AudioManager
from client.audio_config import load_audio_tuning
from client.controllers.overlay_state import GameplayOverlayState
from client.core.assets import ClientAssets
from client.core.camera import CameraController
from client.core.display import DisplayConfig, DisplayManager
from client.core.frame_pipeline import FramePhase, FramePhaseTrace
from client.core.perf import ClientPerfStats
from client.core.surface_cache import UISurfaceCache
from client.death_effects import load_death_effect_tuning
from client.effects.effect_pool import DictEffectPool
from client.effects.visual_effects_state import VisualEffectsState
from client.game.render_frame_cache import RenderFrameCacheKey
from client.game.snapshot_render_adapter import SnapshotRenderAdapter
from client.input.action_buffer import ClientActionBuffer
from client.network import OnlineClient, ping_server
from client.perf.adaptive_performance import AdaptivePerformanceController
from client.perf.frame_budget import FrameBudgetController
from client.perf.perf_log_recorder import PerfLogRecorder
from client.perf.render_quality import QUALITY_PRESETS, quality_profile_for
from client.render.render_context import RenderContext
from client.render.render_frame import RenderFrame
from client.render.render_frame_builder import RenderFrameBuilder
from client.render.render_resources import RenderFonts, RenderText
from client.render.ui.minimap_cache import MinimapStaticCache
from client.render.ui.text_cache import TextCache
from client.render.world.actor_sprite_cache import ActorSpriteCache
from client.render.world.static_world_cache import StaticWorldChunkCache
from client.visibility.render_culling import point_visible, rect_visible
from client.scenes.gameplay_scene import GameplayScene
from client.scenes.loading_scene import LoadingScene
from client.scenes.menu_scene import MenuScene
from client.scenes.options_scene import OptionsScene
from client.scenes.scene_manager import SceneManager
from client.scenes.server_browser_scene import ServerBrowserScene
from client.scenes.single_setup_scene import SingleSetupScene
from client.settings_schema import (
    SETTINGS_TABS,
    tab_has_audio_sliders,
    tab_has_camera_distance,
    tab_has_graphics_quality,
    tab_has_language,
    tab_is_stub,
    tab_toggle_keys,
)
from client.single_setup_schema import DENSITY_ORDER, MAP_OPTIONS
from shared.constants import ARMORS, MAP_HEIGHT, MAP_WIDTH, SLOTS, WEAPONS, ZOMBIES, SOLDIERS
from shared.crafting import craft_rarity_chances
from shared.difficulty import DIFFICULTY_KEYS, load_difficulty
from shared.explosives import GRENADE_SPECS, MINE_SPECS, DEFAULT_GRENADE, DEFAULT_MINE
from shared.game_modes import get_game_mode, list_game_modes
from shared.items import EQUIPMENT_SLOTS, ITEMS, RECIPES
from shared.level import tunnel_segments
from shared.maps import list_available_maps
from shared.maps.loading import LoadingScreenState, LoadingStage
from shared.models import BuildingState, ClientCommand, InputCommand, LootState, PlayerState, RectState, Vec2, WorldSnapshot
from shared.rarities import RARITY_KEYS, rarity_color, rarity_rank, rarity_spec
from shared.simulation import GameWorld
from shared.weapon_modules import WEAPON_MODULES, WEAPON_MODULE_SLOTS


SCREEN_W = 1280
SCREEN_H = 760
MIN_WINDOW_W = 960
MIN_WINDOW_H = 570
FPS = 60
ROOT = Path(__file__).resolve().parents[2]
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
        self.display_manager = DisplayManager(
            DisplayConfig(
                virtual_size=(SCREEN_W, SCREEN_H),
                min_window_size=(MIN_WINDOW_W, MIN_WINDOW_H),
                caption="Neon Outbreak",
            )
        )
        self._sync_display_refs()
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
        self.assets = ClientAssets(
            root=ROOT,
            default_icon_mapping=DEFAULT_ICON_MAPPING,
            icon_mapping_path=ICON_MAPPING_PATH,
        )
        self.icon_mapping = self.assets.icon_mapping
        self.item_images = self.assets.item_images
        self.loading_poster = self.assets.loading.poster
        self.loading_spinner = self.assets.loading.spinner
        self._icon_cache = self.assets.icon_cache
        self.damage_flash = 0.0
        self._last_local_health: float | None = None
        self._regen_target_health: float | None = None
        self._prev_grenade_state: dict[str, tuple[Vec2, int, str]] = {}
        self._prev_mine_state: dict[str, tuple[Vec2, int, str]] = {}
        self._explosion_effects: list[dict[str, object]] = []
        self._explosion_effect_pool = DictEffectPool()
        self._join_notifications: list[dict[str, object]] = []
        self.death_effects = load_death_effect_tuning()
        self._death_effects: list[dict[str, object]] = []
        self._death_effect_pool = DictEffectPool()
        self.visual_effects = VisualEffectsState(
            damage_flash=self.damage_flash,
            explosion_effects=self._explosion_effects,
            death_effects=self._death_effects,
            join_notifications=self._join_notifications,
        )
        self._prev_zombie_death_state: dict[str, dict[str, object]] = {}
        self._prev_player_death_state: dict[str, dict[str, object]] = {}
        self._prev_projectile_audio_state: dict[str, dict[str, object]] = {}
        self._played_projectile_sounds: set[str] = set()
        self._played_grenade_throw_sounds: set[str] = set()
        self._played_explosion_sounds: set[str] = set()
        self._shot_sound_debounce: dict[str, float] = {}
        self._prev_reload_audio_state: dict[str, float] = {}
        self._last_empty_sound_at = 0.0
        self.overlay_state = GameplayOverlayState()
        self.perf_stats = ClientPerfStats()
        self.frame_phases = FramePhaseTrace()
        self.frame_budget = FrameBudgetController()
        self.perf_log_recorder = PerfLogRecorder(ROOT)
        self._gc_callback_started_at: float | None = None
        self.gc_pacing_enabled = False
        self.perf_logging_enabled = False
        self.render_frame_builder = RenderFrameBuilder()
        self.snapshot_render_adapter = SnapshotRenderAdapter()
        self._render_frame_cache_key: RenderFrameCacheKey | None = None
        self._render_frame_cache: RenderFrame | None = None
        self.text_cache = TextCache()
        self.ui_surface_cache = UISurfaceCache()
        self.static_world_cache = StaticWorldChunkCache()
        self.actor_sprite_cache = ActorSpriteCache()
        self.minimap_static_cache = MinimapStaticCache()
        self.show_perf_overlay = False
        self.detailed_perf_overlay = False
        self.overlay_state.scoreboard_scroll = 0
        saved_settings = self._load_client_settings()
        self.gc_pacing_enabled = bool(saved_settings.get("gc_pacing_enabled", False))
        self.perf_logging_enabled = bool(saved_settings.get("perf_logging_enabled", False))
        self.perf_log_recorder.set_enabled(self.perf_logging_enabled)
        self.graphics_quality = str(saved_settings.get("graphics_quality", "adaptive")).lower()
        if self.graphics_quality not in QUALITY_PRESETS:
            self.graphics_quality = "adaptive"
        self.render_quality = quality_profile_for("high" if self.graphics_quality == "adaptive" else self.graphics_quality)
        self.adaptive_performance = AdaptivePerformanceController(self.render_quality, observe_only=True)
        self.render_frame_builder.quality = self.render_quality
        self.camera_distance = max(0.78, min(1.08, float(saved_settings.get("camera_distance", 0.92))))
        self.camera_zoom = self.camera_distance
        self.camera_controller = CameraController(
            viewport_size=(SCREEN_W, SCREEN_H),
            world_size=(MAP_WIDTH, MAP_HEIGHT),
            distance=self.camera_distance,
            zoom=self.camera_zoom,
        )
        self.actions = ClientActionBuffer()
        self.audio_tuning = load_audio_tuning()
        self.master_volume = self._read_volume(saved_settings, "master_volume", 0.8)
        self.music_volume = self._read_volume(saved_settings, "music_volume", 0.55)
        self.effects_volume = self._read_volume(saved_settings, "effects_volume", 0.8)
        self.audio = AudioManager(self.audio_tuning.menu_music_path, self.audio_tuning.actions_dir)
        self.audio.set_master_volume(self.master_volume)
        self.audio.set_music_volume(self.music_volume)
        self.audio.set_effects_volume(self.effects_volume)
        self.app_state = AppState.MENU
        self.state = self.app_state.value
        self.navigation = AppNavigation(self)
        self.player_name = self._clean_player_name(str(saved_settings.get("player_name", "Operator")))
        self.name_editing = False
        self.name_input = self.player_name
        self.world: GameWorld | None = None
        self.local_player_id: str | None = None
        self.loading_state: LoadingScreenState | None = None
        self.loading_thread: threading.Thread | None = None
        self.loading_error: str | None = None
        self._loaded_world: GameWorld | None = None
        self._loaded_player_id: str | None = None
        self._loading_started_at = 0.0
        self.online = OnlineClient()
        self.overlay_state.inventory_open = False
        self.overlay_state.backpack_open = False
        self.overlay_state.settings_open = False
        self.overlay_state.craft_open = False
        self.overlay_state.weapon_custom_open = False
        self.overlay_state.minimap_big = False
        self.overlay_state.craft_scroll = 0
        self.overlay_state.weapon_modules_scroll = 0
        self.running = True
        self._local_command_id = 0
        self.overlay_state.drag_source: dict[str, object] | None = None
        self.overlay_state.custom_weapon_slot = "1"
        self.language = str(saved_settings.get("language", self.language))
        if self.language not in self.locales:
            self.language = "en"
        self.settings = {
            "bot_vision": bool(saved_settings.get("bot_vision", True)),
            "bot_vision_range": bool(saved_settings.get("bot_vision_range", True)),
            "soldier_reaction_radius": bool(saved_settings.get("soldier_reaction_radius", True)),
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
        self.single_game_mode_key = str(saved_settings.get("single_game_mode", "survival"))
        self.single_game_mode_options = tuple(mode.id for mode in list_game_modes())
        if self.single_game_mode_key not in self.single_game_mode_options:
            self.single_game_mode_key = "survival"
        mode_spec = get_game_mode(self.single_game_mode_key)
        self.single_player_faction = str(saved_settings.get("single_player_faction", mode_spec.default_player_faction))
        if self.single_player_faction not in mode_spec.player_factions:
            self.single_player_faction = mode_spec.default_player_faction
        self.single_map_key = str(saved_settings.get("single_map", "city"))
        self.single_map_manifests = list_available_maps()
        self.single_map_options = tuple(manifest.id for manifest in self.single_map_manifests) or MAP_OPTIONS
        self.single_map_titles = {manifest.id: manifest.title for manifest in self.single_map_manifests}
        self.single_map_descriptions = {manifest.id: manifest.description for manifest in self.single_map_manifests}
        if self.single_map_key not in self.single_map_options:
            self.single_map_key = self.single_map_options[0]
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
        self.scene_manager = self._build_scene_manager()
        if self.settings["fullscreen"]:
            self._set_display_mode(True)
        self._sync_menu_music()

    def _build_scene_manager(self) -> SceneManager:
        manager = SceneManager(
            state_getter=lambda: self.state,
            state_setter=self._set_state,
            on_quit=self._request_quit,
            on_resize=self._on_display_resize,
        )
        manager.register(AppState.MENU, MenuScene(self))
        manager.register(AppState.OPTIONS, OptionsScene(self))
        manager.register(AppState.SINGLE_SETUP, SingleSetupScene(self))
        manager.register(AppState.SINGLE_LOADING, LoadingScene(self))
        manager.register(AppState.SERVERS, ServerBrowserScene(self))
        manager.register(AppState.SINGLE, GameplayScene(self))
        manager.register(AppState.ONLINE_GAME, GameplayScene(self))
        return manager

    def _set_state(self, state: str | AppState) -> None:
        self.app_state = normalize_app_state(state)
        self.state = self.app_state.value

    def _request_quit(self) -> None:
        self.running = False

    def _on_display_resize(self, size: tuple[int, int]) -> None:
        if self.fullscreen:
            return
        self.display_manager.resize_window(size)
        self._sync_display_refs()

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
            "single_game_mode": self.single_game_mode_key,
            "single_player_faction": self.single_player_faction,
            "single_map": self.single_map_key,
            "graphics_quality": self.graphics_quality,
            "gc_pacing_enabled": self.gc_pacing_enabled,
            "perf_logging_enabled": self.perf_logging_enabled,
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

    def _cycle_graphics_quality(self) -> None:
        order = list(QUALITY_PRESETS)
        current = self.graphics_quality if self.graphics_quality in order else "adaptive"
        self.graphics_quality = order[(order.index(current) + 1) % len(order)]
        self.render_quality = quality_profile_for("high" if self.graphics_quality == "adaptive" else self.graphics_quality)
        self.render_frame_builder.quality = self.render_quality
        self.adaptive_performance.profile = self.render_quality
        self.adaptive_performance.set_observe_only(True)
        self._render_frame_cache_key = None
        self._render_frame_cache = None
        self._save_client_settings()

    def tr(self, key: str, **values: object) -> str:
        text = self.locales.get(self.language, {}).get(key) or self.locales.get("en", {}).get(key) or key
        return text.format(**values) if values else text

    def _load_icon_mapping(self) -> dict[str, str]:
        return self.assets.load_icon_mapping() if hasattr(self, "assets") else dict(DEFAULT_ICON_MAPPING)

    def _load_item_images(self) -> dict[str, pygame.Surface]:
        return self.assets.load_item_images()

    def _load_alpha_image(self, path: Path) -> pygame.Surface:
        return self.assets.load_alpha_image(path)

    def _load_loading_assets(self) -> tuple[pygame.Surface | None, pygame.Surface | None]:
        loading = self.assets.load_loading_assets()
        return loading.poster, loading.spinner

    def _try_load_image(self, *paths: Path) -> pygame.Surface | None:
        return self.assets.try_load_image(*paths)

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
        gc_was_enabled = gc.isenabled()
        if self.gc_pacing_enabled:
            gc.disable()
        while self.running:
            self.frame_phases.begin_frame()
            frame_start = time.perf_counter()
            dt = self.clock.tick(FPS) / 1000.0
            self.frame_phases.begin(FramePhase.INPUT)
            events = pygame.event.get()
            self.scene_manager.handle_events(events)
            self.perf_stats.input_phase_ms = self.frame_phases.end(FramePhase.INPUT)
            self.frame_phases.begin(FramePhase.NETWORK_HANDOFF)
            if self.state == "online_game":
                self.online.flush_handoff()
            self.perf_stats.network_handoff_phase_ms = self.frame_phases.end(FramePhase.NETWORK_HANDOFF)
            self.frame_phases.begin(FramePhase.SESSION_UPDATE)
            update_start = time.perf_counter()
            self.scene_manager.update(dt)
            self.perf_stats.update_ms = (time.perf_counter() - update_start) * 1000.0
            self.perf_stats.scene_update_ms = self.perf_stats.update_ms
            self.perf_stats.session_update_phase_ms = self.frame_phases.end(FramePhase.SESSION_UPDATE)
            self.frame_phases.begin(FramePhase.PREDICTION_RECONCILIATION)
            self.perf_stats.prediction_phase_ms = self.frame_phases.end(FramePhase.PREDICTION_RECONCILIATION)
            self.frame_phases.begin(FramePhase.RENDER_FRAME_BUILD)
            ctx = self._current_render_context(dt)
            self.frame_phases.end(FramePhase.RENDER_FRAME_BUILD)
            self.frame_phases.begin(FramePhase.RENDER)
            render_start = time.perf_counter()
            self.scene_manager.render(ctx)
            self.perf_stats.scene_render_ms = (time.perf_counter() - render_start) * 1000.0
            self.perf_stats.render_phase_ms = self.frame_phases.end(FramePhase.RENDER)
            self.frame_phases.begin(FramePhase.AUDIO_EFFECTS)
            self.perf_stats.audio_effects_phase_ms = self.frame_phases.end(FramePhase.AUDIO_EFFECTS)
            if self.show_perf_overlay or self.detailed_perf_overlay:
                self._render_perf_overlay()
            self._present()
            self.perf_stats.frame_ms = (time.perf_counter() - frame_start) * 1000.0
            self.frame_phases.begin(FramePhase.PERF_LOG)
            self._update_runtime_perf_telemetry()
            self.perf_stats.perf_log_phase_ms = self.frame_phases.end(FramePhase.PERF_LOG)
        if self.gc_pacing_enabled and gc_was_enabled:
            gc.enable()
        if self.world:
            self.world.close()
        self.online.close()
        self.audio.close()
        pygame.quit()

    def _update_runtime_perf_telemetry(self) -> None:
        counts = gc.get_count()
        self.perf_stats.gc_count_0 = counts[0]
        self.perf_stats.gc_count_1 = counts[1]
        self.perf_stats.gc_count_2 = counts[2]
        self.perf_stats.gc_time_ms = 0.0
        self.perf_stats.frame_alloc_estimate = (
            len(self.render_frame_builder.scratch.spatial_items)
            + len(self.render_frame_builder.scratch.actor_items)
            + len(self._explosion_effects)
            + len(self._death_effects)
        )
        self.perf_stats.effect_pool_active = self._explosion_effect_pool.active + self._death_effect_pool.active
        self.perf_stats.effect_pool_free = self._explosion_effect_pool.free_count + self._death_effect_pool.free_count
        budget = self.frame_budget.observe(self.perf_stats.frame_ms, self.perf_stats.draw_world_ms)
        self.perf_stats.frame_p95_ms = budget.p95_ms
        self.perf_stats.frame_p99_ms = budget.p99_ms
        self.perf_stats.over_budget_frames = budget.over_budget_frames
        self.perf_stats.suggested_lod_bias = budget.suggested_lod_bias
        self.perf_stats.suggested_render_radius_scale = budget.suggested_render_radius_scale
        if self.graphics_quality == "adaptive":
            self.adaptive_performance.observe(self.perf_stats)
        else:
            self.adaptive_performance.observe(self.perf_stats)
        if self.gc_pacing_enabled and self.state in {"menu", "options", "single_setup", "single_loading", "servers"}:
            started = time.perf_counter()
            gc.collect(0)
            self.perf_stats.gc_time_ms = (time.perf_counter() - started) * 1000.0
        self.perf_log_recorder.observe(
            self.perf_stats,
            state=self.state,
            fps=self.clock.get_fps(),
            quality_profile=self.graphics_quality,
            online=self.online.online_perf() if self.state == "online_game" else None,
        )

    def toggle_gc_pacing(self) -> None:
        self.gc_pacing_enabled = not self.gc_pacing_enabled
        if self.gc_pacing_enabled and self.state in {"single", "online_game"} and gc.isenabled():
            gc.disable()
        elif not self.gc_pacing_enabled and not gc.isenabled():
            gc.enable()
        self._save_client_settings()

    def toggle_perf_logging(self) -> None:
        self.perf_logging_enabled = not self.perf_logging_enabled
        self.perf_log_recorder.set_enabled(self.perf_logging_enabled)
        self._save_client_settings()

    def _current_render_context(self, dt: float) -> RenderContext:
        prepare_start = time.perf_counter()
        snapshot = self._snapshot()
        player = self._local_player(snapshot)
        camera = self._camera(player)
        snapshot_tick = self._snapshot_tick(snapshot)
        render_frame = self._build_render_frame(snapshot, player, camera, snapshot_tick)
        render_view = self.snapshot_render_adapter.from_world_snapshot(snapshot, snapshot_tick) if snapshot else None
        self.perf_stats.render_prepare_ms = (time.perf_counter() - prepare_start) * 1000.0
        return self._build_render_context(snapshot, player, camera, dt, render_frame, render_view)

    def _build_render_frame(
        self,
        snapshot: WorldSnapshot | None,
        player: PlayerState | None,
        camera: Vec2,
        snapshot_tick: int,
    ) -> RenderFrame | None:
        if not snapshot:
            self.perf_stats.reset_visible_counts()
            self._render_frame_cache_key = None
            self._render_frame_cache = None
            return None
        view = self.camera_controller.visible_world_rect(camera, margin=360.0)
        cache_key = self._render_frame_cache_key_for(snapshot_tick, camera, player)
        if (
            self.state != "online_game"
            and self._render_frame_cache_key == cache_key
            and self._render_frame_cache is not None
        ):
            return self._render_frame_cache
        frame = self.render_frame_builder.build(snapshot, view, player, self.perf_stats)
        self._render_frame_cache_key = cache_key
        self._render_frame_cache = frame
        return frame

    def _snapshot_tick(self, snapshot: WorldSnapshot | None) -> int:
        if self.state == "online_game":
            return self.online.snapshot_tick()
        return int((snapshot.time if snapshot else 0.0) * 1000.0)

    def _render_frame_cache_key_for(
        self,
        snapshot_tick: int,
        camera: Vec2,
        player: PlayerState | None,
    ) -> RenderFrameCacheKey:
        return RenderFrameCacheKey(
            snapshot_tick=snapshot_tick,
            camera_cell_x=int(camera.x // 512),
            camera_cell_y=int(camera.y // 512),
            floor=player.floor if player else 0,
            zoom_bucket=int(round(self.camera_zoom * 100.0)),
            local_facing_bucket=int(((player.angle if player else 0.0) % math.tau) / math.tau * 96),
        )

    def _sync_display_refs(self) -> None:
        self.fullscreen = self.display_manager.fullscreen
        self.windowed_size = self.display_manager.windowed_size
        self.display = self.display_manager.display
        self.screen = self.display_manager.screen
        self.render_rect = self.display_manager.render_rect
        self.render_scale = self.display_manager.render_scale

    def _set_display_mode(self, fullscreen: bool) -> None:
        self.display_manager.set_display_mode(fullscreen)
        self._sync_display_refs()
        self.settings["fullscreen"] = fullscreen

    def _toggle_fullscreen(self) -> None:
        self._set_display_mode(not self.fullscreen)

    def _update_display_transform(self) -> None:
        self.display_manager.update_transform()
        self._sync_display_refs()

    def _display_to_screen(self, pos: tuple[int, int]) -> tuple[int, int]:
        return self.display_manager.display_to_screen(pos)

    def _mouse_pos(self) -> tuple[int, int]:
        return self._display_to_screen(pygame.mouse.get_pos())

    def _present(self) -> None:
        self.display_manager.present()
        self._sync_display_refs()

    def _sync_menu_music(self) -> None:
        self.app_state = normalize_app_state(self.state)
        self.audio.set_menu_music_active(self.app_state.uses_menu_music)

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

    def _play_position_action_event(
        self,
        event: dict[str, object],
        action: str,
        *,
        once_group: str,
    ) -> None:
        entity_id = str(
            event.get("entity_id")
            or event.get("projectile_id")
            or f"{action}:{event.get('tick', '')}:{event.get('x', '')}:{event.get('y', '')}"
        )
        try:
            pos = Vec2(float(event.get("x", 0.0)), float(event.get("y", 0.0)))
            floor = int(event.get("floor", 0))
        except (TypeError, ValueError):
            return

        if once_group == "grenade_throw":
            self._play_grenade_throw_sound_once(entity_id, pos, floor)
        elif once_group == "explosion":
            self._play_explosion_sound_once(entity_id, action, pos, floor)
        else:
            self._play_action_sound(action, pos, floor)

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

    def _play_action_sound(self, action: str, pos: Vec2 | None, floor: int, *, local: bool = False) -> None:
        spec = self.audio_tuning.action_sounds.get(action)
        if not spec:
            return
        volume, pan = (
            (1.0, 0.0)
            if local
            else self._spatial_sound_params(
                pos,
                floor,
                max_distance=spec.hearing_distance,
                full_distance=spec.full_volume_distance,
            )
        )
        if volume <= 0.0:
            return
        self.audio.play_action_sound(
            spec.key,
            volume=volume,
            pan=pan,
            echo_delay=spec.echo_delay,
            echo_volume=spec.echo_volume,
        )

    def _play_grenade_throw_sound_once(self, entity_id: str, pos: Vec2, floor: int) -> None:
        if entity_id in self._played_grenade_throw_sounds:
            return
        self._played_grenade_throw_sounds.add(entity_id)
        if len(self._played_grenade_throw_sounds) > 1024:
            self._played_grenade_throw_sounds.clear()
        self._play_action_sound("grenade_throw", pos, floor)

    def _play_explosion_sound_once(self, entity_id: str, action: str, pos: Vec2, floor: int) -> None:
        key = f"{action}:{entity_id}"
        if key in self._played_explosion_sounds:
            return
        self._played_explosion_sounds.add(key)
        if len(self._played_explosion_sounds) > 1024:
            self._played_explosion_sounds.clear()
        self._play_action_sound(action, pos, floor)

    def _weapon_sound_key(self, weapon_key: str, action: str) -> str:
        spec = self.audio_tuning.weapon_sounds.get(weapon_key)
        if spec:
            return getattr(spec, action, "")
        if action == "shot":
            return weapon_key if weapon_key else "pistol"
        if action == "reload":
            return "reload"
        return "empty"

    def _spatial_sound_params(
        self,
        pos: Vec2 | None,
        floor: int,
        *,
        max_distance: float | None = None,
        full_distance: float | None = None,
    ) -> tuple[float, float]:
        if not pos:
            return 1.0, 0.0
        snapshot = self._snapshot()
        listener = self._local_player(snapshot) if snapshot else None
        if not listener:
            return 1.0, 0.0
        dx = pos.x - listener.pos.x
        dy = pos.y - listener.pos.y
        distance = math.hypot(dx, dy)
        max_distance = max(1.0, float(max_distance if max_distance is not None else self.audio_tuning.shot_hearing_distance))
        full_distance = min(
            max_distance,
            max(0.0, float(full_distance if full_distance is not None else self.audio_tuning.shot_full_volume_distance)),
        )
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

    def _process_online_events(self) -> None:
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
            if kind == "grenade_thrown":
                self._play_position_action_event(event, "grenade_throw", once_group="grenade_throw")
                continue
            if kind == "grenade_exploded":
                self._play_position_action_event(event, "grenade_explosion", once_group="explosion")
                continue
            if kind == "mine_exploded":
                self._play_position_action_event(event, "mine_explosion", once_group="explosion")
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
            self._death_effect_pool.acquire(
                key=key,
                entity_type=entity_type,
                entity_id=entity_id,
                kind=kind,
                name=name,
                pos=pos.copy(),
                floor=int(floor),
                facing=float(facing),
                started=now,
                seed=seed,
            )
        )
        max_effects = max(1, int(self.death_effects.max_effects))
        if len(self._death_effects) > max_effects:
            for effect in self._death_effects[:-max_effects]:
                self._death_effect_pool.release(effect)
            del self._death_effects[:-max_effects]

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
        write_index = 0
        for effect in self._death_effects:
            if now - float(effect.get("started", now)) <= lifetime + 0.08:
                self._death_effects[write_index] = effect
                write_index += 1
            else:
                self._death_effect_pool.release(effect)
        del self._death_effects[write_index:]

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
        self.camera_controller.distance = self.camera_distance
        self.camera_zoom = self.camera_controller.update_zoom(dt, player)

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

    def _dispatch_action_buffer(self, player_id: str) -> None:
        commands = self._action_command_specs()
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

    def _queue_client_action(self, kind: str, payload: dict[str, object] | None = None) -> None:
        self.actions.push(kind, payload)

    def _action_command_specs(self) -> list[tuple[str, dict[str, object]]]:
        return self.actions.peek_command_specs()

    def _clear_transient_inputs(self) -> None:
        self.actions.clear()

    def _reset_death_effect_tracking(self) -> None:
        for effect in self._death_effects:
            self._death_effect_pool.release(effect)
        self._death_effects.clear()
        for effect in self._explosion_effects:
            self._explosion_effect_pool.release(effect)
        self._explosion_effects.clear()
        self._prev_zombie_death_state.clear()
        self._prev_player_death_state.clear()
        self._prev_projectile_audio_state.clear()
        self._played_projectile_sounds.clear()
        self._played_grenade_throw_sounds.clear()
        self._played_explosion_sounds.clear()
        self._shot_sound_debounce.clear()
        self._prev_reload_audio_state.clear()
        self._last_empty_sound_at = 0.0

    def _start_single_player(self) -> None:
        self.online.close()
        if self.world:
            self.world.close()
        self.world = None
        self.local_player_id = None
        self._loaded_world = None
        self._loaded_player_id = None
        self.loading_error = None
        self.loading_state = LoadingScreenState(self.single_map_key)
        self._loading_started_at = time.time()
        self._set_state(AppState.SINGLE_LOADING)
        self._save_client_settings()

        def worker() -> None:
            try:
                world, player_id = self._build_single_player_world(self.loading_state)
                self._loaded_world = world
                self._loaded_player_id = player_id
            except Exception as exc:
                self.loading_error = str(exc)
                if self.loading_state is not None:
                    self.loading_state.fail(str(exc))

        self.loading_thread = threading.Thread(
            target=worker,
            name="single-map-loader",
            daemon=True,
        )
        self.loading_thread.start()

    def _build_single_player_world(
        self,
        loading_state: LoadingScreenState | None,
    ) -> tuple[GameWorld, str]:
        difficulty = load_difficulty(self.difficulty_key)
        density = self.bot_density_profiles[self.bot_density]
        mode = get_game_mode(self.single_game_mode_key)
        if self.single_bots_enabled and mode.uses_zombies:
            initial_zombies = max(1, int(round(difficulty.initial_zombies * density)))
            max_zombies = max(initial_zombies, int(round(difficulty.max_zombies * density)))
        else:
            initial_zombies = 0
            max_zombies = 0
        world = GameWorld(
            seed=int(time.time()),
            initial_zombies=initial_zombies,
            max_zombies=max_zombies,
            difficulty_key=self.difficulty_key,
            zombie_workers=0,
            map_id=self.single_map_key,
            game_mode_id=self.single_game_mode_key,
            player_faction=self.single_player_faction,
            loading_state=loading_state,
        )
        player = world.add_player(self.player_name, "local")
        return world, player.id

    def _finish_single_loading_if_ready(self) -> None:
        if self.state != "single_loading":
            return

        thread_done = self.loading_thread is not None and not self.loading_thread.is_alive()
        ready = self.loading_state and self.loading_state.snapshot().stage == LoadingStage.READY

        if self.loading_error:
            return

        if not thread_done or not ready or self._loaded_world is None or self._loaded_player_id is None:
            return

        self.world = self._loaded_world
        self.local_player_id = self._loaded_player_id
        self._loaded_world = None
        self._loaded_player_id = None
        self.overlay_state.inventory_open = False
        self.overlay_state.backpack_open = False
        self.overlay_state.settings_open = False
        self.overlay_state.craft_open = False
        self.overlay_state.weapon_custom_open = False
        self._reset_death_effect_tracking()
        self._set_state(AppState.SINGLE)

    def _show_servers(self) -> None:
        self._set_state(AppState.SERVERS)
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
            self.overlay_state.inventory_open = False
            self.overlay_state.backpack_open = False
            self.overlay_state.weapon_custom_open = False
            self._reset_death_effect_tracking()
            self._set_state(AppState.ONLINE_GAME)
        except OSError as exc:
            entry.status = f"error: {exc}"

    def _back_to_menu(self) -> None:
        self.online.close()
        if self.world:
            self.world.close()
            self.world = None
        self._set_state(AppState.MENU)
        self.overlay_state.inventory_open = False
        self.overlay_state.backpack_open = False
        self.overlay_state.settings_open = False
        self.overlay_state.craft_open = False
        self.overlay_state.weapon_custom_open = False
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
        self.camera_controller.distance = self.camera_distance
        self.camera_controller.zoom = self.camera_zoom
        return self.camera_controller.camera_for_player(player)

    def _mouse_world(self, player: PlayerState | None) -> Vec2:
        camera = self._camera(player)
        return self.camera_controller.screen_to_world(self._mouse_pos(), camera)

    def _build_render_context(
        self,
        snapshot: WorldSnapshot | None,
        player: PlayerState | None,
        camera: Vec2,
        dt: float,
        render_frame: RenderFrame | None = None,
        render_view=None,
    ) -> RenderContext:
        return RenderContext(
            screen=self.screen,
            camera=camera,
            camera_controller=self.camera_controller,
            assets=self.assets,
            snapshot=snapshot,
            local_player=player,
            dt=dt,
            settings=self.settings,
            fonts=RenderFonts(
                normal=self.font,
                small=self.small,
                big=self.big,
                mid=self.mid,
                label=self.label_font,
                hud_title=self.hud_title_font,
                hud_value=self.hud_value_font,
                emphasis=self.emphasis_font,
            ),
            text=RenderText(
                tr=self.tr,
                item_title=self.item_title,
                weapon_title=self.weapon_title,
                rarity_title=self.rarity_title,
                loot_label=self._loot_label,
                floor_label=self._floor_label,
            ),
            text_cache=self.text_cache,
            ui_cache=self.ui_surface_cache,
            overlay=self.overlay_state,
            local_player_id=self.local_player_id,
            online_player_id=self.online.player_id,
            now=time.time(),
            render_frame=render_frame,
            render_snapshot_view=render_view,
            perf=self.perf_stats,
            effects=self._sync_visual_effect_state(),
            death_tuning=self.death_effects,
            quality=self.render_quality,
            mouse_pos=self._mouse_pos(),
        )

    def _sync_visual_effect_state(self) -> VisualEffectsState:
        self.visual_effects.damage_flash = self.damage_flash
        self.visual_effects.explosion_effects = self._explosion_effects
        self.visual_effects.death_effects = self._death_effects
        self.visual_effects.join_notifications = self._join_notifications
        return self.visual_effects

    def _render_perf_overlay(self) -> None:
        stats = self.perf_stats
        compact = [
            f"FPS {self.clock.get_fps():5.1f}  Frame {stats.frame_ms:5.1f} ms",
            f"Update {stats.update_ms:5.1f}  Prepare {stats.render_prepare_ms:5.1f}",
            f"World {stats.draw_world_ms:5.1f}  UI {stats.draw_ui_ms:5.1f}",
            f"HUD {stats.hud_ms:5.1f}  Minimap {stats.minimap_ms:5.1f}  Overlay {stats.overlay_ms:5.1f}",
            f"Visible P:{stats.visible_players} Z:{stats.visible_zombies} S:{stats.visible_soldiers} L:{stats.visible_loot}",
        ]
        detailed = [
            f"Scene update/render {stats.scene_update_ms:5.1f}/{stats.scene_render_ms:5.1f}  Controller {stats.controller_ms:5.1f}",
            f"Phases in/net/update/predict/render/audio/log {stats.input_phase_ms:4.1f}/{stats.network_handoff_phase_ms:4.1f}/{stats.session_update_phase_ms:4.1f}/{stats.prediction_phase_ms:4.1f}/{stats.render_phase_ms:4.1f}/{stats.audio_effects_phase_ms:4.1f}/{stats.perf_log_phase_ms:4.1f}",
            f"Frame build {stats.render_frame_build_ms:5.2f}  Cull {stats.culling_ms:5.2f}  Spatial {stats.spatial_query_ms:5.2f}",
            f"Map {stats.map_ms:5.2f}  Static {stats.world_static_ms:5.2f}  Dynamic {stats.world_dynamic_ms:5.2f}",
            f"Actors {stats.actors_ms:5.2f}  Projectiles {stats.projectiles_ms:5.2f}  Effects {stats.effects_ms:5.2f}",
            f"Snapshot P:{stats.snapshot_total_players} Z:{stats.snapshot_total_zombies} S:{stats.snapshot_total_soldiers} L:{stats.snapshot_total_loot}",
            f"Chunks visible:{stats.visible_chunks} hit/miss:{stats.static_chunk_hits}/{stats.static_chunk_misses}",
            f"Text hit/miss:{stats.text_cache_hits}/{stats.text_cache_misses}  Icon hit/miss:{stats.icon_cache_hits}/{stats.icon_cache_misses}",
            f"Minimap cache hit/miss:{stats.minimap_cache_hits}/{stats.minimap_cache_misses}",
            f"GC counts:{stats.gc_count_0}/{stats.gc_count_1}/{stats.gc_count_2} gc:{stats.gc_time_ms:5.2f}ms pacing:{'on' if self.gc_pacing_enabled else 'off'}",
            f"Debug toggles F8 GC:{'on' if self.gc_pacing_enabled else 'off'} F9 log:{'on' if self.perf_logging_enabled else 'off'}",
            f"Alloc-est:{stats.frame_alloc_estimate}",
            f"Pools active/free:{stats.effect_pool_active}/{stats.effect_pool_free}",
            f"Frame p95/p99:{stats.frame_p95_ms:5.1f}/{stats.frame_p99_ms:5.1f} over:{stats.over_budget_frames}",
            f"Budget observe LOD:{stats.suggested_lod_bias:.2f} radius:{stats.suggested_render_radius_scale:.2f}",
            f"Quality {self.graphics_quality} observe:{'on' if stats.quality_observe_only else 'off'} radius:{stats.quality_render_radius_multiplier:.2f} lod:{stats.quality_actor_lod_bias} fx:{stats.quality_effects_quality:.2f} map:{stats.quality_minimap_update_rate:.1f}Hz",
            f"Quality advice: {stats.quality_recommendation}",
        ]
        if self.detailed_perf_overlay and self.state == "online_game":
            online = self.online.online_perf()
            detailed.extend(
                [
                    f"Online {online.network_state} tick:{online.snapshot_tick} age:{online.snapshot_age_ms:5.1f}ms buf:{online.snapshot_buffer_size}",
                    f"Net interval:{online.snapshot_interval_ms:5.1f}ms ping:{online.ping_ms:5.1f}ms ack:{online.ack_input_seq}",
                    f"Pending inputs:{online.pending_inputs} commands:{online.pending_commands}",
                    f"Decode:{online.decode_ms:5.2f} Interp:{online.interpolation_ms:5.2f} Predict:{online.prediction_ms:5.2f}",
                    f"Payload snapshot/delta/events:{online.snapshot_bytes}/{online.delta_bytes}/{online.events_bytes}B LOD full/simple/dot:{online.actors_full}/{online.actors_simple}/{online.actors_dot} ratio:{online.compression_ratio:.2f}",
                    f"Prediction error:{online.prediction_error_px:5.1f}px correction:{online.correction_px:5.1f}px",
                    f"Radius server:{online.server_interest_radius:5.0f} render:{online.render_radius:5.0f} minimap:{online.minimap_radius:5.0f} audio:{online.audio_radius:5.0f}",
                ]
            )
        lines = compact + (detailed if self.detailed_perf_overlay else [])
        width = 520 if self.detailed_perf_overlay else 360
        height = 24 + len(lines) * 19
        panel = pygame.Rect(14, 14, width, height)
        surface = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(surface, (5, 9, 18, 220), surface.get_rect(), border_radius=8)
        pygame.draw.rect(surface, (76, 225, 255, 150), surface.get_rect(), 1, border_radius=8)
        self.screen.blit(surface, panel)
        title = "F4 detailed performance" if self.detailed_perf_overlay else "F3 performance"
        self._blit_text(title, panel.x + 12, panel.y + 8, CYAN, self.small)
        for index, line in enumerate(lines):
            self._blit_text(line, panel.x + 12, panel.y + 30 + index * 19, TEXT, self.small)

    def _update_explosion_effects(self, snapshot: WorldSnapshot, player: PlayerState | None) -> None:
        now = time.time()
        current_grenades: dict[str, tuple[Vec2, int, str]] = {
            grenade.id: (grenade.pos.copy(), grenade.floor, grenade.kind) for grenade in snapshot.grenades.values()
        }
        current_mines: dict[str, tuple[Vec2, int, str]] = {
            mine.id: (mine.pos.copy(), mine.floor, mine.kind) for mine in snapshot.mines.values()
        }
        for grenade_id, (pos, floor, _kind) in current_grenades.items():
            if grenade_id not in self._prev_grenade_state:
                self._play_grenade_throw_sound_once(grenade_id, pos, floor)

        for grenade_id, (pos, floor, kind) in self._prev_grenade_state.items():
            if grenade_id in current_grenades:
                continue
            spec = GRENADE_SPECS.get(kind, DEFAULT_GRENADE)
            self._explosion_effects.append(
                self._explosion_effect_pool.acquire(pos=pos, floor=floor, radius=spec.blast_radius, color=(255, 168, 118), start=now, duration=0.34),
            )
            self._play_explosion_sound_once(grenade_id, "grenade_explosion", pos, floor)
        for mine_id, (pos, floor, kind) in self._prev_mine_state.items():
            if mine_id in current_mines:
                continue
            spec = MINE_SPECS.get(kind, DEFAULT_MINE)
            self._explosion_effects.append(
                self._explosion_effect_pool.acquire(pos=pos, floor=floor, radius=spec.blast_radius, color=(212, 140, 255), start=now, duration=0.36),
            )
            self._play_explosion_sound_once(mine_id, "mine_explosion", pos, floor)
        self._prev_grenade_state = current_grenades
        self._prev_mine_state = current_mines
        write_index = 0
        for fx in self._explosion_effects:
            if now - float(fx["start"]) <= float(fx["duration"]) + 0.04:
                self._explosion_effects[write_index] = fx
                write_index += 1
            else:
                self._explosion_effect_pool.release(fx)
        del self._explosion_effects[write_index:]

    def _minimap_rect(self) -> pygame.Rect:
        size = 248 if self.overlay_state.minimap_big else 176
        return pygame.Rect(SCREEN_W - size - 18, 18, size, int(size * MAP_HEIGHT / MAP_WIDTH))

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

    def _format_ping(self, ping_ms: float | int | None) -> str:
        if ping_ms is None or float(ping_ms) <= 0.0:
            return "--"
        if float(ping_ms) >= 1000.0:
            return "999+"
        return f"{float(ping_ms):.0f} ms"

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
        self.overlay_state.craft_scroll = max(0, min(self._craft_max_scroll(), self.overlay_state.craft_scroll + direction * 78))

    def _set_craft_scroll_from_pointer(self, y: int) -> None:
        track = self._craft_scroll_track_rect()
        max_scroll = self._craft_max_scroll()
        if max_scroll <= 0:
            self.overlay_state.craft_scroll = 0
            return
        knob_h = max(42, int(track.h * track.h / max(track.h, self._craft_content_height())))
        ratio = (y - track.y - knob_h * 0.5) / max(1, track.h - knob_h)
        self.overlay_state.craft_scroll = max(0, min(max_scroll, int(max_scroll * ratio)))

    def _craft_recipe_rect(self, index: int) -> pygame.Rect:
        viewport = self._craft_viewport_rect()
        card_w, card_h, gap, cols = self._craft_card_metrics()
        col = index % cols
        row = index // cols
        return pygame.Rect(viewport.x + col * (card_w + gap), viewport.y + row * (card_h + gap) - self.overlay_state.craft_scroll, card_w, card_h)

    def _recipe_result_kind(self, recipe_key: str) -> str:
        recipe = RECIPES[recipe_key]
        result_key, _ = recipe.result
        if result_key in WEAPONS:
            return "weapon"
        spec = ITEMS.get(result_key)
        return spec.kind if spec else "item"

    def _client_weapon_magazine_size(self, weapon: object) -> int:
        base = WEAPONS[weapon.key].magazine_size
        module_key = weapon.modules.get("magazine")
        module = WEAPON_MODULES.get(module_key or "")
        return max(base, int(math.ceil(base * (module.magazine_multiplier if module else 1.0))))

    def _settings_audio_active(self) -> bool:
        return self.settings_tab == "audio" and (self.state == "options" or (self.overlay_state.settings_open and self.state in {"single", "online_game"}))

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

    def _settings_options_scrollbar(self, viewport: pygame.Rect, rows: int, step_y: int) -> None:
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
        if tab_has_graphics_quality(self.settings_tab):
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
            viewport.y + row * (card_h + gap_y) - self.overlay_state.weapon_modules_scroll,
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
        self.overlay_state.weapon_modules_scroll = max(0, min(self._weapon_modules_max_scroll(), self.overlay_state.weapon_modules_scroll + direction * 40))

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
        if self.overlay_state.weapon_custom_open and player:
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
        if not self.overlay_state.drag_source or self.overlay_state.drag_source.get("source") != source:
            return False
        if index is not None and self.overlay_state.drag_source.get("index") != index:
            return False
        if slot is not None and self.overlay_state.drag_source.get("slot") != slot:
            return False
        return True

    def _dragged_payload(self, player: PlayerState | None) -> tuple[str, int, float | None, str] | None:
        if not player or not self.overlay_state.drag_source:
            return None
        source = str(self.overlay_state.drag_source.get("source", ""))
        if source == "backpack":
            index = int(self.overlay_state.drag_source.get("index", -1))
            item = player.backpack[index] if 0 <= index < len(player.backpack) else None
            return (item.key, item.amount, item.durability, item.rarity) if item else None
        if source == "equipment":
            item = player.equipment.get(str(self.overlay_state.drag_source.get("slot", "")))
            return (item.key, item.amount, item.durability, item.rarity) if item else None
        if source == "quick_item":
            item = player.quick_items.get(str(self.overlay_state.drag_source.get("slot", "")))
            return (item.key, item.amount, item.durability, item.rarity) if item else None
        if source == "weapon_module":
            weapon = player.weapons.get(str(self.overlay_state.drag_source.get("slot", "")))
            module_key = weapon.modules.get(str(self.overlay_state.drag_source.get("module_slot", ""))) if weapon else None
            return (module_key, 1, 100.0, "common") if module_key else None
        if source == "weapon_slot":
            weapon = player.weapons.get(str(self.overlay_state.drag_source.get("slot", "")))
            return (weapon.key, 1, weapon.durability, weapon.rarity) if weapon else None
        return None

    def _custom_weapon_slot(self, player: PlayerState | None) -> str:
        if player and player.weapons.get(self.overlay_state.custom_weapon_slot):
            return self.overlay_state.custom_weapon_slot
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

    def _scaled_icon(self, key: str, size: tuple[int, int]) -> pygame.Surface | None:
        return self.assets.scaled_icon(key, size)

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

    def _mini_durability(self, rect: pygame.Rect, durability: float) -> None:
        color = GREEN if durability >= 55 else YELLOW if durability >= 25 else RED
        bar = pygame.Rect(rect.x + 8, rect.bottom - 7, rect.w - 16, 4)
        pygame.draw.rect(self.screen, (34, 38, 50), bar, border_radius=2)
        pygame.draw.rect(self.screen, color, pygame.Rect(bar.x, bar.y, int(bar.w * max(0, min(100, durability)) / 100), bar.h), border_radius=2)

    def _floor_label(self, floor: int) -> str:
        if floor < 0:
            return f"B{abs(floor)}"
        return f"F{floor + 1}"

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
        self.overlay_state.scoreboard_scroll = max(0, min(max_scroll, self.overlay_state.scoreboard_scroll + direction * 36))

    def _blit_text(
        self,
        text: str,
        x: int,
        y: int,
        color: tuple[int, int, int],
        font: pygame.font.Font | None = None,
    ) -> None:
        surface = (font or self.font).render(text, True, color)
        self.screen.blit(surface, (x, y))
