from __future__ import annotations

from typing import cast

from shared.ai.soldiers.base import BaseSoldierAI
from shared.ai.soldiers.types.rifleman import RiflemanSoldierAI


SOLDIER_AI_REGISTRY: dict[str, BaseSoldierAI] = {
    "rifleman": cast(BaseSoldierAI, RiflemanSoldierAI()),
}