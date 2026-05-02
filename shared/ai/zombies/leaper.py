from __future__ import annotations

import math

from shared.ai.context import ZombieActionResult, ZombieContext
from shared.ai.zombies.base_zombie import BaseZombieAI
from shared.ai.zombies.scores import LeaperDecisionScorer, LeaperTuning
from shared.constants import MAP_WIDTH, MAP_HEIGHT
from shared.models import PlayerState, Vec2


class LeaperZombieAI(BaseZombieAI):
    kind = "leaper"
    scorer = LeaperDecisionScorer()
    tuning = LeaperTuning()

    def _update_chase(
            self,
            ctx: ZombieContext,
            target: PlayerState,
            result: ZombieActionResult,
    ) -> None:
        self._strafe_for_spit(ctx, target)
        self._try_special(ctx, target, result)

    def _update_special(
            self,
            ctx: ZombieContext,
            target: PlayerState,
            result: ZombieActionResult,
    ) -> None:
        self._strafe_for_spit(ctx, target)
        self._try_special(ctx, target, result)

    def _strafe_for_spit(self, ctx: ZombieContext, target: PlayerState) -> None:
        zombie = ctx.zombie
        distance = zombie.pos.distance_to(target.pos)

        to_target = Vec2(
            target.pos.x - zombie.pos.x,
            target.pos.y - zombie.pos.y,
        )

        if to_target.length() <= 0.01:
            return

        forward = to_target.normalized()
        right = Vec2(-forward.y, forward.x)

        if zombie.sidestep_timer <= 0.0:
            zombie.sidestep_timer = ctx.rng.uniform(0.75, 1.35)
            zombie.sidestep_bias = ctx.rng.choice([-1.0, 1.0])

        ideal = self.tuning.spit_best_distance
        retreat_distance = ideal - 90.0
        approach_distance = ideal + 140.0

        # Далеко — подойти диагонально, но не прямо в игрока.
        if distance > approach_distance:
            move = Vec2(
                forward.x * 0.55 + right.x * 0.65 * zombie.sidestep_bias,
                forward.y * 0.55 + right.y * 0.65 * zombie.sidestep_bias,
            ).normalized()

        # Игрок слишком близко — отходить назад + вбок.
        elif distance < retreat_distance:
            move = Vec2(
                -forward.x * 0.95 + right.x * 0.75 * zombie.sidestep_bias,
                -forward.y * 0.95 + right.y * 0.75 * zombie.sidestep_bias,
            ).normalized()

        # Хорошая дистанция — чистый стрейф влево/вправо.
        else:
            move = Vec2(
                right.x * zombie.sidestep_bias,
                right.y * zombie.sidestep_bias,
            ).normalized()

        zombie.facing = math.atan2(forward.y, forward.x)

        # Важно: точка должна быть достаточно далёкая, иначе он почти стоит.
        move_target = Vec2(
            zombie.pos.x + move.x * 420.0,
            zombie.pos.y + move.y * 420.0,
        )
        move_target.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)

        before = zombie.pos.copy()
        ctx.move_toward(zombie, move_target, ctx.dt, True, ctx.rng)

        if zombie.pos.distance_to(before) < 0.4:
            zombie.sidestep_bias *= -1.0
            zombie.sidestep_timer = 0.25

    def _try_special(
        self,
        ctx: ZombieContext,
        target: PlayerState,
        result: ZombieActionResult,
    ) -> None:
        zombie = ctx.zombie

        if zombie.special_cooldown > 0:
            return

        if target.inside_building:
            return

        distance = zombie.pos.distance_to(target.pos)

        if distance < self.tuning.spit_min_distance:
            return

        if distance > self.tuning.spit_max_distance:
            return

        if ctx.line_blocked(zombie.pos, target.pos, zombie.floor):
            return

        direction_x = target.pos.x - zombie.pos.x
        direction_y = target.pos.y - zombie.pos.y
        length = max(1.0, math.hypot(direction_x, direction_y))

        velocity = Vec2(
            direction_x / length * self.tuning.spit_projectile_speed,
            direction_y / length * self.tuning.spit_projectile_speed,
        )

        result.poison_spits.append(
            {
                "owner_id": zombie.id,
                "pos": zombie.pos.copy(),
                "velocity": velocity,
                "target": target.pos.copy(),
                "floor": zombie.floor,
            }
        )

        zombie.special_cooldown = ctx.rng.uniform(
            self.tuning.spit_cooldown_min,
            self.tuning.spit_cooldown_max,
        )