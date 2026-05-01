from __future__ import annotations

import json
from pathlib import Path

from shared.models import ArmorSpec, WeaponSpec, ZombieSpec


CONFIG_DIR = Path(__file__).resolve().parents[1] / "configs"

MAP_WIDTH = 28800
MAP_HEIGHT = 19800
TICK_RATE = 30
SNAPSHOT_RATE = 20
INITIAL_ZOMBIES = 8
MAX_ZOMBIES = 32
PLAYER_RADIUS = 24
PICKUP_RADIUS = 72
INTERACT_RADIUS = 86
ZOMBIE_TARGET_RADIUS = 34
SEARCH_DURATION = 5.0
SNEAK_NOISE = 70.0
WALK_NOISE = 230.0
SPRINT_NOISE = 520.0
SHOT_NOISE = 850.0
UNARMED_MELEE_NOISE = WALK_NOISE * 0.5
SPRINT_MULTIPLIER = 1.72

SLOTS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]

DEFAULT_WEAPONS = {
    "pistol": {
        "title": "Viper Pistol",
        "slot": "1",
        "damage": 18,
        "magazine_size": 12,
        "fire_rate": 4.5,
        "reload_time": 1.1,
        "projectile_speed": 980.0,
        "spread": 0.035,
        "pellets": 1,
    },
    "smg": {
        "title": "Pulse SMG",
        "slot": "2",
        "damage": 10,
        "magazine_size": 28,
        "fire_rate": 12.0,
        "reload_time": 1.6,
        "projectile_speed": 920.0,
        "spread": 0.075,
        "pellets": 1,
    },
    "shotgun": {
        "title": "Breaker Shotgun",
        "slot": "3",
        "damage": 12,
        "magazine_size": 6,
        "fire_rate": 1.2,
        "reload_time": 1.9,
        "projectile_speed": 780.0,
        "spread": 0.18,
        "pellets": 7,
    },
    "rifle": {
        "title": "Arc Rifle",
        "slot": "4",
        "damage": 32,
        "magazine_size": 20,
        "fire_rate": 5.0,
        "reload_time": 1.9,
        "projectile_speed": 1180.0,
        "spread": 0.025,
        "pellets": 1,
    },
}

DEFAULT_ARMORS = {
    "none": {"title": "No Armor", "mitigation": 0.0, "armor_points": 0},
    "light": {"title": "Light Vest", "mitigation": 0.18, "armor_points": 45},
    "medium": {"title": "Medium Armor", "mitigation": 0.3, "armor_points": 72},
    "tactical": {"title": "Tactical Rig", "mitigation": 0.3, "armor_points": 70},
    "heavy": {"title": "Heavy Plate", "mitigation": 0.42, "armor_points": 110},
}

DEFAULT_ZOMBIES = {
    "walker": {
        "title": "Walker",
        "health": 70,
        "armor": 0,
        "speed": 92.0,
        "damage": 13,
        "radius": 24.0,
        "color": [114, 222, 158],
        "sight_range": 540.0,
        "hearing_range": 430.0,
        "fov_degrees": 116.0,
        "sensitivity": 0.85,
        "suspicion_time": 1.4,
    },
    "runner": {
        "title": "Runner",
        "health": 38,
        "armor": 0,
        "speed": 165.0,
        "damage": 9,
        "radius": 19.0,
        "color": [255, 101, 112],
        "sight_range": 620.0,
        "hearing_range": 620.0,
        "fov_degrees": 132.0,
        "sensitivity": 1.25,
        "suspicion_time": 0.9,
    },
    "brute": {
        "title": "Brute",
        "health": 115,
        "armor": 55,
        "speed": 62.0,
        "damage": 21,
        "radius": 31.0,
        "color": [127, 164, 255],
        "sight_range": 470.0,
        "hearing_range": 360.0,
        "fov_degrees": 94.0,
        "sensitivity": 0.65,
        "suspicion_time": 1.8,
    },
    "leaper": {
        "title": "Leaper",
        "health": 64,
        "armor": 10,
        "speed": 188.0,
        "damage": 11,
        "radius": 20.0,
        "color": [92, 246, 124],
        "sight_range": 660.0,
        "hearing_range": 560.0,
        "fov_degrees": 124.0,
        "sensitivity": 1.05,
        "suspicion_time": 1.0,
    },
}


