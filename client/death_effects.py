from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "death_effects.json"


@dataclass(frozen=True, slots=True)
class DeathEffectTuning:
    corpse_seconds: float = 10.0
    corpse_fade_seconds: float = 2.4
    blood_seconds: float = 3.0
    blood_spread_seconds: float = 2.2
    blood_fade_seconds: float = 0.75
    blood_start_radius: float = 18.0
    blood_end_radius: float = 76.0
    blood_alpha: int = 150
    corpse_dark_alpha: int = 172
    corpse_outline_alpha: int = 70
    player_cross_size: float = 42.0
    player_cross_width: int = 7
    max_effects: int = 96


def load_death_effect_tuning() -> DeathEffectTuning:
    fallback = DeathEffectTuning()
    if not CONFIG_PATH.exists():
        return fallback
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback
    data = raw if isinstance(raw, dict) else {}
    return DeathEffectTuning(
        corpse_seconds=_float(data, "corpse_seconds", fallback.corpse_seconds, minimum=0.1),
        corpse_fade_seconds=_float(data, "corpse_fade_seconds", fallback.corpse_fade_seconds, minimum=0.0),
        blood_seconds=_float(data, "blood_seconds", fallback.blood_seconds, minimum=0.1),
        blood_spread_seconds=_float(data, "blood_spread_seconds", fallback.blood_spread_seconds, minimum=0.1),
        blood_fade_seconds=_float(data, "blood_fade_seconds", fallback.blood_fade_seconds, minimum=0.0),
        blood_start_radius=_float(data, "blood_start_radius", fallback.blood_start_radius, minimum=1.0),
        blood_end_radius=_float(data, "blood_end_radius", fallback.blood_end_radius, minimum=1.0),
        blood_alpha=_int(data, "blood_alpha", fallback.blood_alpha, minimum=0, maximum=255),
        corpse_dark_alpha=_int(data, "corpse_dark_alpha", fallback.corpse_dark_alpha, minimum=0, maximum=255),
        corpse_outline_alpha=_int(data, "corpse_outline_alpha", fallback.corpse_outline_alpha, minimum=0, maximum=255),
        player_cross_size=_float(data, "player_cross_size", fallback.player_cross_size, minimum=4.0),
        player_cross_width=_int(data, "player_cross_width", fallback.player_cross_width, minimum=1),
        max_effects=_int(data, "max_effects", fallback.max_effects, minimum=1),
    )


def _float(data: dict[str, Any], key: str, default: float, *, minimum: float) -> float:
    try:
        value = float(data.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


def _int(data: dict[str, Any], key: str, default: int, *, minimum: int, maximum: int | None = None) -> int:
    try:
        value = int(data.get(key, default))
    except (TypeError, ValueError):
        value = default
    value = max(minimum, value)
    return min(maximum, value) if maximum is not None else value
