from __future__ import annotations

from shared.ai.context import ZombieActionResult, ZombieContext
from shared.ai.decisions import select_best_target
from shared.ai.zombies.base_zombie import BaseZombieAI
from shared.constants import SEARCH_DURATION, ZOMBIE_TARGET_RADIUS, ZOMBIES


class WalkerZombieAI(BaseZombieAI):
    kind = "walker"

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

            destination = self._resolve_destination(ctx, target)
            ctx.move_toward(zombie, destination, ctx.dt, True, ctx.rng)

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

    def _resolve_destination(self, ctx: ZombieContext, target):
        if target.inside_building:
            entry = ctx.building_entry_target(target.inside_building)
            if entry:
                return entry
        return target.pos

    def _try_attack(self, ctx: ZombieContext, target, result: ZombieActionResult) -> None:
        zombie = ctx.zombie
        spec = ZOMBIES[zombie.kind]

        if zombie.attack_cooldown > 0:
            return

        distance = zombie.pos.distance_to(target.pos)
        if distance > ZOMBIE_TARGET_RADIUS + spec.radius:
            return

        if ctx.line_blocked(zombie.pos, target.pos, zombie.floor):
            return

        damage = max(1, int(round(spec.damage * ctx.difficulty.zombie_damage_multiplier)))
        result.player_hits.append((target.id, damage))
        zombie.attack_cooldown = 0.85

    def _move_to_last_known(self, ctx: ZombieContext) -> None:
        zombie = ctx.zombie

        if not zombie.last_known_pos:
            zombie.mode = "patrol"
            return

        if zombie.pos.distance_to(zombie.last_known_pos) > 34:
            ctx.move_toward(zombie, zombie.last_known_pos, ctx.dt, False, ctx.rng)
            return

        zombie.mode = "search"
        zombie.search_timer = SEARCH_DURATION
        zombie.waypoint = None
        zombie.search_look_timer = 0.0

    def _patrol(self, ctx: ZombieContext) -> None:
        zombie = ctx.zombie

        if not zombie.waypoint or zombie.pos.distance_to(zombie.waypoint) < 32:
            zombie.waypoint = ctx.random_patrol_pos(ctx.rng)

        ctx.move_toward(zombie, zombie.waypoint, ctx.dt, False, ctx.rng)
