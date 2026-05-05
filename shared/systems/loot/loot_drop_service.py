from __future__ import annotations

import random

from shared.models import Vec2
from shared.systems.events.game_events import SpawnLootEvent


class LootDropService:
    def __init__(
        self,
        *,
        rng: random.Random,
        events,
        loot,
    ) -> None:
        self._rng = rng
        self._events = events
        self._loot = loot

    def drop_from_zombie(self, pos: Vec2, floor: int = 0) -> None:
        kind = self._rng.choice(["ammo", "medkit"])

        payload = "ammo_pack" if kind == "ammo" else "medicine"
        amount = self._rng.randint(5, 18) if kind == "ammo" else 1

        self._events.emit(
            SpawnLootEvent(
                pos=pos.copy(),
                kind=kind,
                payload=payload,
                amount=amount,
                floor=floor,
                rarity=self._loot.loot_rarity(kind, payload),
            )
        )
