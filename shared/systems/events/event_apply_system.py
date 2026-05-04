from shared.systems.base import WorldSystem
from shared.systems.events.game_events import *
from shared.models import ProjectileState, PoisonProjectileState, GrenadeState, MineState


class EventApplySystem(WorldSystem):
    def update(self, state, ctx, dt: float) -> None:
        for event in ctx.events.drain():

            if isinstance(event, SpawnProjectileEvent):
                pid = ctx.ids.next("shot")

                state.projectiles[pid] = ProjectileState(
                    id=pid,
                    owner_id=event.owner_id,
                    pos=event.pos,
                    velocity=event.velocity,
                    damage=event.damage,
                    life=event.life,
                    radius=event.radius,
                    floor=event.floor,
                    weapon_key=event.weapon_key,
                )

            elif isinstance(event, SpawnPoisonEvent):
                pid = ctx.ids.next("spit")

                state.poison_projectiles[pid] = PoisonProjectileState(
                    pid,
                    event.owner_id,
                    event.pos,
                    event.velocity,
                    event.target,
                    floor=event.floor,
                )

            elif isinstance(event, SpawnLootEvent):
                lid = ctx.ids.next("l")

                ctx.loot.spawn_loot(
                    loot_id=lid,
                    pos=event.pos,
                    kind=event.kind,
                    payload=event.payload,
                    amount=event.amount,
                    floor=event.floor,
                    rarity=event.rarity,
                )

            elif isinstance(event, SpawnGrenadeEvent):
                grenade_id = ctx.ids.next("g")

                state.grenades[grenade_id] = GrenadeState(
                    grenade_id,
                    event.owner_id,
                    event.pos,
                    event.velocity,
                    timer=event.timer,
                    floor=event.floor,
                    kind=event.kind,
                )

            elif isinstance(event, SpawnMineEvent):
                mine_id = ctx.ids.next("m")

                state.mines[mine_id] = MineState(
                    id=mine_id,
                    owner_id=event.owner_id,
                    kind=event.kind,
                    pos=event.pos,
                    floor=event.floor,
                    armed=event.armed,
                    trigger_radius=event.trigger_radius,
                    blast_radius=event.blast_radius,
                )

            elif isinstance(event, EmitSoundEvent):
                ctx.sounds.emit(
                    pos=event.pos,
                    floor=event.floor,
                    radius=event.radius,
                    source_player_id=event.source_player_id,
                    kind=event.kind,
                    intensity=event.intensity,
                )

            elif isinstance(event, DamagePlayerEvent):
                player = state.players.get(event.player_id)

                if player and player.alive:
                    ctx.damage.damage_player(player, event.damage)

            elif isinstance(event, DamageZombieEvent):
                zombie = state.zombies.get(event.zombie_id)

                if zombie:
                    ctx.damage.damage_zombie(
                        zombie,
                        event.damage,
                        event.attacker_id,
                        source_pos=event.source_pos,
                        reveal_owner=event.reveal_owner,
                    )

            elif isinstance(event, DamageSoldierEvent):
                soldier = state.soldiers.get(event.soldier_id)

                if soldier and soldier.alive:
                    ctx.damage.damage_soldier(
                        soldier,
                        event.damage,
                        event.attacker_id,
                    )

            elif isinstance(event, ApplyPoisonEvent):
                player = state.players.get(event.player_id)

                if player and player.alive:
                    if player.poison_left <= 0.0:
                        player.poison_tick = 1.0

                    player.poison_left = max(player.poison_left, event.duration)

                    if player.poison_tick <= 0.0:
                        player.poison_tick = 1.0

                    player.poison_damage = max(player.poison_damage, event.damage_per_tick)

            elif isinstance(event, PoisonTickDamageEvent):
                player = state.players.get(event.player_id)

                if player and player.alive:
                    player.healing_left = 0.0
                    player.healing_pool = 0.0
                    player.healing_rate = 0.0

                    ctx.damage.damage_player(player, event.damage)
                    # Важно: PoisonTickDamageEvent создаёт обычный DamagePlayerEvent,
                    # но так как ctx.events.drain() уже забрал текущий список событий,
                    # этот damage применится на следующем tick. Если хочешь применить сразу - вместо emit
                    # можно напрямую вызвать ctx.damage.damage_player(player, event.damage)

                    # ctx.events.emit(
                    #     DamagePlayerEvent(
                    #         player_id=player.id,
                    #         damage=event.damage,
                    #     )
                    # )
