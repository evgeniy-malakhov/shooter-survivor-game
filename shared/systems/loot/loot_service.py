from __future__ import annotations

import random

from shared.constants import WEAPONS
from shared.items import ITEMS, WORLD_LOOT
from shared.models import LootState, Vec2
from shared.rarities import RARITIES
from shared.world.world_state import WorldState


class LootService:
    def __init__(self, state: WorldState, rng: random.Random) -> None:
        self._state = state
        self._rng = rng

    def spawn_loot(
        self,
        *,
        loot_id: str,
        pos: Vec2,
        kind: str,
        payload: str,
        amount: int,
        floor: int = 0,
        rarity: str | None = None,
    ) -> LootState:
        if kind == "medkit":
            payload = "medkit"

        item_rarity = rarity or self.loot_rarity(kind, payload)

        item = LootState(
            loot_id,
            kind,
            pos,
            payload,
            amount,
            floor=floor,
            rarity=item_rarity,
        )

        self._state.loot[item.id] = item
        return item

    def loot_rarity(self, kind: str, payload: str) -> str:
        spec = ITEMS.get(payload)

        if kind in {"weapon", "armor"} or (kind == "item" and spec and spec.kind == "armor"):
            return self.roll_rarity()

        return "common"

    def roll_rarity(self) -> str:
        keys = list(RARITIES)
        weights = [RARITIES[key].loot_weight for key in keys]

        if sum(weights) <= 0:
            return "common"

        return self._rng.choices(keys, weights=weights)[0]

    def random_world_loot(self) -> tuple[str, str, int]:
        roll = self._rng.random()

        if roll < 0.30:
            item_key = self._rng.choices(
                [item[0] for item in WORLD_LOOT],
                weights=[item[2] for item in WORLD_LOOT],
            )[0]
            return "item", item_key, self._rng.randint(1, 3)

        if roll < 0.52:
            return "ammo", self._rng.choice(list(WEAPONS)), self._rng.randint(10, 35)

        if roll < 0.65:
            return "medkit", "medkit", 1

        if roll < 0.83:
            return "armor", self._rng.choice(["light", "tactical", "heavy"]), 1

        return "weapon", self._rng.choice(["smg", "shotgun", "rifle"]), 1