from __future__ import annotations

from dataclasses import dataclass

from shared.ai.context import ZombieContext
from shared.models import PlayerState


@dataclass(slots=True)
class TargetScore:
    player: PlayerState
    score: float


def score_player_target(ctx: ZombieContext, player: PlayerState) -> float:
    zombie = ctx.zombie

    if player.floor != zombie.floor or not player.alive:
        return -1.0

    if not ctx.can_see(zombie, player):
        return -1.0

    score = 100.0
    distance = zombie.pos.distance_to(player.pos)

    score += max(0.0, 60.0 - distance / 12.0)

    if player.health <= 35:
        score += 18.0

    if player.sprinting:
        score += 12.0

    if player.sneaking:
        score -= 20.0

    return score


def select_best_target(ctx: ZombieContext) -> PlayerState | None:
    scored = [
        TargetScore(player, score_player_target(ctx, player))
        for player in ctx.players
    ]

    scored = [item for item in scored if item.score > 0]

    if not scored:
        return None

    return max(scored, key=lambda item: item.score).player