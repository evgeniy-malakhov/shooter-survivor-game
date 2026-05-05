from __future__ import annotations
from dataclasses import dataclass
from shared.models import Vec2


class GameEvent:
    pass


@dataclass(slots=True)
class SpawnProjectileEvent(GameEvent):
    owner_id: str
    pos: Vec2
    velocity: Vec2
    damage: int
    life: float
    radius: float
    floor: int
    weapon_key: str


@dataclass(slots=True)
class SpawnPoisonEvent(GameEvent):
    owner_id: str
    pos: Vec2
    velocity: Vec2
    target: Vec2
    floor: int


@dataclass(slots=True)
class SpawnLootEvent(GameEvent):
    pos: Vec2
    kind: str
    payload: str
    amount: int
    floor: int
    rarity: str

@dataclass(slots=True)
class SpawnGrenadeEvent(GameEvent):
    owner_id: str
    kind: str
    pos: Vec2
    velocity: Vec2
    timer: float
    floor: int


@dataclass(slots=True)
class SpawnMineEvent(GameEvent):
    owner_id: str
    kind: str
    pos: Vec2
    floor: int
    armed: bool
    trigger_radius: float
    blast_radius: float


@dataclass(slots=True)
class DamagePlayerEvent(GameEvent):
    player_id: str
    damage: int


@dataclass(slots=True)
class DamageZombieEvent(GameEvent):
    zombie_id: str
    damage: int
    attacker_id: str
    source_pos: Vec2 | None = None
    reveal_owner: bool = True


@dataclass(slots=True)
class DamageSoldierEvent(GameEvent):
    soldier_id: str
    damage: int
    attacker_id: str
    source_pos: Vec2 | None = None
    reveal_owner: bool = True


@dataclass(slots=True)
class ApplyPoisonEvent(GameEvent):
    player_id: str
    damage_per_tick: int
    duration: float = 5.0


@dataclass(slots=True)
class PoisonTickDamageEvent(GameEvent):
    player_id: str
    damage: int


@dataclass(slots=True)
class EmitSoundEvent(GameEvent):
    pos: Vec2
    floor: int
    radius: float
    source_player_id: str | None = None
    kind: str = "generic"
    intensity: float = 1.0