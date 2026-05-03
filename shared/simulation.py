from __future__ import annotations

import math
import os
import random
import threading
from collections import deque
from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import dataclass, fields, replace
from typing import Any, Deque

from shared.systems.combat.damage_service import DamageService
from shared.systems.combat.projectile_system import ProjectileSystem
from shared.systems.sounds.sound_service import SoundService
from shared.systems.sounds.sound_system import SoundSystem

from shared.systems.poison.poison_system import PoisonSystem
from shared.systems.explosives.explosive_system import ExplosiveSystem

from shared.systems.loot.loot_service import LootService
from shared.systems.loot.loot_spawn_system import LootSpawnSystem

from shared.systems.spawning.spawn_service import SpawnService
from shared.systems.spawning.zombie_spawn_system import ZombieSpawnSystem

from shared.systems.geometry.building_service import BuildingService
from shared.systems.geometry.geometry_service import GeometryService
from shared.systems.geometry.movement_service import MovementService
from shared.world.world_config import WorldConfig
from shared.world.world_state import WorldState
from shared.world.world_context import WorldContext
from shared.world.id_generator import IdGenerator
from shared.concurrency.executor_config import build_executor_config
from shared.concurrency.process_pool_service import ProcessPoolService
from shared.concurrency.thread_pool_service import ThreadPoolService
from shared.systems.scheduler import SystemScheduler

from shared.systems.commands.command_router import CommandRouter
from shared.systems.commands.handlers.respawn_handler import RespawnHandler
from shared.systems.commands.handlers.select_slot_handler import SelectSlotHandler
from shared.systems.commands.handlers.use_medkit_handler import UseMedkitHandler
from shared.systems.commands.handlers.reload_handler import ReloadHandler
from shared.systems.commands.handlers.pickup_handler import PickupHandler
from shared.systems.commands.handlers.interact_handler import InteractHandler
from shared.systems.commands.handlers.toggle_utility_handler import ToggleUtilityHandler
from shared.systems.commands.handlers.equip_armor_handler import EquipArmorHandler
from shared.systems.commands.handlers.inventory_action_handler import InventoryActionHandler
from shared.systems.commands.handlers.craft_handler import CraftHandler
from shared.systems.commands.handlers.repair_handler import RepairHandler
from shared.systems.commands.handlers.throw_grenade_handler import ThrowGrenadeHandler

from shared.systems.players.respawn_service import RespawnService
from shared.systems.players.player_update_system import PlayerUpdateSystem

from shared.systems.combat.weapon_runtime_service import WeaponRuntimeService
from shared.systems.combat.player_combat_service import PlayerCombatService
from shared.systems.inventory.inventory_service import InventoryService

from shared.ai.pathfinding import GridPathfinder
from shared.ai.registry import ZOMBIE_AI_REGISTRY
from shared.spawning.soldier_factory import SoldierFactory
from shared.spawning.soldier_spawn_table import SOLDIER_SPAWN_POINTS
from shared.spawning.zombie_factory import ZombieFactory
from shared.spawning.zombie_spawn_table import DEFAULT_ZOMBIE_SPAWN_TABLE
from shared.ai.context import ZombieContext, SoundEvent, ActorTarget
from shared.ai.soldiers.context import SoldierContext
from shared.ai.soldiers.registry import SOLDIER_AI_REGISTRY


from shared.constants import (
    ARMORS,
    INITIAL_ZOMBIES,
    INTERACT_RADIUS,
    MAP_HEIGHT,
    MAP_WIDTH,
    MAX_ZOMBIES,
    PICKUP_RADIUS,
    PLAYER_RADIUS,
    SEARCH_DURATION,
    SHOT_NOISE,
    UNARMED_MELEE_NOISE,
    SNEAK_NOISE,
    SPRINT_MULTIPLIER,
    SPRINT_NOISE,
    WALK_NOISE,
    WEAPONS,
    SLOTS,
    ZOMBIE_TARGET_RADIUS,
    ZOMBIES, SOLDIERS,
)
from shared.backpack_config import load_backpack_config
from shared.crafting import roll_crafted_rarity
from shared.difficulty import load_difficulty
from shared.zombie_process_run import build_process_env, run_one_zombie_task
from shared.explosives import GRENADE_SPECS, MINE_SPECS, DEFAULT_GRENADE, DEFAULT_MINE
from shared.items import BASEMENT_LOOT, HOUSE_LOOT, ITEMS, LEGACY_LOOT_TO_ITEM, RECIPES, WORLD_LOOT
from shared.level import make_buildings, nearest_stairs
from shared.rarities import RARITIES, rarity_rank, rarity_spec
from shared.weapon_modules import WEAPON_MODULES
from shared.models import (
    BuildingState,
    ClientCommand,
    GrenadeState,
    InputCommand,
    InventoryItem,
    LootState,
    MineState,
    PlayerState,
    PoisonPoolState,
    PoisonProjectileState,
    ProjectileState,
    RectState,
    Vec2,
    WeaponRuntime,
    WorldSnapshot,
    ZombieState,
    SoldierState,
)


@dataclass(slots=True)
class _PoisonSpitEvent:
    owner_id: str
    pos: Vec2
    velocity: Vec2
    target: Vec2
    floor: int


@dataclass(slots=True)
class _ZombieUpdateResult:
    zombie: ZombieState
    player_hits: list[tuple[str, int]]
    poison_spits: list[_PoisonSpitEvent]
    soldier_hits: list[tuple[str, int]]


_COMMAND_EVENT_NAMES = {
    "pickup": "pickup_succeeded",
    "interact": "interact_succeeded",
    "inventory_action": "inventory_changed",
    "craft": "craft_finished",
    "repair": "repair_finished",
    "equip_armor": "armor_equipped",
    "select_slot": "slot_selected",
    "reload": "reload_started",
    "throw_grenade": "explosive_used",
    "toggle_utility": "utility_toggled",
    "use_medkit": "medkit_used",
    "respawn": "player_respawned",
}


# def _zombie_ai_decision_batch_worker(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
#     return [_zombie_ai_decision_worker(task) for task in tasks]


# def _zombie_ai_decision_worker(task: dict[str, Any]) -> dict[str, Any]:
#     zombie = task["zombie"]
#     players = task["players"]
#     walls = task["walls"]
#     spec = ZOMBIES.get(zombie["kind"])
#     decision: dict[str, Any] = {
#         "id": zombie["id"],
#         "generation": zombie.get("generation", 0),
#         "mode": zombie["mode"],
#         "target_player_id": zombie.get("target_player_id"),
#         "last_known_pos": zombie.get("last_known_pos"),
#         "search_timer": zombie.get("search_timer", 0.0),
#         "alertness": zombie.get("alertness", 0.0),
#     }
#     if not spec or not players:
#         return decision
#
#     visible = _zombie_ai_visible_player(zombie, players, walls, spec)
#     if visible:
#         decision.update(
#             {
#                 "mode": "chase",
#                 "target_player_id": visible["id"],
#                 "last_known_pos": {"x": visible["x"], "y": visible["y"]},
#                 "search_timer": SEARCH_DURATION,
#                 "alertness": 1.0,
#             }
#         )
#         return decision
#
#     if zombie["mode"] == "chase":
#         return decision
#
#     heard = _zombie_ai_heard_player(zombie, players, walls, spec)
#     if heard:
#         decision.update(
#             {
#                 "mode": "investigate",
#                 "target_player_id": heard["id"],
#                 "last_known_pos": {"x": heard["x"], "y": heard["y"]},
#                 "search_timer": max(float(zombie.get("search_timer", 0.0)), 2.2),
#                 "alertness": min(1.0, float(zombie.get("alertness", 0.0)) + 0.22 * spec.sensitivity),
#             }
#         )
#     return decision


# def _zombie_ai_visible_player(
#     zombie: dict[str, Any],
#     players: list[dict[str, Any]],
#     walls: tuple[tuple[float, float, float, float], ...],
#     spec: Any,
# ) -> dict[str, Any] | None:
#     best: dict[str, Any] | None = None
#     best_dist2 = float("inf")
#     sight2 = spec.sight_range * spec.sight_range
#     half_fov = math.radians(spec.fov_degrees * 0.5)
#     zx = float(zombie["x"])
#     zy = float(zombie["y"])
#     zfloor = int(zombie["floor"])
#     facing = float(zombie["facing"])
#     for player in players:
#         if int(player["floor"]) != zfloor:
#             continue
#         dx = float(player["x"]) - zx
#         dy = float(player["y"]) - zy
#         dist2 = dx * dx + dy * dy
#         if dist2 > sight2 or dist2 >= best_dist2:
#             continue
#         angle = math.atan2(dy, dx)
#         if abs(_worker_angle_delta(facing, angle)) > half_fov:
#             continue
#         if _worker_line_blocked(zx, zy, float(player["x"]), float(player["y"]), walls, sound=False):
#             continue
#         best = player
#         best_dist2 = dist2
#     return best


# def _zombie_ai_heard_player(
#     zombie: dict[str, Any],
#     players: list[dict[str, Any]],
#     walls: tuple[tuple[float, float, float, float], ...],
#     spec: Any,
# ) -> dict[str, Any] | None:
#     best: dict[str, Any] | None = None
#     best_dist2 = float("inf")
#     zx = float(zombie["x"])
#     zy = float(zombie["y"])
#     zfloor = int(zombie["floor"])
#     for player in players:
#         if int(player["floor"]) != zfloor or player.get("inside_building"):
#             continue
#         noise = float(player.get("noise", 0.0))
#         if noise <= 0.0:
#             continue
#         dx = float(player["x"]) - zx
#         dy = float(player["y"]) - zy
#         dist2 = dx * dx + dy * dy
#         hearing = spec.hearing_range + noise * spec.sensitivity
#         if dist2 > hearing * hearing or dist2 >= best_dist2:
#             continue
#         if _worker_line_blocked(zx, zy, float(player["x"]), float(player["y"]), walls, sound=True):
#             continue
#         best = player
#         best_dist2 = dist2
#     return best


# def _worker_line_blocked(
#     ax: float,
#     ay: float,
#     bx: float,
#     by: float,
#     walls: tuple[tuple[float, float, float, float], ...],
#     *,
#     sound: bool,
# ) -> bool:
#     for wall in walls:
#         if _worker_segment_rect_intersects(ax, ay, bx, by, wall):
#             if sound and wall[2] < 28 and wall[3] < 90:
#                 continue
#             return True
#     return False


# def _worker_segment_rect_intersects(
#     ax: float,
#     ay: float,
#     bx: float,
#     by: float,
#     rect: tuple[float, float, float, float],
# ) -> bool:
#     rx, ry, rw, rh = rect
#     rright = rx + rw
#     rbottom = ry + rh
#     if rx <= ax <= rright and ry <= ay <= rbottom:
#         return True
#     if rx <= bx <= rright and ry <= by <= rbottom:
#         return True
#     return (
#         _worker_segments_intersect(ax, ay, bx, by, rx, ry, rright, ry)
#         or _worker_segments_intersect(ax, ay, bx, by, rright, ry, rright, rbottom)
#         or _worker_segments_intersect(ax, ay, bx, by, rright, rbottom, rx, rbottom)
#         or _worker_segments_intersect(ax, ay, bx, by, rx, rbottom, rx, ry)
#     )


# def _worker_segments_intersect(
#     ax: float,
#     ay: float,
#     bx: float,
#     by: float,
#     cx: float,
#     cy: float,
#     dx: float,
#     dy: float,
# ) -> bool:
#     def orient(px: float, py: float, qx: float, qy: float, rx: float, ry: float) -> float:
#         return (qy - py) * (rx - qx) - (qx - px) * (ry - qy)
#
#     def on_segment(px: float, py: float, qx: float, qy: float, rx: float, ry: float) -> bool:
#         return min(px, rx) <= qx <= max(px, rx) and min(py, ry) <= qy <= max(py, ry)
#
#     o1 = orient(ax, ay, bx, by, cx, cy)
#     o2 = orient(ax, ay, bx, by, dx, dy)
#     o3 = orient(cx, cy, dx, dy, ax, ay)
#     o4 = orient(cx, cy, dx, dy, bx, by)
#     if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0):
#         return True
#     epsilon = 1e-7
#     return (
#         abs(o1) <= epsilon
#         and on_segment(ax, ay, cx, cy, bx, by)
#         or abs(o2) <= epsilon
#         and on_segment(ax, ay, dx, dy, bx, by)
#         or abs(o3) <= epsilon
#         and on_segment(cx, cy, ax, ay, dx, dy)
#         or abs(o4) <= epsilon
#         and on_segment(cx, cy, bx, by, dx, dy)
#     )


# def _worker_angle_delta(a: float, b: float) -> float:
#     return (b - a + math.pi) % math.tau - math.pi


