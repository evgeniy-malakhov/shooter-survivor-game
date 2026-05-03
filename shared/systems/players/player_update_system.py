from __future__ import annotations

from typing import Callable

from shared.constants import (
    ARMORS,
    MAP_HEIGHT,
    MAP_WIDTH,
    PLAYER_RADIUS,
    SLOTS,
    SPRINT_MULTIPLIER,
)
from shared.models import Vec2
from shared.systems.base import WorldSystem
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class PlayerUpdateSystem(WorldSystem):
    def __init__(
        self,
        *,
        update_notice: Callable,
        update_healing: Callable,
        player_noise: Callable,
        interact: Callable,
        respawn_player: Callable,
    ) -> None:
        self._update_notice = update_notice
        self._update_healing = update_healing
        self._player_noise = player_noise

        self._interact = interact
        self._respawn_player = respawn_player

    def update(self, state: WorldState, ctx: WorldContext, dt: float) -> None:
        for player in state.players.values():
            command = state.inputs.get(player.id)

            if not command:
                continue

            state.grenade_cooldowns[player.id] = max(
                0.0,
                state.grenade_cooldowns.get(player.id, 0.0) - dt,
            )

            self._update_notice(player, dt)

            if not player.alive:
                if command.respawn:
                    self._respawn_player(player.id)
                continue

            self._apply_discrete_input(player, command, ctx)
            self._update_healing(player, dt)

            player.melee_cooldown = max(0.0, player.melee_cooldown - dt)

            aim = Vec2(command.aim_x, command.aim_y)
            player.angle = player.pos.angle_to(aim)

            movement = Vec2(command.move_x, command.move_y).normalized()

            player.sneaking = command.sneak and movement.length() > 0
            player.sprinting = command.sprint and not player.sneaking and movement.length() > 0

            speed = player.speed * (
                0.48
                if player.sneaking
                else SPRINT_MULTIPLIER
                if player.sprinting
                else 1.0
            )

            weapon = player.active_weapon()
            meleeing = command.alt_attack and weapon is None

            player.noise = self._player_noise(
                player,
                movement,
                command.shooting,
                meleeing,
            )

            ctx.movement.move_circle(
                player.pos,
                movement.scaled(speed * dt),
                PLAYER_RADIUS,
                player.floor,
            )

            player.pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
            player.inside_building = ctx.buildings.point_building(player.pos)

            if player.noise > 0.0 and not player.inside_building:
                ctx.sounds.emit(
                    pos=player.pos,
                    floor=player.floor,
                    radius=player.noise,
                    source_player_id=player.id,
                    kind="movement",
                    intensity=0.45 if player.sprinting else 0.25,
                )

            ctx.weapons.update_player_weapons(player, dt)

            interacted = False

            if command.pickup:
                ctx.inventory.pickup_nearby(player)

            if command.interact:
                interacted = self._interact(player)

            if command.toggle_utility and not interacted:
                ctx.weapons.toggle_utility(player)

            if command.reload:
                ctx.weapons.start_reload(player)

            if command.shooting:
                ctx.player_combat.shoot(player, ctx)

            if command.alt_attack:
                ctx.player_combat.unarmed_attack(player, ctx)

            if command.throw_grenade:
                ctx.player_combat.throw_grenade(player, ctx)

    def _apply_discrete_input(self, player, command, ctx: WorldContext) -> None:
        if command.active_slot and command.active_slot in SLOTS:
            player.active_slot = command.active_slot

        if command.equip_armor and command.equip_armor in ARMORS:
            ctx.inventory.equip_armor(player, command.equip_armor)

        if command.use_medkit and player.medkits > 0 and player.health < 100:
            player.medkits -= 1
            player.health = min(100, player.health + 42)

        if command.inventory_action:
            ctx.inventory.apply_inventory_action(player, command.inventory_action)

        if command.craft_key:
            ctx.inventory.craft(player, command.craft_key)

        if command.repair_slot:
            ctx.inventory.repair_armor(player, command.repair_slot)