from __future__ import annotations

import random
import threading
from dataclasses import dataclass

from shared.ai.pathfinding import GridPathfinder
from shared.ai.registry import ZOMBIE_AI_REGISTRY
from shared.ai.soldiers.registry import SOLDIER_AI_REGISTRY
from shared.backpack_config import load_backpack_config
from shared.concurrency.executor_config import build_executor_config
from shared.concurrency.process_pool_service import ProcessPoolService
from shared.concurrency.thread_pool_service import ThreadPoolService
from shared.difficulty import load_difficulty
from shared.maps.registry import DEFAULT_MAP_REGISTRY
from shared.maps.core.map_runtime import MapRuntime
from shared.maps.loading.loading_screen_state import LoadingScreenState
from shared.maps.loading.loading_stage import LoadingStage
from shared.systems.actors.soldier_runtime_service import SoldierRuntimeService
from shared.systems.actors.soldier_runtime_system import SoldierRuntimeSystem
from shared.systems.actors.zombie_runtime_service import ZombieRuntimeService
from shared.systems.actors.zombie_runtime_system import ZombieRuntimeSystem
from shared.systems.actors.decision import (
    ActorDecisionExecutionConfig,
    ActorDecisionExecutor,
    ActorDecisionRegistry,
    ActorSnapshotBuilder,
)
from shared.systems.actors.decision.workers import SoldierDecisionWorker, ZombieDecisionWorker
from shared.systems.bootstrap.map_bootstrap_service import MapBootstrapService
from shared.systems.commands.command_router import CommandRouter
from shared.systems.commands.command_router_factory import build_command_router
from shared.systems.combat.damage_service import DamageService
from shared.systems.combat.player_combat_service import PlayerCombatService
from shared.systems.combat.projectile_system import ProjectileSystem
from shared.systems.combat.weapon_runtime_service import WeaponRuntimeService
from shared.systems.events.event_apply_system import EventApplySystem
from shared.systems.events.event_buffer import EventBuffer
from shared.systems.explosives.explosive_system import ExplosiveSystem
from shared.systems.geometry.building_service import BuildingService
from shared.systems.geometry.geometry_service import GeometryService
from shared.systems.geometry.movement_service import MovementService
from shared.systems.interactions.interaction_service import InteractionService
from shared.systems.inventory.inventory_service import InventoryService
from shared.systems.loot.loot_service import LootService
from shared.systems.loot.loot_drop_service import LootDropService
from shared.systems.loot.loot_spawn_system import LootSpawnSystem
from shared.systems.players.player_service import PlayerService
from shared.systems.players.player_status_service import PlayerStatusService
from shared.systems.players.player_update_system import PlayerUpdateSystem
from shared.systems.players.respawn_service import RespawnService
from shared.systems.poison.poison_system import PoisonSystem
from shared.systems.scheduler import SystemScheduler
from shared.systems.sounds.sound_service import SoundService
from shared.systems.sounds.sound_system import SoundSystem
from shared.systems.spatial.spatial_index_service import SpatialIndexService
from shared.systems.spatial.spatial_index_system import SpatialIndexSystem
from shared.systems.spawning.spawn_service import SpawnService
from shared.systems.spawning.zombie_spawn_system import ZombieSpawnSystem
from shared.world.id_generator import IdGenerator
from shared.world.world_config import WorldConfig
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState



@dataclass(slots=True)
class WorldComposition:
    state: WorldState
    ctx: WorldContext
    systems: SystemScheduler
    map_bootstrap: MapBootstrapService
    command_router: CommandRouter
    executor_config: object
    difficulty: object
    backpack_config: object


