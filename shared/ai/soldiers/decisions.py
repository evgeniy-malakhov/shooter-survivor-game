from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from shared.ai.context import ActorTarget
from shared.ai.soldiers.context import SoldierContext


class SoldierDecisionKind(str, Enum):
    GUARD = "guard"
    COMBAT = "combat"
    RELOAD = "reload"
    RETREAT = "retreat"
    INVESTIGATE = "investigate"


@dataclass(slots=True)
class SoldierDecision:
    kind: SoldierDecisionKind
    score: float
    target: ActorTarget | None = None


@dataclass(frozen=True, slots=True)
class SoldierDecisionWeights:
    zombie_priority: float = 160.0
    player_priority: float = 110.0
    distance: float = 80.0
    low_ammo_reload: float = 250.0
    close_threat_retreat: float = 220.0
    guard: float = 10.0


class SoldierDecisionScorer:
    weights = SoldierDecisionWeights()

    def choose(self, ctx: SoldierContext) -> SoldierDecision:
        decisions: list[SoldierDecision] = []

        if ctx.soldier.weapon.reload_left > 0.0:
            return SoldierDecision(SoldierDecisionKind.RELOAD, 999.0)

        if ctx.soldier.weapon.ammo_in_mag <= 0 and ctx.soldier.weapon.reserve_ammo > 0:
            return SoldierDecision(SoldierDecisionKind.RELOAD, self.weights.low_ammo_reload)

        visible_targets = self._visible_targets(ctx)

        for target in visible_targets:
            dist = ctx.soldier.pos.distance_to(target.pos)

            if dist < self._danger_distance(ctx):
                decisions.append(
                    SoldierDecision(
                        kind=SoldierDecisionKind.RETREAT,
                        score=self.weights.close_threat_retreat + max(0.0, 200.0 - dist),
                        target=target,
                    )
                )

            base = self.weights.zombie_priority if target.kind == "zombie" else self.weights.player_priority
            score = base + max(0.0, self.weights.distance - dist / 10.0)

            decisions.append(
                SoldierDecision(
                    kind=SoldierDecisionKind.COMBAT,
                    score=score,
                    target=target,
                )
            )

        decisions.append(SoldierDecision(SoldierDecisionKind.GUARD, self.weights.guard))

        return max(decisions, key=lambda d: d.score)

    def _visible_targets(self, ctx: SoldierContext) -> list[ActorTarget]:
        result: list[ActorTarget] = []

        for target in ctx.targets:
            if not target.alive:
                continue

            if target.floor != ctx.soldier.floor:
                continue

            if target.kind not in {"zombie", "player"}:
                continue

            if target.kind == "player" and target.inside_building:
                continue

            dist = ctx.soldier.pos.distance_to(target.pos)

            if dist > ctx.spec.sight_range:
                continue

            angle = ctx.soldier.pos.angle_to(target.pos)
            delta = (angle - ctx.soldier.facing + math.pi) % math.tau - math.pi

            if abs(delta) > math.radians(ctx.spec.fov_degrees * 0.5):
                continue

            if ctx.line_blocked(ctx.soldier.pos, target.pos, ctx.soldier.floor):
                continue

            result.append(target)

        return result

    def _danger_distance(self, ctx: SoldierContext) -> float:
        return max(170.0, ctx.spec.radius + 120.0)