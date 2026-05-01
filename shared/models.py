from __future__ import annotations

from dataclasses import dataclass, field
from math import atan2, hypot
from typing import Any


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(slots=True)
class Vec2:
    x: float
    y: float

    def copy(self) -> "Vec2":
        return Vec2(self.x, self.y)

    def to_dict(self) -> dict[str, float]:
        return {"x": round(self.x, 3), "y": round(self.y, 3)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Vec2":
        return cls(float(data.get("x", 0.0)), float(data.get("y", 0.0)))

    def add(self, other: "Vec2") -> "Vec2":
        self.x += other.x
        self.y += other.y
        return self

    def scaled(self, scale: float) -> "Vec2":
        return Vec2(self.x * scale, self.y * scale)

    def length(self) -> float:
        return hypot(self.x, self.y)

    def normalized(self) -> "Vec2":
        length = self.length()
        if length <= 0.0001:
            return Vec2(0.0, 0.0)
        return Vec2(self.x / length, self.y / length)

    def distance_to(self, other: "Vec2") -> float:
        return hypot(self.x - other.x, self.y - other.y)

    def angle_to(self, other: "Vec2") -> float:
        return atan2(other.y - self.y, other.x - self.x)

    def clamp_to_map(self, width: float, height: float) -> None:
        self.x = clamp(self.x, 0.0, width)
        self.y = clamp(self.y, 0.0, height)


@dataclass(slots=True)
class RectState:
    x: float
    y: float
    w: float
    h: float

    @property
    def center(self) -> Vec2:
        return Vec2(self.x + self.w * 0.5, self.y + self.h * 0.5)

    def contains(self, pos: Vec2) -> bool:
        return self.x <= pos.x <= self.x + self.w and self.y <= pos.y <= self.y + self.h

    def inflated(self, amount: float) -> "RectState":
        return RectState(self.x - amount, self.y - amount, self.w + amount * 2.0, self.h + amount * 2.0)

    def to_dict(self) -> dict[str, float]:
        return {"x": round(self.x, 3), "y": round(self.y, 3), "w": round(self.w, 3), "h": round(self.h, 3)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RectState":
        return cls(
            float(data.get("x", 0.0)),
            float(data.get("y", 0.0)),
            float(data.get("w", 0.0)),
            float(data.get("h", 0.0)),
        )


@dataclass(slots=True)
class DoorState:
    id: str
    rect: RectState
    open: bool = False
    floor: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "rect": self.rect.to_dict(), "open": self.open, "floor": self.floor}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DoorState":
        return cls(
            id=str(data["id"]),
            rect=RectState.from_dict(data.get("rect", {})),
            open=bool(data.get("open", False)),
            floor=int(data.get("floor", 0)),
        )


@dataclass(slots=True)
class PropState:
    id: str
    kind: str
    rect: RectState
    floor: int = 0
    blocks: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "rect": self.rect.to_dict(), "floor": self.floor, "blocks": self.blocks}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PropState":
        return cls(
            id=str(data["id"]),
            kind=str(data.get("kind", "table")),
            rect=RectState.from_dict(data.get("rect", {})),
            floor=int(data.get("floor", 0)),
            blocks=bool(data.get("blocks", True)),
        )


@dataclass(slots=True)
class BuildingState:
    id: str
    name: str
    bounds: RectState
    walls: list[RectState]
    doors: list[DoorState]
    props: list[PropState]
    stairs: list[RectState]
    floors: int = 4
    min_floor: int = -1

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "bounds": self.bounds.to_dict(),
            "walls": [wall.to_dict() for wall in self.walls],
            "doors": [door.to_dict() for door in self.doors],
            "props": [prop.to_dict() for prop in self.props],
            "stairs": [stairs.to_dict() for stairs in self.stairs],
            "floors": self.floors,
            "min_floor": self.min_floor,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BuildingState":
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", "Building")),
            bounds=RectState.from_dict(data.get("bounds", {})),
            walls=[RectState.from_dict(wall) for wall in data.get("walls", [])],
            doors=[DoorState.from_dict(door) for door in data.get("doors", [])],
            props=[PropState.from_dict(prop) for prop in data.get("props", [])],
            stairs=[RectState.from_dict(stairs) for stairs in data.get("stairs", [])],
            floors=int(data.get("floors", 4)),
            min_floor=int(data.get("min_floor", -1)),
        )

    @property
    def max_floor(self) -> int:
        return self.min_floor + self.floors - 1


