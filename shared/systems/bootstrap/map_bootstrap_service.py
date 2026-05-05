from __future__ import annotations

import random

from shared.constants import WEAPONS
from shared.items import BASEMENT_LOOT, HOUSE_LOOT
from shared.models import Vec2
from shared.systems.events.game_events import SpawnLootEvent


class MapBootstrapService:
    def __init__(
        self,
        *,
        state,
        rng: random.Random,
        difficulty,
        buildings,
        geometry,
        spawning,
        events,
        initial_zombies: int,
        max_zombies: int,
    ) -> None:
        self._state = state
        self._rng = rng
        self._difficulty = difficulty
        self._buildings = buildings
        self._geometry = geometry
        self._spawning = spawning
        self._events = events
        self._initial_zombies = initial_zombies
        self._max_zombies = max_zombies

    def bootstrap(self) -> None:
        self._spawn_initial_zombies()
        self._spawn_initial_world_loot()
        self._spawn_initial_building_loot()
        self._spawning.spawn_initial_soldiers()

    def _spawn_initial_zombies(self) -> None:
        start_count = (
            min(self._initial_zombies, self._max_zombies)
            if self._max_zombies > 0
            else 0
        )

        for _ in range(start_count):
            self._spawning.spawn_zombie()

    def _spawn_initial_world_loot(self) -> None:
        for weapon in ("smg", "shotgun", "rifle"):
            self.spawn_loot("weapon", weapon, 1)

        for armor in ("light_head", "light_torso", "light_arms", "light_legs", "medium_torso", "medium_legs", "medium_arms", "heavy_torso"):
            self.spawn_loot("armor", armor, 1)

        for _ in range(self.loot_count(24, minimum=8)):
            self.spawn_loot("ammo", "ammo_pack", self._rng.randint(1, 3))

        for _ in range(self.loot_count(10, minimum=2)):
            self.spawn_loot("medkit", "medicine", 1)

    def _spawn_initial_building_loot(self) -> None:
        for building in self._state.buildings.values():
            for _ in range(self.loot_count(14, minimum=6)):
                pos = Vec2(
                    self._rng.uniform(
                        building.bounds.x + 80,
                        building.bounds.x + building.bounds.w - 80,
                    ),
                    self._rng.uniform(
                        building.bounds.y + 90,
                        building.bounds.y + building.bounds.h - 90,
                    ),
                )

                floor = self._rng.choice([
                    building.min_floor,
                    building.min_floor,
                    0,
                    0,
                    1,
                    2,
                ])

                if self._geometry.blocked_at(pos, 16, floor):
                    continue

                loot_table = BASEMENT_LOOT if floor == building.min_floor else HOUSE_LOOT

                item_key = self._rng.choices(
                    [item[0] for item in loot_table],
                    weights=[item[2] for item in loot_table],
                )[0]

                self.spawn_loot_at(
                    pos,
                    "item",
                    item_key,
                    self._rng.randint(1, 3),
                    floor=floor,
                )

    def spawn_loot(
        self,
        kind: str,
        payload: str,
        amount: int,
        rarity: str | None = None,
    ) -> None:
        pos = self._buildings.random_open_pos(
            centered=False,
            rng=self._rng,
            blocked_at=lambda p, r: self._geometry.blocked_at(p, r, 0),
        )

        self.spawn_loot_at(
            pos,
            kind,
            payload,
            amount,
            floor=0,
            rarity=rarity,
        )

    def spawn_loot_at(
        self,
        pos: Vec2,
        kind: str,
        payload: str,
        amount: int,
        floor: int = 0,
        rarity: str | None = None,
    ) -> None:
        self._events.emit(
            SpawnLootEvent(
                pos=pos,
                kind=kind,
                payload=payload,
                amount=amount,
                floor=floor,
                rarity=rarity or "common",
            )
        )

    def loot_count(self, base: int, minimum: int = 1) -> int:
        return max(
            minimum,
            int(round(base * self._difficulty.loot_spawn_multiplier)),
        )