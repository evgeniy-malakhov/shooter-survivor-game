from __future__ import annotations

from shared.ai.soldiers.base import BaseSoldierAI
from shared.ai.soldiers.configs.rifleman import RIFLEMAN_DECISION_WEIGHTS, RIFLEMAN_HEARING
from shared.ai.soldiers.configs.schema import SoldierDecisionWeights, SoldierHearingTuning
from shared.ai.soldiers.decisions import SoldierDecisionScorer


class RiflemanDecisionScorer(SoldierDecisionScorer):
    weights = SoldierDecisionWeights(**RIFLEMAN_DECISION_WEIGHTS)
    hearing_tuning = SoldierHearingTuning(**RIFLEMAN_HEARING)


class RiflemanSoldierAI(BaseSoldierAI):
    kind = "rifleman"
    scorer = RiflemanDecisionScorer()
