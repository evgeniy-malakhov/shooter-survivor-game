from __future__ import annotations

from shared.ai.soldiers.base import BaseSoldierAI
from shared.ai.soldiers.decisions import SoldierDecisionScorer, SoldierDecisionWeights


class RiflemanDecisionScorer(SoldierDecisionScorer):
    weights = SoldierDecisionWeights(
        zombie_priority=170.0,
        player_priority=115.0,
        distance=85.0,
        low_ammo_reload=260.0,
        close_threat_retreat=230.0,
        guard=10.0,
    )


class RiflemanSoldierAI(BaseSoldierAI):
    kind = "rifleman"
    scorer = RiflemanDecisionScorer()