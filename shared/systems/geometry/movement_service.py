from __future__ import annotations

import math
import random

from shared.constants import MAP_HEIGHT, MAP_WIDTH
from shared.models import Vec2, ZombieState
from shared.constants import ZOMBIES
from shared.systems.geometry.geometry_service import GeometryService
from shared.systems.geometry.building_service import BuildingService


class MovementService:
    def __init__(
        self,
        geometry: GeometryService,
        buildings: BuildingService,
    ) -> None:
        self._geometry = geometry
        self._buildings = buildings

    def move_circle(
        self,
        pos: Vec2,
        delta: Vec2,
        radius: float,
        floor: int,
    ) -> None:
        self._geometry.move_circle(pos, delta, radius, floor)

    def unstick_zombie_from_building(
        self,
        zombie: ZombieState,
        radius: float,
        rng: random.Random,
    ) -> bool:
        # Пока можно оставить старую реализацию в GameWorld.
        # На этом шаге создаем место для переноса.
        return False