def _read_json(filename: str, fallback: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    path = CONFIG_DIR / filename
    if not path.exists():
        return fallback
    data = json.loads(path.read_text(encoding="utf-8"))
    return dict(data) or fallback


def _color(raw: object, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 3:
        return fallback
    return tuple(max(0, min(255, int(value))) for value in raw)


def _load_weapons() -> dict[str, WeaponSpec]:
    weapons: dict[str, WeaponSpec] = {}
    for key, data in _read_json("weapons.json", DEFAULT_WEAPONS).items():
        fallback = DEFAULT_WEAPONS.get(key, DEFAULT_WEAPONS["pistol"])
        slot = str(data.get("slot", fallback["slot"]))
        weapons[str(key)] = WeaponSpec(
            key=str(key),
            title=str(data.get("title", fallback["title"])),
            slot=slot if slot in SLOTS else str(fallback["slot"]),
            damage=max(1, int(data.get("damage", fallback["damage"]))),
            magazine_size=max(1, int(data.get("magazine_size", fallback["magazine_size"]))),
            fire_rate=max(0.1, float(data.get("fire_rate", fallback["fire_rate"]))),
            reload_time=max(0.05, float(data.get("reload_time", fallback["reload_time"]))),
            projectile_speed=max(10.0, float(data.get("projectile_speed", fallback["projectile_speed"]))),
            spread=max(0.0, float(data.get("spread", fallback["spread"]))),
            pellets=max(1, int(data.get("pellets", fallback.get("pellets", 1)))),
        )
    return weapons


def _load_armors() -> dict[str, ArmorSpec]:
    armors: dict[str, ArmorSpec] = {}
    for key, data in _read_json("armors.json", DEFAULT_ARMORS).items():
        fallback = DEFAULT_ARMORS.get(key, DEFAULT_ARMORS["none"])
        armors[str(key)] = ArmorSpec(
            key=str(key),
            title=str(data.get("title", fallback["title"])),
            mitigation=max(0.0, min(0.92, float(data.get("mitigation", fallback["mitigation"])))),
            armor_points=max(0, int(data.get("armor_points", fallback["armor_points"]))),
        )
    armors.setdefault("none", ArmorSpec("none", "No Armor", mitigation=0.0, armor_points=0))
    return armors


def _load_zombies() -> dict[str, ZombieSpec]:
    zombies: dict[str, ZombieSpec] = {}
    for key, data in _read_json("zombies.json", DEFAULT_ZOMBIES).items():
        fallback = DEFAULT_ZOMBIES.get(key, DEFAULT_ZOMBIES["walker"])
        zombies[str(key)] = ZombieSpec(
            key=str(key),
            title=str(data.get("title", fallback["title"])),
            health=max(1, int(data.get("health", fallback["health"]))),
            armor=max(0, int(data.get("armor", fallback["armor"]))),
            speed=max(1.0, float(data.get("speed", fallback["speed"]))),
            damage=max(1, int(data.get("damage", fallback["damage"]))),
            radius=max(4.0, float(data.get("radius", fallback["radius"]))),
            color=_color(data.get("color", fallback["color"]), tuple(fallback["color"])),
            sight_range=max(1.0, float(data.get("sight_range", fallback["sight_range"]))),
            hearing_range=max(1.0, float(data.get("hearing_range", fallback["hearing_range"]))),
            fov_degrees=max(1.0, min(360.0, float(data.get("fov_degrees", fallback["fov_degrees"])))),
            sensitivity=max(0.0, float(data.get("sensitivity", fallback["sensitivity"]))),
            suspicion_time=max(0.0, float(data.get("suspicion_time", fallback["suspicion_time"]))),
        )
    return zombies


WEAPONS = _load_weapons()
ARMORS = _load_armors()
ZOMBIES = _load_zombies()
