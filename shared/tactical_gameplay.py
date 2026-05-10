from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from shared.models import RectState, Vec2


class BuildingPowerState(str, Enum):
    POWERED = "powered"
    PARTIAL = "partial"
    BLACKOUT = "blackout"
    EMERGENCY = "emergency"


class MissionKind(str, Enum):
    RESCUE_CIVILIAN = "rescue_civilian"
    ESCORT_CONVOY = "escort_convoy"
    CLEAR_INFESTATION = "clear_infestation"
    RESTORE_POWER = "restore_power"
    DEFEND_SAFE_ZONE = "defend_safe_zone"
    RETRIEVE_MEDICINE = "retrieve_medicine"
    RETRIEVE_AMMO = "retrieve_ammo"
    SABOTAGE_OUTPOST = "sabotage_outpost"


class MissionStatus(str, Enum):
    AVAILABLE = "available"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class ExtractionStatus(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    CONTESTED = "contested"
    EVACUATING = "evacuating"


class CompanionCommandKind(str, Enum):
    FOLLOW = "follow"
    HOLD = "hold"
    REGROUP = "regroup"
    BREACH = "breach"
    SUPPRESS = "suppress"
    HEAL = "heal"
    LOOT = "loot"
    SILENT = "silent"


class DirectorPressure(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    RELIEF = "relief"


@dataclass(slots=True)
class BuildingRoomState:
    id: str
    building_id: str
    rect: RectState
    floor: int = 0
    loot_zone: bool = False
    danger_score: float = 0.0
    occupants: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "building_id": self.building_id,
            "rect": self.rect.to_dict(),
            "floor": self.floor,
            "loot_zone": self.loot_zone,
            "danger_score": round(self.danger_score, 3),
            "occupants": list(self.occupants),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BuildingRoomState":
        return cls(
            id=str(data.get("id", "")),
            building_id=str(data.get("building_id", "")),
            rect=RectState.from_dict(data.get("rect", {})),
            floor=int(data.get("floor", 0)),
            loot_zone=bool(data.get("loot_zone", False)),
            danger_score=float(data.get("danger_score", 0.0)),
            occupants=[str(value) for value in data.get("occupants", [])],
        )


@dataclass(slots=True)
class BuildingTacticalState:
    id: str
    rooms: list[BuildingRoomState] = field(default_factory=list)
    windows: list[RectState] = field(default_factory=list)
    breach_points: list[RectState] = field(default_factory=list)
    light_state: BuildingPowerState = BuildingPowerState.POWERED
    noise_level: float = 0.0
    occupants: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "rooms": [room.to_dict() for room in self.rooms],
            "windows": [window.to_dict() for window in self.windows],
            "breach_points": [point.to_dict() for point in self.breach_points],
            "light_state": self.light_state.value,
            "noise_level": round(self.noise_level, 3),
            "occupants": list(self.occupants),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BuildingTacticalState":
        return cls(
            id=str(data.get("id", "")),
            rooms=[BuildingRoomState.from_dict(room) for room in data.get("rooms", [])],
            windows=[RectState.from_dict(window) for window in data.get("windows", [])],
            breach_points=[RectState.from_dict(point) for point in data.get("breach_points", [])],
            light_state=_enum(BuildingPowerState, data.get("light_state"), BuildingPowerState.POWERED),
            noise_level=float(data.get("noise_level", 0.0)),
            occupants=[str(value) for value in data.get("occupants", [])],
        )


@dataclass(slots=True)
class MissionState:
    id: str
    kind: MissionKind
    district_id: str
    title_key: str
    objective_key: str
    target_pos: Vec2
    floor: int = 0
    risk: float = 0.0
    reward_score: float = 0.0
    status: MissionStatus = MissionStatus.AVAILABLE
    source_safe_zone_id: str | None = None
    expires_at: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "district_id": self.district_id,
            "title_key": self.title_key,
            "objective_key": self.objective_key,
            "target_pos": self.target_pos.to_dict(),
            "floor": self.floor,
            "risk": round(self.risk, 3),
            "reward_score": round(self.reward_score, 3),
            "status": self.status.value,
            "source_safe_zone_id": self.source_safe_zone_id,
            "expires_at": round(self.expires_at, 3),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MissionState":
        return cls(
            id=str(data.get("id", "")),
            kind=_enum(MissionKind, data.get("kind"), MissionKind.CLEAR_INFESTATION),
            district_id=str(data.get("district_id", "")),
            title_key=str(data.get("title_key", "")),
            objective_key=str(data.get("objective_key", "")),
            target_pos=Vec2.from_dict(data.get("target_pos", {})),
            floor=int(data.get("floor", 0)),
            risk=float(data.get("risk", 0.0)),
            reward_score=float(data.get("reward_score", 0.0)),
            status=_enum(MissionStatus, data.get("status"), MissionStatus.AVAILABLE),
            source_safe_zone_id=str(data["source_safe_zone_id"]) if data.get("source_safe_zone_id") else None,
            expires_at=float(data.get("expires_at", 0.0)),
        )


@dataclass(slots=True)
class ExtractionPointState:
    id: str
    district_id: str
    pos: Vec2
    floor: int = 0
    radius: float = 260.0
    status: ExtractionStatus = ExtractionStatus.CLOSED
    opens_at: float = 0.0
    closes_at: float = 0.0
    pressure: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "district_id": self.district_id,
            "pos": self.pos.to_dict(),
            "floor": self.floor,
            "radius": round(self.radius, 3),
            "status": self.status.value,
            "opens_at": round(self.opens_at, 3),
            "closes_at": round(self.closes_at, 3),
            "pressure": round(self.pressure, 3),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExtractionPointState":
        return cls(
            id=str(data.get("id", "")),
            district_id=str(data.get("district_id", "")),
            pos=Vec2.from_dict(data.get("pos", {})),
            floor=int(data.get("floor", 0)),
            radius=float(data.get("radius", 260.0)),
            status=_enum(ExtractionStatus, data.get("status"), ExtractionStatus.CLOSED),
            opens_at=float(data.get("opens_at", 0.0)),
            closes_at=float(data.get("closes_at", 0.0)),
            pressure=float(data.get("pressure", 0.0)),
        )


@dataclass(slots=True)
class CompanionCommandState:
    player_id: str
    command: CompanionCommandKind = CompanionCommandKind.FOLLOW
    target_pos: Vec2 | None = None
    issued_at: float = 0.0
    expires_at: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "player_id": self.player_id,
            "command": self.command.value,
            "target_pos": self.target_pos.to_dict() if self.target_pos else None,
            "issued_at": round(self.issued_at, 3),
            "expires_at": round(self.expires_at, 3),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompanionCommandState":
        target = data.get("target_pos")
        return cls(
            player_id=str(data.get("player_id", "")),
            command=_enum(CompanionCommandKind, data.get("command"), CompanionCommandKind.FOLLOW),
            target_pos=Vec2.from_dict(target) if isinstance(target, dict) else None,
            issued_at=float(data.get("issued_at", 0.0)),
            expires_at=float(data.get("expires_at", 0.0)),
        )


@dataclass(slots=True)
class DirectorState:
    pressure: DirectorPressure = DirectorPressure.LOW
    score: float = 0.0
    last_action: str = ""
    next_action_at: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "pressure": self.pressure.value,
            "score": round(self.score, 3),
            "last_action": self.last_action,
            "next_action_at": round(self.next_action_at, 3),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DirectorState":
        return cls(
            pressure=_enum(DirectorPressure, data.get("pressure"), DirectorPressure.LOW),
            score=float(data.get("score", 0.0)),
            last_action=str(data.get("last_action", "")),
            next_action_at=float(data.get("next_action_at", 0.0)),
        )


def _enum(enum_cls, value: object, fallback):
    try:
        return enum_cls(str(value))
    except ValueError:
        return fallback
