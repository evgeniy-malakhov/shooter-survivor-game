from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from shared.models import Vec2


class ZombieEcologyMode(str, Enum):
    DORMANT = "dormant"
    WANDER = "wander"
    ALERTED = "alerted"
    INVESTIGATE = "investigate"
    STALK = "stalk"
    FRENZY = "frenzy"
    FEED = "feed"
    PANIC = "panic"
    MIGRATE = "migrate"


@dataclass(slots=True)
class ZombieInterest:
    visual: float = 0.0
    memory: float = 0.0
    sound: float = 0.0
    horde: float = 0.0

    @property
    def total(self) -> float:
        return self.visual + self.memory + self.sound + self.horde

    def to_dict(self) -> dict[str, float]:
        return {
            "visual": round(self.visual, 3),
            "memory": round(self.memory, 3),
            "sound": round(self.sound, 3),
            "horde": round(self.horde, 3),
            "total": round(self.total, 3),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ZombieInterest":
        if not data:
            return cls()
        return cls(
            visual=float(data.get("visual", 0.0)),
            memory=float(data.get("memory", 0.0)),
            sound=float(data.get("sound", 0.0)),
            horde=float(data.get("horde", 0.0)),
        )


@dataclass(slots=True)
class HordePressureZone:
    id: str
    center: Vec2
    floor: int = 0
    radius: float = 900.0
    pressure: float = 0.0
    aggression: float = 0.0
    density: int = 0
    target_pos: Vec2 | None = None
    last_noise_at: float = 0.0
    expires_at: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "center": self.center.to_dict(),
            "floor": self.floor,
            "radius": round(self.radius, 3),
            "pressure": round(self.pressure, 3),
            "aggression": round(self.aggression, 3),
            "density": self.density,
            "target_pos": self.target_pos.to_dict() if self.target_pos else None,
            "last_noise_at": round(self.last_noise_at, 3),
            "expires_at": round(self.expires_at, 3),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HordePressureZone":
        target = data.get("target_pos")
        return cls(
            id=str(data.get("id", "")),
            center=Vec2.from_dict(data.get("center", {})),
            floor=int(data.get("floor", 0)),
            radius=float(data.get("radius", 900.0)),
            pressure=float(data.get("pressure", 0.0)),
            aggression=float(data.get("aggression", 0.0)),
            density=int(data.get("density", 0)),
            target_pos=Vec2.from_dict(target) if isinstance(target, dict) else None,
            last_noise_at=float(data.get("last_noise_at", 0.0)),
            expires_at=float(data.get("expires_at", 0.0)),
        )


@dataclass(slots=True)
class DistrictSimulationState:
    id: str
    title: str
    center: Vec2
    radius: float
    floor: int = 0
    military_control: float = 0.0
    zombie_pressure: float = 0.0
    loot_remaining: float = 1.0
    danger_level: float = 0.0
    noise_level: float = 0.0
    territory_owner: str = "neutral"
    lockdown: bool = False
    infestation_level: float = 0.0
    civilian_population: float = 1.0
    military_strength: float = 0.0
    infrastructure_integrity: float = 1.0
    electricity_level: float = 1.0
    food_supply: float = 1.0
    medical_supply: float = 1.0
    morale: float = 0.55
    quarantine_level: float = 0.0
    tags: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "center": self.center.to_dict(),
            "radius": round(self.radius, 3),
            "floor": self.floor,
            "military_control": round(self.military_control, 3),
            "zombie_pressure": round(self.zombie_pressure, 3),
            "loot_remaining": round(self.loot_remaining, 3),
            "danger_level": round(self.danger_level, 3),
            "noise_level": round(self.noise_level, 3),
            "territory_owner": self.territory_owner,
            "lockdown": self.lockdown,
            "infestation_level": round(self.infestation_level, 3),
            "civilian_population": round(self.civilian_population, 3),
            "military_strength": round(self.military_strength, 3),
            "infrastructure_integrity": round(self.infrastructure_integrity, 3),
            "electricity_level": round(self.electricity_level, 3),
            "food_supply": round(self.food_supply, 3),
            "medical_supply": round(self.medical_supply, 3),
            "morale": round(self.morale, 3),
            "quarantine_level": round(self.quarantine_level, 3),
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DistrictSimulationState":
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "")),
            center=Vec2.from_dict(data.get("center", {})),
            radius=float(data.get("radius", 0.0)),
            floor=int(data.get("floor", 0)),
            military_control=float(data.get("military_control", 0.0)),
            zombie_pressure=float(data.get("zombie_pressure", 0.0)),
            loot_remaining=float(data.get("loot_remaining", 1.0)),
            danger_level=float(data.get("danger_level", 0.0)),
            noise_level=float(data.get("noise_level", 0.0)),
            territory_owner=str(data.get("territory_owner", "neutral")),
            lockdown=bool(data.get("lockdown", False)),
            infestation_level=float(data.get("infestation_level", data.get("zombie_pressure", 0.0))),
            civilian_population=float(data.get("civilian_population", 1.0)),
            military_strength=float(data.get("military_strength", data.get("military_control", 0.0))),
            infrastructure_integrity=float(data.get("infrastructure_integrity", 1.0)),
            electricity_level=float(data.get("electricity_level", 1.0)),
            food_supply=float(data.get("food_supply", 1.0)),
            medical_supply=float(data.get("medical_supply", 1.0)),
            morale=float(data.get("morale", 0.55)),
            quarantine_level=float(data.get("quarantine_level", 0.0)),
            tags=tuple(str(tag) for tag in data.get("tags", ())),
        )
