from __future__ import annotations

import random
import threading
from concurrent.futures import Future
from dataclasses import dataclass, replace
from typing import Any

from shared.systems.combat.damage_service import DamageService
from shared.systems.combat.projectile_system import ProjectileSystem
from shared.systems.events.event_apply_system import EventApplySystem
from shared.systems.events.event_buffer import EventBuffer
from shared.systems.events.game_events import SpawnLootEvent
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
from shared.systems.interactions.interaction_service import InteractionService
from shared.systems.actors.soldier_runtime_system import SoldierRuntimeSystem
from shared.systems.actors.soldier_runtime_service import SoldierRuntimeService
from shared.systems.actors.zombie_runtime_service import ZombieRuntimeService
from shared.systems.actors.zombie_runtime_system import ZombieRuntimeSystem
from shared.systems.players.player_service import PlayerService
from shared.systems.players.player_status_service import PlayerStatusService

from shared.ai.pathfinding import GridPathfinder
from shared.ai.registry import ZOMBIE_AI_REGISTRY
from shared.ai.soldiers.registry import SOLDIER_AI_REGISTRY


from shared.constants import (
    MAP_HEIGHT,
    MAP_WIDTH,
    PLAYER_RADIUS,
    WEAPONS,
    SLOTS,
    ZOMBIES, AMMO_BY_WEAPON
)
from shared.backpack_config import load_backpack_config
from shared.difficulty import load_difficulty
from shared.items import BASEMENT_LOOT, HOUSE_LOOT, ITEMS
from shared.level import make_buildings
from shared.models import (
    ClientCommand,
    InputCommand,
    InventoryItem,
    LootState,
    PlayerState,
    Vec2,
    WeaponRuntime,
    WorldSnapshot,
    ZombieState,
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

        event_buffer = EventBuffer()

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
        self.command_router.register("interact", InteractHandler())
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

        soldier_runtime_service = SoldierRuntimeService(
            state=self.state,
            rng=rng,
            soldier_ai_registry=self.soldier_ai_registry,
        )

        zombie_runtime_service = ZombieRuntimeService(
            state=self.state,
            rng=rng,
            zombie_ai_registry=self.zombie_ai_registry,
            difficulty=difficulty,
            pathfinder=self.zombie_pathfinder,
        )

        inventory_service = InventoryService(
            state=self.state,
            rng=rng,
            backpack_config=backpack_config,
            loot=loot_service,
            buildings=building_service,
            ids=id_generator,
            events=event_buffer,
        )

        player_service = PlayerService(
            state=self.state,
            rng=rng,
            backpack_config=backpack_config,
            ids=id_generator,
            inventory=inventory_service,
        )

        interaction_service = InteractionService(
            state=self.state,
            buildings=building_service,
            geometry=geometry_service,
        )

        player_status_service = PlayerStatusService()

        self.ctx = WorldContext(
            player_service=player_service,
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
            player_status=player_status_service,
            inventory=inventory_service,
            interactions=interaction_service,
            soldier_runtime=soldier_runtime_service,
            zombie_runtime=zombie_runtime_service,
            events=event_buffer,
        )

        self.systems = SystemScheduler([
            PlayerUpdateSystem(),
            ProjectileSystem(),
            ExplosiveSystem(),
            PoisonSystem(),
            ZombieSpawnSystem(),
            LootSpawnSystem(),
            SoundSystem(),
            ZombieRuntimeSystem(),
            SoldierRuntimeSystem(),
            EventApplySystem(),
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
        EventApplySystem().update(self.state, self.ctx, 0.0)

    def close(self) -> None:
        self.ctx.process_pool.close()
        self.ctx.thread_pool.close()

        self._zombie_executor = None
        self._zombie_ai_pending.clear()
        self._zombie_ai_futures.clear()

    def update(self, dt: float) -> None:
        with self._lock:
            self._update_unlocked(dt)

    def _update_unlocked(self, dt: float) -> None:
        self.time += dt
        self.state.time = self.time

        if dt <= 0.0:
            return

        self.systems.update_all(self.state, self.ctx, dt)

    def _prime_map(self) -> None:
        start_count = min(self.initial_zombies, self.max_zombies) if self.max_zombies > 0 else 0
        for _ in range(start_count):
            self.spawn_zombie()
        for weapon in ("smg", "shotgun", "rifle"):
            self.spawn_loot("weapon", weapon, 1)
        for armor in ("light_head", "light_torso", "light_arms", "light_legs", "medium_torso", "heavy_torso"):
            self.spawn_loot("armor", armor, 1)
        for _ in range(self._loot_count(24, minimum=8)):
            self.spawn_loot("ammo", "ammo_pack", self.rng.randint(12, 34))
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

    def add_player(self, name: str, player_id: str | None = None) -> PlayerState:
        with self._lock:
            return self.ctx.player_service.create_player(name, player_id)

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

    def spawn_zombie(self, kind: str | None = None, pos: Vec2 | None = None) -> ZombieState | None:
        return self.ctx.spawning.spawn_zombie(kind=kind, pos=pos)

    def _loot_count(self, base: int, minimum: int = 1) -> int:
        return max(minimum, int(round(base * self.difficulty.loot_spawn_multiplier)))

    def spawn_loot(
        self,
        kind: str,
        payload: str,
        amount: int,
        rarity: str | None = None,
    ) -> None:
        pos = self.ctx.buildings.random_open_pos(
            centered=False,
            rng=self.rng,
            blocked_at=lambda p, r: self.ctx.geometry.blocked_at(p, r, 0),
        )

        self.ctx.events.emit(
            SpawnLootEvent(
                pos=pos,
                kind=kind,
                payload=payload,
                amount=amount,
                floor=0,
                rarity=rarity or self.ctx.loot.loot_rarity(kind, payload),
            )
        )

    def _spawn_loot_at(
            self,
            pos: Vec2,
            kind: str,
            payload: str,
            amount: int,
            floor: int = 0,
            rarity: str | None = None,
    ) -> None:
        self.ctx.events.emit(
            SpawnLootEvent(
                pos=pos,
                kind=kind,
                payload=payload,
                amount=amount,
                floor=floor,
                rarity=rarity or self.ctx.loot.loot_rarity(kind, payload),
            )
        )

    def _drop_from_zombie(self, pos: Vec2) -> None:
        kind = self.rng.choice(["ammo", "medkit"])
        payload = "ammo_pack" if kind == "ammo" else "medkit"
        amount = self.rng.randint(5, 18) if kind == "ammo" else 1

        self.ctx.events.emit(
            SpawnLootEvent(
                pos=pos.copy(),
                kind=kind,
                payload=payload,
                amount=amount,
                floor=0,
                rarity=self.ctx.loot.loot_rarity(kind, payload),
            )
        )

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


def _clean_player_name(name: str) -> str:
    return "Operator" if not name.strip() else name.strip()[:18]