def build_world_composition(
    *,
    config: WorldConfig,
    get_time,
    initial_zombies: int,
    max_zombies: int,
    loading_state: LoadingScreenState | None = None,
) -> WorldComposition:
    state = WorldState()

    map_runtime = MapRuntime(DEFAULT_MAP_REGISTRY)
    map_result = map_runtime.start_map(config.map_id, loading_state)
    state.map_id = map_result.map_id
    state.map_width = map_result.width
    state.map_height = map_result.height
    state.buildings = map_result.buildings

    id_generator = IdGenerator()

    lock = threading.RLock()
    geometry_cache_lock = threading.Lock()

    rng = random.Random(config.seed)
    difficulty = load_difficulty(config.difficulty_key)
    backpack_config = load_backpack_config()

    event_buffer = EventBuffer()

    geometry_service = GeometryService(
        buildings=state.buildings,
        cache_lock=geometry_cache_lock,
    )

    building_service = BuildingService(
        buildings=state.buildings,
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

    sound_service = SoundService(state=state)
    loot_service = LootService(state=state, rng=rng)
    loot_drop_service = LootDropService(
        rng=rng,
        events=event_buffer,
        loot=loot_service,
    )
    damage_service = DamageService(
        players=state.players,
        zombies=state.zombies,
        soldiers=state.soldiers,
        difficulty=difficulty,
        rng=rng,
        drop_from_zombie=loot_drop_service.drop_from_zombie,
        zombie_ai_generation={},
        zombie_ai_pending={},
        zombie_ai_next_at={},
        get_time=get_time,
    )
    spatial_service = SpatialIndexService(cell_size=256)
    command_router = build_command_router()

    spawn_service = SpawnService(
        state=state,
        rng=rng,
        ids=id_generator,
        geometry=geometry_service,
        difficulty=difficulty,
        max_zombies=max_zombies,
    )

    respawn_service = RespawnService(
        state=state,
        rng=rng,
        geometry=geometry_service,
        spatial=spatial_service,
    )

    weapon_runtime_service = WeaponRuntimeService()

    player_combat_service = PlayerCombatService(
        state=state,
        rng=rng,
    )

    soldier_runtime_service = SoldierRuntimeService(
        state=state,
        rng=rng,
        soldier_ai_registry=SOLDIER_AI_REGISTRY,
    )

    zombie_pathfinder = GridPathfinder(cell_size=96)

    zombie_runtime_service = ZombieRuntimeService(
        state=state,
        rng=rng,
        zombie_ai_registry=ZOMBIE_AI_REGISTRY,
        difficulty=difficulty,
        pathfinder=zombie_pathfinder,
    )

    actor_decision_registry = ActorDecisionRegistry()
    actor_decision_registry.register("zombie", ZombieDecisionWorker())
    actor_decision_registry.register("soldier", SoldierDecisionWorker())

    actor_snapshot_builder = ActorSnapshotBuilder()
    actor_decision_executor = ActorDecisionExecutor(
        actor_decision_registry,
        ActorDecisionExecutionConfig(
            sync_actor_limit=config.actor_decision_sync_actor_limit,
            thread_actor_limit=config.actor_decision_thread_actor_limit,
            process_actor_limit=config.actor_decision_process_actor_limit,
            enable_threads=config.actor_decision_enable_threads,
            enable_processes=config.actor_decision_enable_processes,
        ),
    )

    inventory_service = InventoryService(
        state=state,
        rng=rng,
        backpack_config=backpack_config,
        loot=loot_service,
        buildings=building_service,
        ids=id_generator,
        events=event_buffer,
        spatial=spatial_service,
    )

    player_service = PlayerService(
        state=state,
        rng=rng,
        backpack_config=backpack_config,
        ids=id_generator,
        inventory=inventory_service,
    )

    interaction_service = InteractionService(
        state=state,
        buildings=building_service,
        geometry=geometry_service,
    )

    player_status_service = PlayerStatusService()

    ctx = WorldContext(
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
        max_zombies=max_zombies,
        spawning=spawn_service,
        respawn=respawn_service,
        weapons=weapon_runtime_service,
        player_combat=player_combat_service,
        player_status=player_status_service,
        inventory=inventory_service,
        interactions=interaction_service,
        soldier_runtime=soldier_runtime_service,
        zombie_runtime=zombie_runtime_service,
        actor_snapshots=actor_snapshot_builder,
        actor_decisions=actor_decision_executor,
        spatial=spatial_service,
        events=event_buffer,
    )

    systems = SystemScheduler([
        PlayerUpdateSystem(),
        SpatialIndexSystem(),
        ProjectileSystem(),
        ExplosiveSystem(),
        PoisonSystem(),
        ZombieSpawnSystem(),
        LootSpawnSystem(),
        SoundSystem(),
        ZombieRuntimeSystem(),
        SpatialIndexSystem(),
        SoldierRuntimeSystem(),
        EventApplySystem(),
    ])

    map_bootstrap = MapBootstrapService(
        state=state,
        rng=rng,
        difficulty=difficulty,
        buildings=building_service,
        geometry=geometry_service,
        spawning=spawn_service,
        events=event_buffer,
        initial_zombies=initial_zombies,
        max_zombies=max_zombies,
    )

    if loading_state is not None:
        loading_state.update(LoadingStage.COMPOSE_WORLD, "World systems ready", 0.98)

    return WorldComposition(
        state=state,
        ctx=ctx,
        systems=systems,
        map_bootstrap=map_bootstrap,
        command_router=command_router,
        executor_config=executor_config,
        difficulty=difficulty,
        backpack_config=backpack_config,
    )