class GameWorld:
    def __init__(
        self,
        seed: int | None = None,
        initial_zombies: int | None = None,
        max_zombies: int | None = None,
        difficulty_key: str = "medium",
        zombie_workers: int | None = None,
        zombie_ai_decision_rate: float = 6.0,
        zombie_ai_far_decision_rate: float = 2.0,
        zombie_ai_active_radius: float = 1800.0,
        zombie_ai_far_radius: float = 3200.0,
        zombie_ai_batch_size: int = 8,
        config: WorldConfig | None = None,
    ) -> None:
        if config is None:
            config = WorldConfig(
                seed=seed,
                initial_zombies=initial_zombies,
                max_zombies=max_zombies,
                difficulty_key=difficulty_key,
                zombie_workers=zombie_workers,
                zombie_ai_decision_rate=zombie_ai_decision_rate,
                zombie_ai_far_decision_rate=zombie_ai_far_decision_rate,
                zombie_ai_active_radius=zombie_ai_active_radius,
                zombie_ai_far_radius=zombie_ai_far_radius,
                zombie_ai_batch_size=zombie_ai_batch_size,
            )

        id_generator = IdGenerator()

        self.state = WorldState()
        self.state.buildings = make_buildings()

        lock = threading.RLock()
        geometry_cache_lock = threading.Lock()

        rng = random.Random(config.seed)
        difficulty = load_difficulty(config.difficulty_key)
        backpack_config = load_backpack_config()

        self.time = self.state.time

        self.players = self.state.players
        self.zombies = self.state.zombies
        self.soldiers = self.state.soldiers

        self.projectiles = self.state.projectiles
        self.grenades = self.state.grenades
        self.mines = self.state.mines
        self.poison_projectiles = self.state.poison_projectiles
        self.poison_pools = self.state.poison_pools

        self.loot = self.state.loot
        self.inputs = self.state.inputs
        self.sound_events = self.state.sound_events
        self._domain_events = self.state.domain_events
        self._grenade_cooldowns = self.state.grenade_cooldowns
        self.buildings = self.state.buildings

        self.initial_zombies = (
            difficulty.initial_zombies
            if config.initial_zombies is None
            else config.initial_zombies
        )
        self.max_zombies = (
            difficulty.max_zombies
            if config.max_zombies is None
            else config.max_zombies
        )

        self._zombie_ai_wall_cache: dict[int, tuple[int, tuple[tuple[float, float, float, float], ...]]] = {}
        self._zombie_rngs: dict[str, random.Random] = {}
        self._zombie_ai_next_at: dict[str, float] = {}
        self._zombie_ai_pending: dict[str, Future] = {}
        self._zombie_ai_futures: set[Future] = set()
        self._zombie_ai_generation: dict[str, int] = {}

        self._zombie_ai_decision_interval = 1.0 / max(
            0.25,
            float(config.zombie_ai_decision_rate),
        )
        self._zombie_ai_far_decision_interval = 1.0 / max(
            0.1,
            float(config.zombie_ai_far_decision_rate),
        )
        self._zombie_ai_active_radius = max(
            240.0,
            float(config.zombie_ai_active_radius),
        )
        self._zombie_ai_far_radius = max(
            self._zombie_ai_active_radius,
            float(config.zombie_ai_far_radius),
        )
        self._zombie_ai_batch_size = max(1, int(config.zombie_ai_batch_size))

        self.zombie_pathfinder = GridPathfinder(cell_size=96)
        self._zombie_path_cache: dict[str, tuple[Vec2, list[Vec2]]] = {}

        self.zombie_ai_registry = ZOMBIE_AI_REGISTRY

        self.soldier_ai_registry = SOLDIER_AI_REGISTRY

        self.command_router = CommandRouter()
        self.command_router.register("respawn", RespawnHandler())
        self.command_router.register("select_slot", SelectSlotHandler())
        self.command_router.register("use_medkit", UseMedkitHandler())
        self.command_router.register("reload", ReloadHandler())
        self.command_router.register("pickup", PickupHandler())

        self.command_router.register(
            "interact",
            InteractHandler(
                interact=self._interact,
            ),
        )

        self.command_router.register("toggle_utility", ToggleUtilityHandler())
        self.command_router.register("equip_armor", EquipArmorHandler())
        self.command_router.register("inventory_action", InventoryActionHandler())
        self.command_router.register("craft", CraftHandler())
        self.command_router.register("repair", RepairHandler())
        self.command_router.register("throw_grenade", ThrowGrenadeHandler())

        geometry_service = GeometryService(
            buildings=self.buildings,
            cache_lock=geometry_cache_lock,
        )

        building_service = BuildingService(
            buildings=self.buildings,
        )

        movement_service = MovementService(
            geometry=geometry_service,
            buildings=building_service,
        )

        executor_config = build_executor_config(
            requested_process_workers=config.zombie_workers,
            enable_process_pool=config.enable_process_pool,
            enable_thread_pool=config.enable_thread_pool,
        )

        process_pool = ProcessPoolService(executor_config.process_workers)
        thread_pool = ThreadPoolService(executor_config.thread_workers)

        damage_service = DamageService(
            players=self.players,
            zombies=self.zombies,
            soldiers=self.soldiers,
            difficulty=difficulty,
            rng=rng,
            drop_from_zombie=self._drop_from_zombie,
            zombie_ai_generation=self._zombie_ai_generation,
            zombie_ai_pending=self._zombie_ai_pending,
            zombie_ai_next_at=self._zombie_ai_next_at,
            get_time=lambda: self.time,
        )

        sound_service = SoundService(
            state=self.state,
        )

        loot_service = LootService(
            state=self.state,
            rng=rng,
        )

        spawn_service = SpawnService(
            state=self.state,
            rng=rng,
            ids=id_generator,
            geometry=geometry_service,
            difficulty=difficulty,
            max_zombies=self.max_zombies,
        )

        respawn_service = RespawnService(
            state=self.state,
            rng=rng,
            geometry=geometry_service,
        )

        weapon_runtime_service = WeaponRuntimeService()
        player_combat_service = PlayerCombatService(
            state=self.state,
            rng=rng,
        )

        inventory_service = InventoryService(
            state=self.state,
            rng=rng,
            backpack_config=backpack_config,
            loot=loot_service,
            buildings=building_service,
            ids=id_generator,
        )

        self.ctx = WorldContext(
            rng=rng,
            lock=lock,
            geometry_cache_lock=geometry_cache_lock,
            ids=id_generator,
            difficulty=difficulty,
            backpack_config=backpack_config,
            process_pool=process_pool,
            thread_pool=thread_pool,
            geometry=geometry_service,
            buildings=building_service,
            movement=movement_service,
            damage=damage_service,
            sounds=sound_service,
            loot=loot_service,
            max_zombies=self.max_zombies,
            spawning=spawn_service,
            respawn=respawn_service,
            weapons=weapon_runtime_service,
            player_combat=player_combat_service,
            inventory=inventory_service,
        )

        self.systems = SystemScheduler([
            PlayerUpdateSystem(
                update_notice=self._update_notice,
                update_healing=self._update_healing,
                player_noise=self._player_noise,
                interact=self._interact,
                respawn_player=self.respawn_player,
            ),
            ProjectileSystem(),
            ExplosiveSystem(),
            PoisonSystem(),
            ZombieSpawnSystem(),
            LootSpawnSystem(),
            SoundSystem(),
        ])

        self._lock = self.ctx.lock
        self._geometry_cache_lock = self.ctx.geometry_cache_lock
        self.rng = self.ctx.rng
        self.difficulty = self.ctx.difficulty
        self.backpack_config = self.ctx.backpack_config

        self._zombie_executor = self.ctx.process_pool.executor
        self._zombie_pool_workers = executor_config.process_workers
        self._zombie_ai_max_pending_batches = max(2, executor_config.process_workers * 2)

        self._prime_map()

    def close(self) -> None:
        self.ctx.process_pool.close()
        self.ctx.thread_pool.close()

        self._zombie_executor = None
        self._zombie_ai_pending.clear()
        self._zombie_ai_futures.clear()

    def _id(self, prefix: str) -> str:
        return self.ctx.ids.next(prefix)

    def _prime_map(self) -> None:
        start_count = min(self.initial_zombies, self.max_zombies) if self.max_zombies > 0 else 0
        for _ in range(start_count):
            self.spawn_zombie()
        for weapon in ("smg", "shotgun", "rifle"):
            self.spawn_loot("weapon", weapon, 1)
        for armor in ("light", "tactical", "heavy"):
            self.spawn_loot("armor", armor, 1)
        for _ in range(self._loot_count(24, minimum=8)):
            self.spawn_loot("ammo", self.rng.choice(list(WEAPONS)), self.rng.randint(12, 34))
        for _ in range(self._loot_count(10, minimum=2)):
            self.spawn_loot("medkit", "medkit", 1)
        for building in self.buildings.values():
            for _ in range(self._loot_count(14, minimum=6)):
                pos = Vec2(
                    self.rng.uniform(building.bounds.x + 80, building.bounds.x + building.bounds.w - 80),
                    self.rng.uniform(building.bounds.y + 90, building.bounds.y + building.bounds.h - 90),
                )
                floor = self.rng.choice([building.min_floor, building.min_floor, 0, 0, 1, 2])
                if not self.ctx.geometry.blocked_at(pos, 16, floor):
                    loot_table = BASEMENT_LOOT if floor == building.min_floor else HOUSE_LOOT
                    item_key = self.rng.choices([item[0] for item in loot_table], weights=[item[2] for item in loot_table])[0]
                    self._spawn_loot_at(pos, "item", item_key, self.rng.randint(1, 3), floor=floor)
        self._spawn_initial_soldiers()

    def _spawn_initial_soldiers(self) -> None:
        self.ctx.spawning.spawn_initial_soldiers()

    def spawn_soldier(
            self,
            kind: str,
            pos: Vec2,
            guard_point: Vec2 | None = None,
    ) -> SoldierState:
        return self.ctx.spawning.spawn_soldier(
            kind=kind,
            pos=pos,
            guard_point=guard_point,
        )

    def add_player(self, name: str, player_id: str | None = None) -> PlayerState:
        with self._lock:
            return self._add_player_unlocked(name, player_id)

    def _add_player_unlocked(self, name: str, player_id: str | None = None) -> PlayerState:
        player_id = player_id or self._id("p")
        player = PlayerState(
            id=player_id,
            name=_clean_player_name(name),
            pos=self._random_open_pos(centered=True),
            kills_by_kind={kind: 0 for kind in ZOMBIES},
            backpack=[None] * self.backpack_config.slots,
        )
        weapon_key = self.backpack_config.starting_weapon.key
        if weapon_key not in WEAPONS:
            weapon_key = "pistol"
        weapon_spec = WEAPONS[weapon_key]
        player.weapons[weapon_spec.slot] = WeaponRuntime(
            weapon_key,
            weapon_spec.magazine_size,
            self.backpack_config.starting_weapon.reserve_ammo,
            rarity="common",
        )
        player.quick_items = {slot: None for slot in SLOTS}
        for item in self.backpack_config.starting_items:
            self._add_item(player, item.key, item.amount)
        self.players[player_id] = player
        self.inputs[player_id] = InputCommand(player_id=player_id, aim_x=player.pos.x + 1, aim_y=player.pos.y)
        self._grenade_cooldowns[player_id] = 0.0
        return player

    def remove_player(self, player_id: str) -> None:
        with self._lock:
            self.players.pop(player_id, None)
            self.inputs.pop(player_id, None)
            self._grenade_cooldowns.pop(player_id, None)

    def rename_player(self, player_id: str, name: str) -> None:
        with self._lock:
            player = self.players.get(player_id)
            if player:
                player.name = _clean_player_name(name)

    def set_input(self, command: InputCommand) -> None:
        with self._lock:
            if command.player_id in self.players:
                self.inputs[command.player_id] = command

    def apply_client_command(self, command: ClientCommand) -> tuple[bool, str]:
        with self._lock:
            player = self.players.get(command.player_id)
            if not player:
                return False, "player_missing"
            ok, reason = self._apply_client_command_unlocked(player.id, command)
            self._push_command_event(command, ok, reason)
            return ok, reason

    def drain_domain_events(self) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._domain_events)
            self._domain_events.clear()
            return events

    def _push_command_event(self, command: ClientCommand, ok: bool, reason: str) -> None:
        event_kind = _COMMAND_EVENT_NAMES.get(command.kind, command.kind)
        self._domain_events.append(
            {
                "kind": event_kind if ok else f"{command.kind}_rejected",
                "player_id": command.player_id,
                "command_id": command.command_id,
                "command_kind": command.kind,
                "ok": ok,
                "reason": reason,
                "time": round(self.time, 3),
            }
        )

    def _zombie_path_next_point(self, zombie: ZombieState, target: Vec2) -> Vec2:
        # если цель видна по прямой — pathfinding не нужен
        if not self.ctx.geometry.line_blocked(zombie.pos, target, zombie.floor):
            self._zombie_path_cache.pop(zombie.id, None)
            return target

        cached = self._zombie_path_cache.get(zombie.id)

        if cached:
            cached_target, path = cached
            if cached_target.distance_to(target) < 96 and path:
                while path and zombie.pos.distance_to(path[0]) < 48:
                    path.pop(0)

                if path:
                    return path[0]

        path = self.zombie_pathfinder.find_path(
            start=zombie.pos,
            goal=target,
            walls=self._closed_walls(zombie.floor),
            map_width=MAP_WIDTH,
            map_height=MAP_HEIGHT,
        )

        if not path:
            return target

        self._zombie_path_cache[zombie.id] = (target.copy(), path)

        return path[0]

    def _apply_client_command_unlocked(
        self,
        player_id: str,
        command: ClientCommand,
    ) -> tuple[bool, str]:
        player = self.players.get(player_id)

        if not player:
            return False, "player_missing"

        if self.command_router.has_handler(command.kind):
            return self.command_router.handle(
                self.state,
                self.ctx,
                player,
                command,
            )

        return self._apply_client_command_legacy(player, command)

    def _apply_client_command_legacy(
            self,
            player: PlayerState,
            command: ClientCommand,
    ) -> tuple[bool, str]:
        if not player.alive:
            return False, "player_dead"
        return False, "unknown_command"

    def update(self, dt: float) -> None:
        with self._lock:
            self._update_unlocked(dt)

    def _update_unlocked(self, dt: float) -> None:
        self.time += dt
        self.state.time = self.time

        if dt <= 0.0:
            return

        self.systems.update_all(self.state, self.ctx, dt)

        self._update_zombies(dt)
        self._update_soldiers(dt)

    def respawn_player(self, player_id: str) -> None:
        player = self.players.get(player_id)

        if not player:
            return

        self.ctx.respawn.respawn(player)

    def _update_players(self, dt: float) -> None:
        for player in self.players.values():
            command = self.inputs.get(player.id)
            if not command:
                continue
            self._grenade_cooldowns[player.id] = max(0.0, self._grenade_cooldowns.get(player.id, 0.0) - dt)
            self._update_notice(player, dt)
            if not player.alive:
                if command.respawn:
                    self.respawn_player(player.id)
                continue

            if command.active_slot and command.active_slot in SLOTS:
                player.active_slot = command.active_slot
            if command.equip_armor and command.equip_armor in ARMORS:
                self._equip_armor(player, command.equip_armor)
            if command.use_medkit and player.medkits > 0 and player.health < 100:
                player.medkits -= 1
                player.health = min(100, player.health + 42)
            if command.inventory_action:
                self._apply_inventory_action(player, command.inventory_action)
            if command.craft_key:
                self._craft(player, command.craft_key)
            if command.repair_slot:
                self._repair_armor(player, command.repair_slot)
            self._update_healing(player, dt)
            player.melee_cooldown = max(0.0, player.melee_cooldown - dt)

            player.angle = player.pos.angle_to(Vec2(command.aim_x, command.aim_y))
            movement = Vec2(command.move_x, command.move_y).normalized()
            player.sneaking = command.sneak and movement.length() > 0
            player.sprinting = command.sprint and not player.sneaking and movement.length() > 0
            speed = player.speed * (0.48 if player.sneaking else SPRINT_MULTIPLIER if player.sprinting else 1.0)
            weapon = player.active_weapon()
            meleeing = command.alt_attack and weapon is None
            player.noise = self._player_noise(player, movement, command.shooting, meleeing)

            old_inside_building = player.inside_building
            self.ctx.movement.move_circle(player.pos, movement.scaled(speed * dt), PLAYER_RADIUS, player.floor)
            player.pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
            player.inside_building = self.ctx.buildings.point_building(player.pos)

            if player.noise > 0.0 and not player.inside_building:
                self._emit_sound(
                    pos=player.pos,
                    floor=player.floor,
                    radius=player.noise,
                    source_player_id=player.id,
                    kind="movement",
                    intensity=0.45 if player.sprinting else 0.25,
                )

            for weapon in player.weapons.values():
                weapon.cooldown = max(0.0, weapon.cooldown - dt)
                if weapon.reload_left > 0.0:
                    weapon.reload_left = max(0.0, weapon.reload_left - dt)
                    if weapon.reload_left == 0.0:
                        self._finish_reload(weapon)

            if command.pickup:
                self._pickup_nearby(player)
            interacted = False
            if command.interact:
                interacted = self._interact(player)
            if command.toggle_utility and not interacted:
                self._toggle_weapon_utility(player)
            if command.reload:
                self._start_reload(player)
            if command.shooting:
                self._shoot(player)
            if command.alt_attack:
                self._unarmed_attack(player)
            if command.throw_grenade:
                self._throw_grenade(player)

    def _emit_sound(
            self,
            pos: Vec2,
            floor: int,
            radius: float,
            source_player_id: str | None = None,
            kind: str = "generic",
            intensity: float = 1.0,
    ) -> None:
        self.ctx.sounds.emit(
            pos=pos,
            floor=floor,
            radius=radius,
            source_player_id=source_player_id,
            kind=kind,
            intensity=intensity,
        )

    def _player_noise(self, player: PlayerState, movement: Vec2, shooting: bool, meleeing: bool = False) -> float:
        if player.sneaking:
            return 0.0
        move_noise = 0.0
        if movement.length() > 0:
            move_noise = SPRINT_NOISE if player.sprinting else WALK_NOISE

        melee_noise = UNARMED_MELEE_NOISE if meleeing else 0.0
        return max(move_noise, melee_noise)

    def _update_projectiles(self, dt: float) -> None:
        dead_projectiles: list[str] = []
        for projectile in self.projectiles.values():
            projectile.life -= dt
            projectile.pos.add(projectile.velocity.scaled(dt))
            if (
                projectile.life <= 0.0
                or projectile.pos.x < 0
                or projectile.pos.y < 0
                or projectile.pos.x > MAP_WIDTH
                or projectile.pos.y > MAP_HEIGHT
                or self.ctx.geometry.blocked_at(projectile.pos, projectile.radius, projectile.floor)
            ):
                dead_projectiles.append(projectile.id)
                continue

            for zombie in list(self.zombies.values()):
                if zombie.floor != projectile.floor:
                    continue
                spec = ZOMBIES[zombie.kind]
                if projectile.pos.distance_to(zombie.pos) <= spec.radius + projectile.radius:
                    self._damage_zombie(zombie, projectile.damage, projectile.owner_id)
                    dead_projectiles.append(projectile.id)
                    break

            for soldier in list(self.soldiers.values()):
                if soldier.floor != projectile.floor:
                    continue

                if projectile.owner_id == soldier.id:
                    continue

                spec = SOLDIERS[soldier.kind]
                if projectile.pos.distance_to(soldier.pos) <= spec.radius + projectile.radius:
                    self._damage_soldier(soldier, projectile.damage, projectile.owner_id)
                    dead_projectiles.append(projectile.id)
                    break

            for player in list(self.players.values()):
                if not player.alive:
                    continue

                if player.floor != projectile.floor:
                    continue

                if projectile.owner_id == player.id:
                    continue

                if projectile.pos.distance_to(player.pos) <= PLAYER_RADIUS + projectile.radius:
                    self._damage_player(player, projectile.damage)
                    dead_projectiles.append(projectile.id)
                    break

        for projectile_id in dead_projectiles:
            self.projectiles.pop(projectile_id, None)

    def _update_grenades(self, dt: float) -> None:
        detonated: list[str] = []
        for grenade in self.grenades.values():
            spec = GRENADE_SPECS.get(grenade.kind, DEFAULT_GRENADE)
            grenade.timer -= dt
            grenade.velocity = grenade.velocity.scaled(0.92)
            grenade.pos.add(grenade.velocity.scaled(dt))
            hit_wall = self.ctx.geometry.blocked_at(grenade.pos, grenade.radius, grenade.floor)
            if hit_wall:
                grenade.velocity = grenade.velocity.scaled(-0.22)
                grenade.pos.add(grenade.velocity.scaled(dt))
            if grenade.timer <= 0.0 or (spec.contact and (hit_wall or self._grenade_touched_actor(grenade))):
                detonated.append(grenade.id)
        for grenade_id in detonated:
            grenade = self.grenades.pop(grenade_id, None)
            if grenade:
                self._detonate_grenade(grenade)

    def _grenade_touched_actor(self, grenade: GrenadeState) -> bool:
        for zombie in self.zombies.values():
            if zombie.floor != grenade.floor:
                continue
            spec = ZOMBIES[zombie.kind]
            if grenade.pos.distance_to(zombie.pos) <= spec.radius + grenade.radius:
                return True
        for player in self.players.values():
            if player.alive and player.floor == grenade.floor and grenade.pos.distance_to(player.pos) <= PLAYER_RADIUS + grenade.radius:
                return True
        return False

    def _update_mines(self, dt: float) -> None:
        detonated: list[str] = []
        for mine in self.mines.values():
            mine.rotation = (mine.rotation + dt * (1.6 if mine.armed else 0.55)) % math.tau
            if not mine.armed:
                owner = self.players.get(mine.owner_id)
                if (
                    not owner
                    or not owner.alive
                    or owner.floor != mine.floor
                    or owner.pos.distance_to(mine.pos) > mine.trigger_radius + PLAYER_RADIUS
                ):
                    mine.armed = True
                continue
            if self._mine_has_trigger(mine):
                detonated.append(mine.id)
        for mine_id in detonated:
            mine = self.mines.pop(mine_id, None)
            if mine:
                self._detonate_mine(mine)

    def _mine_has_trigger(self, mine: MineState) -> bool:
        for zombie in self.zombies.values():
            if zombie.floor != mine.floor:
                continue
            if (
                zombie.pos.distance_to(mine.pos) <= mine.trigger_radius + ZOMBIES[zombie.kind].radius * 0.35
                and not self.ctx.geometry.line_blocked(mine.pos, zombie.pos, mine.floor)
            ):
                return True
        for player in self.players.values():
            if not player.alive or player.floor != mine.floor:
                continue
            if (
                player.pos.distance_to(mine.pos) <= mine.trigger_radius + PLAYER_RADIUS * 0.25
                and not self.ctx.geometry.line_blocked(mine.pos, player.pos, mine.floor)
            ):
                return True
        return False

    def _update_poison_projectiles(self, dt: float) -> None:
        expired: list[str] = []
        for spit in self.poison_projectiles.values():
            spit.life -= dt
            old_pos = spit.pos.copy()
            spit.pos.add(spit.velocity.scaled(dt))
            hit_wall = self.ctx.geometry.blocked_at(spit.pos, spit.radius, spit.floor)
            reached_target = old_pos.distance_to(spit.target) <= spit.pos.distance_to(spit.target) or spit.pos.distance_to(spit.target) <= 18
            hit_player = None
            for player in self.players.values():
                if player.alive and player.floor == spit.floor and player.pos.distance_to(spit.pos) <= PLAYER_RADIUS + spit.radius:
                    hit_player = player
                    break
            if hit_player:
                self._apply_poison(hit_player, damage_per_tick=3)
                expired.append(spit.id)
            elif hit_wall or reached_target or spit.life <= 0.0:
                self._spawn_poison_pool(spit.pos if not reached_target else spit.target, spit.floor)
                expired.append(spit.id)
        for spit_id in expired:
            self.poison_projectiles.pop(spit_id, None)

    def _update_poison_pools(self, dt: float) -> None:
        expired: list[str] = []
        for pool in self.poison_pools.values():
            pool.timer -= dt
            if pool.timer <= 0.0:
                expired.append(pool.id)
                continue
            for player in self.players.values():
                if player.alive and player.floor == pool.floor and player.pos.distance_to(pool.pos) <= pool.radius + PLAYER_RADIUS * 0.35:
                    self._apply_poison(player, damage_per_tick=2)
        for pool_id in expired:
            self.poison_pools.pop(pool_id, None)

    def _update_soldiers(self, dt: float) -> None:
        for soldier in list(self.soldiers.values()):
            if not soldier.alive:
                self.soldiers.pop(soldier.id, None)
                continue

            ai = self.soldier_ai_registry.get(soldier.kind)
            if not ai:
                continue

            ctx = self._make_soldier_context(soldier, dt, self.rng)
            result = ai.update(ctx)

            self._apply_soldier_result(soldier, result)

    def _soldier_move_toward(self, soldier: SoldierState, target: Vec2, dt: float, rng: random.Random) -> None:
        spec = SOLDIERS[soldier.kind]

        direction = Vec2(target.x - soldier.pos.x, target.y - soldier.pos.y)

        if direction.length() <= 0.01:
            return

        soldier.facing = math.atan2(direction.y, direction.x)

        step = direction.normalized().scaled(spec.speed * dt)

        self.ctx.movement.move_circle(
            soldier.pos,
            step,
            spec.radius,
            soldier.floor,
        )

        soldier.pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)

    def _soldier_targets(self) -> tuple[ActorTarget, ...]:
        targets: list[ActorTarget] = []

        for zombie in self.zombies.values():
            if not zombie.health > 0:
                continue

            spec = ZOMBIES[zombie.kind]

            targets.append(
                ActorTarget(
                    id=zombie.id,
                    kind="zombie",
                    pos=zombie.pos.copy(),
                    floor=zombie.floor,
                    alive=True,
                    radius=spec.radius,
                    health=zombie.health,
                    inside_building=zombie.inside_building,
                )
            )

        for player in self.players.values():
            if not player.alive:
                continue

            targets.append(
                ActorTarget(
                    id=player.id,
                    kind="player",
                    pos=player.pos.copy(),
                    floor=player.floor,
                    alive=player.alive,
                    sprinting=player.sprinting,
                    radius=PLAYER_RADIUS,
                    health=player.health,
                    inside_building=player.inside_building,
                )
            )

        return tuple(targets)

    def _update_poisoned_players(self, dt: float) -> None:
        for player in self.players.values():
            if player.poison_left <= 0.0 or not player.alive:
                player.poison_left = 0.0
                player.poison_tick = 0.0
                player.poison_damage = 0
                continue
            player.poison_left = max(0.0, player.poison_left - dt)
            player.poison_tick -= dt
            if player.poison_tick <= 0.0:
                player.poison_tick = 1.0
                self._apply_poison_damage(player, max(1, player.poison_damage))

    def _spawn_poison_pool(self, pos: Vec2, floor: int) -> None:
        pool_id = self._id("acid")
        pool_pos = pos.copy()
        pool_pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
        self.poison_pools[pool_id] = PoisonPoolState(pool_id, pool_pos, floor=floor, timer=5.0)

    def _apply_poison(self, player: PlayerState, damage_per_tick: int) -> None:
        if player.poison_left <= 0.0:
            player.poison_tick = 1.0
        player.poison_left = max(player.poison_left, 5.0)
        if player.poison_tick <= 0.0:
            player.poison_tick = 1.0
        player.poison_damage = max(player.poison_damage, damage_per_tick)

    def _apply_poison_damage(self, player: PlayerState, damage: int) -> None:
        player.healing_left = 0.0
        player.healing_pool = 0.0
        player.healing_rate = 0.0
        player.health -= damage
        if player.health <= 0:
            player.health = 0
            player.alive = False

    def _update_zombies(self, dt: float) -> None:
        living_players = tuple(player for player in self.players.values() if player.alive)
        zombies = list(self.zombies.values())
        if not zombies:
            self._drain_zombie_ai_decisions()
            return
        active_ids = {zombie.id for zombie in zombies}
        for zombie_id in list(self._zombie_rngs):
            if zombie_id not in active_ids:
                self._zombie_rngs.pop(zombie_id, None)
        for zombie_id in list(self._zombie_ai_next_at):
            if zombie_id not in active_ids:
                self._zombie_ai_next_at.pop(zombie_id, None)
        for zombie_id in list(self._zombie_ai_pending):
            if zombie_id not in active_ids:
                self._zombie_ai_pending.pop(zombie_id, None)
        for zombie_id in list(self._zombie_ai_generation):
            if zombie_id not in active_ids:
                self._zombie_ai_generation.pop(zombie_id, None)

        if self._zombie_executor and zombies:
            self._update_zombies_process_pool(zombies, living_players, dt)
            return

        for zombie in zombies:
            if zombie.id not in self.zombies:
                continue
            result = self._advance_zombie_actor(zombie, dt, living_players, self._zombie_rng(zombie.id))
            self._apply_zombie_result(result)

    def _zombie_process_env_snapshot(self, zombies: list[ZombieState]) -> Any:
        floors = {z.floor for z in zombies}
        return build_process_env(
            self.difficulty,
            self.buildings,
            self.sound_events,
            floors,
        )

    def _apply_zombie_dict_to_live(self, live: ZombieState, data: dict[str, Any]) -> None:
        updated = ZombieState.from_dict(data)
        for f in fields(ZombieState):
            setattr(live, f.name, getattr(updated, f.name))

    def _update_zombies_process_pool(
        self,
        zombies: list[ZombieState],
        living_players: tuple[PlayerState, ...],
        dt: float,
    ) -> None:
        env = self._zombie_process_env_snapshot(zombies)
        player_payload = tuple(p.to_dict() for p in living_players)
        tasks: list[tuple[Any, ...]] = []
        for zombie in zombies:
            if zombie.id not in self.zombies:
                continue
            seed = self.rng.randrange(1, 2**31 - 1)
            tasks.append(
                (
                    env,
                    zombie.to_dict(),
                    player_payload,
                    dt,
                    self.time,
                    seed,
                )
            )
        if not tasks:
            return
        try:
            chunksize = max(1, len(tasks) // max(1, self._zombie_pool_workers * 2))
            results = self._zombie_executor.map(run_one_zombie_task, tasks, chunksize=chunksize)
        except Exception:
            for zombie in zombies:
                if zombie.id not in self.zombies:
                    continue
                result = self._advance_zombie_actor(zombie, dt, living_players, self._zombie_rng(zombie.id))
                self._apply_zombie_result(result)
            return

        for row in results:
            zid = str(row.get("id", ""))
            live = self.zombies.get(zid)
            if not live:
                continue
            zdata = row.get("zombie")
            if isinstance(zdata, dict):
                self._apply_zombie_dict_to_live(live, zdata)
            hits = row.get("player_hits") or []
            spits = row.get("poison_spits") or []
            self._apply_zombie_result(
                _ZombieUpdateResult(zombie=live, player_hits=list(hits), poison_spits=list(spits))
            )

    def _drain_zombie_ai_decisions(self) -> None:
        for future in list(self._zombie_ai_futures):
            if not future.done():
                continue
            self._zombie_ai_futures.discard(future)
            for zombie_id, pending in list(self._zombie_ai_pending.items()):
                if pending is future:
                    self._zombie_ai_pending.pop(zombie_id, None)
            try:
                decisions = future.result()
            except Exception:
                continue
            for decision in decisions:
                self._apply_zombie_ai_decision(decision)

    # def _schedule_zombie_ai_decisions(self, zombies: list[ZombieState], living_players: tuple[PlayerState, ...]) -> None:
    #     if not living_players:
    #         return
    #     if self._zombie_executor and len(self._zombie_ai_futures) >= self._zombie_ai_max_pending_batches:
    #         return
    #     tasks: list[dict[str, Any]] = []
    #     for zombie in zombies:
    #         if len(tasks) >= self._zombie_ai_batch_size:
    #             break
    #         if zombie.id in self._zombie_ai_pending:
    #             continue
    #         if self.time < self._zombie_ai_next_at.get(zombie.id, 0.0):
    #             continue
    #         candidates, interval = self._zombie_ai_candidates(zombie, living_players)
    #         self._zombie_ai_next_at[zombie.id] = self.time + interval * self.rng.uniform(0.75, 1.35)
    #         if not candidates:
    #             continue
    #         tasks.append(self._zombie_ai_task(zombie, candidates))
    #     if not tasks:
    #         return
    #     if not self._zombie_executor:
    #         for decision in _zombie_ai_decision_batch_worker(tasks):
    #             self._apply_zombie_ai_decision(decision)
    #         return
    #     try:
    #         future = self._zombie_executor.submit(_zombie_ai_decision_batch_worker, tasks)
    #     except Exception:
    #         for decision in _zombie_ai_decision_batch_worker(tasks):
    #             self._apply_zombie_ai_decision(decision)
    #         return
    #     self._zombie_ai_futures.add(future)
    #     for task in tasks:
    #         self._zombie_ai_pending[str(task["zombie"]["id"])] = future

    # def _zombie_ai_candidates(
    #     self,
    #     zombie: ZombieState,
    #     living_players: tuple[PlayerState, ...],
    # ) -> tuple[tuple[PlayerState, ...], float]:
    #     spec = ZOMBIES[zombie.kind]
    #     active_radius2 = self._zombie_ai_active_radius * self._zombie_ai_active_radius
    #     far_radius = max(self._zombie_ai_far_radius, spec.sight_range + 160.0, spec.hearing_range + SPRINT_NOISE * spec.sensitivity)
    #     far_radius2 = far_radius * far_radius
    #     target_player_id = zombie.target_player_id
    #     active = zombie.mode != "patrol"
    #     candidates: list[tuple[float, PlayerState]] = []
    #     for player in living_players:
    #         if player.floor != zombie.floor:
    #             continue
    #         dx = player.pos.x - zombie.pos.x
    #         dy = player.pos.y - zombie.pos.y
    #         dist2 = dx * dx + dy * dy
    #         noisy_radius = spec.hearing_range + max(0.0, player.noise) * spec.sensitivity + 128.0
    #         noisy_radius2 = noisy_radius * noisy_radius
    #         is_target = target_player_id == player.id
    #         if dist2 <= far_radius2 or (player.noise > 0.0 and dist2 <= noisy_radius2) or is_target:
    #             candidates.append((dist2, player))
    #             if dist2 <= active_radius2 or player.noise > 0.0 or is_target:
    #                 active = True
    #     if not candidates:
    #         return (), self._zombie_ai_far_decision_interval
    #     candidates.sort(key=lambda item: item[0])
    #     interval = self._zombie_ai_decision_interval if active else self._zombie_ai_far_decision_interval
    #     return tuple(player for _, player in candidates[:8]), interval

    # def _zombie_ai_task(self, zombie: ZombieState, players: tuple[PlayerState, ...]) -> dict[str, Any]:
    #     return {
    #         "zombie": {
    #             "id": zombie.id,
    #             "generation": self._zombie_ai_generation.get(zombie.id, 0),
    #             "kind": zombie.kind,
    #             "x": zombie.pos.x,
    #             "y": zombie.pos.y,
    #             "floor": zombie.floor,
    #             "facing": zombie.facing,
    #             "mode": zombie.mode,
    #             "target_player_id": zombie.target_player_id,
    #             "last_known_pos": zombie.last_known_pos.to_dict() if zombie.last_known_pos else None,
    #             "search_timer": zombie.search_timer,
    #             "alertness": zombie.alertness,
    #         },
    #         "players": [
    #             {
    #                 "id": player.id,
    #                 "x": player.pos.x,
    #                 "y": player.pos.y,
    #                 "floor": player.floor,
    #                 "noise": player.noise,
    #                 "inside_building": player.inside_building,
    #             }
    #             for player in players
    #         ],
    #         "walls": self._zombie_ai_wall_payload(zombie.floor),
    #     }

    # def _zombie_ai_wall_payload(self, floor: int) -> tuple[tuple[float, float, float, float], ...]:
    #     cached = self._zombie_ai_wall_cache.get(floor)
    #     if cached and cached[0] == self._geometry_version:
    #         return cached[1]
    #     walls = tuple((wall.x, wall.y, wall.w, wall.h) for wall in self._closed_walls(floor))
    #     self._zombie_ai_wall_cache[floor] = (self._geometry_version, walls)
    #     return walls

    # def _apply_zombie_ai_decision(self, decision: dict[str, Any]) -> None:
    #     zombie = self.zombies.get(str(decision.get("id", "")))
    #     if not zombie:
    #         return
    #     generation = int(decision.get("generation", -1))
    #     if generation != self._zombie_ai_generation.get(zombie.id, 0):
    #         return
    #     mode = str(decision.get("mode", zombie.mode))
    #     if mode not in {"chase", "investigate"}:
    #         return
    #     zombie.mode = mode
    #     zombie.target_player_id = decision.get("target_player_id")
    #     last_known = decision.get("last_known_pos")
    #     if isinstance(last_known, dict):
    #         zombie.last_known_pos = Vec2(float(last_known.get("x", zombie.pos.x)), float(last_known.get("y", zombie.pos.y)))
    #     zombie.search_timer = max(zombie.search_timer, float(decision.get("search_timer", zombie.search_timer)))
    #     zombie.alertness = max(zombie.alertness, float(decision.get("alertness", zombie.alertness)))

    def _zombie_rng(self, zombie_id: str) -> random.Random:
        rng = self._zombie_rngs.get(zombie_id)
        if rng is None:
            rng = random.Random(self.rng.randrange(1, 2**63))
            self._zombie_rngs[zombie_id] = rng
        return rng

    # def _clone_zombie(self, zombie: ZombieState) -> ZombieState:
    #     return replace(
    #         zombie,
    #         pos=zombie.pos.copy(),
    #         last_known_pos=zombie.last_known_pos.copy() if zombie.last_known_pos else None,
    #         waypoint=zombie.waypoint.copy() if zombie.waypoint else None,
    #     )

    def _advance_zombie_actor(
        self,
        zombie: ZombieState,
        dt: float,
        living_players: tuple[PlayerState, ...],
        rng: random.Random,
    ) -> _ZombieUpdateResult:
        if not living_players and zombie.mode != "patrol":
            zombie.mode = "patrol"
            zombie.target_player_id = None
            zombie.last_known_pos = None
            zombie.waypoint = None
            zombie.alertness = 0.0

        ai = self.zombie_ai_registry.get(zombie.kind)

        if not ai:
            ai = self.zombie_ai_registry["walker"]

        ctx = self._make_zombie_context(zombie, dt, living_players, rng)
        ai_result = ai.update(ctx)

        zombie.inside_building = self.ctx.buildings.point_building(zombie.pos)

        return _ZombieUpdateResult(
            zombie=zombie,
            player_hits=ai_result.player_hits,
            soldier_hits=ai_result.soldier_hits,
            poison_spits=ai_result.poison_spits,
        )

    # def _update_chase_movement(
    #     self,
    #     zombie: ZombieState,
    #     dt: float,
    #     players: tuple[PlayerState, ...],
    #     rng: random.Random,
    #     player_hits: list[tuple[str, int]],
    #     poison_spits: list[_PoisonSpitEvent],
    # ) -> None:
    #     target = self._find_player(players, zombie.target_player_id)
    #     destination = zombie.last_known_pos
    #     if target and target.alive and target.floor == zombie.floor:
    #         if target.inside_building:
    #             entry = self.ctx.buildings.building_entry_target(target.inside_building)
    #             if entry:
    #                 destination = entry
    #         elif destination is None:
    #             destination = target.pos.copy()
    #         if zombie.kind == "leaper":
    #             self._try_poison_spit(zombie, target, rng, poison_spits)
    #         if zombie.pos.distance_to(target.pos) <= ZOMBIE_TARGET_RADIUS + ZOMBIES[zombie.kind].radius:
    #             if not self.ctx.geometry.line_blocked(zombie.pos, target.pos, zombie.floor):
    #                 self._try_zombie_attack(zombie, target, player_hits)
    #
    #     if destination:
    #         if zombie.pos.distance_to(destination) > 28:
    #             if zombie.kind == "leaper" and target and target.alive and target.floor == zombie.floor and not target.inside_building:
    #                 self._leaper_move_toward(zombie, destination, dt, rng)
    #             else:
    #                 self._zombie_move_toward(zombie, destination, dt, sprint=True, rng=rng)
    #         else:
    #             zombie.mode = "search"
    #             zombie.search_timer = SEARCH_DURATION
    #         return
    #
    #     zombie.mode = "patrol"
    #     zombie.target_player_id = None

    def _apply_zombie_result(self, result: _ZombieUpdateResult) -> None:
        for player_id, damage in result.player_hits:
            player = self.players.get(player_id)
            if player and player.alive:
                self._damage_player(player, damage)

        for soldier_id, damage in result.soldier_hits:
            soldier = self.soldiers.get(soldier_id)
            if soldier and soldier.alive:
                self._damage_soldier(soldier, damage, result.zombie.id)

        for spit in result.poison_spits:
            spit_id = self._id("spit")

            if isinstance(spit, dict):
                self.poison_projectiles[spit_id] = PoisonProjectileState(
                    spit_id,
                    spit["owner_id"],
                    spit["pos"],
                    spit["velocity"],
                    spit["target"],
                    floor=spit["floor"],
                )
                continue

            self.poison_projectiles[spit_id] = PoisonProjectileState(
                spit_id,
                spit.owner_id,
                spit.pos,
                spit.velocity,
                spit.target,
                floor=spit.floor,
            )

    def _apply_soldier_result(self, soldier: SoldierState, result) -> None:
        for projectile in result.projectiles:
            projectile_id = self._id("shot")

            self.projectiles[projectile_id] = ProjectileState(
                id=projectile_id,
                owner_id=str(projectile["owner_id"]),
                pos=projectile["pos"],
                velocity=projectile["velocity"],
                damage=int(projectile["damage"]),
                life=float(projectile["life"]),
                radius=float(projectile["radius"]),
                floor=int(projectile["floor"]),
                weapon_key=str(projectile["weapon_key"]),
            )

        for sound in result.sounds:
            self._emit_sound(
                pos=sound["pos"],
                floor=int(sound["floor"]),
                radius=float(sound["radius"]),
                source_player_id=str(sound["source_player_id"]),
                kind=str(sound["kind"]),
                intensity=float(sound["intensity"]),
            )

    def _random_soldier_guard_pos(self, soldier: SoldierState, rng: random.Random) -> Vec2:
        base = soldier.guard_point or soldier.pos

        for _ in range(30):
            angle = rng.uniform(0.0, math.tau)
            dist = rng.uniform(80.0, 220.0)

            pos = Vec2(
                base.x + math.cos(angle) * dist,
                base.y + math.sin(angle) * dist,
            )
            pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)

            if not self.ctx.geometry.blocked_at(pos, SOLDIERS[soldier.kind].radius, soldier.floor):
                return pos

        return base.copy()

    def _random_soldier_spawn_pos(self, spawn_point) -> Vec2 | None:
        return self.ctx.spawning.random_soldier_spawn_pos(spawn_point)

    def _find_player(self, players: tuple[PlayerState, ...], player_id: str | None) -> PlayerState | None:
        if not player_id:
            return None
        for player in players:
            if player.id == player_id:
                return player
        return None

    # def _update_chase(
    #     self,
    #     zombie: ZombieState,
    #     dt: float,
    #     players: tuple[PlayerState, ...],
    #     rng: random.Random,
    #     player_hits: list[tuple[str, int]],
    #     poison_spits: list[_PoisonSpitEvent],
    # ) -> None:
    #     target = self._find_player(players, zombie.target_player_id)
    #     if target and target.alive and self._can_see(zombie, target):
    #         zombie.last_known_pos = target.pos.copy()
    #         if zombie.kind == "leaper":
    #             self._try_poison_spit(zombie, target, rng, poison_spits)
    #             self._leaper_move_toward(zombie, target.pos, dt, rng)
    #         else:
    #             self._zombie_move_toward(zombie, target.pos, dt, sprint=True, rng=rng)
    #         self._try_zombie_attack(zombie, target, player_hits)
    #         return
    #     if target and target.inside_building:
    #         entry = self.ctx.buildings.building_entry_target(target.inside_building)
    #         if entry and target.floor == zombie.floor:
    #             zombie.last_known_pos = entry
    #         elif target.floor != zombie.floor:
    #             zombie.mode = "search"
    #             zombie.search_timer = SEARCH_DURATION
    #     if zombie.last_known_pos:
    #         if zombie.pos.distance_to(zombie.last_known_pos) > 28:
    #             self._zombie_move_toward(zombie, zombie.last_known_pos, dt, sprint=True, rng=rng)
    #         else:
    #             zombie.mode = "search"
    #             zombie.search_timer = SEARCH_DURATION
    #     else:
    #         zombie.mode = "patrol"

    # def _update_investigate(
    #     self,
    #     zombie: ZombieState,
    #     dt: float,
    #     players: tuple[PlayerState, ...],
    #     rng: random.Random,
    # ) -> None:
    #     if not zombie.last_known_pos:
    #         zombie.mode = "patrol"
    #         return
    #     target = self._find_player(players, zombie.target_player_id)
    #     if target and target.inside_building:
    #         entry = self.ctx.buildings.building_entry_target(target.inside_building)
    #         if entry:
    #             zombie.last_known_pos = entry
    #     if zombie.pos.distance_to(zombie.last_known_pos) > 34:
    #         self._zombie_move_toward(zombie, zombie.last_known_pos, dt, sprint=False, rng=rng)
    #     else:
    #         zombie.mode = "search"
    #         zombie.search_timer = SEARCH_DURATION

    # def _update_search(self, zombie: ZombieState, dt: float, rng: random.Random) -> None:
    #     zombie.search_timer -= dt
    #     if zombie.search_timer <= 0.0:
    #         zombie.mode = "patrol"
    #         zombie.target_player_id = None
    #         zombie.last_known_pos = None
    #         zombie.waypoint = None
    #         zombie.alertness = 0.0
    #         return
    #     if not zombie.waypoint or zombie.pos.distance_to(zombie.waypoint) < 26:
    #         base = zombie.last_known_pos or zombie.pos
    #         angle = rng.uniform(0, math.tau)
    #         distance = rng.uniform(80, 220)
    #         zombie.waypoint = Vec2(base.x + math.cos(angle) * distance, base.y + math.sin(angle) * distance)
    #         zombie.waypoint.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
    #     self._zombie_move_toward(zombie, zombie.waypoint, dt, sprint=False, rng=rng)

    # def _update_patrol(self, zombie: ZombieState, dt: float, rng: random.Random) -> None:
    #     if zombie.idle_timer > 0.0:
    #         zombie.idle_timer = max(0.0, zombie.idle_timer - dt)
    #         return
    #     if zombie.waypoint and rng.random() < 0.0035:
    #         zombie.idle_timer = rng.uniform(0.8, 2.4)
    #         return
    #     if not zombie.waypoint or zombie.pos.distance_to(zombie.waypoint) < 38 or self._near_building(zombie.waypoint, 120):
    #         if zombie.waypoint and zombie.pos.distance_to(zombie.waypoint) < 38 and rng.random() < 0.46:
    #             zombie.idle_timer = rng.uniform(0.8, 2.6)
    #             zombie.waypoint = None
    #             return
    #         zombie.waypoint = self._random_patrol_pos(rng)
    #     self._zombie_move_toward(zombie, zombie.waypoint, dt, sprint=False, rng=rng)

    def _zombie_move_toward(
        self,
        zombie: ZombieState,
        target: Vec2,
        dt: float,
        sprint: bool,
        rng: random.Random | None = None,
    ) -> None:
        rng = rng or self.rng
        spec = ZOMBIES[zombie.kind]
        direction = Vec2(target.x - zombie.pos.x, target.y - zombie.pos.y)
        if direction.length() <= 0.01:
            return
        zombie.facing = math.atan2(direction.y, direction.x)
        speed = spec.speed * self.difficulty.zombie_speed_multiplier * (1.22 if sprint else 1.0)
        step = direction.normalized().scaled(speed * dt)
        old_pos = zombie.pos.copy()
        self.ctx.movement.move_circle(zombie.pos, step, spec.radius, zombie.floor)
        if zombie.pos.distance_to(old_pos) < 0.5:
            if self._unstick_zombie_from_building(zombie, spec.radius, rng):
                return

            door = self.ctx.buildings.nearest_door(zombie.pos, 160, zombie.floor)
            if door and door.open:
                zombie.waypoint = door.rect.center
                return

            # Не меняем цель резко каждый тик.
            # Даем зомби мягкий боковой обход.
            angle = zombie.facing + rng.choice([-1.0, 1.0]) * math.pi * 0.5
            sidestep = Vec2(math.cos(angle), math.sin(angle)).scaled(spec.radius * 1.8)
            self.ctx.movement.move_circle(zombie.pos, sidestep, spec.radius, zombie.floor)
        # if zombie.pos.distance_to(old_pos) < 0.5:
        #     if self._unstick_zombie_from_building(zombie, spec.radius, rng):
        #         zombie.waypoint = self._random_patrol_pos(rng)
        #         return
        #     door = self.self.ctx.buildings.nearest_door(self.buildings, zombie.pos, 120, zombie.floor)
        #     if door and door.open:
        #         zombie.waypoint = door.rect.center
        #     else:
        #         zombie.waypoint = self._random_patrol_pos(rng)

    def _leaper_move_toward(self, zombie: ZombieState, target: Vec2, dt: float, rng: random.Random) -> None:
        spec = ZOMBIES[zombie.kind]
        to_target = Vec2(target.x - zombie.pos.x, target.y - zombie.pos.y)
        distance = to_target.length()
        if distance <= 0.01:
            return
        forward = to_target.normalized()
        if zombie.sidestep_timer <= 0.0:
            zombie.sidestep_timer = rng.uniform(0.55, 1.05)
            zombie.sidestep_bias = rng.choice([-1.0, 1.0]) * rng.uniform(0.42, 0.78)
        zombie.strafe_phase += dt * (1.75 + min(1.0, distance / 620.0) * 0.55)
        wave = math.sin(zombie.strafe_phase) * 0.55 + math.sin(zombie.strafe_phase * 0.43 + zombie.sidestep_bias) * 0.25
        lateral_strength = max(-0.74, min(0.74, wave + zombie.sidestep_bias * 0.32))
        if distance < 150:
            lateral_strength *= distance / 150.0
        perpendicular = Vec2(-forward.y, forward.x)
        blended = Vec2(
            forward.x + perpendicular.x * lateral_strength,
            forward.y + perpendicular.y * lateral_strength,
        ).normalized()
        zombie.facing = math.atan2(forward.y, forward.x)
        speed = spec.speed * self.difficulty.zombie_speed_multiplier * 1.16
        old_pos = zombie.pos.copy()
        self.ctx.movement.move_circle(zombie.pos, blended.scaled(speed * dt), spec.radius, zombie.floor)
        if zombie.pos.distance_to(old_pos) < 0.5:
            zombie.sidestep_bias *= -1.0
            self._zombie_move_toward(zombie, target, dt, sprint=True, rng=rng)

    # def _try_poison_spit(
    #     self,
    #     zombie: ZombieState,
    #     target: PlayerState,
    #     rng: random.Random,
    #     poison_spits: list[_PoisonSpitEvent] | None = None,
    # ) -> None:
    #     if zombie.special_cooldown > 0.0:
    #         return
    #     distance = zombie.pos.distance_to(target.pos)
    #     if not 180 <= distance <= 720:
    #         return
    #     if self.ctx.geometry.line_blocked(zombie.pos, target.pos, zombie.floor):
    #         return
    #     direction = Vec2(target.pos.x - zombie.pos.x, target.pos.y - zombie.pos.y).normalized()
    #     start = Vec2(
    #         zombie.pos.x + direction.x * (ZOMBIES[zombie.kind].radius + 14),
    #         zombie.pos.y + direction.y * (ZOMBIES[zombie.kind].radius + 14),
    #     )
    #     speed = 520.0
    #     if poison_spits is None:
    #         spit_id = self._id("spit")
    #         self.poison_projectiles[spit_id] = PoisonProjectileState(
    #             spit_id,
    #             zombie.id,
    #             start,
    #             direction.scaled(speed),
    #             target.pos.copy(),
    #             floor=zombie.floor,
    #         )
    #     else:
    #         poison_spits.append(_PoisonSpitEvent(zombie.id, start, direction.scaled(speed), target.pos.copy(), zombie.floor))
    #     zombie.special_cooldown = rng.uniform(2.8, 4.2)

    # def _try_zombie_attack(
    #     self,
    #     zombie: ZombieState,
    #     target: PlayerState,
    #     player_hits: list[tuple[str, int]] | None = None,
    # ) -> None:
    #     spec = ZOMBIES[zombie.kind]
    #     if zombie.pos.distance_to(target.pos) <= ZOMBIE_TARGET_RADIUS + spec.radius and zombie.attack_cooldown <= 0.0:
    #         damage = max(1, int(round(spec.damage * self.difficulty.zombie_damage_multiplier)))
    #         if player_hits is None:
    #             self._damage_player(target, damage)
    #         else:
    #             player_hits.append((target.id, damage))
    #         zombie.attack_cooldown = 0.7

    # def _visible_player(self, zombie: ZombieState, players: list[PlayerState]) -> PlayerState | None:
    #     visible = [player for player in players if self._can_see(zombie, player)]
    #     if not visible:
    #         return None
    #     return min(visible, key=lambda player: zombie.pos.distance_to(player.pos))

    def _can_see(self, zombie: ZombieState, player: PlayerState) -> bool:
        if zombie.floor != player.floor:
            return False

        # Если игрок в доме, а зомби не в том же доме — не видит.
        if player.inside_building and zombie.inside_building != player.inside_building:
            return False

        spec = ZOMBIES[zombie.kind]
        distance = zombie.pos.distance_to(player.pos)

        if distance > spec.sight_range:
            return False

        angle_to_player = zombie.pos.angle_to(player.pos)
        if abs(_angle_delta(zombie.facing, angle_to_player)) > math.radians(spec.fov_degrees * 0.5):
            return False

        return not self.ctx.geometry.line_blocked(zombie.pos, player.pos, zombie.floor)

    def _can_hear(self, zombie: ZombieState) -> SoundEvent | None:
        spec = ZOMBIES[zombie.kind]

        hearing_radius = spec.hearing_range * max(0.1, spec.sensitivity)

        best_event: SoundEvent | None = None
        best_dist = float("inf")

        for event in self.sound_events:
            if event.floor != zombie.floor:
                continue

            dist = zombie.pos.distance_to(event.pos)

            # пересечение двух окружностей:
            # область слуха зомби + область шума
            if dist > hearing_radius + event.radius:
                continue

            # звук не проходит через стены/дома/двери
            if self.ctx.geometry.line_blocked(zombie.pos, event.pos, zombie.floor, sound=True):
                continue

            if dist < best_dist:
                best_dist = dist
                best_event = event

        return best_event

    def _alert_zombie_from_damage(
        self,
        zombie: ZombieState,
        owner_id: str,
        source_pos: Vec2 | None = None,
        reveal_owner: bool = True,
    ) -> None:
        owner = self.players.get(owner_id) if reveal_owner else None
        if owner and owner.alive:
            alert_pos = source_pos.copy() if source_pos else owner.pos.copy()
            if owner.floor == zombie.floor:
                zombie.mode = "chase"
                zombie.target_player_id = owner.id
            else:
                zombie.mode = "search"
                zombie.target_player_id = None
        elif source_pos:
            alert_pos = source_pos.copy()
            zombie.mode = "investigate"
            zombie.target_player_id = None
        else:
            return
        alert_pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
        zombie.last_known_pos = alert_pos
        zombie.waypoint = None
        zombie.search_look_timer = 0.0
        zombie.idle_timer = 0.0
        zombie.search_timer = SEARCH_DURATION
        zombie.alertness = 1.0
        zombie.facing = zombie.pos.angle_to(alert_pos)
        self._zombie_ai_generation[zombie.id] = self._zombie_ai_generation.get(zombie.id, 0) + 1
        self._zombie_ai_pending.pop(zombie.id, None)
        self._zombie_ai_next_at[zombie.id] = self.time

    def _damage_player(self, player: PlayerState, damage: int) -> None:
        self.ctx.damage.damage_player(player, damage)

    def _damage_soldier(self, soldier: SoldierState, damage: int, owner_id: str) -> None:
        self.ctx.damage.damage_soldier(soldier, damage, owner_id)

    def _damage_zombie(
        self,
        zombie: ZombieState,
        damage: int,
        owner_id: str,
        source_pos: Vec2 | None = None,
        reveal_owner: bool = True,
    ) -> None:
        self.ctx.damage.damage_zombie(
            zombie,
            damage,
            owner_id,
            source_pos=source_pos,
            reveal_owner=reveal_owner,
        )

    def _player_armor_mitigation(self, player: PlayerState) -> float:
        best = 0.0
        for item in player.equipment.values():
            spec = ITEMS.get(item.key) if item else None
            if not item or not spec or not spec.armor_key or item.durability <= 0:
                continue
            armor = ARMORS.get(spec.armor_key, ARMORS["none"])
            rarity = rarity_spec(item.rarity)
            best = max(best, armor.mitigation * rarity.armor_mitigation_multiplier)
        return min(0.88, best)

    def _effective_armor_points(self, item: InventoryItem | None) -> int:
        spec = ITEMS.get(item.key) if item else None
        if not item or not spec or not spec.armor_key:
            return 0
        armor = ARMORS.get(spec.armor_key, ARMORS["none"])
        rarity = rarity_spec(item.rarity)
        return max(0, int(round(armor.armor_points * rarity.armor_points_multiplier)))

    def _update_healing(self, player: PlayerState, dt: float) -> None:
        if player.healing_left <= 0.0 or player.healing_pool <= 0.0 or player.health >= 100:
            if player.healing_pool <= 0.0 or player.health >= 100:
                player.healing_stacks = 0
            return
        stacks = max(1, player.healing_stacks)
        healed = min(player.healing_pool, player.healing_rate * dt * stacks)
        player.healing_pool -= healed
        player.healing_left = max(0.0, player.healing_left - dt)
        player.health = min(100, player.health + healed)
        if player.healing_left <= 0.0 or player.healing_pool <= 0.0 or player.health >= 100:
            player.healing_stacks = 0

    def _set_notice(self, player: PlayerState, key: str, seconds: float = 2.2) -> None:
        player.notice = key
        player.notice_timer = max(player.notice_timer, seconds)

    def _update_notice(self, player: PlayerState, dt: float) -> None:
        if player.notice_timer <= 0.0:
            player.notice = ""
            player.notice_timer = 0.0
            return
        player.notice_timer = max(0.0, player.notice_timer - dt)
        if player.notice_timer <= 0.0:
            player.notice = ""

    def _apply_inventory_action(self, player: PlayerState, action: dict[str, object]) -> None:
        action_type = str(action.get("type", ""))
        if action_type == "move":
            self._move_inventory_item(player, action)
        elif action_type == "quick_swap":
            a = str(action.get("a", ""))
            b = str(action.get("b", ""))
            if a in SLOTS and b in SLOTS:
                player.weapons[a], player.weapons[b] = player.weapons.get(b), player.weapons.get(a)
                if player.weapons.get(a) is None:
                    player.weapons.pop(a, None)
                if player.weapons.get(b) is None:
                    player.weapons.pop(b, None)
                player.quick_items[a], player.quick_items[b] = player.quick_items.get(b), player.quick_items.get(a)
        elif action_type == "repair_drag":
            self._repair_with_kit(player, action)
        elif action_type == "unequip_module":
            slot = str(action.get("slot", ""))
            module_slot = str(action.get("module_slot", ""))
            item = self._take_item(player, "weapon_module", -1, slot, module_slot)
            if item and not self._add_item(player, item.key, item.amount, item.rarity):
                self._place_item(player, "weapon_module", -1, slot, item, module_slot)
        elif action_type == "drop":
            source = str(action.get("source", "backpack"))
            index = int(action.get("index", -1))
            slot = str(action.get("slot", ""))
            module_slot = str(action.get("module_slot", ""))
            if source == "weapon_slot" and slot in player.weapons:
                weapon = player.weapons.pop(slot, None)
                if weapon:
                    self._spawn_loot_at(player.pos.copy(), "weapon", weapon.key, 1, floor=player.floor, rarity=weapon.rarity)
                    if player.active_slot == slot:
                        player.active_slot = next((slot_key for slot_key in SLOTS if player.weapons.get(slot_key)), "1")
                return
            item = self._take_item(player, source, index, slot, module_slot)
            if item:
                self._spawn_loot_at(player.pos.copy(), "item", item.key, item.amount, floor=player.floor, rarity=item.rarity)
        elif action_type == "use":
            index = int(action.get("index", -1))
            if 0 <= index < len(player.backpack):
                item = player.backpack[index]
                if item and self._use_item(player, item):
                    item.amount -= 1
                    if item.amount <= 0:
                        player.backpack[index] = None

    def _move_inventory_item(self, player: PlayerState, action: dict[str, object]) -> None:
        src = str(action.get("src", "backpack"))
        dst = str(action.get("dst", "backpack"))
        src_index = int(action.get("src_index", -1))
        dst_index = int(action.get("dst_index", -1))
        src_slot = str(action.get("src_slot", ""))
        dst_slot = str(action.get("dst_slot", ""))
        src_module = str(action.get("src_module", ""))
        dst_module = str(action.get("dst_module", ""))
        if src == "weapon_slot":
            if dst != "backpack":
                return
            if not (0 <= dst_index < len(player.backpack)) or player.backpack[dst_index] is not None:
                return
        item = self._take_item(player, src, src_index, src_slot, src_module)
        if not item:
            return
        displaced = self._place_item(player, dst, dst_index, dst_slot, item, dst_module)
        if displaced:
            self._place_item(player, src, src_index, src_slot, displaced, src_module)
        self._recalculate_armor(player)

    def _take_item(self, player: PlayerState, source: str, index: int, slot: str, module_slot: str = "") -> InventoryItem | None:
        if source == "backpack" and 0 <= index < len(player.backpack):
            item = player.backpack[index]
            player.backpack[index] = None
            return item
        if source == "weapon_slot" and slot in player.weapons:
            weapon = player.weapons.pop(slot, None)
            if not weapon:
                return None
            if player.active_slot == slot:
                player.active_slot = next((slot_key for slot_key in SLOTS if player.weapons.get(slot_key)), slot)
            return InventoryItem(self._id("it"), weapon.key, 1, durability=weapon.durability, rarity=weapon.rarity)
        if source == "equipment" and slot in player.equipment:
            item = player.equipment[slot]
            player.equipment[slot] = None
            return item
        if source == "quick_item" and slot in SLOTS:
            item = player.quick_items.get(slot)
            player.quick_items[slot] = None
            return item
        if source == "weapon_module":
            weapon = player.weapons.get(slot)
            if not weapon or module_slot not in weapon.modules:
                return None
            module_key = weapon.modules.get(module_slot)
            if not module_key:
                return None
            weapon.modules[module_slot] = None
            if module_slot == "utility":
                weapon.utility_on = False
            if module_slot == "magazine":
                weapon.ammo_in_mag = min(weapon.ammo_in_mag, self._weapon_magazine_size(weapon))
            return InventoryItem(self._id("it"), module_key, 1)
        return None

    def _place_item(
        self,
        player: PlayerState,
        destination: str,
        index: int,
        slot: str,
        item: InventoryItem,
        module_slot: str = "",
    ) -> InventoryItem | None:
        if destination == "weapon_module" and slot in player.weapons:
            module = WEAPON_MODULES.get(item.key)
            if not module or module.slot != module_slot:
                return item
            weapon = player.weapons[slot]
            displaced_key = weapon.modules.get(module_slot)
            weapon.modules[module_slot] = item.key
            if module_slot == "magazine":
                weapon.ammo_in_mag = min(weapon.ammo_in_mag, self._weapon_magazine_size(weapon))
            if module_slot == "utility":
                weapon.utility_on = False
            return InventoryItem(self._id("it"), displaced_key, 1) if displaced_key else None
        if destination == "weapon_slot" and slot in SLOTS:
            if player.weapons.get(slot) or player.quick_items.get(slot):
                return item
            if item.key in WEAPONS:
                spec = WEAPONS[item.key]
                player.weapons[slot] = WeaponRuntime(
                    item.key,
                    spec.magazine_size,
                    spec.magazine_size * 2,
                    durability=item.durability,
                    rarity=item.rarity,
                )
                player.active_slot = slot
                return None
            spec = ITEMS.get(item.key)
            if spec and spec.kind in {"grenade", "mine"}:
                player.quick_items[slot] = item
                return None
            return item
        if destination == "equipment" and slot in player.equipment:
            spec = ITEMS.get(item.key)
            if not spec or spec.equipment_slot != slot:
                return item
            displaced = player.equipment.get(slot)
            player.equipment[slot] = item
            return displaced
        if destination == "quick_item" and slot in SLOTS:
            spec = ITEMS.get(item.key)
            if not spec or spec.kind not in {"grenade", "mine"}:
                return item
            displaced = player.quick_items.get(slot)
            player.quick_items[slot] = item
            return displaced
        if destination == "backpack" and 0 <= index < len(player.backpack):
            displaced = player.backpack[index]
            player.backpack[index] = item
            return displaced
        return item

    def _use_item(self, player: PlayerState, item: InventoryItem) -> bool:
        spec = ITEMS.get(item.key)
        if not spec:
            return False
        if spec.kind in {"food", "medical"} and spec.heal_total > 0 and player.health < 100:
            player.healing_pool += float(spec.heal_total)
            player.healing_left = max(player.healing_left, max(0.1, spec.heal_seconds))
            player.healing_rate = spec.heal_total / max(0.1, spec.heal_seconds)
            player.healing_stacks = max(1, player.healing_stacks + 1)
            return True
        if spec.kind == "ammo":
            for weapon in player.weapons.values():
                weapon.reserve_ammo += 12 * item.amount
            return True
        return False

    def _craft(self, player: PlayerState, recipe_key: str) -> None:
        if not self.ctx.buildings.nearest_prop(player.pos, INTERACT_RADIUS, player.floor):
            return
        recipe = RECIPES.get(recipe_key)
        if not recipe:
            return
        if any(self._count_item(player, key) < amount for key, amount in recipe.requires.items()):
            return
        result_key, result_amount = recipe.result
        result_spec = ITEMS.get(result_key)
        result_kind = result_spec.kind if result_spec else "item"
        result_rarity = roll_crafted_rarity(self.rng, recipe.key, result_kind)
        if not self._can_add_item(player, result_key, result_amount, result_rarity):
            self._pickup_failed_full(player)
            return
        for key, amount in recipe.requires.items():
            self._remove_items(player, key, amount)
        self._add_item(player, result_key, result_amount, rarity=result_rarity)

    def _repair_armor(self, player: PlayerState, slot: str) -> None:
        if not self.ctx.buildings.nearest_prop(player.pos, INTERACT_RADIUS, player.floor):
            return
        item = player.equipment.get(slot)
        if not item:
            return
        if not self._remove_items(player, "repair_kit", 1):
            return
        spec = ITEMS.get(item.key)
        if spec and spec.armor_key and spec.armor_key in ARMORS:
            player.armor_key = spec.armor_key
            player.armor = min(self._effective_armor_points(item), player.armor + 35)

    def _repair_with_kit(self, player: PlayerState, action: dict[str, object]) -> None:
        kit_index = int(action.get("kit_index", -1))
        target_source = str(action.get("target_source", ""))
        target_index = int(action.get("target_index", -1))
        target_slot = str(action.get("target_slot", ""))
        if not (0 <= kit_index < len(player.backpack)):
            return
        kit = player.backpack[kit_index]
        if not kit or kit.key != "repair_kit":
            return
        target = None
        if target_source == "backpack" and 0 <= target_index < len(player.backpack):
            target = player.backpack[target_index]
        elif target_source == "equipment" and target_slot in player.equipment:
            target = player.equipment[target_slot]
        elif target_source == "quick_item" and target_slot in SLOTS:
            target = player.quick_items.get(target_slot)
        elif target_source == "weapon_slot" and target_slot in player.weapons:
            weapon = player.weapons[target_slot]
            weapon.durability = 100.0
            kit.amount -= 1
            if kit.amount <= 0:
                player.backpack[kit_index] = None
            return
        if not target or target.durability >= 100.0:
            return
        target.durability = 100.0
        kit.amount -= 1
        if kit.amount <= 0:
            player.backpack[kit_index] = None

    def _add_item(self, player: PlayerState, key: str, amount: int, rarity: str = "common") -> bool:
        spec = ITEMS.get(key)
        if not spec:
            return False
        remaining = amount
        for item in player.backpack:
            if item and item.key == key and item.rarity == rarity and item.amount < spec.stack_size:
                add = min(remaining, spec.stack_size - item.amount)
                item.amount += add
                remaining -= add
                if remaining <= 0:
                    return True
        for index, item in enumerate(player.backpack):
            if item is None:
                add = min(remaining, spec.stack_size)
                player.backpack[index] = InventoryItem(self._id("it"), key, add, rarity=rarity)
                remaining -= add
                if remaining <= 0:
                    return True
        return False

    def _can_add_item(self, player: PlayerState, key: str, amount: int, rarity: str = "common") -> bool:
        spec = ITEMS.get(key)
        if not spec:
            return False
        capacity = 0
        for item in player.backpack:
            if item is None:
                capacity += spec.stack_size
            elif item.key == key and item.rarity == rarity:
                capacity += max(0, spec.stack_size - item.amount)
            if capacity >= amount:
                return True
        return False

    def _add_weapon_to_backpack(self, player: PlayerState, weapon_key: str, rarity: str, durability: float = 100.0) -> bool:
        if weapon_key not in WEAPONS:
            return False
        for index, item in enumerate(player.backpack):
            if item is None:
                player.backpack[index] = InventoryItem(self._id("it"), weapon_key, 1, durability=durability, rarity=rarity)
                return True
        return False

    def _free_quick_slot(self, player: PlayerState, preferred: str | None = None) -> str | None:
        ordered = ([preferred] if preferred in SLOTS else []) + [slot for slot in SLOTS if slot != preferred]
        for slot in ordered:
            if not player.weapons.get(slot) and not player.quick_items.get(slot):
                return slot
        return None

    def _pickup_failed_full(self, player: PlayerState) -> None:
        self._set_notice(player, "notice.backpack_full")

    def _count_item(self, player: PlayerState, key: str) -> int:
        return sum(item.amount for item in player.backpack if item and item.key == key)

    def _remove_items(self, player: PlayerState, key: str, amount: int) -> bool:
        if self._count_item(player, key) < amount:
            return False
        remaining = amount
        for index, item in enumerate(player.backpack):
            if not item or item.key != key:
                continue
            take = min(remaining, item.amount)
            item.amount -= take
            remaining -= take
            if item.amount <= 0:
                player.backpack[index] = None
            if remaining <= 0:
                return True
        return True

    def _recalculate_armor(self, player: PlayerState) -> None:
        best_key = "none"
        best_points = 0
        for item in player.equipment.values():
            spec = ITEMS.get(item.key) if item else None
            if spec and spec.armor_key and item.durability > 0:
                points = self._effective_armor_points(item)
                if points > best_points:
                    best_key = spec.armor_key
                    best_points = points
        player.armor_key = best_key
        if best_key == "none":
            player.armor = 0
        else:
            player.armor = max(player.armor, int(best_points * 0.65))
            player.armor = min(player.armor, best_points)

    def _equip_armor(self, player: PlayerState, armor_key: str) -> None:
        spec = ARMORS[armor_key]
        if armor_key == "none":
            player.armor_key = "none"
            return
        if armor_key not in player.owned_armors:
            return
        player.armor_key = armor_key
        player.armor = max(player.armor, spec.armor_points)

    def _start_reload(self, player: PlayerState) -> None:
        self.ctx.weapons.start_reload(player)

    def _finish_reload(self, weapon: WeaponRuntime) -> None:
        self.ctx.weapons.finish_reload(weapon)

    def _weapon_magazine_size(self, weapon: WeaponRuntime) -> int:
        return self.ctx.weapons.magazine_size(weapon)

    def _weapon_spread(self, weapon: WeaponRuntime) -> float:
        return self.ctx.weapons.spread(weapon)

    def _weapon_fire_rate(self, weapon: WeaponRuntime) -> float:
        return self.ctx.weapons.fire_rate(weapon)

    def _toggle_weapon_utility(self, player: PlayerState) -> None:
        self.ctx.weapons.toggle_utility(player)

    def _projectile_life(self, projectile_speed: float) -> float:
        return self.ctx.weapons.projectile_life(projectile_speed)

    def _shoot(self, player: PlayerState) -> None:
        self.ctx.player_combat.shoot(player, self.ctx)

    def _unarmed_attack(self, player: PlayerState) -> None:
        self.ctx.player_combat.unarmed_attack(player, self.ctx)

    def _throw_grenade(self, player: PlayerState) -> None:
        self.ctx.player_combat.throw_grenade(player, self.ctx)

    def _throw_grenade_from_quick(self, player: PlayerState, slot: str) -> None:
        if self._grenade_cooldowns.get(player.id, 0.0) > 0:
            return
        item = player.quick_items.get(slot)
        spec = ITEMS.get(item.key) if item else None
        if not item or not spec or spec.kind != "grenade":
            return
        grenade_key = item.key
        item.amount -= 1
        if item.amount <= 0:
            player.quick_items[slot] = None
        self._spawn_grenade(player, grenade_key)
        self._grenade_cooldowns[player.id] = 0.6

    def _spawn_grenade(self, player: PlayerState, grenade_key: str = "grenade") -> None:
        grenade_spec = GRENADE_SPECS.get(grenade_key, DEFAULT_GRENADE)
        self._grenade_cooldowns[player.id] = 0.6
        distance = grenade_spec.throw_distance
        velocity = Vec2(math.cos(player.angle) * distance, math.sin(player.angle) * distance)
        start = Vec2(
            player.pos.x + math.cos(player.angle) * (PLAYER_RADIUS + 12),
            player.pos.y + math.sin(player.angle) * (PLAYER_RADIUS + 12),
        )
        grenade_id = self._id("g")
        self.grenades[grenade_id] = GrenadeState(
            grenade_id,
            player.id,
            start,
            velocity,
            timer=grenade_spec.timer,
            floor=player.floor,
            kind=grenade_key,
        )

    def _detonate_grenade(self, grenade: GrenadeState) -> None:
        spec = GRENADE_SPECS.get(grenade.kind, DEFAULT_GRENADE)
        self._emit_sound(
            pos=grenade.pos,
            floor=grenade.floor,
            radius=1800.0,
            source_player_id=grenade.owner_id,
            kind="explosion",
            intensity=1.4,
        )
        self._explode_at(
            grenade.pos,
            grenade.floor,
            grenade.owner_id,
            spec.blast_radius,
            spec.zombie_damage,
            spec.zombie_damage_bonus,
            spec.player_damage,
            spec.player_damage_bonus,
        )

    def _place_mine_from_quick(self, player: PlayerState, slot: str) -> None:
        if self._grenade_cooldowns.get(player.id, 0.0) > 0:
            return
        item = player.quick_items.get(slot)
        spec = ITEMS.get(item.key) if item else None
        if not item or not spec or spec.kind != "mine":
            return
        mine_spec = MINE_SPECS.get(item.key, DEFAULT_MINE)
        place_pos = Vec2(
            player.pos.x + math.cos(player.angle) * (PLAYER_RADIUS + 20),
            player.pos.y + math.sin(player.angle) * (PLAYER_RADIUS + 20),
        )
        place_pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
        if self.ctx.geometry.blocked_at(place_pos, 12, player.floor):
            place_pos = player.pos.copy()
        mine_id = self._id("m")
        self.mines[mine_id] = MineState(
            id=mine_id,
            owner_id=player.id,
            kind=item.key,
            pos=place_pos,
            floor=player.floor,
            armed=False,
            trigger_radius=mine_spec.trigger_radius,
            blast_radius=mine_spec.blast_radius,
        )
        item.amount -= 1
        if item.amount <= 0:
            player.quick_items[slot] = None
        self._grenade_cooldowns[player.id] = 0.45

    def _detonate_mine(self, mine: MineState) -> None:
        spec = MINE_SPECS.get(mine.kind, DEFAULT_MINE)
        self._emit_sound(
            pos=mine.pos,
            floor=mine.floor,
            radius=1500.0,
            source_player_id=mine.owner_id,
            kind="explosion",
            intensity=1.25,
        )
        self._explode_at(
            mine.pos,
            mine.floor,
            mine.owner_id,
            spec.blast_radius,
            spec.zombie_damage,
            spec.zombie_damage_bonus,
            spec.player_damage,
            spec.player_damage_bonus,
        )

    def _explode_at(
        self,
        pos: Vec2,
        floor: int,
        owner_id: str,
        blast_radius: float,
        zombie_damage: int,
        zombie_damage_bonus: int,
        player_damage: int,
        player_damage_bonus: int,
    ) -> None:
        for zombie in list(self.zombies.values()):
            if zombie.floor != floor:
                continue
            distance = zombie.pos.distance_to(pos)
            if distance <= blast_radius and not self.ctx.geometry.line_blocked(pos, zombie.pos, floor):
                damage = int(zombie_damage * (1.0 - distance / blast_radius)) + zombie_damage_bonus
                self._damage_zombie(zombie, damage, owner_id, source_pos=pos, reveal_owner=False)
        for player in self.players.values():
            if player.floor != floor or not player.alive:
                continue
            player_radius = blast_radius * 0.65
            distance = player.pos.distance_to(pos)
            if distance <= player_radius and not self.ctx.geometry.line_blocked(pos, player.pos, floor):
                damage = int(player_damage * (1.0 - distance / player_radius)) + player_damage_bonus
                self._damage_player(player, damage)

    def _pickup_nearby(self, player: PlayerState) -> None:
        closest = self._nearest_loot(player)
        if not closest:
            return

        if closest.kind == "weapon" and closest.payload in WEAPONS:
            spec = WEAPONS[closest.payload]
            current = player.weapons.get(spec.slot)
            if current:
                current.reserve_ammo += spec.magazine_size
                if rarity_rank(closest.rarity) > rarity_rank(current.rarity):
                    current.rarity = closest.rarity
                    current.durability = max(current.durability, 100.0)
            else:
                target_slot = self._free_quick_slot(player, spec.slot)
                if target_slot:
                    player.weapons[target_slot] = WeaponRuntime(
                        spec.key,
                        spec.magazine_size,
                        spec.magazine_size * 2,
                        rarity=closest.rarity,
                    )
                    player.active_slot = target_slot
                elif not self._add_weapon_to_backpack(player, spec.key, closest.rarity):
                    self._pickup_failed_full(player)
                    return
            self._add_item(player, "ammo_pack", 1)
        elif closest.kind == "ammo":
            if not self._add_item(player, "ammo_pack", max(1, closest.amount // 12)):
                self._pickup_failed_full(player)
                return
            for weapon in player.weapons.values():
                if weapon.key == closest.payload:
                    weapon.reserve_ammo += closest.amount
                    break
        elif closest.kind == "armor" and closest.payload in ARMORS:
            armor_item = f"{closest.payload}_torso" if f"{closest.payload}_torso" in ITEMS else "light_torso"
            if not self._add_item(player, armor_item, 1, rarity=closest.rarity):
                self._pickup_failed_full(player)
                return
        elif closest.kind == "medkit":
            if not self._add_item(player, "medicine", closest.amount):
                self._pickup_failed_full(player)
                return
            player.medkits += closest.amount
        elif closest.kind == "item" and closest.payload in ITEMS:
            if not self._add_item(player, closest.payload, closest.amount, rarity=closest.rarity):
                self._pickup_failed_full(player)
                return

        self.loot.pop(closest.id, None)

    def _nearest_loot(self, player: PlayerState) -> LootState | None:
        closest = None
        closest_distance = PICKUP_RADIUS
        for item in self.loot.values():
            if item.floor != player.floor:
                continue
            distance = player.pos.distance_to(item.pos)
            if distance <= closest_distance:
                closest = item
                closest_distance = distance
        return closest

    def _interact(self, player: PlayerState) -> bool:
        door = self.ctx.buildings.nearest_door(player.pos, INTERACT_RADIUS, player.floor)
        if door:
            door.open = not door.open
            self._mark_geometry_dirty()
            return True
        building = nearest_stairs(self.buildings, player.pos, INTERACT_RADIUS)
        if building and building.bounds.contains(player.pos):
            player.floor += 1
            if player.floor > building.max_floor:
                player.floor = building.min_floor
            player.inside_building = building.id
            return True
        return False

    def spawn_zombie(self, kind: str | None = None, pos: Vec2 | None = None) -> ZombieState | None:
        return self.ctx.spawning.spawn_zombie(kind=kind, pos=pos)

    def _heard_sound(self, zombie: ZombieState) -> SoundEvent | None:
        spec = ZOMBIES[zombie.kind]
        hearing_radius = spec.hearing_range * max(0.1, spec.sensitivity)

        best_event: SoundEvent | None = None
        best_dist = float("inf")

        for event in self.sound_events:
            if event.floor != zombie.floor:
                continue

            dist = zombie.pos.distance_to(event.pos)

            if dist > hearing_radius + event.radius:
                continue

            if self.ctx.geometry.line_blocked(zombie.pos, event.pos, zombie.floor, sound=True):
                continue

            if dist < best_dist:
                best_dist = dist
                best_event = event

        return best_event

    def _make_zombie_context(
            self,
            zombie: ZombieState,
            dt: float,
            living_players: tuple[PlayerState, ...],
            rng: random.Random,
    ) -> ZombieContext:
        return ZombieContext(
            zombie=zombie,
            players=living_players,
            dt=dt,
            time=self.time,
            rng=rng,
            difficulty=self.difficulty,
            can_see=self._can_see,
            can_hear=self._heard_sound,
            line_blocked=self._zombie_line_blocked_for_vision,
            move_toward=self._zombie_move_toward_adapter,
            random_patrol_pos=self._random_patrol_pos,
            pick_search_waypoint=self._pick_search_waypoint,
            building_entry_target=self.ctx.buildings.building_entry_target,
            path_next_point=self._zombie_path_next_point,
            targets=self._zombie_targets(living_players),
        )

    def _make_soldier_context(
            self,
            soldier: SoldierState,
            dt: float,
            rng: random.Random,
    ) -> SoldierContext:
        spec = SOLDIERS[soldier.kind]
        weapon = WEAPONS[spec.weapon_key]

        return SoldierContext(
            soldier=soldier,
            targets=self._soldier_targets(),
            dt=dt,
            time=self.time,
            rng=rng,
            spec=spec,
            weapon=weapon,
            line_blocked=lambda a, b, floor: self.ctx.geometry.line_blocked(a, b, floor),
            move_toward=self._soldier_move_toward,
            random_guard_pos=self._random_soldier_guard_pos,
            projectile_life=self._projectile_life,
    )

    def _zombie_targets(self, living_players: tuple[PlayerState, ...]) -> tuple[ActorTarget, ...]:
        targets: list[ActorTarget] = []

        for player in living_players:
            targets.append(
                ActorTarget(
                    id=player.id,
                    kind="player",
                    pos=player.pos.copy(),
                    floor=player.floor,
                    alive=player.alive,
                    sprinting=player.sprinting,
                    radius=PLAYER_RADIUS,
                    health=player.health,
                    inside_building=player.inside_building,
                )
            )

        for soldier in self.soldiers.values():
            if not soldier.alive:
                continue

            spec = SOLDIERS[soldier.kind]

            targets.append(
                ActorTarget(
                    id=soldier.id,
                    kind="soldier",
                    pos=soldier.pos.copy(),
                    floor=soldier.floor,
                    alive=soldier.alive,
                    sprinting=soldier.sprinting,
                    radius=spec.radius,
                    health=soldier.health,
                )
            )

        return tuple(targets)

    def _zombie_line_blocked_for_vision(self, start: Vec2, end: Vec2, floor: int) -> bool:
        return self.ctx.geometry.line_blocked(start, end, floor, sound=False)

    def _zombie_move_toward_adapter(
            self,
            zombie: ZombieState,
            target: Vec2,
            dt: float,
            sprint: bool,
            rng: random.Random,
    ) -> None:
        self._zombie_move_toward(zombie, target, dt, sprint=sprint, rng=rng)

    def _loot_count(self, base: int, minimum: int = 1) -> int:
        return max(minimum, int(round(base * self.difficulty.loot_spawn_multiplier)))

    def spawn_loot(self, kind: str, payload: str, amount: int, rarity: str | None = None) -> LootState:
        return self._spawn_loot_at(
            self.ctx.buildings.random_open_pos(
                centered=False,
                rng=self.rng,
                blocked_at=lambda p, r: self.ctx.geometry.blocked_at(p, r, 0),
            ),
            kind,
            payload,
            amount,
            rarity=rarity,
        )

    def _spawn_loot_at(
        self,
        pos: Vec2,
        kind: str,
        payload: str,
        amount: int,
        floor: int = 0,
        rarity: str | None = None,
    ) -> LootState:
        return self.ctx.loot.spawn_loot(
            loot_id=self._id("l"),
            pos=pos,
            kind=kind,
            payload=payload,
            amount=amount,
            floor=floor,
            rarity=rarity,
        )

    def _loot_rarity(self, kind: str, payload: str) -> str:
        return self.ctx.loot.loot_rarity(kind, payload)

    def _roll_rarity(self) -> str:
        return self.ctx.loot.roll_rarity()

    def _spawn_random_loot(self) -> None:
        kind, payload, amount = self.ctx.loot.random_world_loot()
        self.spawn_loot(kind, payload, amount)

    def _drop_from_zombie(self, pos: Vec2) -> None:
        kind = self.rng.choice(["ammo", "medkit"])
        payload = self.rng.choice(list(WEAPONS)) if kind == "ammo" else "medkit"
        amount = self.rng.randint(5, 18) if kind == "ammo" else 1
        item = LootState(self._id("l"), kind, replace(pos), payload, amount)
        self.loot[item.id] = item

    def _building_entry_target(self, building_id: str) -> Vec2 | None:
        building = self.buildings.get(building_id)
        if not building:
            return None
        open_doors = [door for door in building.doors if door.open and door.floor == 0]
        if open_doors:
            return min(open_doors, key=lambda door: door.rect.center.distance_to(building.bounds.center)).rect.center
        front = min(building.doors, key=lambda door: door.rect.center.y)
        center = front.rect.center
        return Vec2(center.x, center.y - 80)

    def _random_open_pos(self, centered: bool, rng: random.Random | None = None) -> Vec2:
        rng = rng or self.rng
        for _ in range(500):
            if centered:
                pos = Vec2(
                    MAP_WIDTH * 0.5 + rng.uniform(-360, 360),
                    MAP_HEIGHT * 0.5 + rng.uniform(-300, 300),
                )
            else:
                pos = Vec2(rng.uniform(160, MAP_WIDTH - 160), rng.uniform(160, MAP_HEIGHT - 160))
            if not self.ctx.geometry.blocked_at(pos, PLAYER_RADIUS):
                return pos
        return Vec2(MAP_WIDTH * 0.5, MAP_HEIGHT * 0.5)

    def _random_patrol_pos(self, rng: random.Random | None = None) -> Vec2:
        rng = rng or self.rng
        for _ in range(500):
            pos = self._random_open_pos(centered=False, rng=rng)
            if not self._near_building(pos, 340):
                return pos
        return self._random_open_pos(centered=False, rng=rng)

    def _pick_search_waypoint(
        self,
        zombie: ZombieState,
        anchor: Vec2,
        rng: random.Random,
    ) -> Vec2 | None:
        spec = ZOMBIES[zombie.kind]
        radius = spec.radius
        clearance = 52.0
        for _ in range(72):
            angle = rng.uniform(0.0, math.tau)
            dist = rng.uniform(72.0, 312.0)
            pos = Vec2(anchor.x + math.cos(angle) * dist, anchor.y + math.sin(angle) * dist)
            pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
            if self.ctx.buildings.point_building(pos) is not None:
                continue
            if self._near_building(pos, clearance):
                continue
            if self.ctx.geometry.blocked_at(pos, radius, zombie.floor):
                continue
            return pos
        for _ in range(28):
            pos = Vec2(
                anchor.x + rng.uniform(-240.0, 240.0),
                anchor.y + rng.uniform(-240.0, 240.0),
            )
            pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
            if self.ctx.buildings.point_building(pos) is not None:
                continue
            if self._near_building(pos, clearance * 0.88):
                continue
            if self.ctx.geometry.blocked_at(pos, radius, zombie.floor):
                continue
            return pos
        return None

    def _near_building(self, pos: Vec2, margin: float) -> bool:
        for building in self.buildings.values():
            if building.bounds.inflated(margin).contains(pos):
                return True
        return False

    def _unstick_zombie_from_building(
        self,
        zombie: ZombieState,
        radius: float,
        rng: random.Random | None = None,
    ) -> bool:
        rng = rng or self.rng
        nearest = min(self.buildings.values(), key=lambda building: building.bounds.center.distance_to(zombie.pos), default=None)
        if not nearest or not nearest.bounds.inflated(120).contains(zombie.pos):
            return False
        if nearest.bounds.inflated(8).contains(zombie.pos):
            exits = [
                Vec2(nearest.bounds.x - 90, zombie.pos.y),
                Vec2(nearest.bounds.x + nearest.bounds.w + 90, zombie.pos.y),
                Vec2(zombie.pos.x, nearest.bounds.y - 90),
                Vec2(zombie.pos.x, nearest.bounds.y + nearest.bounds.h + 90),
            ]
            exits.sort(key=lambda candidate: candidate.distance_to(zombie.pos))
            for candidate in exits:
                candidate.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
                if not self.ctx.geometry.blocked_at(candidate, radius):
                    zombie.pos = candidate
                    zombie.facing = zombie.pos.angle_to(nearest.bounds.center) + math.pi
                    return True
        center = nearest.bounds.center
        away = Vec2(zombie.pos.x - center.x, zombie.pos.y - center.y).normalized()
        if away.length() <= 0.0:
            away = Vec2(rng.choice([-1.0, 1.0]), rng.choice([-1.0, 1.0])).normalized()
        for distance in (72, 128, 196, 280):
            candidate = Vec2(zombie.pos.x + away.x * distance, zombie.pos.y + away.y * distance)
            candidate.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
            if not self.ctx.geometry.blocked_at(candidate, radius) and not self._near_building(candidate, 38):
                zombie.pos = candidate
                zombie.facing = math.atan2(away.y, away.x)
                return True
        return False

    def _random_edge_pos(self) -> Vec2:
        side = self.rng.choice(["top", "right", "bottom", "left"])
        if side == "top":
            return Vec2(self.rng.uniform(0, MAP_WIDTH), 40)
        if side == "right":
            return Vec2(MAP_WIDTH - 40, self.rng.uniform(0, MAP_HEIGHT))
        if side == "bottom":
            return Vec2(self.rng.uniform(0, MAP_WIDTH), MAP_HEIGHT - 40)
        return Vec2(40, self.rng.uniform(0, MAP_HEIGHT))

    def _move_circle(self, pos: Vec2, delta: Vec2, radius: float, floor: int) -> None:
        self.ctx.movement.move_circle(pos, delta, radius, floor)

    def _mark_geometry_dirty(self) -> None:
        self.ctx.geometry.mark_dirty()

    def _closed_walls(self, floor: int) -> tuple[RectState, ...]:
        return self.ctx.geometry.closed_walls(floor)

    def _blocked_at(self, pos: Vec2, radius: float, floor: int = 0) -> bool:
        return self.ctx.geometry.blocked_at(pos, radius, floor)

    def _line_blocked(self, start: Vec2, end: Vec2, floor: int, sound: bool = False) -> bool:
        return self.ctx.geometry.line_blocked(start, end, floor, sound=sound)

    def snapshot(self) -> WorldSnapshot:
        with self._lock:
            return WorldSnapshot(
                time=self.time,
                map_width=MAP_WIDTH,
                map_height=MAP_HEIGHT,
                players=dict(self.players),
                zombies=dict(self.zombies),
                soldiers=dict(self.soldiers),
                projectiles=dict(self.projectiles),
                grenades=dict(self.grenades),
                mines=dict(self.mines),
                poison_projectiles=dict(self.poison_projectiles),
                poison_pools=dict(self.poison_pools),
                loot=dict(self.loot),
                buildings=dict(self.buildings),
            )

    def zombie_count(self) -> int:
        with self._lock:
            return len(self.zombies)


def _angle_delta(a: float, b: float) -> float:
    return (b - a + math.pi) % (math.tau) - math.pi


def _clean_player_name(name: str) -> str:
    return "Operator" if not name.strip() else name.strip()[:18]
