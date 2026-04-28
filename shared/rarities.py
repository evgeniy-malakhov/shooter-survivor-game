from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "rarities.json"


@dataclass(frozen=True, slots=True)
class RaritySpec:
    key: str
    title: str
    color: tuple[int, int, int]
    loot_weight: float
    weapon_damage_multiplier: float
    weapon_durability_multiplier: float
    armor_points_multiplier: float
    armor_mitigation_multiplier: float
    armor_durability_multiplier: float


DEFAULT_RARITY = RaritySpec(
    key="common",
    title="Common",
    color=(145, 154, 166),
    loot_weight=1.0,
    weapon_damage_multiplier=1.0,
    weapon_durability_multiplier=1.0,
    armor_points_multiplier=1.0,
    armor_mitigation_multiplier=1.0,
    armor_durability_multiplier=1.0,
)


def _load() -> dict[str, RaritySpec]:
    if not CONFIG_PATH.exists():
        return {DEFAULT_RARITY.key: DEFAULT_RARITY}
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    rarities: dict[str, RaritySpec] = {}
    for key, raw in dict(data).items():
        color = tuple(max(0, min(255, int(value))) for value in raw.get("color", DEFAULT_RARITY.color))
        if len(color) != 3:
            color = DEFAULT_RARITY.color
        rarities[str(key)] = RaritySpec(
            key=str(key),
            title=str(raw.get("title", key)),
            color=color,
            loot_weight=max(0.0, float(raw.get("loot_weight", DEFAULT_RARITY.loot_weight))),
            weapon_damage_multiplier=max(0.1, float(raw.get("weapon_damage_multiplier", DEFAULT_RARITY.weapon_damage_multiplier))),
            weapon_durability_multiplier=max(0.1, float(raw.get("weapon_durability_multiplier", DEFAULT_RARITY.weapon_durability_multiplier))),
            armor_points_multiplier=max(0.1, float(raw.get("armor_points_multiplier", DEFAULT_RARITY.armor_points_multiplier))),
            armor_mitigation_multiplier=max(0.1, float(raw.get("armor_mitigation_multiplier", DEFAULT_RARITY.armor_mitigation_multiplier))),
            armor_durability_multiplier=max(0.1, float(raw.get("armor_durability_multiplier", DEFAULT_RARITY.armor_durability_multiplier))),
        )
    rarities.setdefault(DEFAULT_RARITY.key, DEFAULT_RARITY)
    return rarities


RARITIES = _load()
BASE_RARITY_ORDER = ("common", "uncommon", "rare", "legendary")
RARITY_KEYS = tuple(key for key in BASE_RARITY_ORDER if key in RARITIES) + tuple(
    key for key in RARITIES if key not in BASE_RARITY_ORDER
)
RARITY_RANK = {key: index for index, key in enumerate(RARITY_KEYS)}


def rarity_spec(key: str | None) -> RaritySpec:
    return RARITIES.get(str(key or DEFAULT_RARITY.key), DEFAULT_RARITY)


def rarity_rank(key: str | None) -> int:
    return RARITY_RANK.get(str(key or DEFAULT_RARITY.key), 0)


def rarity_color(key: str | None) -> tuple[int, int, int]:
    return rarity_spec(key).color
