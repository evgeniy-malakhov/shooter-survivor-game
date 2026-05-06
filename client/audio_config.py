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
class ActionSoundSpec:
    key: str
    hearing_distance: float
    full_volume_distance: float
    echo_delay: float = 0.0
    echo_volume: float = 0.0


@dataclass(frozen=True, slots=True)
class AudioTuning:
    menu_music_path: Path
    actions_dir: Path
    shot_hearing_distance: float
    shot_full_volume_distance: float
    different_floor_volume_multiplier: float
    min_spatial_volume: float
    weapon_sounds: dict[str, WeaponSoundSpec]
    action_sounds: dict[str, ActionSoundSpec]


DEFAULT_WEAPON_SOUNDS = {
    "pistol": {"shot": "pistol", "reload": "pistol_reload", "empty": "empty"},
    "rifle": {"shot": "rifle", "reload": "rifle_reload", "empty": "empty"},
    "shotgun": {"shot": "shotgun", "reload": "reload", "empty": "empty"},
    "smg": {"shot": "smg", "reload": "reload", "empty": "empty"},
}

DEFAULT_ACTION_SOUNDS = {
    "grenade_throw": {
        "key": "sound-of-falling-granade",
        "hearing_distance": 1450.0,
        "full_volume_distance": 160.0,
        "echo_delay": 0.08,
        "echo_volume": 0.18,
    },
    "grenade_explosion": {
        "key": "explode",
        "hearing_distance": 2600.0,
        "full_volume_distance": 320.0,
        "echo_delay": 0.16,
        "echo_volume": 0.34,
    },
    "mine_explosion": {
        "key": "explode",
        "hearing_distance": 2300.0,
        "full_volume_distance": 280.0,
        "echo_delay": 0.14,
        "echo_volume": 0.3,
    },
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

    action_raw = data.get("action_sounds", DEFAULT_ACTION_SOUNDS)
    action_sounds: dict[str, ActionSoundSpec] = {}
    action_source = action_raw if isinstance(action_raw, dict) else DEFAULT_ACTION_SOUNDS
    for action_key, spec_raw in action_source.items():
        action_name = str(action_key)
        spec = spec_raw if isinstance(spec_raw, dict) else {}
        fallback = DEFAULT_ACTION_SOUNDS.get(action_name, {"key": action_name})
        action_sounds[action_name] = ActionSoundSpec(
            key=str(spec.get("key", fallback.get("key", action_name))),
            hearing_distance=_float(spec, "hearing_distance", float(fallback.get("hearing_distance", 1900.0)), minimum=120.0),
            full_volume_distance=_float(spec, "full_volume_distance", float(fallback.get("full_volume_distance", 220.0)), minimum=0.0),
            echo_delay=_float(spec, "echo_delay", float(fallback.get("echo_delay", 0.0)), minimum=0.0),
            echo_volume=_float(spec, "echo_volume", float(fallback.get("echo_volume", 0.0)), minimum=0.0),
        )

    return AudioTuning(
        menu_music_path=_path(data.get("menu_music", "assets/menu/AtriumCarceri-Reunion.mp3")),
        actions_dir=_path(data.get("actions_dir", "assets/actions")),
        shot_hearing_distance=_float(data, "shot_hearing_distance", 1900.0, minimum=120.0),
        shot_full_volume_distance=_float(data, "shot_full_volume_distance", 220.0, minimum=0.0),
        different_floor_volume_multiplier=_float(data, "different_floor_volume_multiplier", 0.28, minimum=0.0),
        min_spatial_volume=_float(data, "min_spatial_volume", 0.02, minimum=0.0),
        weapon_sounds=weapon_sounds,
        action_sounds=action_sounds,
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
