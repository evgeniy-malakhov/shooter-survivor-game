from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "weapon_modules.json"


@dataclass(frozen=True, slots=True)
class WeaponModuleSpec:
    key: str
    title: str
    slot: str
    beam_length: float = 0.0
    cone_range: float = 0.0
    cone_degrees: float = 0.0
    spread_multiplier: float = 1.0
    magazine_multiplier: float = 1.0
    noise_multiplier: float = 1.0
    fire_rate_bonus: float = 0.0
    fire_rate_rarity_step: float = 0.0


def load_weapon_modules() -> dict[str, WeaponModuleSpec]:
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
    modules: dict[str, WeaponModuleSpec] = {}
    for key, raw in data.items():
        values = dict(raw)
        modules[str(key)] = WeaponModuleSpec(
            key=str(key),
            title=str(values.get("title", key)),
            slot=str(values.get("slot", "utility")),
            beam_length=float(values.get("beam_length", 0.0)),
            cone_range=float(values.get("cone_range", 0.0)),
            cone_degrees=float(values.get("cone_degrees", 0.0)),
            spread_multiplier=max(0.05, float(values.get("spread_multiplier", 1.0))),
            magazine_multiplier=max(1.0, float(values.get("magazine_multiplier", 1.0))),
            noise_multiplier=max(0.0, float(values.get("noise_multiplier", 1.0))),
            fire_rate_bonus=max(0.0, float(values.get("fire_rate_bonus", 0.0))),
            fire_rate_rarity_step=max(0.0, float(values.get("fire_rate_rarity_step", 0.0))),
        )
    return modules


WEAPON_MODULES = load_weapon_modules()
WEAPON_MODULE_SLOTS = ("utility", "magazine")
