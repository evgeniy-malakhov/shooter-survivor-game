from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "audio.json"


@dataclass(frozen=True, slots=True)
class WeaponSoundSpec:
    shot: str
    reload: str
    empty: str


@dataclass(frozen=True, slots=True)
class AudioTuning:
    menu_music_path: Path
    actions_dir: Path
    shot_hearing_distance: float
    shot_full_volume_distance: float
    different_floor_volume_multiplier: float
    min_spatial_volume: float
    weapon_sounds: dict[str, WeaponSoundSpec]


DEFAULT_WEAPON_SOUNDS = {
    "pistol": {"shot": "pistol", "reload": "pistol_reload", "empty": "empty"},
    "rifle": {"shot": "rifle", "reload": "rifle_reload", "empty": "empty"},
    "shotgun": {"shot": "shotgun", "reload": "reload", "empty": "empty"},
    "smg": {"shot": "smg", "reload": "reload", "empty": "empty"},
}


def load_audio_tuning() -> AudioTuning:
    fallback = _default_tuning({})
    if not CONFIG_PATH.exists():
        return fallback
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback
    data = raw if isinstance(raw, dict) else {}
    return _default_tuning(data)


def _default_tuning(data: dict[str, Any]) -> AudioTuning:
    weapon_raw = data.get("weapon_sounds", DEFAULT_WEAPON_SOUNDS)
    weapon_sounds: dict[str, WeaponSoundSpec] = {}
    source = weapon_raw if isinstance(weapon_raw, dict) else DEFAULT_WEAPON_SOUNDS
    for weapon_key, spec_raw in source.items():
        spec = spec_raw if isinstance(spec_raw, dict) else {}
        fallback = DEFAULT_WEAPON_SOUNDS.get(str(weapon_key), {"shot": str(weapon_key), "reload": "reload", "empty": "empty"})
        weapon_sounds[str(weapon_key)] = WeaponSoundSpec(
            shot=str(spec.get("shot", fallback["shot"])),
            reload=str(spec.get("reload", fallback["reload"])),
            empty=str(spec.get("empty", fallback["empty"])),
        )
    return AudioTuning(
        menu_music_path=_path(data.get("menu_music", "assets/menu/AtriumCarceri-Reunion.mp3")),
        actions_dir=_path(data.get("actions_dir", "assets/actions")),
        shot_hearing_distance=_float(data, "shot_hearing_distance", 1900.0, minimum=120.0),
        shot_full_volume_distance=_float(data, "shot_full_volume_distance", 220.0, minimum=0.0),
        different_floor_volume_multiplier=_float(data, "different_floor_volume_multiplier", 0.28, minimum=0.0),
        min_spatial_volume=_float(data, "min_spatial_volume", 0.02, minimum=0.0),
        weapon_sounds=weapon_sounds,
    )


def _path(value: object) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else ROOT / path


def _float(data: dict[str, Any], key: str, default: float, *, minimum: float) -> float:
    try:
        value = float(data.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)
