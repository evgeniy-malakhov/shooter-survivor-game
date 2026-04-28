from __future__ import annotations

import json
from pathlib import Path
from random import Random

from shared.rarities import RARITIES


CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "crafting.json"

DEFAULT_CRAFTING_CONFIG = {
    "rarity_weights": {"common": 68, "uncommon": 22, "rare": 8, "legendary": 2},
    "kind_overrides": {
        "armor": {"common": 54, "uncommon": 28, "rare": 14, "legendary": 4},
        "weapon_module": {"common": 60, "uncommon": 26, "rare": 11, "legendary": 3},
        "grenade": {"common": 74, "uncommon": 18, "rare": 6, "legendary": 2},
        "mine": {"common": 70, "uncommon": 20, "rare": 8, "legendary": 2},
    },
    "recipe_overrides": {},
}


def _read_config() -> dict[str, object]:
    if not CONFIG_PATH.exists():
        return DEFAULT_CRAFTING_CONFIG
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_CRAFTING_CONFIG
    return raw if isinstance(raw, dict) else DEFAULT_CRAFTING_CONFIG


CRAFTING_CONFIG = _read_config()


def _weights(raw: object, fallback: dict[str, float] | None = None) -> dict[str, float]:
    fallback = fallback or DEFAULT_CRAFTING_CONFIG["rarity_weights"]
    data = raw if isinstance(raw, dict) else {}
    weights: dict[str, float] = {}
    for rarity in RARITIES:
        value = data.get(rarity, fallback.get(rarity, 0.0))
        try:
            weights[rarity] = max(0.0, float(value))
        except (TypeError, ValueError):
            weights[rarity] = max(0.0, float(fallback.get(rarity, 0.0)))
    if sum(weights.values()) <= 0:
        weights["common"] = 1.0
    return weights


BASE_CRAFT_RARITY_WEIGHTS = _weights(CRAFTING_CONFIG.get("rarity_weights"))


def craft_rarity_weights(recipe_key: str, result_kind: str) -> dict[str, float]:
    weights = BASE_CRAFT_RARITY_WEIGHTS
    kind_overrides = CRAFTING_CONFIG.get("kind_overrides", {})
    if isinstance(kind_overrides, dict) and result_kind in kind_overrides:
        weights = _weights(kind_overrides[result_kind], weights)
    recipe_overrides = CRAFTING_CONFIG.get("recipe_overrides", {})
    if isinstance(recipe_overrides, dict) and recipe_key in recipe_overrides:
        weights = _weights(recipe_overrides[recipe_key], weights)
    return weights


def craft_rarity_chances(recipe_key: str, result_kind: str) -> dict[str, float]:
    weights = craft_rarity_weights(recipe_key, result_kind)
    total = sum(weights.values())
    if total <= 0:
        return {"common": 100.0}
    return {key: value / total * 100.0 for key, value in weights.items()}


def roll_crafted_rarity(rng: Random, recipe_key: str, result_kind: str) -> str:
    weights = craft_rarity_weights(recipe_key, result_kind)
    keys = list(weights)
    values = [weights[key] for key in keys]
    if sum(values) <= 0:
        return "common"
    return rng.choices(keys, weights=values)[0]
