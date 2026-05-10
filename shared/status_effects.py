from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StatusEffectKind(str, Enum):
    BLEEDING = "bleeding"
    INFECTION = "infection"
    FEAR = "fear"
    SUPPRESSION = "suppression"
    CONCUSSION = "concussion"
    POISON = "poison"
    EXHAUSTION = "exhaustion"
    ADRENALINE = "adrenaline"
    STIMPACK = "stimpack"
    MILITARY_RATION = "military_ration"
    MORALE_AURA = "morale_aura"


@dataclass(frozen=True, slots=True)
class StatusEffectSpec:
    key: str
    title: str
    buff: bool
    speed_multiplier: float = 1.0
    aim_multiplier: float = 1.0
    accuracy_multiplier: float = 1.0
    reload_multiplier: float = 1.0
    stamina_multiplier: float = 1.0
    damage_per_second: float = 0.0


STATUS_EFFECTS: dict[str, StatusEffectSpec] = {
    StatusEffectKind.BLEEDING.value: StatusEffectSpec("bleeding", "Bleeding", False, damage_per_second=1.0),
    StatusEffectKind.INFECTION.value: StatusEffectSpec("infection", "Infection", False, stamina_multiplier=0.82),
    StatusEffectKind.FEAR.value: StatusEffectSpec("fear", "Fear", False, aim_multiplier=0.82),
    StatusEffectKind.SUPPRESSION.value: StatusEffectSpec("suppression", "Suppression", False, accuracy_multiplier=0.76),
    StatusEffectKind.CONCUSSION.value: StatusEffectSpec("concussion", "Concussion", False, aim_multiplier=0.68),
    StatusEffectKind.POISON.value: StatusEffectSpec("poison", "Poison", False, speed_multiplier=0.84, damage_per_second=0.55),
    StatusEffectKind.EXHAUSTION.value: StatusEffectSpec("exhaustion", "Exhaustion", False, speed_multiplier=0.88, reload_multiplier=1.16),
    StatusEffectKind.ADRENALINE.value: StatusEffectSpec("adrenaline", "Adrenaline", True, speed_multiplier=1.12),
    StatusEffectKind.STIMPACK.value: StatusEffectSpec("stimpack", "Stimpack", True, accuracy_multiplier=1.08),
    StatusEffectKind.MILITARY_RATION.value: StatusEffectSpec("military_ration", "Ration", True, stamina_multiplier=1.12),
    StatusEffectKind.MORALE_AURA.value: StatusEffectSpec("morale_aura", "Morale", True, accuracy_multiplier=1.06),
}


def active_status_effects(raw: dict[str, float]) -> dict[str, float]:
    return {key: duration for key, duration in raw.items() if key in STATUS_EFFECTS and duration > 0.0}


def combined_speed_multiplier(raw: dict[str, float]) -> float:
    value = 1.0
    for key in active_status_effects(raw):
        value *= STATUS_EFFECTS[key].speed_multiplier
    return max(0.45, min(1.35, value))


def combined_reload_multiplier(raw: dict[str, float]) -> float:
    value = 1.0
    for key in active_status_effects(raw):
        value *= STATUS_EFFECTS[key].reload_multiplier
    return max(0.65, min(1.45, value))


def combined_accuracy_multiplier(raw: dict[str, float]) -> float:
    value = 1.0
    for key in active_status_effects(raw):
        value *= STATUS_EFFECTS[key].accuracy_multiplier
    return max(0.45, min(1.35, value))


def combined_aim_multiplier(raw: dict[str, float]) -> float:
    value = 1.0
    for key in active_status_effects(raw):
        value *= STATUS_EFFECTS[key].aim_multiplier
    return max(0.45, min(1.25, value))
