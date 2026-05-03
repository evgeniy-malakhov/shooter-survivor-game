from __future__ import annotations

import math
import random

from shared.constants import SOLDIERS, WEAPONS
from shared.models import SoldierState, Vec2, WeaponRuntime


class SoldierFactory:
    def create(
        self,
        *,
        soldier_id: str,
        kind: str,
        pos: Vec2,
        guard_point: Vec2,
        rng: random.Random,
    ) -> SoldierState:
        spec = SOLDIERS[kind]
        weapon_spec = WEAPONS[spec.weapon_key]
        weapon = WeaponRuntime(
            key=weapon_spec.key,
            ammo_in_mag=weapon_spec.magazine_size,
            reserve_ammo=weapon_spec.magazine_size * 100,
        )

        return SoldierState(
            id=soldier_id,
            kind=kind,
            pos=pos.copy(),
            health=spec.health,
            armor=spec.armor,
            facing=rng.uniform(-math.pi, math.pi),
            guard_point=guard_point.copy(),
            weapon=weapon,
        )