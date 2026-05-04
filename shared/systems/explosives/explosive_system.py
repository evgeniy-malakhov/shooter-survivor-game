from __future__ import annotations

import math

from shared.constants import PLAYER_RADIUS, ZOMBIES
from shared.explosives import DEFAULT_GRENADE, DEFAULT_MINE, GRENADE_SPECS, MINE_SPECS
from shared.models import GrenadeState, MineState, Vec2
from shared.systems.base import WorldSystem
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState
from shared.systems.events.game_events import EmitSoundEvent, DamagePlayerEvent, DamageZombieEvent, DamageSoldierEvent


class ExplosiveSystem(WorldSystem):
    def update(self, state: WorldState, ctx: WorldContext, dt: float) -> None:
        self._update_grenades(state, ctx, dt)
        self._update_mines(state, ctx, dt)

    def _update_grenades(self, state: WorldState, ctx: WorldContext, dt: float) -> None:
        detonated: list[str] = []

        for grenade in list(state.grenades.values()):
            spec = GRENADE_SPECS.get(grenade.kind, DEFAULT_GRENADE)

            grenade.timer -= dt
            grenade.velocity = grenade.velocity.scaled(0.92)
            grenade.pos.add(grenade.velocity.scaled(dt))

            hit_wall = ctx.geometry.blocked_at(grenade.pos, grenade.radius, grenade.floor)

            if hit_wall:
                grenade.velocity = grenade.velocity.scaled(-0.22)
                grenade.pos.add(grenade.velocity.scaled(dt))

            if grenade.timer <= 0.0 or (
                spec.contact and (hit_wall or self._grenade_touched_actor(state, grenade))
            ):
                detonated.append(grenade.id)

        for grenade_id in detonated:
            grenade = state.grenades.pop(grenade_id, None)

            if grenade:
                self._detonate_grenade(state, ctx, grenade)

    def _update_mines(self, state: WorldState, ctx: WorldContext, dt: float) -> None:
        detonated: list[str] = []

        for mine in list(state.mines.values()):
            mine.rotation = (mine.rotation + dt * (1.6 if mine.armed else 0.55)) % math.tau

            if not mine.armed:
                owner = state.players.get(mine.owner_id)

                if (
                    not owner
                    or not owner.alive
                    or owner.floor != mine.floor
                    or owner.pos.distance_to(mine.pos) > mine.trigger_radius + PLAYER_RADIUS
                ):
                    mine.armed = True

                continue

            if self._mine_has_trigger(state, ctx, mine):
                detonated.append(mine.id)

        for mine_id in detonated:
            mine = state.mines.pop(mine_id, None)

            if mine:
                self._detonate_mine(state, ctx, mine)

    def _grenade_touched_actor(self, state: WorldState, grenade: GrenadeState) -> bool:
        for zombie in state.zombies.values():
            if zombie.floor != grenade.floor:
                continue

            spec = ZOMBIES[zombie.kind]

            if grenade.pos.distance_to(zombie.pos) <= spec.radius + grenade.radius:
                return True

        for player in state.players.values():
            if (
                player.alive
                and player.floor == grenade.floor
                and player.pos.distance_to(grenade.pos) <= PLAYER_RADIUS + grenade.radius
            ):
                return True

        return False

    def _mine_has_trigger(self, state: WorldState, ctx: WorldContext, mine: MineState) -> bool:
        for zombie in state.zombies.values():
            if zombie.floor != mine.floor:
                continue

            if (
                zombie.pos.distance_to(mine.pos) <= mine.trigger_radius + ZOMBIES[zombie.kind].radius * 0.35
                and not ctx.geometry.line_blocked(mine.pos, zombie.pos, mine.floor)
            ):
                return True

        for player in state.players.values():
            if not player.alive or player.floor != mine.floor:
                continue

            if (
                player.pos.distance_to(mine.pos) <= mine.trigger_radius + PLAYER_RADIUS * 0.25
                and not ctx.geometry.line_blocked(mine.pos, player.pos, mine.floor)
            ):
                return True

        return False

    def _detonate_grenade(self, state: WorldState, ctx: WorldContext, grenade: GrenadeState) -> None:
        spec = GRENADE_SPECS.get(grenade.kind, DEFAULT_GRENADE)

        ctx.events.emit(
            EmitSoundEvent(
                pos=grenade.pos.copy(),
                floor=grenade.floor,
                radius=1800.0,
                source_player_id=grenade.owner_id,
                kind="explosion",
                intensity=1.4,
            )
        )

        self._explode_at(
            state,
            ctx,
            grenade.pos,
            grenade.floor,
            grenade.owner_id,
            spec.blast_radius,
            spec.zombie_damage,
            spec.zombie_damage_bonus,
            spec.player_damage,
            spec.player_damage_bonus,
            spec.soldier_damage,
            spec.soldier_damage_bonus,
        )

    def _detonate_mine(self, state: WorldState, ctx: WorldContext, mine: MineState) -> None:
        spec = MINE_SPECS.get(mine.kind, DEFAULT_MINE)

        ctx.events.emit(
            EmitSoundEvent(
                pos=mine.pos.copy(),
                floor=mine.floor,
                radius=1500.0,
                source_player_id=mine.owner_id,
                kind="explosion",
                intensity=1.25,
            )
        )

        self._explode_at(
            state,
            ctx,
            mine.pos,
            mine.floor,
            mine.owner_id,
            spec.blast_radius,
            spec.zombie_damage,
            spec.zombie_damage_bonus,
            spec.player_damage,
            spec.player_damage_bonus,
            spec.soldier_damage,
            spec.soldier_damage_bonus,
        )

    def _explode_at(
        self,
        state: WorldState,
        ctx: WorldContext,
        pos: Vec2,
        floor: int,
        owner_id: str,
        blast_radius: float,
        zombie_damage: int,
        zombie_damage_bonus: int,
        player_damage: int,
        player_damage_bonus: int,
        soldier_damage: int,
        soldier_damage_bonus: int,
    ) -> None:
        for zombie in ctx.spatial.nearby_zombies(pos, blast_radius, floor):
            if zombie.floor != floor:
                continue

            distance = zombie.pos.distance_to(pos)

            if distance <= blast_radius and not ctx.geometry.line_blocked(pos, zombie.pos, floor):
                damage = int(zombie_damage * (1.0 - distance / blast_radius)) + zombie_damage_bonus

                ctx.events.emit(
                    DamageZombieEvent(
                        zombie_id=zombie.id,
                        damage=damage,
                        attacker_id=owner_id,
                        source_pos=pos.copy(),
                        reveal_owner=False,
                    )
                )

        for soldier in ctx.spatial.nearby_soldiers(pos, blast_radius, floor):
            if soldier.floor != floor or not soldier.alive:
                continue

            distance = soldier.pos.distance_to(pos)

            if distance <= blast_radius and not ctx.geometry.line_blocked(pos, soldier.pos, floor):
                # just a test of new damage for soldier based on factor
                factor = 1.0 - min(1.0, distance / max(1.0, blast_radius))
                damage = max(1, int(soldier_damage * factor))
                #damage = int(soldier_damage * (1.0 - distance / blast_radius)) + soldier_damage_bonus
                ctx.events.emit(
                    DamageSoldierEvent(
                        soldier_id=soldier.id,
                        damage=damage,
                        attacker_id=owner_id,
                        #source_pos=pos.copy(),
                        #reveal_owner=False,
                    )
                )

        for player in ctx.spatial.nearby_players(pos, blast_radius, floor):
            if player.floor != floor or not player.alive:
                continue

            player_radius = blast_radius * 0.65
            distance = player.pos.distance_to(pos)

            if distance <= player_radius and not ctx.geometry.line_blocked(pos, player.pos, floor):
                damage = int(player_damage * (1.0 - distance / player_radius)) + player_damage_bonus
                ctx.events.emit(
                    DamagePlayerEvent(
                        player_id=player.id,
                        damage=damage,
                    )
                )