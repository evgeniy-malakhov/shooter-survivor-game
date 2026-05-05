from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SoldierDecisionWeights:
    zombie_priority: float = 160.0
    player_priority: float = 110.0
    distance: float = 80.0
    wounded_target: float = 18.0
    sprinting_target: float = 12.0
    low_ammo_reload: float = 250.0
    close_threat_retreat: float = 220.0
    investigate_last_known: float = 82.0
    sound_interest: float = 96.0
    sound_distance: float = 72.0
    guard: float = 10.0
    grenade: float = 0.0


@dataclass(frozen=True, slots=True)
class SoldierHearingTuning:
    hearing_multiplier: float = 2.35
    extra_radius: float = 1900.0
    min_reaction_score: float = 85.0
    shot_bonus: float = 54.0
    explosion_bonus: float = 78.0
    movement_penalty: float = -18.0
    already_investigating_penalty: float = -22.0


@dataclass(frozen=True, slots=True)
class GrenadierTuning:
    grenade_kind: str = "heavy_grenade"
    min_throw_distance: float = 210.0
    best_throw_distance: float = 520.0
    max_throw_distance: float = 860.0
    cooldown_min: float = 4.2
    cooldown_max: float = 6.8
    throw_speed_multiplier: float = 1.9
    minimum_target_cluster_bonus: float = 0.0
