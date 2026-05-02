from __future__ import annotations

import math

from shared.ai.context import ZombieActionResult, ZombieContext, SoundEvent
from shared.ai.decisions import DecisionScorer, ZombieDecision, ZombieDecisionKind
from shared.constants import SEARCH_DURATION, ZOMBIE_TARGET_RADIUS, ZOMBIES
from shared.models import PlayerState, Vec2


class BaseZombieAI:
    kind = "base"
    scorer: DecisionScorer = DecisionScorer()

    def update(self, ctx: ZombieContext) -> ZombieActionResult:
        zombie = ctx.zombie
        result = ZombieActionResult()

        self._tick_cooldowns(ctx)

        decision = self.scorer.choose(ctx)
        self._apply_decision(ctx, decision, result)

        return result

    def _apply_decision(
            self,
            ctx: ZombieContext,
            decision: ZombieDecision,
            result: ZombieActionResult,
    ) -> None:
        zombie = ctx.zombie

        if decision.kind == ZombieDecisionKind.SPECIAL and decision.target:
            self._enter_chase(ctx, decision.target)
            self._update_special(ctx, decision.target, result)
            return

        if decision.kind == ZombieDecisionKind.ATTACK and decision.target:
            self._enter_chase(ctx, decision.target)
            self._update_chase(ctx, decision.target, result)
            return

        if decision.kind == ZombieDecisionKind.CHASE_VISIBLE_TARGET and decision.target:
            self._enter_chase(ctx, decision.target)
            self._update_chase(ctx, decision.target, result)
            return

        if decision.kind == ZombieDecisionKind.ORIENT_TO_SOUND and decision.pos:
            self._react_to_sound_decision(ctx, decision)
            return

        if zombie.mode == "orient_to_sound":
            self._update_orient_to_sound(ctx)
            return

        if zombie.mode == "investigate":
            self._update_investigate(ctx)
            return

        if zombie.mode == "search":
            self._update_search(ctx)
            return

        if decision.kind == ZombieDecisionKind.SEARCH_LAST_KNOWN:
            if zombie.mode == "chase":
                self._update_lost_target(ctx)
            else:
                self._update_investigate(ctx)
            return

        self._update_patrol(ctx)

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

    def _sound_reaction_delay(self, ctx: ZombieContext, decision) -> float:
        tuning = self.scorer.sound_tuning

        if decision.score >= tuning.instant_reaction_score:
            return 0.0

        t = max(0.0, min(1.0, decision.score / tuning.instant_reaction_score))
        return tuning.reaction_delay_max - (t * (tuning.reaction_delay_max - tuning.reaction_delay_min))

    def _react_to_sound_decision(
            self,
            ctx: ZombieContext,
            decision: ZombieDecision,
    ) -> None:
        zombie = ctx.zombie

        sound_pos = decision.pos
        if not sound_pos:
            return

        zombie.last_known_pos = sound_pos.copy()
        zombie.target_player_id = None
        zombie.alertness = min(1.0, zombie.alertness + 0.18)

        # Если бот уже расследует/ищет источник — не стопорим его заново.
        # Просто обновляем точку интереса.
        if zombie.mode in {"investigate", "search"}:
            zombie.mode = "investigate"
            zombie.search_timer = max(zombie.search_timer, 2.2)
            zombie.waypoint = None
            return

        # Если бот уже повернулся на звук — тоже не сбрасываем реакцию.
        if zombie.mode == "orient_to_sound":
            zombie.search_timer = min(zombie.search_timer, 0.25)
            return

        # Если бот в chase, звук не должен ломать преследование.
        if zombie.mode == "chase":
            return

        # Только patrol получает полноценную первую реакцию.
        delay = self._sound_reaction_delay(ctx, decision)

        if delay <= 0.0:
            self._enter_orient_to_sound(ctx, sound_pos)
            return

        zombie.mode = "orient_to_sound"
        zombie.search_timer = delay

    def _update_chase(
        self,
        ctx: ZombieContext,
        target: PlayerState,
        result: ZombieActionResult,
    ) -> None:
        zombie = ctx.zombie

        self._try_special(ctx, target, result)

        destination = self._resolve_destination(ctx, target)
        self._move_to(ctx, destination, sprint=True)

        self._try_attack(ctx, target, result)

    def _update_special(
            self,
            ctx: ZombieContext,
            target: PlayerState,
            result: ZombieActionResult,
    ) -> None:
        self._try_special(ctx, target, result)

        destination = self._resolve_destination(ctx, target)
        self._move_to(ctx, destination, sprint=True)

    def _update_investigate(self, ctx: ZombieContext) -> None:
        zombie = ctx.zombie

        if not zombie.last_known_pos:
            self._enter_patrol(zombie)
            return

        if zombie.pos.distance_to(zombie.last_known_pos) > 38:
            self._move_to(ctx, zombie.last_known_pos, sprint=False)
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

        self._move_to(ctx, zombie.waypoint, sprint=False)

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

        self._move_to(ctx, zombie.waypoint, sprint=False)

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

    def _move_to(self, ctx: ZombieContext, destination: Vec2, sprint: bool) -> None:
        #next_point = ctx.path_next_point(ctx.zombie, destination)
        ctx.move_toward(ctx.zombie, destination, ctx.dt, sprint, ctx.rng)

    def _try_special(
        self,
        ctx: ZombieContext,
        target: PlayerState,
        result: ZombieActionResult,
    ) -> None:
        return

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