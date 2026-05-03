from __future__ import annotations

import math
import random

from shared.constants import MAP_HEIGHT, MAP_WIDTH, PLAYER_RADIUS, SHOT_NOISE, UNARMED_MELEE_NOISE, WEAPONS, ZOMBIES
from shared.explosives import GRENADE_SPECS, MINE_SPECS, DEFAULT_GRENADE, DEFAULT_MINE
from shared.models import GrenadeState, MineState, PlayerState, ProjectileState, Vec2
from shared.world.world_state import WorldState
from shared.items import ITEMS


class PlayerCombatService:
    def __init__(self, *, state: WorldState, rng: random.Random) -> None:
        self._state = state
        self._rng = rng

    def shoot(self, player: PlayerState, ctx) -> None:
        quick_item = player.quick_items.get(player.active_slot)

        if quick_item:
            spec = ITEMS.get(quick_item.key)

            if spec and spec.kind == "grenade":
                self.throw_grenade_from_quick(player, ctx, player.active_slot)
                return

            if spec and spec.kind == "mine":
                self.place_mine_from_quick(player, ctx, player.active_slot)
                return

        weapon = player.active_weapon()

        if not weapon:
            return

        if weapon.reload_left > 0.0 or weapon.cooldown > 0.0 or weapon.ammo_in_mag <= 0:
            return

        spec = WEAPONS[weapon.key]
        angle = player.angle + self._rng.uniform(
            -ctx.weapons.spread(weapon),
            ctx.weapons.spread(weapon),
        )

        direction = Vec2(math.cos(angle), math.sin(angle))
        projectile_id = ctx.ids.next("shot")

        self._state.projectiles[projectile_id] = ProjectileState(
            id=projectile_id,
            owner_id=player.id,
            pos=Vec2(
                player.pos.x + direction.x * (PLAYER_RADIUS + 8),
                player.pos.y + direction.y * (PLAYER_RADIUS + 8),
            ),
            velocity=direction.scaled(spec.projectile_speed),
            damage=spec.damage,
            life=ctx.weapons.projectile_life(spec.projectile_speed),
            radius=spec.projectile_radius,
            floor=player.floor,
            weapon_key=weapon.key,
        )

        weapon.ammo_in_mag -= 1
        weapon.cooldown = 1.0 / ctx.weapons.fire_rate(weapon)

        ctx.sounds.emit(
            pos=player.pos,
            floor=player.floor,
            radius=SHOT_NOISE,
            source_player_id=player.id,
            kind="shot",
            intensity=1.0,
        )

    def unarmed_attack(self, player: PlayerState, ctx) -> None:
        if player.melee_cooldown > 0.0:
            return

        player.melee_cooldown = 0.55

        ctx.sounds.emit(
            pos=player.pos,
            floor=player.floor,
            radius=UNARMED_MELEE_NOISE,
            source_player_id=player.id,
            kind="melee",
            intensity=0.45,
        )

        reach = PLAYER_RADIUS + 34

        for zombie in list(self._state.zombies.values()):
            if zombie.floor != player.floor:
                continue

            spec = ZOMBIES[zombie.kind]

            if player.pos.distance_to(zombie.pos) <= reach + spec.radius:
                ctx.damage.damage_zombie(
                    zombie,
                    12,
                    player.id,
                    source_pos=player.pos,
                )
                return

    def throw_grenade_from_quick(
        self,
        player: PlayerState,
        ctx,
        slot: str,
    ) -> None:
        if self._state.grenade_cooldowns.get(player.id, 0.0) > 0.0:
            return

        item = player.quick_items.get(slot)
        spec = ITEMS.get(item.key) if item else None

        if not item or not spec or spec.kind != "grenade":
            return

        grenade_key = item.key

        item.amount -= 1

        if item.amount <= 0:
            player.quick_items[slot] = None

        self.spawn_grenade(player, ctx, grenade_key)
        self._state.grenade_cooldowns[player.id] = 0.6

    def place_mine_from_quick(
        self,
        player: PlayerState,
        ctx,
        slot: str,
    ) -> None:
        if self._state.grenade_cooldowns.get(player.id, 0.0) > 0.0:
            return

        item = player.quick_items.get(slot)
        spec = ITEMS.get(item.key) if item else None

        if not item or not spec or spec.kind != "mine":
            return

        mine_spec = MINE_SPECS.get(item.key, DEFAULT_MINE)

        place_pos = Vec2(
            player.pos.x + math.cos(player.angle) * (PLAYER_RADIUS + 20),
            player.pos.y + math.sin(player.angle) * (PLAYER_RADIUS + 20),
        )
        place_pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)

        if ctx.geometry.blocked_at(place_pos, 12, player.floor):
            place_pos = player.pos.copy()

        mine_id = ctx.ids.next("m")

        self._state.mines[mine_id] = MineState(
            id=mine_id,
            owner_id=player.id,
            kind=item.key,
            pos=place_pos,
            floor=player.floor,
            armed=False,
            trigger_radius=mine_spec.trigger_radius,
            blast_radius=mine_spec.blast_radius,
        )

        item.amount -= 1

        if item.amount <= 0:
            player.quick_items[slot] = None

        self._state.grenade_cooldowns[player.id] = 0.6

    def spawn_grenade(
        self,
        player: PlayerState,
        ctx,
        grenade_key: str = "grenade",
    ) -> None:
        grenade_spec = GRENADE_SPECS.get(grenade_key, DEFAULT_GRENADE)

        self._state.grenade_cooldowns[player.id] = 0.6

        distance = grenade_spec.throw_distance
        velocity = Vec2(
            math.cos(player.angle) * distance,
            math.sin(player.angle) * distance,
        )

        start = Vec2(
            player.pos.x + math.cos(player.angle) * (PLAYER_RADIUS + 12),
            player.pos.y + math.sin(player.angle) * (PLAYER_RADIUS + 12),
        )

        grenade_id = ctx.ids.next("g")

        self._state.grenades[grenade_id] = GrenadeState(
            grenade_id,
            player.id,
            start,
            velocity,
            timer=grenade_spec.timer,
            floor=player.floor,
            kind=grenade_key,
        )

    def throw_grenade(self, player: PlayerState, ctx) -> None:
        # grenade_kind = "grenade"
        #
        # if player.grenades <= 0:
        #     return
        #
        # if self._state.grenade_cooldowns.get(player.id, 0.0) > 0.0:
        #     return
        #
        # player.grenades -= 1
        # self._state.grenade_cooldowns[player.id] = 0.8
        #
        # spec = GRENADE_SPECS.get(grenade_kind, DEFAULT_GRENADE)
        # direction = Vec2(math.cos(player.angle), math.sin(player.angle))
        #
        # grenade_id = ctx.ids.next("g")
        #
        # self._state.grenades[grenade_id] = GrenadeState(
        #     grenade_id,
        #     player.id,
        #     grenade_kind,
        #     Vec2(
        #         player.pos.x + direction.x * (PLAYER_RADIUS + 12),
        #         player.pos.y + direction.y * (PLAYER_RADIUS + 12),
        #     ),
        #     direction.scaled(spec.throw_speed),
        #     floor=player.floor,
        # )
        self.throw_grenade_from_quick(player, ctx, player.active_slot)

    def place_mine(self, player: PlayerState, ctx, mine_kind: str = "mine") -> None:
        # if player.mines <= 0:
        #     return
        #
        # player.mines -= 1
        #
        # spec = MINE_SPECS.get(mine_kind, DEFAULT_MINE)
        # direction = Vec2(math.cos(player.angle), math.sin(player.angle))
        # mine_pos = Vec2(
        #     player.pos.x + direction.x * (PLAYER_RADIUS + 26),
        #     player.pos.y + direction.y * (PLAYER_RADIUS + 26),
        # )
        #
        # mine_id = ctx.ids.next("m")
        #
        # self._state.mines[mine_id] = MineState(
        #     mine_id,
        #     player.id,
        #     mine_kind,
        #     mine_pos,
        #     floor=player.floor,
        #     trigger_radius=spec.trigger_radius,
        # )
        self.place_mine_from_quick(player, ctx, player.active_slot)