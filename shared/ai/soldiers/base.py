from __future__ import annotations

import math

from shared.ai.context import ActorTarget
from shared.ai.cover import choose_cover_position
from shared.ai.soldiers.context import SoldierActionResult, SoldierContext
from shared.ai.soldiers.decisions import SoldierDecision, SoldierDecisionKind, SoldierDecisionScorer
from shared.constants import MAP_HEIGHT, MAP_WIDTH, SHOT_NOISE
from shared.models import Vec2


class BaseSoldierAI:
    kind = "base"
    scorer = SoldierDecisionScorer()

    def update(self, ctx: SoldierContext) -> SoldierActionResult:
        result = SoldierActionResult()
        ctx.soldier.sprinting = False

        self._tick(ctx)

        decision = self.scorer.choose(ctx)
        self._apply_decision(ctx, decision, result)

        return result

    def _tick(self, ctx: SoldierContext) -> None:
        soldier = ctx.soldier
        soldier.attack_cooldown = max(0.0, soldier.attack_cooldown - ctx.dt)
        soldier.grenade_cooldown = max(0.0, soldier.grenade_cooldown - ctx.dt)
        soldier.support_cooldown = max(0.0, soldier.support_cooldown - ctx.dt)

        if soldier.weapon.reload_left > 0.0:
            soldier.weapon.reload_left = max(0.0, soldier.weapon.reload_left - ctx.dt)

            if soldier.weapon.reload_left <= 0.0:
                self._finish_reload(ctx)

    def _apply_decision(
        self,
        ctx: SoldierContext,
        decision: SoldierDecision,
        result: SoldierActionResult,
    ) -> None:
        soldier = ctx.soldier

        if decision.kind == SoldierDecisionKind.RELOAD:
            self._start_reload(ctx)
            return

        if decision.kind == SoldierDecisionKind.HEAL_ALLY and decision.target:
            soldier.mode = "support"
            soldier.last_known_pos = decision.target.pos.copy()
            self._try_heal(ctx, decision.target, result)
            return

        if decision.kind == SoldierDecisionKind.THROW_GRENADE and decision.target:
            soldier.mode = "combat"
            soldier.target_id = decision.target.id
            soldier.target_kind = decision.target.kind
            soldier.last_known_pos = decision.target.pos.copy()
            self._try_special(ctx, decision.target, result)
            self._try_shoot(ctx, decision.target, result)
            return

        if decision.kind == SoldierDecisionKind.RETREAT and decision.target:
            soldier.mode = "retreat"
            soldier.target_id = decision.target.id
            soldier.target_kind = decision.target.kind
            soldier.last_known_pos = decision.target.pos.copy()
            self._retreat_from(ctx, decision.target)
            self._try_shoot(ctx, decision.target, result)
            return

        if decision.kind == SoldierDecisionKind.COMBAT and decision.target:
            soldier.mode = "combat"
            soldier.target_id = decision.target.id
            soldier.target_kind = decision.target.kind
            soldier.last_known_pos = decision.target.pos.copy()
            self._combat(ctx, decision.target, result)
            return

        if decision.kind == SoldierDecisionKind.SQUAD_MOVE and decision.pos:
            soldier.mode = "squad"
            soldier.last_known_pos = decision.pos.copy()
            if soldier.pos.distance_to(decision.pos) > 54:
                soldier.sprinting = True
                ctx.move_toward(soldier, decision.pos, ctx.dt, ctx.rng)
            else:
                soldier.sprinting = False
            return

        if decision.kind == SoldierDecisionKind.HOLD_POSITION:
            soldier.mode = "hold"
            soldier.sprinting = False
            if decision.pos and soldier.pos.distance_to(decision.pos) > 72:
                ctx.move_toward(soldier, decision.pos, ctx.dt * 0.65, ctx.rng)
            return

        if decision.kind in {SoldierDecisionKind.INVESTIGATE, SoldierDecisionKind.INVESTIGATE_SOUND} and decision.pos:
            soldier.mode = "investigate"
            soldier.last_known_pos = decision.pos.copy()
            soldier.alertness = min(1.0, soldier.alertness + 0.25)
            self._investigate(ctx)
            return

        if soldier.mode in {"combat", "investigate"} and soldier.last_known_pos:
            self._investigate(ctx)
            return

        self._guard(ctx)

    def _combat(
        self,
        ctx: SoldierContext,
        target: ActorTarget,
        result: SoldierActionResult,
    ) -> None:
        soldier = ctx.soldier
        soldier.facing = soldier.pos.angle_to(target.pos)

        distance = soldier.pos.distance_to(target.pos)

        if distance > ctx.spec.fire_range:
            soldier.sprinting = True
            ctx.move_toward(soldier, target.pos, ctx.dt, ctx.rng)
            return

        self._try_shoot(ctx, target, result)

    def _try_special(
        self,
        ctx: SoldierContext,
        target: ActorTarget,
        result: SoldierActionResult,
    ) -> None:
        return

    def _try_heal(
        self,
        ctx: SoldierContext,
        target: ActorTarget,
        result: SoldierActionResult,
    ) -> None:
        return

    def _try_shoot(
        self,
        ctx: SoldierContext,
        target: ActorTarget,
        result: SoldierActionResult,
    ) -> None:
        soldier = ctx.soldier

        if soldier.attack_cooldown > 0.0:
            return

        if soldier.weapon.reload_left > 0.0:
            return

        if soldier.weapon.ammo_in_mag <= 0:
            self._start_reload(ctx)
            return

        if soldier.pos.distance_to(target.pos) > ctx.spec.fire_range:
            return

        if ctx.line_blocked(soldier.pos, target.pos, soldier.floor):
            return

        soldier.facing = soldier.pos.angle_to(target.pos)

        shots = min(soldier.weapon.ammo_in_mag, self._shots_per_attack(ctx))
        pellets = max(1, int(getattr(ctx.weapon, "pellets", 1)))
        spread_max = self._spread_for_weapon(ctx)

        for _ in range(shots):
            for _pellet in range(pellets):
                spread = ctx.rng.uniform(-spread_max, spread_max)
                angle = soldier.facing + spread

                start = Vec2(
                    soldier.pos.x + math.cos(angle) * (ctx.spec.radius + 10),
                    soldier.pos.y + math.sin(angle) * (ctx.spec.radius + 10),
                )

                velocity = Vec2(
                    math.cos(angle) * ctx.spec.projectile_speed,
                    math.sin(angle) * ctx.spec.projectile_speed,
                )

                result.projectiles.append(
                    {
                        "owner_id": soldier.id,
                        "pos": start,
                        "velocity": velocity,
                        "damage": ctx.spec.damage,
                        "life": ctx.projectile_life(ctx.spec.projectile_speed),
                        "radius": getattr(ctx.weapon, "projectile_radius", 4.5),
                        "floor": soldier.floor,
                        "weapon_key": ctx.spec.weapon_key,
                    }
                )

        result.sounds.append(
            {
                "pos": soldier.pos.copy(),
                "floor": soldier.floor,
                "radius": SHOT_NOISE * 1.4,
                "kind": "shot",
                "intensity": 0.95,
                "source_player_id": soldier.id,
            }
        )

        soldier.weapon.ammo_in_mag -= shots
        soldier.attack_cooldown = ctx.spec.fire_cooldown

        if soldier.weapon.ammo_in_mag <= 0:
            self._start_reload(ctx)

    def _shots_per_attack(self, ctx: SoldierContext) -> int:
        if ctx.spec.weapon_key in {"rifle", "smg"}:
            return 3
        return 1

    def _spread_for_weapon(self, ctx: SoldierContext) -> float:
        weapon_spread = max(0.01, float(getattr(ctx.weapon, "spread", 0.04)))
        skill_spread = max(0.01, (1.0 - ctx.spec.accuracy) * 0.18)
        return max(weapon_spread, skill_spread)

    def _start_reload(self, ctx: SoldierContext) -> None:
        soldier = ctx.soldier

        if soldier.weapon.reload_left > 0.0:
            return

        if soldier.weapon.reserve_ammo <= 0:
            return

        if soldier.weapon.ammo_in_mag >= ctx.spec.magazine_size:
            return

        soldier.mode = "reload"
        soldier.weapon.reload_left = ctx.weapon.reload_time

    def _finish_reload(self, ctx: SoldierContext) -> None:
        soldier = ctx.soldier
        need = ctx.spec.magazine_size - soldier.weapon.ammo_in_mag
        loaded = min(need, soldier.weapon.reserve_ammo)

        soldier.weapon.ammo_in_mag += loaded
        soldier.weapon.reserve_ammo -= loaded
        soldier.weapon.reload_left = 0.0
        soldier.mode = "combat" if soldier.target_id else "guard"

    def _retreat_from(self, ctx: SoldierContext, target: ActorTarget) -> None:
        soldier = ctx.soldier

        away = Vec2(
            soldier.pos.x - target.pos.x,
            soldier.pos.y - target.pos.y,
        )

        if away.length() <= 0.01:
            away = Vec2(math.cos(soldier.facing + math.pi), math.sin(soldier.facing + math.pi))

        direction = away.normalized()

        soldier.facing = soldier.pos.angle_to(target.pos)

        step_target = choose_cover_position(
            origin=soldier.pos,
            threat=target.pos,
            floor=soldier.floor,
            line_blocked=ctx.line_blocked,
            rng=ctx.rng,
        )
        if step_target is None:
            step_target = Vec2(
                soldier.pos.x + direction.x * 180.0,
                soldier.pos.y + direction.y * 180.0,
            )
        step_target.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)

        ctx.move_toward(soldier, step_target, ctx.dt * 0.62, ctx.rng)
        soldier.sprinting = True

    def _investigate(self, ctx: SoldierContext) -> None:
        soldier = ctx.soldier

        if not soldier.last_known_pos:
            soldier.mode = "guard"
            return

        if soldier.pos.distance_to(soldier.last_known_pos) > 42:
            soldier.sprinting = True
            ctx.move_toward(soldier, soldier.last_known_pos, ctx.dt, ctx.rng)
            return

        soldier.mode = "guard"
        soldier.target_id = None
        soldier.target_kind = None
        soldier.last_known_pos = None
        soldier.waypoint = None
        soldier.alertness = max(0.0, soldier.alertness - ctx.dt * 0.35)

    def _guard(self, ctx: SoldierContext) -> None:
        soldier = ctx.soldier
        soldier.mode = "guard"
        soldier.sprinting = False
        soldier.alertness = max(0.0, soldier.alertness - ctx.dt * 0.18)

        if soldier.idle_timer > 0.0:
            soldier.idle_timer = max(0.0, soldier.idle_timer - ctx.dt)
            return

        if not soldier.guard_point:
            soldier.guard_point = soldier.pos.copy()

        if not soldier.waypoint or soldier.pos.distance_to(soldier.waypoint) < 36:
            soldier.waypoint = ctx.random_guard_pos(soldier, ctx.rng)

            if ctx.rng.random() < 0.35:
                soldier.idle_timer = ctx.rng.uniform(0.5, 1.8)
                return

        ctx.move_toward(soldier, soldier.waypoint, ctx.dt, ctx.rng)
