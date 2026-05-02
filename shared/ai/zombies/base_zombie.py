from __future__ import annotations

import math

from shared.ai.context import ZombieActionResult, ZombieContext, SoundEvent
from shared.ai.decisions import select_best_target
from shared.constants import SEARCH_DURATION, ZOMBIE_TARGET_RADIUS, ZOMBIES
from shared.models import PlayerState, Vec2


class BaseZombieAI:
    kind = "base"

    def update(self, ctx: ZombieContext) -> ZombieActionResult:
        zombie = ctx.zombie
        result = ZombieActionResult()

        self._tick_cooldowns(ctx)

        visible_target = self._visible_target(ctx)
        if visible_target:
            self._enter_chase(ctx, visible_target)
            self._update_chase(ctx, visible_target, result)
            return result

        heard_sound = self._heard_sound(ctx)
        if heard_sound and zombie.mode not in ("chase", "orient_to_sound"):
            if zombie.mode == "patrol":
                self._enter_orient_to_sound(ctx, heard_sound.pos)
                if heard_sound.source_player_id:
                    zombie.target_player_id = heard_sound.source_player_id
            else:
                zombie.last_known_pos = heard_sound.pos.copy()
                if heard_sound.source_player_id:
                    zombie.target_player_id = heard_sound.source_player_id
                zombie.search_timer = max(zombie.search_timer, 2.2)
                zombie.alertness = min(1.0, zombie.alertness + 0.12)
            return result

        if zombie.mode == "orient_to_sound":
            self._update_orient_to_sound(ctx)
        elif zombie.mode == "investigate":
            self._update_investigate(ctx)
        elif zombie.mode == "search":
            self._update_search(ctx)
        elif zombie.mode == "chase":
            self._update_lost_target(ctx)
        else:
            self._update_patrol(ctx)

        return result

    def _tick_cooldowns(self, ctx: ZombieContext) -> None:
        zombie = ctx.zombie
        zombie.attack_cooldown = max(0.0, zombie.attack_cooldown - ctx.dt)
        zombie.special_cooldown = max(0.0, zombie.special_cooldown - ctx.dt)
        zombie.sidestep_timer = max(0.0, zombie.sidestep_timer - ctx.dt)

    def _visible_target(self, ctx: ZombieContext) -> PlayerState | None:
        visible = [player for player in ctx.players if ctx.can_see(ctx.zombie, player)]
        if not visible:
            return None
        return min(visible, key=lambda player: ctx.zombie.pos.distance_to(player.pos))

    def _heard_sound(self, ctx: ZombieContext) -> SoundEvent | None:
        return ctx.can_hear(ctx.zombie)

    def _enter_chase(self, ctx: ZombieContext, target: PlayerState) -> None:
        zombie = ctx.zombie
        zombie.mode = "chase"
        zombie.target_player_id = target.id
        zombie.last_known_pos = target.pos.copy()
        zombie.search_timer = SEARCH_DURATION
        zombie.alertness = 1.0
        zombie.waypoint = None
        zombie.search_look_timer = 0.0

    def _enter_orient_to_sound(self, ctx: ZombieContext, sound_pos: Vec2) -> None:
        zombie = ctx.zombie
        zombie.mode = "orient_to_sound"
        zombie.target_player_id = None
        zombie.last_known_pos = sound_pos.copy()
        zombie.search_timer = 0.45
        zombie.alertness = max(zombie.alertness, 0.45)

        dx = sound_pos.x - zombie.pos.x
        dy = sound_pos.y - zombie.pos.y
        zombie.facing = math.atan2(dy, dx)

    def _update_orient_to_sound(self, ctx: ZombieContext) -> None:
        zombie = ctx.zombie

        if zombie.last_known_pos:
            self._turn_toward(
                zombie,
                zombie.last_known_pos,
                max_turn=ctx.dt * 4.5,
            )

        zombie.search_timer -= ctx.dt

        if zombie.search_timer <= 0.0:
            zombie.mode = "investigate"
            zombie.search_timer = 2.4

    def _update_chase(
        self,
        ctx: ZombieContext,
        target: PlayerState,
        result: ZombieActionResult,
    ) -> None:
        zombie = ctx.zombie

        destination = self._resolve_destination(ctx, target)
        ctx.move_toward(zombie, destination, ctx.dt, True, ctx.rng)

        self._try_attack(ctx, target, result)

    def _update_investigate(self, ctx: ZombieContext) -> None:
        zombie = ctx.zombie

        if not zombie.last_known_pos:
            self._enter_patrol(zombie)
            return

        if zombie.pos.distance_to(zombie.last_known_pos) > 38:
            ctx.move_toward(zombie, zombie.last_known_pos, ctx.dt, False, ctx.rng)
            return

        zombie.mode = "search"
        zombie.search_timer = SEARCH_DURATION
        zombie.waypoint = None
        zombie.search_look_timer = 0.0

    def _update_search(self, ctx: ZombieContext) -> None:
        zombie = ctx.zombie
        zombie.search_timer -= ctx.dt

        if zombie.search_timer <= 0:
            self._enter_patrol(zombie)
            return

        if zombie.search_look_timer > 0.0:
            zombie.search_look_timer = max(0.0, zombie.search_look_timer - ctx.dt)
            jitter = sum(ord(c) for c in zombie.id) * 0.011
            phase = ctx.time * (2.55 + zombie.alertness * 1.1) + jitter
            sway = math.sin(phase) * (0.52 + zombie.alertness * 0.3)
            sway += math.sin(phase * 2.31 + 0.6) * 0.22
            sway += math.sin(phase * 0.47 + 2.1) * 0.12
            zombie.facing = zombie.search_gaze_anchor + sway
            return

        base = zombie.last_known_pos or zombie.pos
        reach = 26.0 + ctx.rng.uniform(0.0, 9.0)

        if zombie.waypoint and zombie.pos.distance_to(zombie.waypoint) < reach:
            zombie.search_gaze_anchor = zombie.facing
            zombie.search_look_timer = ctx.rng.uniform(0.42, 1.08)
            zombie.waypoint = None
            return

        if not zombie.waypoint:
            wp = ctx.pick_search_waypoint(zombie, base, ctx.rng)
            zombie.waypoint = wp if wp is not None else ctx.random_patrol_pos(ctx.rng)

        ctx.move_toward(zombie, zombie.waypoint, ctx.dt, False, ctx.rng)

    def _update_patrol(self, ctx: ZombieContext) -> None:
        zombie = ctx.zombie

        if zombie.idle_timer > 0.0:
            zombie.idle_timer = max(0.0, zombie.idle_timer - ctx.dt)
            return

        reached = zombie.waypoint and zombie.pos.distance_to(zombie.waypoint) < 46

        if reached:
            if ctx.rng.random() < 0.45:
                zombie.idle_timer = ctx.rng.uniform(0.6, 2.2)
                zombie.waypoint = None
                return

            zombie.waypoint = None

        if not zombie.waypoint:
            zombie.waypoint = ctx.random_patrol_pos(ctx.rng)

        ctx.move_toward(zombie, zombie.waypoint, ctx.dt, False, ctx.rng)

    def _update_lost_target(self, ctx: ZombieContext) -> None:
        zombie = ctx.zombie

        if zombie.last_known_pos:
            zombie.mode = "investigate"
            zombie.search_timer = 2.4
            return

        self._enter_patrol(zombie)

    def _enter_patrol(self, zombie) -> None:
        zombie.mode = "patrol"
        zombie.target_player_id = None
        zombie.last_known_pos = None
        zombie.waypoint = None
        zombie.search_timer = 0.0
        zombie.search_look_timer = 0.0
        zombie.search_gaze_anchor = 0.0
        zombie.alertness = 0.0

    def _resolve_destination(self, ctx: ZombieContext, target: PlayerState) -> Vec2:
        if target.inside_building:
            entry = ctx.building_entry_target(target.inside_building)
            if entry:
                return entry
        return target.pos

    def _turn_toward(self, zombie, target_pos: Vec2, max_turn: float) -> None:
        desired = zombie.pos.angle_to(target_pos)
        delta = (desired - zombie.facing + math.pi) % math.tau - math.pi

        if abs(delta) <= max_turn:
            zombie.facing = desired
            return

        zombie.facing += max_turn if delta > 0 else -max_turn

    def _try_attack(
        self,
        ctx: ZombieContext,
        target: PlayerState,
        result: ZombieActionResult,
    ) -> None:
        zombie = ctx.zombie
        spec = ZOMBIES[zombie.kind]

        if zombie.attack_cooldown > 0:
            return

        if zombie.pos.distance_to(target.pos) > ZOMBIE_TARGET_RADIUS + spec.radius:
            return

        if ctx.line_blocked(zombie.pos, target.pos, zombie.floor):
            return

        damage = max(1, int(round(spec.damage * ctx.difficulty.zombie_damage_multiplier)))
        result.player_hits.append((target.id, damage))
        zombie.attack_cooldown = 0.85