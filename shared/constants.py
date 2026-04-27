from __future__ import annotations

from shared.models import ArmorSpec, WeaponSpec, ZombieSpec

MAP_WIDTH = 9600
MAP_HEIGHT = 6600
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
SPRINT_MULTIPLIER = 1.72

SLOTS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]

WEAPONS: dict[str, WeaponSpec] = {
    "pistol": WeaponSpec(
        key="pistol",
        title="Viper Pistol",
        slot="1",
        damage=18,
        magazine_size=12,
        fire_rate=4.5,
        reload_time=1.1,
        projectile_speed=980.0,
        spread=0.035,
    ),
    "smg": WeaponSpec(
        key="smg",
        title="Pulse SMG",
        slot="2",
        damage=10,
        magazine_size=28,
        fire_rate=12.0,
        reload_time=1.6,
        projectile_speed=920.0,
        spread=0.075,
    ),
    "shotgun": WeaponSpec(
        key="shotgun",
        title="Breaker Shotgun",
        slot="3",
        damage=12,
        magazine_size=6,
        fire_rate=1.2,
        reload_time=1.9,
        projectile_speed=780.0,
        spread=0.18,
        pellets=7,
    ),
    "rifle": WeaponSpec(
        key="rifle",
        title="Arc Rifle",
        slot="4",
        damage=32,
        magazine_size=20,
        fire_rate=5.0,
        reload_time=1.9,
        projectile_speed=1180.0,
        spread=0.025,
    ),
}

ARMORS: dict[str, ArmorSpec] = {
    "none": ArmorSpec("none", "No Armor", mitigation=0.0, armor_points=0),
    "light": ArmorSpec("light", "Light Vest", mitigation=0.18, armor_points=45),
    "medium": ArmorSpec("medium", "Medium Armor", mitigation=0.3, armor_points=72),
    "tactical": ArmorSpec("tactical", "Tactical Rig", mitigation=0.3, armor_points=70),
    "heavy": ArmorSpec("heavy", "Heavy Plate", mitigation=0.42, armor_points=110),
}

ZOMBIES: dict[str, ZombieSpec] = {
    "walker": ZombieSpec(
        key="walker",
        title="Walker",
        health=70,
        armor=0,
        speed=92.0,
        damage=13,
        radius=24.0,
        color=(114, 222, 158),
        sight_range=540.0,
        hearing_range=430.0,
        fov_degrees=116.0,
        sensitivity=0.85,
        suspicion_time=1.4,
    ),
    "runner": ZombieSpec(
        key="runner",
        title="Runner",
        health=38,
        armor=0,
        speed=165.0,
        damage=9,
        radius=19.0,
        color=(255, 101, 112),
        sight_range=620.0,
        hearing_range=620.0,
        fov_degrees=132.0,
        sensitivity=1.25,
        suspicion_time=0.9,
    ),
    "brute": ZombieSpec(
        key="brute",
        title="Brute",
        health=115,
        armor=55,
        speed=62.0,
        damage=21,
        radius=31.0,
        color=(127, 164, 255),
        sight_range=470.0,
        hearing_range=360.0,
        fov_degrees=94.0,
        sensitivity=0.65,
        suspicion_time=1.8,
    ),
    "leaper": ZombieSpec(
        key="leaper",
        title="Leaper",
        health=64,
        armor=10,
        speed=188.0,
        damage=11,
        radius=20.0,
        color=(92, 246, 124),
        sight_range=660.0,
        hearing_range=560.0,
        fov_degrees=124.0,
        sensitivity=1.05,
        suspicion_time=1.0,
    ),
}
