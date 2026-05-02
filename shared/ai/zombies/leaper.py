from __future__ import annotations

import math

from shared.ai.context import ZombieActionResult, ZombieContext
from shared.ai.decisions import select_best_target
from shared.ai.zombies.walker import WalkerZombieAI
from shared.constants import SEARCH_DURATION


class LeaperZombieAI(WalkerZombieAI):
    kind = "leaper"

    def update(self, ctx: ZombieContext) -> ZombieActionResult:
        zombie = ctx.zombie
        result = ZombieActionResult()

        zombie.attack_cooldown = max(0.0, zombie.attack_cooldown - ctx.dt)
        zombie.special_cooldown = max(0.0, zombie.special_cooldown - ctx.dt)
        zombie.sidestep_timer = max(0.0, zombie.sidestep_timer - ctx.dt)

        target = select_best_target(ctx)

        if target:
            zombie.mode = "chase"
            zombie.target_player_id = target.id
            zombie.last_known_pos = target.pos.copy()
            zombie.search_timer = SEARCH_DURATION
            zombie.alertness = 1.0
            zombie.waypoint = None
            zombie.search_look_timer = 0.0

            self._try_poison_spit(ctx, target, result)
            ctx.move_toward(zombie, target.pos, ctx.dt, True, ctx.rng)
            self._try_attack(ctx, target, result)

            return result

        heard = ctx.can_hear(ctx.zombie)

        if zombie.last_known_pos:
            if heard:
                zombie.last_known_pos = heard.pos.copy()
                if heard.source_player_id:
                    zombie.target_player_id = heard.source_player_id
                zombie.alertness = min(1.0, zombie.alertness + 0.06)
            if zombie.mode == "search":
                self._update_search(ctx)
                return result
            zombie.mode = "investigate"
            self._move_to_last_known(ctx)
            return result

        if heard:
            zombie.last_known_pos = heard.pos.copy()
            zombie.target_player_id = heard.source_player_id
            zombie.mode = "investigate"
            zombie.search_timer = max(2.4, zombie.search_timer)
            zombie.alertness = min(1.0, zombie.alertness + 0.28)
            self._move_to_last_known(ctx)
            return result

        self._patrol(ctx)
        return result

    def _try_poison_spit(self, ctx: ZombieContext, target, result: ZombieActionResult) -> None:
        zombie = ctx.zombie

        if zombie.special_cooldown > 0:
            return

        distance = zombie.pos.distance_to(target.pos)

        if distance < 180 or distance > 720:
            return

        if ctx.line_blocked(zombie.pos, target.pos, zombie.floor):
            return

        direction_x = target.pos.x - zombie.pos.x
        direction_y = target.pos.y - zombie.pos.y
        length = max(1.0, math.hypot(direction_x, direction_y))

        velocity = type(zombie.pos)(
            direction_x / length * 520.0,
            direction_y / length * 520.0,
        )

        result.poison_spits.append({
            "owner_id": zombie.id,
            "pos": zombie.pos.copy(),
            "velocity": velocity,
            "target": target.pos.copy(),
            "floor": zombie.floor,
        })

        zombie.special_cooldown = ctx.rng.uniform(2.8, 4.4)