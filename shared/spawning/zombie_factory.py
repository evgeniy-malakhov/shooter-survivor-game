from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

from shared.constants import ZOMBIES
from shared.models import Vec2, ZombieState


@dataclass(slots=True)
class ZombieFactory:
    def create(
        self,
        *,
        zombie_id: str,
        kind: str,
        pos: Vec2,
        difficulty: Any,
        rng: random.Random,
    ) -> ZombieState:
        spec = ZOMBIES[kind]

        health = max(1, int(round(spec.health * difficulty.zombie_health_multiplier)))
        armor = max(0, int(round(spec.armor * difficulty.zombie_armor_multiplier)))

        return ZombieState(
            id=zombie_id,
            kind=kind,
            pos=pos,
            health=health,
            armor=armor,
            facing=rng.uniform(-math.pi, math.pi),
        )