@dataclass(frozen=True, slots=True)
class ItemSpec:
    key: str
    title: str
    kind: str
    stack_size: int = 1
    heal_total: int = 0
    heal_seconds: float = 0.0
    equipment_slot: str | None = None
    armor_key: str | None = None
    color: tuple[int, int, int] = (220, 220, 220)


@dataclass(slots=True)
class InventoryItem:
    id: str
    key: str
    amount: int = 1
    durability: float = 100.0
    rarity: str = "common"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "key": self.key,
            "amount": self.amount,
            "durability": round(self.durability, 2),
            "rarity": self.rarity,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InventoryItem":
        return cls(
            str(data["id"]),
            str(data["key"]),
            int(data.get("amount", 1)),
            float(data.get("durability", 100.0)),
            str(data.get("rarity", "common")),
        )


@dataclass(frozen=True, slots=True)
class WeaponSpec:
    key: str
    title: str
    slot: str
    damage: int
    magazine_size: int
    fire_rate: float
    reload_time: float
    projectile_speed: float
    spread: float
    pellets: int = 1


@dataclass(frozen=True, slots=True)
class ArmorSpec:
    key: str
    title: str
    mitigation: float
    armor_points: int


@dataclass(frozen=True, slots=True)
class ZombieSpec:
    key: str
    title: str
    health: int
    armor: int
    speed: float
    damage: int
    radius: float
    color: tuple[int, int, int]
    sight_range: float
    hearing_range: float
    fov_degrees: float
    sensitivity: float
    suspicion_time: float


@dataclass(slots=True)
class WeaponRuntime:
    key: str
    ammo_in_mag: int
    reserve_ammo: int
    cooldown: float = 0.0
    reload_left: float = 0.0
    durability: float = 100.0
    rarity: str = "common"
    modules: dict[str, str | None] = field(default_factory=lambda: {"utility": None, "magazine": None})
    utility_on: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "ammo_in_mag": self.ammo_in_mag,
            "reserve_ammo": self.reserve_ammo,
            "cooldown": round(self.cooldown, 3),
            "reload_left": round(self.reload_left, 3),
            "durability": round(self.durability, 2),
            "rarity": self.rarity,
            "modules": dict(self.modules),
            "utility_on": self.utility_on,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WeaponRuntime":
        weapon = cls(
            key=str(data["key"]),
            ammo_in_mag=int(data.get("ammo_in_mag", 0)),
            reserve_ammo=int(data.get("reserve_ammo", 0)),
            cooldown=float(data.get("cooldown", 0.0)),
            reload_left=float(data.get("reload_left", 0.0)),
            durability=float(data.get("durability", 100.0)),
            rarity=str(data.get("rarity", "common")),
        )
        weapon.modules.update({str(slot): value if value is None else str(value) for slot, value in data.get("modules", {}).items()})
        weapon.utility_on = bool(data.get("utility_on", False))
        return weapon


