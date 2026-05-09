from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque

from shared.combat_ecosystem import (
    BattleEscalationState,
    CivilianState,
    ReinforcementRequest,
    ResourceScarcityState,
    SafeZoneState,
    SupplyConvoyState,
)
from shared.models import (
    BuildingState,
    GrenadeState,
    InputCommand,
    LootState,
    MineState,
    PlayerState,
    PoisonPoolState,
    PoisonProjectileState,
    ProjectileState,
    RectState,
    SoldierState,
    ZombieState,
)
from shared.ai.context import SoundEvent
from shared.ai.squads import SquadState
from shared.ai.zombie_ecology import DistrictSimulationState, HordePressureZone
from shared.maps.core.map_types import MapZone


@dataclass(slots=True)
class WorldState:
    time: float = 0.0
    map_id: str = "forest_outpost"
    map_width: int = 1
    map_height: int = 1

    players: dict[str, PlayerState] = field(default_factory=dict)
    zombies: dict[str, ZombieState] = field(default_factory=dict)
    soldiers: dict[str, SoldierState] = field(default_factory=dict)
    squads: dict[str, SquadState] = field(default_factory=dict)
    horde_pressure_zones: dict[str, HordePressureZone] = field(default_factory=dict)
    district_simulation: dict[str, DistrictSimulationState] = field(default_factory=dict)
    map_zones: list[MapZone] = field(default_factory=list)
    battle_escalation: dict[str, BattleEscalationState] = field(default_factory=dict)
    reinforcement_requests: dict[str, ReinforcementRequest] = field(default_factory=dict)
    civilians: dict[str, CivilianState] = field(default_factory=dict)
    resource_scarcity: dict[str, ResourceScarcityState] = field(default_factory=dict)
    supply_convoys: dict[str, SupplyConvoyState] = field(default_factory=dict)
    safe_zones: dict[str, SafeZoneState] = field(default_factory=dict)

    projectiles: dict[str, ProjectileState] = field(default_factory=dict)
    grenades: dict[str, GrenadeState] = field(default_factory=dict)
    mines: dict[str, MineState] = field(default_factory=dict)
    poison_projectiles: dict[str, PoisonProjectileState] = field(default_factory=dict)
    poison_pools: dict[str, PoisonPoolState] = field(default_factory=dict)

    loot: dict[str, LootState] = field(default_factory=dict)
    inputs: dict[str, InputCommand] = field(default_factory=dict)
    buildings: dict[str, BuildingState] = field(default_factory=dict)

    sound_events: list[SoundEvent] = field(default_factory=list)
    domain_events: Deque[dict[str, Any]] = field(default_factory=deque)

    grenade_cooldowns: dict[str, float] = field(default_factory=dict)

    spawn_timer: float = 0.0
    loot_timer: float = 0.0

    geometry_version: int = 0
    closed_walls_cache: dict[int, tuple[int, tuple[RectState, ...]]] = field(default_factory=dict)
