from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from shared.factions import FACTION_INFECTED, FACTION_MILITARY, FACTION_NEUTRAL
from shared.models import Vec2


class EscalationLevel(str, Enum):
    CALM = "calm"
    TENSE = "tense"
    CONTACT = "contact"
    LOCKDOWN = "lockdown"
    COLLAPSE = "collapse"


class TerritoryOwner(str, Enum):
    NEUTRAL = "neutral"
    MILITARY = "military"
    INFECTED = "infected"
    CONTESTED = "contested"
    SURVIVORS = "survivors"


class ReinforcementType(str, Enum):
    PATROL = "patrol"
    HEAVY_SQUAD = "heavy_squad"
    EXTRACTION_UNIT = "extraction_unit"
    SNIPER_TEAM = "sniper_team"
    APC_CONVOY = "apc_convoy"


class ConvoyStatus(str, Enum):
    EN_ROUTE = "en_route"
    ARRIVED = "arrived"
    DESTROYED = "destroyed"
    RAIDED = "raided"


class SafeZoneStatus(str, Enum):
    INACTIVE = "inactive"
    FORMING = "forming"
    ACTIVE = "active"
    COLLAPSING = "collapsing"
    LOST = "lost"


@dataclass(slots=True)
class BattleEscalationState:
    district_id: str
    score: float = 0.0
    level: EscalationLevel = EscalationLevel.CALM
    territory_owner: TerritoryOwner = TerritoryOwner.NEUTRAL
    radio_activity: float = 0.0
    lockdown: bool = False
    last_event_at: float = 0.0
    reinforcement_cooldown: float = 0.0
    wave_cooldown: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "district_id": self.district_id,
            "score": round(self.score, 3),
            "level": self.level.value,
            "territory_owner": self.territory_owner.value,
            "radio_activity": round(self.radio_activity, 3),
            "lockdown": self.lockdown,
            "last_event_at": round(self.last_event_at, 3),
            "reinforcement_cooldown": round(self.reinforcement_cooldown, 3),
            "wave_cooldown": round(self.wave_cooldown, 3),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BattleEscalationState":
        return cls(
            district_id=str(data.get("district_id", "")),
            score=float(data.get("score", 0.0)),
            level=_enum(EscalationLevel, data.get("level"), EscalationLevel.CALM),
            territory_owner=_enum(TerritoryOwner, data.get("territory_owner"), TerritoryOwner.NEUTRAL),
            radio_activity=float(data.get("radio_activity", 0.0)),
            lockdown=bool(data.get("lockdown", False)),
            last_event_at=float(data.get("last_event_at", 0.0)),
            reinforcement_cooldown=float(data.get("reinforcement_cooldown", 0.0)),
            wave_cooldown=float(data.get("wave_cooldown", 0.0)),
        )


@dataclass(slots=True)
class ReinforcementRequest:
    id: str
    district_id: str
    kind: ReinforcementType
    target_pos: Vec2
    floor: int = 0
    priority: float = 0.0
    requested_at: float = 0.0
    arrives_at: float = 0.0
    status: str = "pending"
    squad_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "district_id": self.district_id,
            "kind": self.kind.value,
            "target_pos": self.target_pos.to_dict(),
            "floor": self.floor,
            "priority": round(self.priority, 3),
            "requested_at": round(self.requested_at, 3),
            "arrives_at": round(self.arrives_at, 3),
            "status": self.status,
            "squad_id": self.squad_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReinforcementRequest":
        return cls(
            id=str(data.get("id", "")),
            district_id=str(data.get("district_id", "")),
            kind=_enum(ReinforcementType, data.get("kind"), ReinforcementType.PATROL),
            target_pos=Vec2.from_dict(data.get("target_pos", {})),
            floor=int(data.get("floor", 0)),
            priority=float(data.get("priority", 0.0)),
            requested_at=float(data.get("requested_at", 0.0)),
            arrives_at=float(data.get("arrives_at", 0.0)),
            status=str(data.get("status", "pending")),
            squad_id=str(data["squad_id"]) if data.get("squad_id") else None,
        )


@dataclass(slots=True)
class CivilianState:
    id: str
    pos: Vec2
    floor: int = 0
    health: int = 60
    mode: str = "hide"
    panic: float = 0.0
    trust: float = 0.5
    faction: str = FACTION_NEUTRAL
    last_safe_pos: Vec2 | None = None
    help_timer: float = 0.0

    @property
    def alive(self) -> bool:
        return self.health > 0

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "pos": self.pos.to_dict(),
            "floor": self.floor,
            "health": self.health,
            "mode": self.mode,
            "panic": round(self.panic, 3),
            "trust": round(self.trust, 3),
            "faction": self.faction,
            "last_safe_pos": self.last_safe_pos.to_dict() if self.last_safe_pos else None,
            "help_timer": round(self.help_timer, 3),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CivilianState":
        raw_safe = data.get("last_safe_pos")
        return cls(
            id=str(data.get("id", "")),
            pos=Vec2.from_dict(data.get("pos", {})),
            floor=int(data.get("floor", 0)),
            health=int(data.get("health", 60)),
            mode=str(data.get("mode", "hide")),
            panic=float(data.get("panic", 0.0)),
            trust=float(data.get("trust", 0.5)),
            faction=str(data.get("faction", FACTION_NEUTRAL)),
            last_safe_pos=Vec2.from_dict(raw_safe) if isinstance(raw_safe, dict) else None,
            help_timer=float(data.get("help_timer", 0.0)),
        )