@dataclass(slots=True)
class PlayerState:
    id: str
    name: str
    pos: Vec2
    angle: float = 0.0
    health: int = 100
    armor: int = 0
    armor_key: str = "none"
    speed: float = 245.0
    active_slot: str = "1"
    alive: bool = True
    score: int = 0
    kills_by_kind: dict[str, int] = field(default_factory=dict)
    medkits: int = 0
    owned_armors: list[str] = field(default_factory=lambda: ["none"])
    noise: float = 0.0
    sprinting: bool = False
    floor: int = 0
    inside_building: str | None = None
    sneaking: bool = False
    backpack: list[InventoryItem | None] = field(default_factory=lambda: [None] * 30)
    equipment: dict[str, InventoryItem | None] = field(
        default_factory=lambda: {"head": None, "torso": None, "legs": None, "arms": None}
    )
    quick_items: dict[str, InventoryItem | None] = field(default_factory=dict)
    healing_left: float = 0.0
    healing_rate: float = 0.0
    healing_pool: float = 0.0
    healing_stacks: int = 0
    poison_left: float = 0.0
    poison_tick: float = 0.0
    poison_damage: int = 0
    melee_cooldown: float = 0.0
    notice: str = ""
    notice_timer: float = 0.0
    ping_ms: int = 0
    connection_quality: str = "stable"
    weapons: dict[str, WeaponRuntime] = field(default_factory=dict)

    def active_weapon(self) -> WeaponRuntime | None:
        return self.weapons.get(self.active_slot)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "pos": self.pos.to_dict(),
            "angle": round(self.angle, 4),
            "health": self.health,
            "armor": self.armor,
            "armor_key": self.armor_key,
            "speed": self.speed,
            "active_slot": self.active_slot,
            "alive": self.alive,
            "score": self.score,
            "kills_by_kind": dict(self.kills_by_kind),
            "medkits": self.medkits,
            "owned_armors": list(self.owned_armors),
            "noise": round(self.noise, 3),
            "sprinting": self.sprinting,
            "floor": self.floor,
            "inside_building": self.inside_building,
            "sneaking": self.sneaking,
            "backpack": [item.to_dict() if item else None for item in self.backpack],
            "equipment": {slot: item.to_dict() if item else None for slot, item in self.equipment.items()},
            "quick_items": {slot: item.to_dict() if item else None for slot, item in self.quick_items.items()},
            "healing_left": round(self.healing_left, 3),
            "healing_rate": round(self.healing_rate, 3),
            "healing_pool": round(self.healing_pool, 3),
            "healing_stacks": self.healing_stacks,
            "poison_left": round(self.poison_left, 3),
            "poison_tick": round(self.poison_tick, 3),
            "poison_damage": self.poison_damage,
            "melee_cooldown": round(self.melee_cooldown, 3),
            "notice": self.notice,
            "notice_timer": round(self.notice_timer, 3),
            "ping_ms": self.ping_ms,
            "connection_quality": self.connection_quality,
            "weapons": {slot: weapon.to_dict() for slot, weapon in self.weapons.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlayerState":
        player = cls(
            id=str(data["id"]),
            name=str(data.get("name", "Player")),
            pos=Vec2.from_dict(data.get("pos", {})),
            angle=float(data.get("angle", 0.0)),
            health=int(data.get("health", 100)),
            armor=int(data.get("armor", 0)),
            armor_key=str(data.get("armor_key", "none")),
            speed=float(data.get("speed", 245.0)),
            active_slot=str(data.get("active_slot", "1")),
            alive=bool(data.get("alive", True)),
            score=int(data.get("score", 0)),
            kills_by_kind={str(key): int(value) for key, value in data.get("kills_by_kind", {}).items()},
            medkits=int(data.get("medkits", 0)),
            owned_armors=list(data.get("owned_armors", ["none"])),
            noise=float(data.get("noise", 0.0)),
            sprinting=bool(data.get("sprinting", False)),
            floor=int(data.get("floor", 0)),
            inside_building=data.get("inside_building"),
            sneaking=bool(data.get("sneaking", False)),
            backpack=[InventoryItem.from_dict(item) if item else None for item in data.get("backpack", [None] * 30)],
            equipment={
                str(slot): InventoryItem.from_dict(item) if item else None
                for slot, item in data.get("equipment", {"head": None, "torso": None, "legs": None, "arms": None}).items()
            },
            quick_items={
                str(slot): InventoryItem.from_dict(item) if item else None
                for slot, item in data.get("quick_items", {}).items()
            },
            healing_left=float(data.get("healing_left", 0.0)),
            healing_rate=float(data.get("healing_rate", 0.0)),
            healing_pool=float(data.get("healing_pool", 0.0)),
            healing_stacks=max(0, int(data.get("healing_stacks", 0))),
            poison_left=float(data.get("poison_left", 0.0)),
            poison_tick=float(data.get("poison_tick", 0.0)),
            poison_damage=int(data.get("poison_damage", 0)),
            melee_cooldown=float(data.get("melee_cooldown", 0.0)),
            notice=str(data.get("notice", "")),
            notice_timer=float(data.get("notice_timer", 0.0)),
            ping_ms=int(data.get("ping_ms", 0)),
            connection_quality=str(data.get("connection_quality", "stable")),
        )
        player.weapons = {
            str(slot): WeaponRuntime.from_dict(weapon)
            for slot, weapon in data.get("weapons", {}).items()
        }
        return player


@dataclass(slots=True)
class ZombieState:
    id: str
    kind: str
    pos: Vec2
    health: int
    armor: int
    attack_cooldown: float = 0.0
    mode: str = "patrol"
    facing: float = 0.0
    target_player_id: str | None = None
    last_known_pos: Vec2 | None = None
    waypoint: Vec2 | None = None
    search_timer: float = 0.0
    alertness: float = 0.0
    idle_timer: float = 0.0
    special_cooldown: float = 0.0
    strafe_phase: float = 0.0
    sidestep_bias: float = 0.0
    sidestep_timer: float = 0.0
    floor: int = 0
    inside_building: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "pos": self.pos.to_dict(),
            "health": self.health,
            "armor": self.armor,
            "attack_cooldown": round(self.attack_cooldown, 3),
            "mode": self.mode,
            "facing": round(self.facing, 4),
            "target_player_id": self.target_player_id,
            "last_known_pos": self.last_known_pos.to_dict() if self.last_known_pos else None,
            "waypoint": self.waypoint.to_dict() if self.waypoint else None,
            "search_timer": round(self.search_timer, 3),
            "alertness": round(self.alertness, 3),
            "idle_timer": round(self.idle_timer, 3),
            "special_cooldown": round(self.special_cooldown, 3),
            "strafe_phase": round(self.strafe_phase, 3),
            "sidestep_bias": round(self.sidestep_bias, 3),
            "sidestep_timer": round(self.sidestep_timer, 3),
            "floor": self.floor,
            "inside_building": self.inside_building,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ZombieState":
        return cls(
            id=str(data["id"]),
            kind=str(data["kind"]),
            pos=Vec2.from_dict(data.get("pos", {})),
            health=int(data.get("health", 1)),
            armor=int(data.get("armor", 0)),
            attack_cooldown=float(data.get("attack_cooldown", 0.0)),
            mode=str(data.get("mode", "patrol")),
            facing=float(data.get("facing", 0.0)),
            target_player_id=data.get("target_player_id"),
            last_known_pos=Vec2.from_dict(data["last_known_pos"]) if data.get("last_known_pos") else None,
            waypoint=Vec2.from_dict(data["waypoint"]) if data.get("waypoint") else None,
            search_timer=float(data.get("search_timer", 0.0)),
            alertness=float(data.get("alertness", 0.0)),
            idle_timer=float(data.get("idle_timer", 0.0)),
            special_cooldown=float(data.get("special_cooldown", 0.0)),
            strafe_phase=float(data.get("strafe_phase", 0.0)),
            sidestep_bias=float(data.get("sidestep_bias", 0.0)),
            sidestep_timer=float(data.get("sidestep_timer", 0.0)),
            floor=int(data.get("floor", 0)),
            inside_building=data.get("inside_building"),
        )


@dataclass(slots=True)
class ProjectileState:
    id: str
    owner_id: str
    pos: Vec2
    velocity: Vec2
    damage: int
    life: float
    radius: float = 5.0
    floor: int = 0
    weapon_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "pos": self.pos.to_dict(),
            "velocity": self.velocity.to_dict(),
            "damage": self.damage,
            "life": round(self.life, 3),
            "radius": self.radius,
            "floor": self.floor,
            "weapon_key": self.weapon_key,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectileState":
        return cls(
            id=str(data["id"]),
            owner_id=str(data.get("owner_id", "")),
            pos=Vec2.from_dict(data.get("pos", {})),
            velocity=Vec2.from_dict(data.get("velocity", {})),
            damage=int(data.get("damage", 1)),
            life=float(data.get("life", 0.0)),
            radius=float(data.get("radius", 5.0)),
            floor=int(data.get("floor", 0)),
            weapon_key=str(data.get("weapon_key", "")),
        )


@dataclass(slots=True)
class GrenadeState:
    id: str
    owner_id: str
    pos: Vec2
    velocity: Vec2
    timer: float
    floor: int = 0
    radius: float = 10.0
    kind: str = "grenade"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "pos": self.pos.to_dict(),
            "velocity": self.velocity.to_dict(),
            "timer": round(self.timer, 3),
            "floor": self.floor,
            "radius": self.radius,
            "kind": self.kind,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GrenadeState":
        return cls(
            id=str(data["id"]),
            owner_id=str(data.get("owner_id", "")),
            pos=Vec2.from_dict(data.get("pos", {})),
            velocity=Vec2.from_dict(data.get("velocity", {})),
            timer=float(data.get("timer", 0.0)),
            floor=int(data.get("floor", 0)),
            radius=float(data.get("radius", 10.0)),
            kind=str(data.get("kind", "grenade")),
        )


@dataclass(slots=True)
class MineState:
    id: str
    owner_id: str
    kind: str
    pos: Vec2
    floor: int = 0
    armed: bool = False
    trigger_radius: float = 100.0
    blast_radius: float = 220.0
    rotation: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "kind": self.kind,
            "pos": self.pos.to_dict(),
            "floor": self.floor,
            "armed": self.armed,
            "trigger_radius": self.trigger_radius,
            "blast_radius": self.blast_radius,
            "rotation": round(self.rotation, 3),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MineState":
        return cls(
            id=str(data["id"]),
            owner_id=str(data.get("owner_id", "")),
            kind=str(data.get("kind", "mine_standard")),
            pos=Vec2.from_dict(data.get("pos", {})),
            floor=int(data.get("floor", 0)),
            armed=bool(data.get("armed", False)),
            trigger_radius=float(data.get("trigger_radius", 100.0)),
            blast_radius=float(data.get("blast_radius", 220.0)),
            rotation=float(data.get("rotation", 0.0)),
        )


@dataclass(slots=True)
class PoisonProjectileState:
    id: str
    owner_id: str
    pos: Vec2
    velocity: Vec2
    target: Vec2
    floor: int = 0
    radius: float = 9.0
    life: float = 2.4

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "pos": self.pos.to_dict(),
            "velocity": self.velocity.to_dict(),
            "target": self.target.to_dict(),
            "floor": self.floor,
            "radius": self.radius,
            "life": round(self.life, 3),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PoisonProjectileState":
        return cls(
            id=str(data["id"]),
            owner_id=str(data.get("owner_id", "")),
            pos=Vec2.from_dict(data.get("pos", {})),
            velocity=Vec2.from_dict(data.get("velocity", {})),
            target=Vec2.from_dict(data.get("target", {})),
            floor=int(data.get("floor", 0)),
            radius=float(data.get("radius", 9.0)),
            life=float(data.get("life", 2.4)),
        )


@dataclass(slots=True)
class PoisonPoolState:
    id: str
    pos: Vec2
    floor: int = 0
    timer: float = 5.0
    radius: float = 54.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pos": self.pos.to_dict(),
            "floor": self.floor,
            "timer": round(self.timer, 3),
            "radius": self.radius,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PoisonPoolState":
        return cls(
            id=str(data["id"]),
            pos=Vec2.from_dict(data.get("pos", {})),
            floor=int(data.get("floor", 0)),
            timer=float(data.get("timer", 5.0)),
            radius=float(data.get("radius", 54.0)),
        )


@dataclass(slots=True)
class LootState:
    id: str
    kind: str
    pos: Vec2
    payload: str
    amount: int = 1
    floor: int = 0
    rarity: str = "common"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "pos": self.pos.to_dict(),
            "payload": self.payload,
            "amount": self.amount,
            "floor": self.floor,
            "rarity": self.rarity,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LootState":
        return cls(
            id=str(data["id"]),
            kind=str(data.get("kind", "ammo")),
            pos=Vec2.from_dict(data.get("pos", {})),
            payload=str(data.get("payload", "")),
            amount=int(data.get("amount", 1)),
            floor=int(data.get("floor", 0)),
            rarity=str(data.get("rarity", "common")),
        )


@dataclass(slots=True)
class InputCommand:
    player_id: str
    move_x: float = 0.0
    move_y: float = 0.0
    aim_x: float = 0.0
    aim_y: float = 0.0
    shooting: bool = False
    alt_attack: bool = False
    reload: bool = False
    pickup: bool = False
    interact: bool = False
    use_medkit: bool = False
    sprint: bool = False
    sneak: bool = False
    respawn: bool = False
    throw_grenade: bool = False
    toggle_utility: bool = False
    inventory_action: dict[str, Any] | None = None
    craft_key: str | None = None
    repair_slot: str | None = None
    active_slot: str | None = None
    equip_armor: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "move_x": round(self.move_x, 3),
            "move_y": round(self.move_y, 3),
            "aim_x": round(self.aim_x, 3),
            "aim_y": round(self.aim_y, 3),
            "shooting": self.shooting,
            "alt_attack": self.alt_attack,
            "reload": self.reload,
            "pickup": self.pickup,
            "interact": self.interact,
            "use_medkit": self.use_medkit,
            "sprint": self.sprint,
            "sneak": self.sneak,
            "respawn": self.respawn,
            "throw_grenade": self.throw_grenade,
            "toggle_utility": self.toggle_utility,
            "inventory_action": self.inventory_action,
            "craft_key": self.craft_key,
            "repair_slot": self.repair_slot,
            "active_slot": self.active_slot,
            "equip_armor": self.equip_armor,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InputCommand":
        return cls(
            player_id=str(data.get("player_id", "")),
            move_x=float(data.get("move_x", 0.0)),
            move_y=float(data.get("move_y", 0.0)),
            aim_x=float(data.get("aim_x", 0.0)),
            aim_y=float(data.get("aim_y", 0.0)),
            shooting=bool(data.get("shooting", False)),
            alt_attack=bool(data.get("alt_attack", False)),
            reload=bool(data.get("reload", False)),
            pickup=bool(data.get("pickup", False)),
            interact=bool(data.get("interact", False)),
            use_medkit=bool(data.get("use_medkit", False)),
            sprint=bool(data.get("sprint", False)),
            sneak=bool(data.get("sneak", False)),
            respawn=bool(data.get("respawn", False)),
            throw_grenade=bool(data.get("throw_grenade", False)),
            toggle_utility=bool(data.get("toggle_utility", False)),
            inventory_action=data.get("inventory_action"),
            craft_key=data.get("craft_key"),
            repair_slot=data.get("repair_slot"),
            active_slot=data.get("active_slot"),
            equip_armor=data.get("equip_armor"),
        )


@dataclass(slots=True)
class ClientCommand:
    player_id: str
    command_id: int
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "command_id": self.command_id,
            "kind": self.kind,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClientCommand":
        payload = data.get("payload", {})
        return cls(
            player_id=str(data.get("player_id", "")),
            command_id=max(0, int(data.get("command_id", 0))),
            kind=str(data.get("kind", "")),
            payload=payload if isinstance(payload, dict) else {},
        )


@dataclass(slots=True)
class WorldSnapshot:
    time: float
    map_width: int
    map_height: int
    players: dict[str, PlayerState]
    zombies: dict[str, ZombieState]
    projectiles: dict[str, ProjectileState]
    loot: dict[str, LootState]
    grenades: dict[str, GrenadeState] = field(default_factory=dict)
    mines: dict[str, MineState] = field(default_factory=dict)
    poison_projectiles: dict[str, PoisonProjectileState] = field(default_factory=dict)
    poison_pools: dict[str, PoisonPoolState] = field(default_factory=dict)
    buildings: dict[str, BuildingState] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "time": round(self.time, 3),
            "map_width": self.map_width,
            "map_height": self.map_height,
            "players": {key: value.to_dict() for key, value in self.players.items()},
            "zombies": {key: value.to_dict() for key, value in self.zombies.items()},
            "projectiles": {key: value.to_dict() for key, value in self.projectiles.items()},
            "grenades": {key: value.to_dict() for key, value in self.grenades.items()},
            "mines": {key: value.to_dict() for key, value in self.mines.items()},
            "poison_projectiles": {key: value.to_dict() for key, value in self.poison_projectiles.items()},
            "poison_pools": {key: value.to_dict() for key, value in self.poison_pools.items()},
            "loot": {key: value.to_dict() for key, value in self.loot.items()},
            "buildings": {key: value.to_dict() for key, value in self.buildings.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorldSnapshot":
        return cls(
            time=float(data.get("time", 0.0)),
            map_width=int(data.get("map_width", 1)),
            map_height=int(data.get("map_height", 1)),
            players={key: PlayerState.from_dict(value) for key, value in data.get("players", {}).items()},
            zombies={key: ZombieState.from_dict(value) for key, value in data.get("zombies", {}).items()},
            projectiles={key: ProjectileState.from_dict(value) for key, value in data.get("projectiles", {}).items()},
            grenades={key: GrenadeState.from_dict(value) for key, value in data.get("grenades", {}).items()},
            mines={key: MineState.from_dict(value) for key, value in data.get("mines", {}).items()},
            poison_projectiles={
                key: PoisonProjectileState.from_dict(value)
                for key, value in data.get("poison_projectiles", {}).items()
            },
            poison_pools={key: PoisonPoolState.from_dict(value) for key, value in data.get("poison_pools", {}).items()},
            loot={key: LootState.from_dict(value) for key, value in data.get("loot", {}).items()},
            buildings={key: BuildingState.from_dict(value) for key, value in data.get("buildings", {}).items()},
        )
