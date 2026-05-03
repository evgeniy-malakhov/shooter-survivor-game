from __future__ import annotations

from shared.constants import MAP_HEIGHT, MAP_WIDTH, PLAYER_RADIUS
from shared.models import PlayerState, PoisonPoolState, Vec2
from shared.systems.base import WorldSystem
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class PoisonSystem(WorldSystem):
    def update(self, state: WorldState, ctx: WorldContext, dt: float) -> None:
        self._update_projectiles(state, ctx, dt)
        self._update_pools(state, dt)
        self._update_poisoned_players(state, dt)

    def _update_projectiles(self, state: WorldState, ctx: WorldContext, dt: float) -> None:
        expired: list[str] = []

        for spit in list(state.poison_projectiles.values()):
            spit.life -= dt
            old_pos = spit.pos.copy()
            spit.pos.add(spit.velocity.scaled(dt))

            hit_wall = ctx.geometry.blocked_at(spit.pos, spit.radius, spit.floor)
            reached_target = (
                old_pos.distance_to(spit.target) <= spit.pos.distance_to(spit.target)
                or spit.pos.distance_to(spit.target) <= 18
            )

            hit_player = self._find_hit_player(state, spit.pos, spit.radius, spit.floor)

            if hit_player:
                self.apply_poison(hit_player, damage_per_tick=3)
                expired.append(spit.id)
            elif hit_wall or reached_target or spit.life <= 0.0:
                pool_pos = spit.target if reached_target else spit.pos
                self._spawn_pool(state, ctx, pool_pos, spit.floor)
                expired.append(spit.id)

        for spit_id in expired:
            state.poison_projectiles.pop(spit_id, None)

    def _update_pools(self, state: WorldState, dt: float) -> None:
        expired: list[str] = []

        for pool in list(state.poison_pools.values()):
            pool.timer -= dt

            if pool.timer <= 0.0:
                expired.append(pool.id)
                continue

            for player in state.players.values():
                if (
                    player.alive
                    and player.floor == pool.floor
                    and player.pos.distance_to(pool.pos) <= pool.radius + PLAYER_RADIUS * 0.35
                ):
                    self.apply_poison(player, damage_per_tick=2)

        for pool_id in expired:
            state.poison_pools.pop(pool_id, None)

    def _update_poisoned_players(self, state: WorldState, dt: float) -> None:
        for player in state.players.values():
            if player.poison_left <= 0.0 or not player.alive:
                player.poison_left = 0.0
                player.poison_tick = 0.0
                player.poison_damage = 0
                continue

            player.poison_left = max(0.0, player.poison_left - dt)
            player.poison_tick -= dt

            if player.poison_tick <= 0.0:
                player.poison_tick = 1.0
                self._apply_poison_damage(player, max(1, player.poison_damage))

    def apply_poison(self, player: PlayerState, damage_per_tick: int) -> None:
        if player.poison_left <= 0.0:
            player.poison_tick = 1.0

        player.poison_left = max(player.poison_left, 5.0)

        if player.poison_tick <= 0.0:
            player.poison_tick = 1.0

        player.poison_damage = max(player.poison_damage, damage_per_tick)

    def _apply_poison_damage(self, player: PlayerState, damage: int) -> None:
        player.healing_left = 0.0
        player.healing_pool = 0.0
        player.healing_rate = 0.0
        player.health -= damage

        if player.health <= 0:
            player.health = 0
            player.alive = False

    def _spawn_pool(
        self,
        state: WorldState,
        ctx: WorldContext,
        pos: Vec2,
        floor: int,
    ) -> None:
        pool_id = ctx.ids.next("acid")
        pool_pos = pos.copy()
        pool_pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)

        state.poison_pools[pool_id] = PoisonPoolState(
            pool_id,
            pool_pos,
            floor=floor,
            timer=5.0,
        )

    def _find_hit_player(
        self,
        state: WorldState,
        pos: Vec2,
        radius: float,
        floor: int,
    ) -> PlayerState | None:
        for player in state.players.values():
            if (
                player.alive
                and player.floor == floor
                and player.pos.distance_to(pos) <= PLAYER_RADIUS + radius
            ):
                return player

        return None