from __future__ import annotations

import random
import threading
from typing import TYPE_CHECKING, Protocol
from dataclasses import dataclass

from shared.backpack_config import BackpackConfig
from shared.concurrency.process_pool_service import ProcessPoolService
from shared.concurrency.thread_pool_service import ThreadPoolService
from shared.difficulty import DifficultyConfig
from shared.systems.players.player_service import PlayerService
from shared.world.id_generator import IdGenerator

from shared.systems.combat.damage_service import DamageService
from shared.systems.sounds.sound_service import SoundService

from shared.systems.loot.loot_service import LootService

from shared.systems.spawning.spawn_service import SpawnService

from shared.systems.geometry.geometry_service import GeometryService
from shared.systems.geometry.building_service import BuildingService
from shared.systems.geometry.movement_service import MovementService

from shared.systems.players.respawn_service import RespawnService
from shared.systems.combat.weapon_runtime_service import WeaponRuntimeService
from shared.systems.combat.player_combat_service import PlayerCombatService
from shared.systems.inventory.inventory_service import InventoryService
from shared.systems.interactions.interaction_service import InteractionService
from shared.systems.actors.soldier_runtime_service import SoldierRuntimeService
from shared.systems.actors.zombie_runtime_service import ZombieRuntimeService
from shared.systems.players.player_status_service import PlayerStatusService
from shared.systems.spatial.spatial_index_service import SpatialIndexService

from shared.systems.events.event_buffer import EventBuffer

if TYPE_CHECKING:
    from shared.systems.actors.decision.actor_decision_executor import ActorDecisionExecutor
    from shared.systems.actors.decision.actor_snapshot_builder import ActorSnapshotBuilder


@dataclass(slots=True)
class WorldContext:
    rng: random.Random
    lock: threading.RLock
    geometry_cache_lock: threading.Lock

    ids: IdGenerator

    player_service: PlayerService

    difficulty: DifficultyConfig
    backpack_config: BackpackConfig

    process_pool: ProcessPoolService
    thread_pool: ThreadPoolService

    geometry: GeometryService
    buildings: BuildingService
    movement: MovementService

    damage: DamageService
    sounds: SoundService

    loot: LootService

    max_zombies: int
    spawning: SpawnService
    respawn: RespawnService
    weapons: WeaponRuntimeService
    player_combat: PlayerCombatService
    player_status: PlayerStatusService
    inventory: InventoryService
    interactions: InteractionService
    soldier_runtime: SoldierRuntimeService
    zombie_runtime: ZombieRuntimeService
    actor_snapshots: ActorSnapshotBuilder
    actor_decisions: ActorDecisionExecutor

    events: EventBuffer
    spatial: SpatialIndexService
