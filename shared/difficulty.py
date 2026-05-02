from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from pathlib import Path


DIFFICULTY_KEYS = ("easy", "medium", "hard", "insane")
CONFIG_DIR = Path(__file__).resolve().parents[1] / "configs" / "difficulty"


@dataclass(frozen=True, slots=True)
class DifficultyConfig:
    key: str = "medium"
    initial_zombies: int = 8
    max_zombies: int = 32
    zombie_health_multiplier: float = 1.0
    zombie_armor_multiplier: float = 1.0
    zombie_speed_multiplier: float = 1.0
    zombie_damage_multiplier: float = 1.0
    weapon_wear_multiplier: float = 1.0
    armor_wear_multiplier: float = 1.0
    weapon_damage_multiplier: float = 1.0
    weapon_damage_multipliers: dict[str, float] = field(default_factory=dict)
    loot_spawn_multiplier: float = 1.0
    zombie_spawn_interval_multiplier: float = 1.0
    loot_spawn_interval_multiplier: float = 1.0
    world_loot_cap: int = 88


def load_difficulty(key: str | None = None) -> DifficultyConfig:
    selected = key if key in DIFFICULTY_KEYS else "medium"
    data = _read_config(selected)
    allowed = {field.name for field in fields(DifficultyConfig)}
    values = {name: data[name] for name in allowed if name in data}
    values["key"] = selected
    config = DifficultyConfig(**values)
    return _clamp(config)


def list_difficulties() -> list[DifficultyConfig]:
    return [load_difficulty(key) for key in DIFFICULTY_KEYS]


def _read_config(key: str) -> dict[str, object]:
    path = CONFIG_DIR / f"{key}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _clamp(config: DifficultyConfig) -> DifficultyConfig:
    initial_zombies = max(0, int(config.initial_zombies))
    max_zombies = max(0, int(config.max_zombies))
    if max_zombies > 0:
        initial_zombies = min(initial_zombies, max_zombies)
    else:
        initial_zombies = 0
    return DifficultyConfig(
        key=config.key,
        initial_zombies=initial_zombies,
        max_zombies=max_zombies,
        zombie_health_multiplier=max(0.1, float(config.zombie_health_multiplier)),
        zombie_armor_multiplier=max(0.0, float(config.zombie_armor_multiplier)),
        zombie_speed_multiplier=max(0.1, float(config.zombie_speed_multiplier)),
        zombie_damage_multiplier=max(0.1, float(config.zombie_damage_multiplier)),
        weapon_wear_multiplier=max(0.0, float(config.weapon_wear_multiplier)),
        armor_wear_multiplier=max(0.0, float(config.armor_wear_multiplier)),
        weapon_damage_multiplier=max(0.1, float(config.weapon_damage_multiplier)),
        weapon_damage_multipliers={
            str(key): max(0.1, float(value))
            for key, value in dict(config.weapon_damage_multipliers).items()
        },
        loot_spawn_multiplier=max(0.1, float(config.loot_spawn_multiplier)),
        zombie_spawn_interval_multiplier=max(0.25, float(config.zombie_spawn_interval_multiplier)),
        loot_spawn_interval_multiplier=max(0.25, float(config.loot_spawn_interval_multiplier)),
        world_loot_cap=max(8, int(config.world_loot_cap)),
    )