@dataclass(slots=True)
class ResourceScarcityState:
    district_id: str
    ammo: float = 0.0
    medicine: float = 0.0
    food: float = 0.0
    fuel: float = 0.0
    last_update: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "district_id": self.district_id,
            "ammo": round(self.ammo, 3),
            "medicine": round(self.medicine, 3),
            "food": round(self.food, 3),
            "fuel": round(self.fuel, 3),
            "last_update": round(self.last_update, 3),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResourceScarcityState":
        return cls(
            district_id=str(data.get("district_id", "")),
            ammo=float(data.get("ammo", 0.0)),
            medicine=float(data.get("medicine", 0.0)),
            food=float(data.get("food", 0.0)),
            fuel=float(data.get("fuel", 0.0)),
            last_update=float(data.get("last_update", 0.0)),
        )


@dataclass(slots=True)
class SupplyConvoyState:
    id: str
    district_id: str
    pos: Vec2
    target_pos: Vec2
    floor: int = 0
    ammo: float = 0.0
    medicine: float = 0.0
    food: float = 0.0
    fuel: float = 0.0
    guard_strength: float = 0.5
    status: ConvoyStatus = ConvoyStatus.EN_ROUTE
    started_at: float = 0.0
    eta: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "district_id": self.district_id,
            "pos": self.pos.to_dict(),
            "target_pos": self.target_pos.to_dict(),
            "floor": self.floor,
            "ammo": round(self.ammo, 3),
            "medicine": round(self.medicine, 3),
            "food": round(self.food, 3),
            "fuel": round(self.fuel, 3),
            "guard_strength": round(self.guard_strength, 3),
            "status": self.status.value,
            "started_at": round(self.started_at, 3),
            "eta": round(self.eta, 3),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SupplyConvoyState":
        return cls(
            id=str(data.get("id", "")),
            district_id=str(data.get("district_id", "")),
            pos=Vec2.from_dict(data.get("pos", {})),
            target_pos=Vec2.from_dict(data.get("target_pos", {})),
            floor=int(data.get("floor", 0)),
            ammo=float(data.get("ammo", 0.0)),
            medicine=float(data.get("medicine", 0.0)),
            food=float(data.get("food", 0.0)),
            fuel=float(data.get("fuel", 0.0)),
            guard_strength=float(data.get("guard_strength", 0.5)),
            status=_enum(ConvoyStatus, data.get("status"), ConvoyStatus.EN_ROUTE),
            started_at=float(data.get("started_at", 0.0)),
            eta=float(data.get("eta", 0.0)),
        )


@dataclass(slots=True)
class SafeZoneState:
    id: str
    district_id: str
    pos: Vec2
    floor: int = 0
    radius: float = 420.0
    status: SafeZoneStatus = SafeZoneStatus.INACTIVE
    trader_active: bool = False
    medic_active: bool = False
    storage_active: bool = False
    mission_board_active: bool = False
    stability: float = 0.0
    collapse_risk: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "district_id": self.district_id,
            "pos": self.pos.to_dict(),
            "floor": self.floor,
            "radius": round(self.radius, 3),
            "status": self.status.value,
            "trader_active": self.trader_active,
            "medic_active": self.medic_active,
            "storage_active": self.storage_active,
            "mission_board_active": self.mission_board_active,
            "stability": round(self.stability, 3),
            "collapse_risk": round(self.collapse_risk, 3),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SafeZoneState":
        return cls(
            id=str(data.get("id", "")),
            district_id=str(data.get("district_id", "")),
            pos=Vec2.from_dict(data.get("pos", {})),
            floor=int(data.get("floor", 0)),
            radius=float(data.get("radius", 420.0)),
            status=_enum(SafeZoneStatus, data.get("status"), SafeZoneStatus.INACTIVE),
            trader_active=bool(data.get("trader_active", False)),
            medic_active=bool(data.get("medic_active", False)),
            storage_active=bool(data.get("storage_active", False)),
            mission_board_active=bool(data.get("mission_board_active", False)),
            stability=float(data.get("stability", 0.0)),
            collapse_risk=float(data.get("collapse_risk", 0.0)),
        )


def territory_owner(*, military_control: float, zombie_pressure: float) -> TerritoryOwner:
    if zombie_pressure >= 0.72 and military_control <= 0.28:
        return TerritoryOwner.INFECTED
    if military_control >= 0.68 and zombie_pressure <= 0.42:
        return TerritoryOwner.MILITARY
    if abs(military_control - zombie_pressure) <= 0.22 or (military_control >= 0.35 and zombie_pressure >= 0.35):
        return TerritoryOwner.CONTESTED
    return TerritoryOwner.MILITARY if military_control > zombie_pressure else TerritoryOwner.INFECTED


def reinforcement_for_level(level: EscalationLevel, owner: TerritoryOwner) -> ReinforcementType:
    if level == EscalationLevel.COLLAPSE:
        return ReinforcementType.APC_CONVOY if owner == TerritoryOwner.MILITARY else ReinforcementType.HEAVY_SQUAD
    if level == EscalationLevel.LOCKDOWN:
        return ReinforcementType.HEAVY_SQUAD
    if level == EscalationLevel.CONTACT:
        return ReinforcementType.PATROL
    return ReinforcementType.PATROL


def _enum(enum_cls, value: object, fallback):
    try:
        return enum_cls(str(value))
    except ValueError:
        return fallback
