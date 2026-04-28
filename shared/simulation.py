from __future__ import annotations

import math
import os
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace

from shared.constants import (
    ARMORS,
    INITIAL_ZOMBIES,
    INTERACT_RADIUS,
    MAP_HEIGHT,
    MAP_WIDTH,
    MAX_ZOMBIES,
    PICKUP_RADIUS,
    PLAYER_RADIUS,
    SEARCH_DURATION,
    SHOT_NOISE,
    SNEAK_NOISE,
    SPRINT_MULTIPLIER,
    SPRINT_NOISE,
    WALK_NOISE,
    WEAPONS,
    SLOTS,
    ZOMBIE_TARGET_RADIUS,
    ZOMBIES,
)
from shared.backpack_config import BackpackConfig, load_backpack_config
from shared.crafting import roll_crafted_rarity
from shared.difficulty import DifficultyConfig, load_difficulty
from shared.explosives import GRENADE_SPECS, MINE_SPECS, DEFAULT_GRENADE, DEFAULT_MINE
from shared.items import ITEMS, LEGACY_LOOT_TO_ITEM, RECIPES, WORLD_LOOT, HOUSE_LOOT
from shared.level import all_closed_walls, make_buildings, nearest_door, nearest_prop, nearest_stairs, point_building
from shared.rarities import RARITIES, rarity_rank, rarity_spec
from shared.weapon_modules import WEAPON_MODULES
from shared.models import (
    BuildingState,
    GrenadeState,
    InputCommand,
    InventoryItem,
    LootState,
    MineState,
    PlayerState,
    PoisonPoolState,
    PoisonProjectileState,
    ProjectileState,
    RectState,
    Vec2,
    WeaponRuntime,
    WorldSnapshot,
    ZombieState,
)


@dataclass(slots=True)
class _PoisonSpitEvent:
    owner_id: str
    pos: Vec2
    velocity: Vec2
    target: Vec2
    floor: int


@dataclass(slots=True)
class _ZombieUpdateResult:
    zombie: ZombieState
    player_hits: list[tuple[str, int]]
    poison_spits: list[_PoisonSpitEvent]


class GameWorld:
    def __init__(
        self,
        seed: int | None = None,
        initial_zombies: int | None = None,
        max_zombies: int | None = None,
        difficulty_key: str = "medium",
        zombie_workers: int | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._geometry_cache_lock = threading.Lock()
        self.rng = random.Random(seed)
        self.time = 0.0
        self.difficulty: DifficultyConfig = load_difficulty(difficulty_key)
        self.backpack_config: BackpackConfig = load_backpack_config()
        self.initial_zombies = self.difficulty.initial_zombies if initial_zombies is None else initial_zombies
        self.max_zombies = self.difficulty.max_zombies if max_zombies is None else max_zombies
        self.players: dict[str, PlayerState] = {}
        self.zombies: dict[str, ZombieState] = {}
        self.projectiles: dict[str, ProjectileState] = {}
        self.grenades: dict[str, GrenadeState] = {}
        self.mines: dict[str, MineState] = {}
        self.poison_projectiles: dict[str, PoisonProjectileState] = {}
        self.poison_pools: dict[str, PoisonPoolState] = {}
        self.loot: dict[str, LootState] = {}
        self.inputs: dict[str, InputCommand] = {}
        self._grenade_cooldowns: dict[str, float] = {}
        self.buildings: dict[str, BuildingState] = make_buildings()
        self._next_id = 1
        self._spawn_timer = 0.0
        self._loot_timer = 0.0
        self._geometry_version = 0
        self._closed_walls_cache: dict[int, tuple[int, tuple[RectState, ...]]] = {}
        self._zombie_rngs: dict[str, random.Random] = {}
        cpu_budget = max(1, (os.cpu_count() or 4) - 1)
        worker_count = zombie_workers if zombie_workers is not None else min(12, cpu_budget, self.max_zombies)
        self._zombie_executor = ThreadPoolExecutor(
            max_workers=max(1, worker_count),
            thread_name_prefix="zombie-ai",
        )
        self._prime_map()

    def close(self) -> None:
        self._zombie_executor.shutdown(wait=False, cancel_futures=True)

    def _id(self, prefix: str) -> str:
        value = f"{prefix}{self._next_id}"
        self._next_id += 1
        return value

    def _prime_map(self) -> None:
        for _ in range(self.initial_zombies):
            self.spawn_zombie()
        for weapon in ("smg", "shotgun", "rifle"):
            self.spawn_loot("weapon", weapon, 1)
        for armor in ("light", "tactical", "heavy"):
            self.spawn_loot("armor", armor, 1)
        for _ in range(self._loot_count(24, minimum=8)):
            self.spawn_loot("ammo", self.rng.choice(list(WEAPONS)), self.rng.randint(12, 34))
        for _ in range(self._loot_count(10, minimum=2)):
            self.spawn_loot("medkit", "medkit", 1)
        for building in self.buildings.values():
            for _ in range(self._loot_count(14, minimum=6)):
                pos = Vec2(
                    self.rng.uniform(building.bounds.x + 80, building.bounds.x + building.bounds.w - 80),
                    self.rng.uniform(building.bounds.y + 90, building.bounds.y + building.bounds.h - 90),
                )
                if not self._blocked_at(pos, 16):
                    item_key = self.rng.choices([item[0] for item in HOUSE_LOOT], weights=[item[2] for item in HOUSE_LOOT])[0]
                    floor = self.rng.choice([building.min_floor, 0, 0, 1, 2])
                    self._spawn_loot_at(pos, "item", item_key, self.rng.randint(1, 3), floor=floor)

    def add_player(self, name: str, player_id: str | None = None) -> PlayerState:
        with self._lock:
            return self._add_player_unlocked(name, player_id)

    def _add_player_unlocked(self, name: str, player_id: str | None = None) -> PlayerState:
        player_id = player_id or self._id("p")
        player = PlayerState(
            id=player_id,
            name=_clean_player_name(name),
            pos=self._random_open_pos(centered=True),
            kills_by_kind={kind: 0 for kind in ZOMBIES},
            backpack=[None] * self.backpack_config.slots,
        )
        weapon_key = self.backpack_config.starting_weapon.key
        if weapon_key not in WEAPONS:
            weapon_key = "pistol"
        weapon_spec = WEAPONS[weapon_key]
        player.weapons[weapon_spec.slot] = WeaponRuntime(
            weapon_key,
            weapon_spec.magazine_size,
            self.backpack_config.starting_weapon.reserve_ammo,
            rarity="common",
        )
        player.quick_items = {slot: None for slot in SLOTS}
        for item in self.backpack_config.starting_items:
            self._add_item(player, item.key, item.amount)
        self.players[player_id] = player
        self.inputs[player_id] = InputCommand(player_id=player_id, aim_x=player.pos.x + 1, aim_y=player.pos.y)
        self._grenade_cooldowns[player_id] = 0.0
        return player

    def remove_player(self, player_id: str) -> None:
        with self._lock:
            self.players.pop(player_id, None)
            self.inputs.pop(player_id, None)
            self._grenade_cooldowns.pop(player_id, None)

    def rename_player(self, player_id: str, name: str) -> None:
        with self._lock:
            player = self.players.get(player_id)
            if player:
                player.name = _clean_player_name(name)

    def set_input(self, command: InputCommand) -> None:
        with self._lock:
            if command.player_id in self.players:
                self.inputs[command.player_id] = command

    def update(self, dt: float) -> None:
        with self._lock:
            self._update_unlocked(dt)

    def _update_unlocked(self, dt: float) -> None:
        self.time += dt
        self._update_players(dt)
        if dt <= 0.0:
            return
        self._update_projectiles(dt)
        self._update_grenades(dt)
        self._update_mines(dt)
        self._update_poison_projectiles(dt)
        self._update_poison_pools(dt)
        self._update_poisoned_players(dt)
        self._update_zombies(dt)
        self._spawn_timer -= dt
        self._loot_timer -= dt
        living_players = [player for player in self.players.values() if player.alive]
        if living_players and self._spawn_timer <= 0.0 and len(self.zombies) < self.max_zombies:
            self.spawn_zombie()
            self._spawn_timer = max(0.8, max(1.2, 4.2 - self.time * 0.003) * self.difficulty.zombie_spawn_interval_multiplier)
        if self._loot_timer <= 0.0 and len(self.loot) < self.difficulty.world_loot_cap:
            self._spawn_random_loot()
            self._loot_timer = self.rng.uniform(2.5, 5.4) * self.difficulty.loot_spawn_interval_multiplier

    def respawn_player(self, player_id: str) -> None:
        player = self.players.get(player_id)
        if not player:
            return
        pos, floor, building_id = self._safe_respawn()
        player.pos = pos
        player.health = 100
        player.armor = max(0, player.armor // 2)
        player.alive = True
        player.floor = floor
        player.inside_building = building_id
        player.noise = 0.0
        player.sprinting = False
        player.sneaking = False

    def _update_players(self, dt: float) -> None:
        for player in self.players.values():
            command = self.inputs.get(player.id)
            if not command:
                continue
            self._grenade_cooldowns[player.id] = max(0.0, self._grenade_cooldowns.get(player.id, 0.0) - dt)
            self._update_notice(player, dt)
            if not player.alive:
                if command.respawn:
                    self.respawn_player(player.id)
                continue

            if command.active_slot and command.active_slot in SLOTS:
                player.active_slot = command.active_slot
            if command.equip_armor and command.equip_armor in ARMORS:
                self._equip_armor(player, command.equip_armor)
            if command.use_medkit and player.medkits > 0 and player.health < 100:
                player.medkits -= 1
                player.health = min(100, player.health + 42)
            if command.inventory_action:
                self._apply_inventory_action(player, command.inventory_action)
            if command.craft_key:
                self._craft(player, command.craft_key)
            if command.repair_slot:
                self._repair_armor(player, command.repair_slot)
            self._update_healing(player, dt)

            player.angle = player.pos.angle_to(Vec2(command.aim_x, command.aim_y))
            movement = Vec2(command.move_x, command.move_y).normalized()
            player.sneaking = command.sneak and movement.length() > 0
            player.sprinting = command.sprint and not player.sneaking and movement.length() > 0
            speed = player.speed * (0.48 if player.sneaking else SPRINT_MULTIPLIER if player.sprinting else 1.0)
            player.noise = self._player_noise(player, movement, command.shooting)
            self._move_circle(player.pos, movement.scaled(speed * dt), PLAYER_RADIUS, player.floor)
            player.pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
            player.inside_building = point_building(self.buildings, player.pos)

            for weapon in player.weapons.values():
                weapon.cooldown = max(0.0, weapon.cooldown - dt)
                if weapon.reload_left > 0.0:
                    weapon.reload_left = max(0.0, weapon.reload_left - dt)
                    if weapon.reload_left == 0.0:
                        self._finish_reload(weapon)

            if command.pickup:
                self._pickup_nearby(player)
            interacted = False
            if command.interact:
                interacted = self._interact(player)
            if command.toggle_utility and not interacted:
                self._toggle_weapon_utility(player)
            if command.reload:
                self._start_reload(player)
            if command.shooting:
                self._shoot(player)
            if command.throw_grenade:
                self._throw_grenade(player)

    def _player_noise(self, player: PlayerState, movement: Vec2, shooting: bool) -> float:
        if player.sneaking:
            return 0.0
        if shooting:
            return SHOT_NOISE
        if movement.length() <= 0:
            return 0.0
        return SPRINT_NOISE if player.sprinting else WALK_NOISE

    def _update_projectiles(self, dt: float) -> None:
        dead_projectiles: list[str] = []
        for projectile in self.projectiles.values():
            projectile.life -= dt
            projectile.pos.add(projectile.velocity.scaled(dt))
            if (
                projectile.life <= 0.0
                or projectile.pos.x < 0
                or projectile.pos.y < 0
                or projectile.pos.x > MAP_WIDTH
                or projectile.pos.y > MAP_HEIGHT
                or self._blocked_at(projectile.pos, projectile.radius, projectile.floor)
            ):
                dead_projectiles.append(projectile.id)
                continue

            for zombie in list(self.zombies.values()):
                if zombie.floor != projectile.floor:
                    continue
                spec = ZOMBIES[zombie.kind]
                if projectile.pos.distance_to(zombie.pos) <= spec.radius + projectile.radius:
                    self._damage_zombie(zombie, projectile.damage, projectile.owner_id)
                    dead_projectiles.append(projectile.id)
                    break

        for projectile_id in dead_projectiles:
            self.projectiles.pop(projectile_id, None)

    def _update_grenades(self, dt: float) -> None:
        detonated: list[str] = []
        for grenade in self.grenades.values():
            spec = GRENADE_SPECS.get(grenade.kind, DEFAULT_GRENADE)
            grenade.timer -= dt
            grenade.velocity = grenade.velocity.scaled(0.92)
            grenade.pos.add(grenade.velocity.scaled(dt))
            hit_wall = self._blocked_at(grenade.pos, grenade.radius, grenade.floor)
            if hit_wall:
                grenade.velocity = grenade.velocity.scaled(-0.22)
                grenade.pos.add(grenade.velocity.scaled(dt))
            if grenade.timer <= 0.0 or (spec.contact and (hit_wall or self._grenade_touched_actor(grenade))):
                detonated.append(grenade.id)
        for grenade_id in detonated:
            grenade = self.grenades.pop(grenade_id, None)
            if grenade:
                self._detonate_grenade(grenade)

    def _grenade_touched_actor(self, grenade: GrenadeState) -> bool:
        for zombie in self.zombies.values():
            if zombie.floor != grenade.floor:
                continue
            spec = ZOMBIES[zombie.kind]
            if grenade.pos.distance_to(zombie.pos) <= spec.radius + grenade.radius:
                return True
        for player in self.players.values():
            if player.alive and player.floor == grenade.floor and grenade.pos.distance_to(player.pos) <= PLAYER_RADIUS + grenade.radius:
                return True
        return False

    def _update_mines(self, dt: float) -> None:
        detonated: list[str] = []
        for mine in self.mines.values():
            mine.rotation = (mine.rotation + dt * (1.6 if mine.armed else 0.55)) % math.tau
            if not mine.armed:
                owner = self.players.get(mine.owner_id)
                if (
                    not owner
                    or not owner.alive
                    or owner.floor != mine.floor
                    or owner.pos.distance_to(mine.pos) > mine.trigger_radius + PLAYER_RADIUS
                ):
                    mine.armed = True
                continue
            if self._mine_has_trigger(mine):
                detonated.append(mine.id)
        for mine_id in detonated:
            mine = self.mines.pop(mine_id, None)
            if mine:
                self._detonate_mine(mine)

    def _mine_has_trigger(self, mine: MineState) -> bool:
        for zombie in self.zombies.values():
            if zombie.floor != mine.floor:
                continue
            if (
                zombie.pos.distance_to(mine.pos) <= mine.trigger_radius + ZOMBIES[zombie.kind].radius * 0.35
                and not self._line_blocked(mine.pos, zombie.pos, mine.floor)
            ):
                return True
        for player in self.players.values():
            if not player.alive or player.floor != mine.floor:
                continue
            if (
                player.pos.distance_to(mine.pos) <= mine.trigger_radius + PLAYER_RADIUS * 0.25
                and not self._line_blocked(mine.pos, player.pos, mine.floor)
            ):
                return True
        return False

    def _update_poison_projectiles(self, dt: float) -> None:
        expired: list[str] = []
        for spit in self.poison_projectiles.values():
            spit.life -= dt
            old_pos = spit.pos.copy()
            spit.pos.add(spit.velocity.scaled(dt))
            hit_wall = self._blocked_at(spit.pos, spit.radius, spit.floor)
            reached_target = old_pos.distance_to(spit.target) <= spit.pos.distance_to(spit.target) or spit.pos.distance_to(spit.target) <= 18
            hit_player = None
            for player in self.players.values():
                if player.alive and player.floor == spit.floor and player.pos.distance_to(spit.pos) <= PLAYER_RADIUS + spit.radius:
                    hit_player = player
                    break
            if hit_player:
                self._apply_poison(hit_player, damage_per_tick=3)
                expired.append(spit.id)
            elif hit_wall or reached_target or spit.life <= 0.0:
                self._spawn_poison_pool(spit.pos if not reached_target else spit.target, spit.floor)
                expired.append(spit.id)
        for spit_id in expired:
            self.poison_projectiles.pop(spit_id, None)

    def _update_poison_pools(self, dt: float) -> None:
        expired: list[str] = []
        for pool in self.poison_pools.values():
            pool.timer -= dt
            if pool.timer <= 0.0:
                expired.append(pool.id)
                continue
            for player in self.players.values():
                if player.alive and player.floor == pool.floor and player.pos.distance_to(pool.pos) <= pool.radius + PLAYER_RADIUS * 0.35:
                    self._apply_poison(player, damage_per_tick=2)
        for pool_id in expired:
            self.poison_pools.pop(pool_id, None)

    def _update_poisoned_players(self, dt: float) -> None:
        for player in self.players.values():
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

    def _spawn_poison_pool(self, pos: Vec2, floor: int) -> None:
        pool_id = self._id("acid")
        pool_pos = pos.copy()
        pool_pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
        self.poison_pools[pool_id] = PoisonPoolState(pool_id, pool_pos, floor=floor, timer=5.0)

    def _apply_poison(self, player: PlayerState, damage_per_tick: int) -> None:
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

    def _update_zombies(self, dt: float) -> None:
        living_players = tuple(player for player in self.players.values() if player.alive)
        zombies = list(self.zombies.values())
        active_ids = {zombie.id for zombie in zombies}
        for zombie_id in list(self._zombie_rngs):
            if zombie_id not in active_ids:
                self._zombie_rngs.pop(zombie_id, None)

        if len(zombies) < 2:
            for zombie in zombies:
                result = self._update_zombie_actor(zombie, dt, living_players, self._zombie_rng(zombie.id), clone=False)
                self._apply_zombie_result(result)
            return

        futures = [
            self._zombie_executor.submit(
                self._update_zombie_actor,
                self._clone_zombie(zombie),
                dt,
                living_players,
                self._zombie_rng(zombie.id),
                False,
            )
            for zombie in zombies
        ]
        for future in futures:
            result = future.result()
            if result.zombie.id in self.zombies:
                self.zombies[result.zombie.id] = result.zombie
                self._apply_zombie_result(result)

    def _zombie_rng(self, zombie_id: str) -> random.Random:
        rng = self._zombie_rngs.get(zombie_id)
        if rng is None:
            rng = random.Random(self.rng.randrange(1, 2**63))
            self._zombie_rngs[zombie_id] = rng
        return rng

    def _clone_zombie(self, zombie: ZombieState) -> ZombieState:
        return replace(
            zombie,
            pos=zombie.pos.copy(),
            last_known_pos=zombie.last_known_pos.copy() if zombie.last_known_pos else None,
            waypoint=zombie.waypoint.copy() if zombie.waypoint else None,
        )

    def _update_zombie_actor(
        self,
        zombie: ZombieState,
        dt: float,
        living_players: tuple[PlayerState, ...],
        rng: random.Random,
        clone: bool = True,
    ) -> _ZombieUpdateResult:
        actor = self._clone_zombie(zombie) if clone else zombie
        player_hits: list[tuple[str, int]] = []
        poison_spits: list[_PoisonSpitEvent] = []
        spec = ZOMBIES[actor.kind]
        actor.attack_cooldown = max(0.0, actor.attack_cooldown - dt)
        actor.special_cooldown = max(0.0, actor.special_cooldown - dt)
        actor.sidestep_timer = max(0.0, actor.sidestep_timer - dt)
        visible_player = self._visible_player(actor, living_players)
        if visible_player:
            actor.mode = "chase"
            actor.target_player_id = visible_player.id
            actor.last_known_pos = visible_player.pos.copy()
            actor.search_timer = SEARCH_DURATION
            actor.alertness = 1.0
        elif actor.mode != "chase":
            heard_player = self._heard_player(actor, living_players)
            if heard_player:
                actor.mode = "investigate"
                actor.target_player_id = heard_player.id
                actor.last_known_pos = heard_player.pos.copy()
                actor.search_timer = max(actor.search_timer, 2.2)
                actor.alertness = min(1.0, actor.alertness + dt * spec.sensitivity)

        if actor.mode == "chase":
            self._update_chase(actor, dt, living_players, rng, player_hits, poison_spits)
        elif actor.mode == "investigate":
            self._update_investigate(actor, dt, living_players, rng)
        elif actor.mode == "search":
            self._update_search(actor, dt, rng)
        else:
            self._update_patrol(actor, dt, rng)

        actor.inside_building = point_building(self.buildings, actor.pos)
        return _ZombieUpdateResult(actor, player_hits, poison_spits)

    def _apply_zombie_result(self, result: _ZombieUpdateResult) -> None:
        for player_id, damage in result.player_hits:
            player = self.players.get(player_id)
            if player and player.alive:
                self._damage_player(player, damage)
        for spit in result.poison_spits:
            spit_id = self._id("spit")
            self.poison_projectiles[spit_id] = PoisonProjectileState(
                spit_id,
                spit.owner_id,
                spit.pos,
                spit.velocity,
                spit.target,
                floor=spit.floor,
            )

    def _find_player(self, players: tuple[PlayerState, ...], player_id: str | None) -> PlayerState | None:
        if not player_id:
            return None
        for player in players:
            if player.id == player_id:
                return player
        return None

    def _update_chase(
        self,
        zombie: ZombieState,
        dt: float,
        players: tuple[PlayerState, ...],
        rng: random.Random,
        player_hits: list[tuple[str, int]],
        poison_spits: list[_PoisonSpitEvent],
    ) -> None:
        target = self._find_player(players, zombie.target_player_id)
        if target and target.alive and self._can_see(zombie, target):
            zombie.last_known_pos = target.pos.copy()
            if zombie.kind == "leaper":
                self._try_poison_spit(zombie, target, rng, poison_spits)
                self._leaper_move_toward(zombie, target.pos, dt, rng)
            else:
                self._zombie_move_toward(zombie, target.pos, dt, sprint=True, rng=rng)
            self._try_zombie_attack(zombie, target, player_hits)
            return
        if target and target.inside_building:
            entry = self._building_entry_target(target.inside_building)
            if entry and target.floor == zombie.floor:
                zombie.last_known_pos = entry
            elif target.floor != zombie.floor:
                zombie.mode = "search"
                zombie.search_timer = SEARCH_DURATION
        if zombie.last_known_pos:
            if zombie.pos.distance_to(zombie.last_known_pos) > 28:
                self._zombie_move_toward(zombie, zombie.last_known_pos, dt, sprint=True, rng=rng)
            else:
                zombie.mode = "search"
                zombie.search_timer = SEARCH_DURATION
        else:
            zombie.mode = "patrol"

    def _update_investigate(
        self,
        zombie: ZombieState,
        dt: float,
        players: tuple[PlayerState, ...],
        rng: random.Random,
    ) -> None:
        if not zombie.last_known_pos:
            zombie.mode = "patrol"
            return
        target = self._find_player(players, zombie.target_player_id)
        if target and target.inside_building:
            entry = self._building_entry_target(target.inside_building)
            if entry:
                zombie.last_known_pos = entry
        if zombie.pos.distance_to(zombie.last_known_pos) > 34:
            self._zombie_move_toward(zombie, zombie.last_known_pos, dt, sprint=False, rng=rng)
        else:
            zombie.mode = "search"
            zombie.search_timer = SEARCH_DURATION

    def _update_search(self, zombie: ZombieState, dt: float, rng: random.Random) -> None:
        zombie.search_timer -= dt
        if zombie.search_timer <= 0.0:
            zombie.mode = "patrol"
            zombie.target_player_id = None
            zombie.last_known_pos = None
            zombie.waypoint = None
            zombie.alertness = 0.0
            return
        if not zombie.waypoint or zombie.pos.distance_to(zombie.waypoint) < 26:
            base = zombie.last_known_pos or zombie.pos
            angle = rng.uniform(0, math.tau)
            distance = rng.uniform(80, 220)
            zombie.waypoint = Vec2(base.x + math.cos(angle) * distance, base.y + math.sin(angle) * distance)
            zombie.waypoint.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
        self._zombie_move_toward(zombie, zombie.waypoint, dt, sprint=False, rng=rng)

    def _update_patrol(self, zombie: ZombieState, dt: float, rng: random.Random) -> None:
        if zombie.idle_timer > 0.0:
            zombie.idle_timer = max(0.0, zombie.idle_timer - dt)
            return
        if zombie.waypoint and rng.random() < 0.0035:
            zombie.idle_timer = rng.uniform(0.8, 2.4)
            return
        if not zombie.waypoint or zombie.pos.distance_to(zombie.waypoint) < 38 or self._near_building(zombie.waypoint, 120):
            if zombie.waypoint and zombie.pos.distance_to(zombie.waypoint) < 38 and rng.random() < 0.46:
                zombie.idle_timer = rng.uniform(0.8, 2.6)
                zombie.waypoint = None
                return
            zombie.waypoint = self._random_patrol_pos(rng)
        self._zombie_move_toward(zombie, zombie.waypoint, dt, sprint=False, rng=rng)

    def _zombie_move_toward(
        self,
        zombie: ZombieState,
        target: Vec2,
        dt: float,
        sprint: bool,
        rng: random.Random | None = None,
    ) -> None:
        rng = rng or self.rng
        spec = ZOMBIES[zombie.kind]
        direction = Vec2(target.x - zombie.pos.x, target.y - zombie.pos.y)
        if direction.length() <= 0.01:
            return
        zombie.facing = math.atan2(direction.y, direction.x)
        speed = spec.speed * self.difficulty.zombie_speed_multiplier * (1.22 if sprint else 1.0)
        step = direction.normalized().scaled(speed * dt)
        old_pos = zombie.pos.copy()
        self._move_circle(zombie.pos, step, spec.radius, zombie.floor)
        if zombie.pos.distance_to(old_pos) < 0.5:
            if self._unstick_zombie_from_building(zombie, spec.radius, rng):
                zombie.waypoint = self._random_patrol_pos(rng)
                return
            door = nearest_door(self.buildings, zombie.pos, 120, zombie.floor)
            if door and door.open:
                zombie.waypoint = door.rect.center
            else:
                zombie.waypoint = self._random_patrol_pos(rng)

    def _leaper_move_toward(self, zombie: ZombieState, target: Vec2, dt: float, rng: random.Random) -> None:
        spec = ZOMBIES[zombie.kind]
        to_target = Vec2(target.x - zombie.pos.x, target.y - zombie.pos.y)
        distance = to_target.length()
        if distance <= 0.01:
            return
        forward = to_target.normalized()
        if zombie.sidestep_timer <= 0.0:
            zombie.sidestep_timer = rng.uniform(0.55, 1.05)
            zombie.sidestep_bias = rng.choice([-1.0, 1.0]) * rng.uniform(0.42, 0.78)
        zombie.strafe_phase += dt * (1.75 + min(1.0, distance / 620.0) * 0.55)
        wave = math.sin(zombie.strafe_phase) * 0.55 + math.sin(zombie.strafe_phase * 0.43 + zombie.sidestep_bias) * 0.25
        lateral_strength = max(-0.74, min(0.74, wave + zombie.sidestep_bias * 0.32))
        if distance < 150:
            lateral_strength *= distance / 150.0
        perpendicular = Vec2(-forward.y, forward.x)
        blended = Vec2(
            forward.x + perpendicular.x * lateral_strength,
            forward.y + perpendicular.y * lateral_strength,
        ).normalized()
        zombie.facing = math.atan2(forward.y, forward.x)
        speed = spec.speed * self.difficulty.zombie_speed_multiplier * 1.16
        old_pos = zombie.pos.copy()
        self._move_circle(zombie.pos, blended.scaled(speed * dt), spec.radius, zombie.floor)
        if zombie.pos.distance_to(old_pos) < 0.5:
            zombie.sidestep_bias *= -1.0
            self._zombie_move_toward(zombie, target, dt, sprint=True, rng=rng)

    def _try_poison_spit(
        self,
        zombie: ZombieState,
        target: PlayerState,
        rng: random.Random,
        poison_spits: list[_PoisonSpitEvent] | None = None,
    ) -> None:
        if zombie.special_cooldown > 0.0:
            return
        distance = zombie.pos.distance_to(target.pos)
        if not 180 <= distance <= 720:
            return
        if self._line_blocked(zombie.pos, target.pos, zombie.floor):
            return
        direction = Vec2(target.pos.x - zombie.pos.x, target.pos.y - zombie.pos.y).normalized()
        start = Vec2(
            zombie.pos.x + direction.x * (ZOMBIES[zombie.kind].radius + 14),
            zombie.pos.y + direction.y * (ZOMBIES[zombie.kind].radius + 14),
        )
        speed = 520.0
        if poison_spits is None:
            spit_id = self._id("spit")
            self.poison_projectiles[spit_id] = PoisonProjectileState(
                spit_id,
                zombie.id,
                start,
                direction.scaled(speed),
                target.pos.copy(),
                floor=zombie.floor,
            )
        else:
            poison_spits.append(_PoisonSpitEvent(zombie.id, start, direction.scaled(speed), target.pos.copy(), zombie.floor))
        zombie.special_cooldown = rng.uniform(2.8, 4.2)

    def _try_zombie_attack(
        self,
        zombie: ZombieState,
        target: PlayerState,
        player_hits: list[tuple[str, int]] | None = None,
    ) -> None:
        spec = ZOMBIES[zombie.kind]
        if zombie.pos.distance_to(target.pos) <= ZOMBIE_TARGET_RADIUS + spec.radius and zombie.attack_cooldown <= 0.0:
            damage = max(1, int(round(spec.damage * self.difficulty.zombie_damage_multiplier)))
            if player_hits is None:
                self._damage_player(target, damage)
            else:
                player_hits.append((target.id, damage))
            zombie.attack_cooldown = 0.7

    def _visible_player(self, zombie: ZombieState, players: list[PlayerState]) -> PlayerState | None:
        visible = [player for player in players if self._can_see(zombie, player)]
        if not visible:
            return None
        return min(visible, key=lambda player: zombie.pos.distance_to(player.pos))

    def _can_see(self, zombie: ZombieState, player: PlayerState) -> bool:
        if zombie.floor != player.floor:
            return False
        spec = ZOMBIES[zombie.kind]
        distance = zombie.pos.distance_to(player.pos)
        if distance > spec.sight_range:
            return False
        angle_to_player = zombie.pos.angle_to(player.pos)
        if abs(_angle_delta(zombie.facing, angle_to_player)) > math.radians(spec.fov_degrees * 0.5):
            return False
        return not self._line_blocked(zombie.pos, player.pos, zombie.floor)

    def _heard_player(self, zombie: ZombieState, players: list[PlayerState]) -> PlayerState | None:
        heard: list[PlayerState] = []
        spec = ZOMBIES[zombie.kind]
        for player in players:
            if zombie.floor != player.floor:
                continue
            if player.inside_building:
                continue
            if player.noise <= 0.0:
                continue
            distance = zombie.pos.distance_to(player.pos)
            hearing_radius = spec.hearing_range + player.noise * spec.sensitivity
            if distance <= hearing_radius and not self._line_blocked(zombie.pos, player.pos, zombie.floor, sound=True):
                heard.append(player)
        if not heard:
            return None
        return min(heard, key=lambda player: zombie.pos.distance_to(player.pos))

    def _damage_zombie(self, zombie: ZombieState, damage: int, owner_id: str) -> None:
        if zombie.armor > 0:
            blocked = min(zombie.armor, math.ceil(damage * 0.55))
            zombie.armor -= blocked
            damage -= blocked // 2
        zombie.health -= max(1, damage)
        zombie.mode = "search"
        zombie.last_known_pos = self.players[owner_id].pos.copy() if owner_id in self.players else zombie.last_known_pos
        zombie.search_timer = SEARCH_DURATION
        if zombie.health <= 0:
            self.zombies.pop(zombie.id, None)
            player = self.players.get(owner_id)
            if player:
                player.score += 1
                player.kills_by_kind[zombie.kind] = player.kills_by_kind.get(zombie.kind, 0) + 1
            if self.rng.random() < 0.45:
                self._drop_from_zombie(zombie.pos)

    def _damage_player(self, player: PlayerState, damage: int) -> None:
        player.healing_left = 0.0
        player.healing_pool = 0.0
        player.healing_rate = 0.0
        mitigation = self._player_armor_mitigation(player)
        mitigated = int(damage * mitigation)
        remaining = max(1, damage - mitigated)
        if player.armor > 0:
            absorbed = min(player.armor, max(1, mitigated + damage // 4))
            player.armor -= absorbed
            remaining = max(1, remaining - absorbed // 4)
            for item in player.equipment.values():
                if item:
                    rarity = rarity_spec(item.rarity)
                    wear = (
                        max(0.4, damage * 0.08)
                        * self.difficulty.armor_wear_multiplier
                        / rarity.armor_durability_multiplier
                    )
                    item.durability = max(0.0, item.durability - wear)
        player.health -= remaining
        if player.health <= 0:
            player.health = 0
            player.alive = False

    def _player_armor_mitigation(self, player: PlayerState) -> float:
        best = 0.0
        for item in player.equipment.values():
            spec = ITEMS.get(item.key) if item else None
            if not item or not spec or not spec.armor_key or item.durability <= 0:
                continue
            armor = ARMORS.get(spec.armor_key, ARMORS["none"])
            rarity = rarity_spec(item.rarity)
            best = max(best, armor.mitigation * rarity.armor_mitigation_multiplier)
        return min(0.88, best)

    def _effective_armor_points(self, item: InventoryItem | None) -> int:
        spec = ITEMS.get(item.key) if item else None
        if not item or not spec or not spec.armor_key:
            return 0
        armor = ARMORS.get(spec.armor_key, ARMORS["none"])
        rarity = rarity_spec(item.rarity)
        return max(0, int(round(armor.armor_points * rarity.armor_points_multiplier)))

    def _update_healing(self, player: PlayerState, dt: float) -> None:
        if player.healing_left <= 0.0 or player.healing_pool <= 0.0 or player.health >= 100:
            return
        healed = min(player.healing_pool, player.healing_rate * dt)
        player.healing_pool -= healed
        player.healing_left = max(0.0, player.healing_left - dt)
        player.health = min(100, player.health + healed)

    def _set_notice(self, player: PlayerState, key: str, seconds: float = 2.2) -> None:
        player.notice = key
        player.notice_timer = max(player.notice_timer, seconds)

    def _update_notice(self, player: PlayerState, dt: float) -> None:
        if player.notice_timer <= 0.0:
            player.notice = ""
            player.notice_timer = 0.0
            return
        player.notice_timer = max(0.0, player.notice_timer - dt)
        if player.notice_timer <= 0.0:
            player.notice = ""

    def _apply_inventory_action(self, player: PlayerState, action: dict[str, object]) -> None:
        action_type = str(action.get("type", ""))
        if action_type == "move":
            self._move_inventory_item(player, action)
        elif action_type == "quick_swap":
            a = str(action.get("a", ""))
            b = str(action.get("b", ""))
            if a in SLOTS and b in SLOTS:
                player.weapons[a], player.weapons[b] = player.weapons.get(b), player.weapons.get(a)
                if player.weapons.get(a) is None:
                    player.weapons.pop(a, None)
                if player.weapons.get(b) is None:
                    player.weapons.pop(b, None)
                player.quick_items[a], player.quick_items[b] = player.quick_items.get(b), player.quick_items.get(a)
        elif action_type == "repair_drag":
            self._repair_with_kit(player, action)
        elif action_type == "unequip_module":
            slot = str(action.get("slot", ""))
            module_slot = str(action.get("module_slot", ""))
            item = self._take_item(player, "weapon_module", -1, slot, module_slot)
            if item and not self._add_item(player, item.key, item.amount, item.rarity):
                self._place_item(player, "weapon_module", -1, slot, item, module_slot)
        elif action_type == "drop":
            source = str(action.get("source", "backpack"))
            index = int(action.get("index", -1))
            slot = str(action.get("slot", ""))
            module_slot = str(action.get("module_slot", ""))
            if source == "weapon_slot" and slot in player.weapons:
                weapon = player.weapons.pop(slot, None)
                if weapon:
                    self._spawn_loot_at(player.pos.copy(), "weapon", weapon.key, 1, floor=player.floor, rarity=weapon.rarity)
                    if player.active_slot == slot:
                        player.active_slot = next((slot_key for slot_key in SLOTS if player.weapons.get(slot_key)), "1")
                return
            item = self._take_item(player, source, index, slot, module_slot)
            if item:
                self._spawn_loot_at(player.pos.copy(), "item", item.key, item.amount, floor=player.floor, rarity=item.rarity)
        elif action_type == "use":
            index = int(action.get("index", -1))
            if 0 <= index < len(player.backpack):
                item = player.backpack[index]
                if item and self._use_item(player, item):
                    item.amount -= 1
                    if item.amount <= 0:
                        player.backpack[index] = None

    def _move_inventory_item(self, player: PlayerState, action: dict[str, object]) -> None:
        src = str(action.get("src", "backpack"))
        dst = str(action.get("dst", "backpack"))
        src_index = int(action.get("src_index", -1))
        dst_index = int(action.get("dst_index", -1))
        src_slot = str(action.get("src_slot", ""))
        dst_slot = str(action.get("dst_slot", ""))
        src_module = str(action.get("src_module", ""))
        dst_module = str(action.get("dst_module", ""))
        if src == "weapon_slot":
            if dst != "backpack":
                return
            if not (0 <= dst_index < len(player.backpack)) or player.backpack[dst_index] is not None:
                return
        item = self._take_item(player, src, src_index, src_slot, src_module)
        if not item:
            return
        displaced = self._place_item(player, dst, dst_index, dst_slot, item, dst_module)
        if displaced:
            self._place_item(player, src, src_index, src_slot, displaced, src_module)
        self._recalculate_armor(player)

    def _take_item(self, player: PlayerState, source: str, index: int, slot: str, module_slot: str = "") -> InventoryItem | None:
        if source == "backpack" and 0 <= index < len(player.backpack):
            item = player.backpack[index]
            player.backpack[index] = None
            return item
        if source == "weapon_slot" and slot in player.weapons:
            weapon = player.weapons.pop(slot, None)
            if not weapon:
                return None
            if player.active_slot == slot:
                player.active_slot = next((slot_key for slot_key in SLOTS if player.weapons.get(slot_key)), slot)
            return InventoryItem(self._id("it"), weapon.key, 1, durability=weapon.durability, rarity=weapon.rarity)
        if source == "equipment" and slot in player.equipment:
            item = player.equipment[slot]
            player.equipment[slot] = None
            return item
        if source == "quick_item" and slot in SLOTS:
            item = player.quick_items.get(slot)
            player.quick_items[slot] = None
            return item
        if source == "weapon_module":
            weapon = player.weapons.get(slot)
            if not weapon or module_slot not in weapon.modules:
                return None
            module_key = weapon.modules.get(module_slot)
            if not module_key:
                return None
            weapon.modules[module_slot] = None
            if module_slot == "utility":
                weapon.utility_on = False
            if module_slot == "magazine":
                weapon.ammo_in_mag = min(weapon.ammo_in_mag, self._weapon_magazine_size(weapon))
            return InventoryItem(self._id("it"), module_key, 1)
        return None

    def _place_item(
        self,
        player: PlayerState,
        destination: str,
        index: int,
        slot: str,
        item: InventoryItem,
        module_slot: str = "",
    ) -> InventoryItem | None:
        if destination == "weapon_module" and slot in player.weapons:
            module = WEAPON_MODULES.get(item.key)
            if not module or module.slot != module_slot:
                return item
            weapon = player.weapons[slot]
            displaced_key = weapon.modules.get(module_slot)
            weapon.modules[module_slot] = item.key
            if module_slot == "magazine":
                weapon.ammo_in_mag = min(weapon.ammo_in_mag, self._weapon_magazine_size(weapon))
            if module_slot == "utility":
                weapon.utility_on = False
            return InventoryItem(self._id("it"), displaced_key, 1) if displaced_key else None
        if destination == "weapon_slot" and slot in SLOTS:
            if player.weapons.get(slot) or player.quick_items.get(slot):
                return item
            if item.key in WEAPONS:
                spec = WEAPONS[item.key]
                player.weapons[slot] = WeaponRuntime(
                    item.key,
                    spec.magazine_size,
                    spec.magazine_size * 2,
                    durability=item.durability,
                    rarity=item.rarity,
                )
                player.active_slot = slot
                return None
            spec = ITEMS.get(item.key)
            if spec and spec.kind in {"grenade", "mine"}:
                player.quick_items[slot] = item
                return None
            return item
        if destination == "equipment" and slot in player.equipment:
            spec = ITEMS.get(item.key)
            if not spec or spec.equipment_slot != slot:
                return item
            displaced = player.equipment.get(slot)
            player.equipment[slot] = item
            return displaced
        if destination == "quick_item" and slot in SLOTS:
            spec = ITEMS.get(item.key)
            if not spec or spec.kind not in {"grenade", "mine"}:
                return item
            displaced = player.quick_items.get(slot)
            player.quick_items[slot] = item
            return displaced
        if destination == "backpack" and 0 <= index < len(player.backpack):
            displaced = player.backpack[index]
            player.backpack[index] = item
            return displaced
        return item

    def _use_item(self, player: PlayerState, item: InventoryItem) -> bool:
        spec = ITEMS.get(item.key)
        if not spec:
            return False
        if spec.kind in {"food", "medical"} and spec.heal_total > 0 and player.health < 100:
            player.healing_pool = float(spec.heal_total)
            player.healing_left = max(0.1, spec.heal_seconds)
            player.healing_rate = spec.heal_total / max(0.1, spec.heal_seconds)
            return True
        if spec.kind == "ammo":
            for weapon in player.weapons.values():
                weapon.reserve_ammo += 12 * item.amount
            return True
        return False

    def _craft(self, player: PlayerState, recipe_key: str) -> None:
        if not nearest_prop(self.buildings, player.pos, INTERACT_RADIUS, "work_bench", player.floor):
            return
        recipe = RECIPES.get(recipe_key)
        if not recipe:
            return
        if any(self._count_item(player, key) < amount for key, amount in recipe.requires.items()):
            return
        result_key, result_amount = recipe.result
        result_spec = ITEMS.get(result_key)
        result_kind = result_spec.kind if result_spec else "item"
        result_rarity = roll_crafted_rarity(self.rng, recipe.key, result_kind)
        if not self._can_add_item(player, result_key, result_amount, result_rarity):
            self._pickup_failed_full(player)
            return
        for key, amount in recipe.requires.items():
            self._remove_items(player, key, amount)
        self._add_item(player, result_key, result_amount, rarity=result_rarity)

    def _repair_armor(self, player: PlayerState, slot: str) -> None:
        if not nearest_prop(self.buildings, player.pos, INTERACT_RADIUS, "repair_table", player.floor):
            return
        item = player.equipment.get(slot)
        if not item:
            return
        if not self._remove_items(player, "repair_kit", 1):
            return
        spec = ITEMS.get(item.key)
        if spec and spec.armor_key and spec.armor_key in ARMORS:
            player.armor_key = spec.armor_key
            player.armor = min(self._effective_armor_points(item), player.armor + 35)

    def _repair_with_kit(self, player: PlayerState, action: dict[str, object]) -> None:
        kit_index = int(action.get("kit_index", -1))
        target_source = str(action.get("target_source", ""))
        target_index = int(action.get("target_index", -1))
        target_slot = str(action.get("target_slot", ""))
        if not (0 <= kit_index < len(player.backpack)):
            return
        kit = player.backpack[kit_index]
        if not kit or kit.key != "repair_kit":
            return
        target = None
        if target_source == "backpack" and 0 <= target_index < len(player.backpack):
            target = player.backpack[target_index]
        elif target_source == "equipment" and target_slot in player.equipment:
            target = player.equipment[target_slot]
        elif target_source == "quick_item" and target_slot in SLOTS:
            target = player.quick_items.get(target_slot)
        elif target_source == "weapon_slot" and target_slot in player.weapons:
            weapon = player.weapons[target_slot]
            weapon.durability = 100.0
            kit.amount -= 1
            if kit.amount <= 0:
                player.backpack[kit_index] = None
            return
        if not target or target.durability >= 100.0:
            return
        target.durability = 100.0
        kit.amount -= 1
        if kit.amount <= 0:
            player.backpack[kit_index] = None

    def _add_item(self, player: PlayerState, key: str, amount: int, rarity: str = "common") -> bool:
        spec = ITEMS.get(key)
        if not spec:
            return False
        remaining = amount
        for item in player.backpack:
            if item and item.key == key and item.rarity == rarity and item.amount < spec.stack_size:
                add = min(remaining, spec.stack_size - item.amount)
                item.amount += add
                remaining -= add
                if remaining <= 0:
                    return True
        for index, item in enumerate(player.backpack):
            if item is None:
                add = min(remaining, spec.stack_size)
                player.backpack[index] = InventoryItem(self._id("it"), key, add, rarity=rarity)
                remaining -= add
                if remaining <= 0:
                    return True
        return False

    def _can_add_item(self, player: PlayerState, key: str, amount: int, rarity: str = "common") -> bool:
        spec = ITEMS.get(key)
        if not spec:
            return False
        capacity = 0
        for item in player.backpack:
            if item is None:
                capacity += spec.stack_size
            elif item.key == key and item.rarity == rarity:
                capacity += max(0, spec.stack_size - item.amount)
            if capacity >= amount:
                return True
        return False

    def _add_weapon_to_backpack(self, player: PlayerState, weapon_key: str, rarity: str, durability: float = 100.0) -> bool:
        if weapon_key not in WEAPONS:
            return False
        for index, item in enumerate(player.backpack):
            if item is None:
                player.backpack[index] = InventoryItem(self._id("it"), weapon_key, 1, durability=durability, rarity=rarity)
                return True
        return False

    def _free_quick_slot(self, player: PlayerState, preferred: str | None = None) -> str | None:
        ordered = ([preferred] if preferred in SLOTS else []) + [slot for slot in SLOTS if slot != preferred]
        for slot in ordered:
            if not player.weapons.get(slot) and not player.quick_items.get(slot):
                return slot
        return None

    def _pickup_failed_full(self, player: PlayerState) -> None:
        self._set_notice(player, "notice.backpack_full")

    def _count_item(self, player: PlayerState, key: str) -> int:
        return sum(item.amount for item in player.backpack if item and item.key == key)

    def _remove_items(self, player: PlayerState, key: str, amount: int) -> bool:
        if self._count_item(player, key) < amount:
            return False
        remaining = amount
        for index, item in enumerate(player.backpack):
            if not item or item.key != key:
                continue
            take = min(remaining, item.amount)
            item.amount -= take
            remaining -= take
            if item.amount <= 0:
                player.backpack[index] = None
            if remaining <= 0:
                return True
        return True

    def _recalculate_armor(self, player: PlayerState) -> None:
        best_key = "none"
        best_points = 0
        for item in player.equipment.values():
            spec = ITEMS.get(item.key) if item else None
            if spec and spec.armor_key and item.durability > 0:
                points = self._effective_armor_points(item)
                if points > best_points:
                    best_key = spec.armor_key
                    best_points = points
        player.armor_key = best_key
        if best_key == "none":
            player.armor = 0
        else:
            player.armor = max(player.armor, int(best_points * 0.65))
            player.armor = min(player.armor, best_points)

    def _equip_armor(self, player: PlayerState, armor_key: str) -> None:
        spec = ARMORS[armor_key]
        if armor_key == "none":
            player.armor_key = "none"
            return
        if armor_key not in player.owned_armors:
            return
        player.armor_key = armor_key
        player.armor = max(player.armor, spec.armor_points)

    def _start_reload(self, player: PlayerState) -> None:
        weapon = player.active_weapon()
        if not weapon:
            return
        spec = WEAPONS[weapon.key]
        if weapon.reload_left <= 0.0 and weapon.reserve_ammo > 0 and weapon.ammo_in_mag < self._weapon_magazine_size(weapon):
            weapon.reload_left = spec.reload_time

    def _finish_reload(self, weapon: WeaponRuntime) -> None:
        needed = self._weapon_magazine_size(weapon) - weapon.ammo_in_mag
        loaded = min(needed, weapon.reserve_ammo)
        weapon.ammo_in_mag += loaded
        weapon.reserve_ammo -= loaded

    def _weapon_magazine_size(self, weapon: WeaponRuntime) -> int:
        base = WEAPONS[weapon.key].magazine_size
        module_key = weapon.modules.get("magazine")
        module = WEAPON_MODULES.get(module_key or "")
        multiplier = module.magazine_multiplier if module else 1.0
        return max(base, int(math.ceil(base * multiplier)))

    def _weapon_spread(self, weapon: WeaponRuntime) -> float:
        spread = WEAPONS[weapon.key].spread
        module_key = weapon.modules.get("utility")
        module = WEAPON_MODULES.get(module_key or "")
        if module_key == "laser_module" and weapon.utility_on and module:
            spread *= module.spread_multiplier
        return spread

    def _toggle_weapon_utility(self, player: PlayerState) -> None:
        weapon = player.active_weapon()
        if not weapon:
            return
        if weapon.modules.get("utility") in {"laser_module", "flashlight_module"}:
            weapon.utility_on = not weapon.utility_on

    def _shoot(self, player: PlayerState) -> None:
        quick_item = player.quick_items.get(player.active_slot)
        if quick_item:
            spec = ITEMS.get(quick_item.key)
            if spec and spec.kind == "grenade":
                self._throw_grenade_from_quick(player, player.active_slot)
                return
            if spec and spec.kind == "mine":
                self._place_mine_from_quick(player, player.active_slot)
                return
        weapon = player.active_weapon()
        if not weapon:
            return
        spec = WEAPONS[weapon.key]
        if weapon.cooldown > 0.0 or weapon.reload_left > 0.0:
            return
        if weapon.durability <= 0:
            return
        if weapon.ammo_in_mag <= 0:
            self._start_reload(player)
            return

        weapon.ammo_in_mag -= 1
        rarity = rarity_spec(weapon.rarity)
        wear = self.rng.uniform(0.08, 0.22) * self.difficulty.weapon_wear_multiplier / rarity.weapon_durability_multiplier
        weapon.durability = max(0.0, weapon.durability - wear)
        weapon.cooldown = 1.0 / spec.fire_rate
        damage_multiplier = self.difficulty.weapon_damage_multipliers.get(spec.key, self.difficulty.weapon_damage_multiplier)
        projectile_damage = max(1, int(round(spec.damage * damage_multiplier * rarity.weapon_damage_multiplier)))
        for pellet_index in range(spec.pellets):
            weapon_spread = self._weapon_spread(weapon)
            spread = self.rng.uniform(-weapon_spread, weapon_spread)
            if spec.pellets > 1:
                spread += (pellet_index - (spec.pellets - 1) * 0.5) * weapon_spread * 0.33
            angle = player.angle + spread
            velocity = Vec2(math.cos(angle) * spec.projectile_speed, math.sin(angle) * spec.projectile_speed)
            start = Vec2(
                player.pos.x + math.cos(angle) * (PLAYER_RADIUS + 8),
                player.pos.y + math.sin(angle) * (PLAYER_RADIUS + 8),
            )
            projectile_id = self._id("shot")
            self.projectiles[projectile_id] = ProjectileState(
                id=projectile_id,
                owner_id=player.id,
                pos=start,
                velocity=velocity,
                damage=projectile_damage,
                life=0.82,
                floor=player.floor,
            )

    def _throw_grenade(self, player: PlayerState) -> None:
        if self._grenade_cooldowns.get(player.id, 0.0) > 0:
            return
        quick_item = player.quick_items.get(player.active_slot)
        if quick_item and ITEMS.get(quick_item.key) and ITEMS[quick_item.key].kind == "grenade":
            self._throw_grenade_from_quick(player, player.active_slot)
            return
        for grenade_key in ("grenade", "contact_grenade", "heavy_grenade"):
            if self._remove_items(player, grenade_key, 1):
                self._spawn_grenade(player, grenade_key)
                return

    def _throw_grenade_from_quick(self, player: PlayerState, slot: str) -> None:
        if self._grenade_cooldowns.get(player.id, 0.0) > 0:
            return
        item = player.quick_items.get(slot)
        spec = ITEMS.get(item.key) if item else None
        if not item or not spec or spec.kind != "grenade":
            return
        grenade_key = item.key
        item.amount -= 1
        if item.amount <= 0:
            player.quick_items[slot] = None
        self._spawn_grenade(player, grenade_key)
        self._grenade_cooldowns[player.id] = 0.6

    def _spawn_grenade(self, player: PlayerState, grenade_key: str = "grenade") -> None:
        grenade_spec = GRENADE_SPECS.get(grenade_key, DEFAULT_GRENADE)
        self._grenade_cooldowns[player.id] = 0.6
        distance = grenade_spec.throw_distance
        velocity = Vec2(math.cos(player.angle) * distance, math.sin(player.angle) * distance)
        start = Vec2(
            player.pos.x + math.cos(player.angle) * (PLAYER_RADIUS + 12),
            player.pos.y + math.sin(player.angle) * (PLAYER_RADIUS + 12),
        )
        grenade_id = self._id("g")
        self.grenades[grenade_id] = GrenadeState(
            grenade_id,
            player.id,
            start,
            velocity,
            timer=grenade_spec.timer,
            floor=player.floor,
            kind=grenade_key,
        )

    def _detonate_grenade(self, grenade: GrenadeState) -> None:
        spec = GRENADE_SPECS.get(grenade.kind, DEFAULT_GRENADE)
        self._explode_at(
            grenade.pos,
            grenade.floor,
            grenade.owner_id,
            spec.blast_radius,
            spec.zombie_damage,
            spec.zombie_damage_bonus,
            spec.player_damage,
            spec.player_damage_bonus,
        )

    def _place_mine_from_quick(self, player: PlayerState, slot: str) -> None:
        if self._grenade_cooldowns.get(player.id, 0.0) > 0:
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
        if self._blocked_at(place_pos, 12, player.floor):
            place_pos = player.pos.copy()
        mine_id = self._id("m")
        self.mines[mine_id] = MineState(
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
        self._grenade_cooldowns[player.id] = 0.45

    def _detonate_mine(self, mine: MineState) -> None:
        spec = MINE_SPECS.get(mine.kind, DEFAULT_MINE)
        self._explode_at(
            mine.pos,
            mine.floor,
            mine.owner_id,
            spec.blast_radius,
            spec.zombie_damage,
            spec.zombie_damage_bonus,
            spec.player_damage,
            spec.player_damage_bonus,
        )

    def _explode_at(
        self,
        pos: Vec2,
        floor: int,
        owner_id: str,
        blast_radius: float,
        zombie_damage: int,
        zombie_damage_bonus: int,
        player_damage: int,
        player_damage_bonus: int,
    ) -> None:
        for zombie in list(self.zombies.values()):
            if zombie.floor != floor:
                continue
            distance = zombie.pos.distance_to(pos)
            if distance <= blast_radius and not self._line_blocked(pos, zombie.pos, floor):
                damage = int(zombie_damage * (1.0 - distance / blast_radius)) + zombie_damage_bonus
                self._damage_zombie(zombie, damage, owner_id)
        for player in self.players.values():
            if player.floor != floor or not player.alive:
                continue
            player_radius = blast_radius * 0.65
            distance = player.pos.distance_to(pos)
            if distance <= player_radius and not self._line_blocked(pos, player.pos, floor):
                damage = int(player_damage * (1.0 - distance / player_radius)) + player_damage_bonus
                self._damage_player(player, damage)

    def _pickup_nearby(self, player: PlayerState) -> None:
        closest = None
        closest_distance = PICKUP_RADIUS
        for item in self.loot.values():
            if item.floor != player.floor:
                continue
            distance = player.pos.distance_to(item.pos)
            if distance <= closest_distance:
                closest = item
                closest_distance = distance
        if not closest:
            return

        if closest.kind == "weapon" and closest.payload in WEAPONS:
            spec = WEAPONS[closest.payload]
            current = player.weapons.get(spec.slot)
            if current:
                current.reserve_ammo += spec.magazine_size
                if rarity_rank(closest.rarity) > rarity_rank(current.rarity):
                    current.rarity = closest.rarity
                    current.durability = max(current.durability, 100.0)
            else:
                target_slot = self._free_quick_slot(player, spec.slot)
                if target_slot:
                    player.weapons[target_slot] = WeaponRuntime(
                        spec.key,
                        spec.magazine_size,
                        spec.magazine_size * 2,
                        rarity=closest.rarity,
                    )
                    player.active_slot = target_slot
                elif not self._add_weapon_to_backpack(player, spec.key, closest.rarity):
                    self._pickup_failed_full(player)
                    return
            self._add_item(player, "ammo_pack", 1)
        elif closest.kind == "ammo":
            if not self._add_item(player, "ammo_pack", max(1, closest.amount // 12)):
                self._pickup_failed_full(player)
                return
            for weapon in player.weapons.values():
                if weapon.key == closest.payload:
                    weapon.reserve_ammo += closest.amount
                    break
        elif closest.kind == "armor" and closest.payload in ARMORS:
            armor_item = f"{closest.payload}_torso" if f"{closest.payload}_torso" in ITEMS else "light_torso"
            if not self._add_item(player, armor_item, 1, rarity=closest.rarity):
                self._pickup_failed_full(player)
                return
        elif closest.kind == "medkit":
            if not self._add_item(player, "medicine", closest.amount):
                self._pickup_failed_full(player)
                return
            player.medkits += closest.amount
        elif closest.kind == "item" and closest.payload in ITEMS:
            if not self._add_item(player, closest.payload, closest.amount, rarity=closest.rarity):
                self._pickup_failed_full(player)
                return

        self.loot.pop(closest.id, None)

    def _interact(self, player: PlayerState) -> bool:
        door = nearest_door(self.buildings, player.pos, INTERACT_RADIUS, player.floor)
        if door:
            door.open = not door.open
            self._mark_geometry_dirty()
            return True
        building = nearest_stairs(self.buildings, player.pos, INTERACT_RADIUS)
        if building and building.bounds.contains(player.pos):
            player.floor += 1
            if player.floor > building.max_floor:
                player.floor = building.min_floor
            player.inside_building = building.id
            return True
        return False

    def spawn_zombie(self, kind: str | None = None) -> ZombieState:
        kind = kind or self.rng.choices(["walker", "runner", "brute", "leaper"], weights=[0.48, 0.24, 0.14, 0.14])[0]
        spec = ZOMBIES[kind]
        pos = self._random_edge_pos()
        health = max(1, int(round(spec.health * self.difficulty.zombie_health_multiplier)))
        armor = max(0, int(round(spec.armor * self.difficulty.zombie_armor_multiplier)))
        zombie = ZombieState(self._id("z"), kind, pos, health, armor, facing=self.rng.uniform(-math.pi, math.pi))
        zombie.waypoint = self._random_patrol_pos(self.rng)
        self.zombies[zombie.id] = zombie
        return zombie

    def _loot_count(self, base: int, minimum: int = 1) -> int:
        return max(minimum, int(round(base * self.difficulty.loot_spawn_multiplier)))

    def spawn_loot(self, kind: str, payload: str, amount: int, rarity: str | None = None) -> LootState:
        return self._spawn_loot_at(self._random_open_pos(centered=False), kind, payload, amount, rarity=rarity)

    def _spawn_loot_at(
        self,
        pos: Vec2,
        kind: str,
        payload: str,
        amount: int,
        floor: int = 0,
        rarity: str | None = None,
    ) -> LootState:
        if kind == "medkit":
            payload = "medkit"
        item_rarity = rarity or self._loot_rarity(kind, payload)
        item = LootState(self._id("l"), kind, pos, payload, amount, floor=floor, rarity=item_rarity)
        self.loot[item.id] = item
        return item

    def _loot_rarity(self, kind: str, payload: str) -> str:
        spec = ITEMS.get(payload)
        if kind in {"weapon", "armor"} or (kind == "item" and spec and spec.kind == "armor"):
            return self._roll_rarity()
        return "common"

    def _roll_rarity(self) -> str:
        keys = list(RARITIES)
        weights = [RARITIES[key].loot_weight for key in keys]
        if sum(weights) <= 0:
            return "common"
        return self.rng.choices(keys, weights=weights)[0]

    def _spawn_random_loot(self) -> None:
        roll = self.rng.random()
        if roll < 0.30:
            item_key = self.rng.choices([item[0] for item in WORLD_LOOT], weights=[item[2] for item in WORLD_LOOT])[0]
            self.spawn_loot("item", item_key, self.rng.randint(1, 3))
        elif roll < 0.52:
            self.spawn_loot("ammo", self.rng.choice(list(WEAPONS)), self.rng.randint(10, 35))
        elif roll < 0.65:
            self.spawn_loot("medkit", "medkit", 1)
        elif roll < 0.83:
            self.spawn_loot("armor", self.rng.choice(["light", "tactical", "heavy"]), 1)
        else:
            self.spawn_loot("weapon", self.rng.choice(["smg", "shotgun", "rifle"]), 1)

    def _drop_from_zombie(self, pos: Vec2) -> None:
        kind = self.rng.choice(["ammo", "medkit"])
        payload = self.rng.choice(list(WEAPONS)) if kind == "ammo" else "medkit"
        amount = self.rng.randint(5, 18) if kind == "ammo" else 1
        item = LootState(self._id("l"), kind, replace(pos), payload, amount)
        self.loot[item.id] = item

    def _building_entry_target(self, building_id: str) -> Vec2 | None:
        building = self.buildings.get(building_id)
        if not building:
            return None
        open_doors = [door for door in building.doors if door.open and door.floor == 0]
        if open_doors:
            return min(open_doors, key=lambda door: door.rect.center.distance_to(building.bounds.center)).rect.center
        front = min(building.doors, key=lambda door: door.rect.center.y)
        center = front.rect.center
        return Vec2(center.x, center.y - 80)

    def _random_open_pos(self, centered: bool, rng: random.Random | None = None) -> Vec2:
        rng = rng or self.rng
        for _ in range(500):
            if centered:
                pos = Vec2(
                    MAP_WIDTH * 0.5 + rng.uniform(-360, 360),
                    MAP_HEIGHT * 0.5 + rng.uniform(-300, 300),
                )
            else:
                pos = Vec2(rng.uniform(160, MAP_WIDTH - 160), rng.uniform(160, MAP_HEIGHT - 160))
            if not self._blocked_at(pos, PLAYER_RADIUS):
                return pos
        return Vec2(MAP_WIDTH * 0.5, MAP_HEIGHT * 0.5)

    def _safe_respawn(self) -> tuple[Vec2, int, str | None]:
        buildings = list(self.buildings.values())
        self.rng.shuffle(buildings)
        for building in buildings:
            floors = [floor for floor in (1, 2, -1, 0) if building.min_floor <= floor <= building.max_floor]
            self.rng.shuffle(floors)
            for floor in floors:
                for _ in range(80):
                    pos = Vec2(
                        self.rng.uniform(building.bounds.x + 96, building.bounds.x + building.bounds.w - 96),
                        self.rng.uniform(building.bounds.y + 104, building.bounds.y + building.bounds.h - 104),
                    )
                    if not self._blocked_at(pos, PLAYER_RADIUS, floor) and self._respawn_is_safe(pos, floor):
                        return pos, floor, building.id
        for _ in range(800):
            pos = self._random_open_pos(centered=False)
            if self._respawn_is_safe(pos, 0):
                return pos, 0, None
        return self._random_open_pos(centered=True), 0, None

    def _respawn_is_safe(self, pos: Vec2, floor: int) -> bool:
        for zombie in self.zombies.values():
            if zombie.floor != floor:
                continue
            spec = ZOMBIES[zombie.kind]
            distance = zombie.pos.distance_to(pos)
            if distance < 760:
                return False
            if distance < spec.sight_range + 140 and not self._line_blocked(zombie.pos, pos, floor):
                return False
        return True

    def _random_patrol_pos(self, rng: random.Random | None = None) -> Vec2:
        rng = rng or self.rng
        for _ in range(500):
            pos = self._random_open_pos(centered=False, rng=rng)
            if not self._near_building(pos, 340):
                return pos
        return self._random_open_pos(centered=False, rng=rng)

    def _near_building(self, pos: Vec2, margin: float) -> bool:
        for building in self.buildings.values():
            if building.bounds.inflated(margin).contains(pos):
                return True
        return False

    def _unstick_zombie_from_building(
        self,
        zombie: ZombieState,
        radius: float,
        rng: random.Random | None = None,
    ) -> bool:
        rng = rng or self.rng
        nearest = min(self.buildings.values(), key=lambda building: building.bounds.center.distance_to(zombie.pos), default=None)
        if not nearest or not nearest.bounds.inflated(120).contains(zombie.pos):
            return False
        if nearest.bounds.inflated(8).contains(zombie.pos):
            exits = [
                Vec2(nearest.bounds.x - 90, zombie.pos.y),
                Vec2(nearest.bounds.x + nearest.bounds.w + 90, zombie.pos.y),
                Vec2(zombie.pos.x, nearest.bounds.y - 90),
                Vec2(zombie.pos.x, nearest.bounds.y + nearest.bounds.h + 90),
            ]
            exits.sort(key=lambda candidate: candidate.distance_to(zombie.pos))
            for candidate in exits:
                candidate.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
                if not self._blocked_at(candidate, radius):
                    zombie.pos = candidate
                    zombie.facing = zombie.pos.angle_to(nearest.bounds.center) + math.pi
                    return True
        center = nearest.bounds.center
        away = Vec2(zombie.pos.x - center.x, zombie.pos.y - center.y).normalized()
        if away.length() <= 0.0:
            away = Vec2(rng.choice([-1.0, 1.0]), rng.choice([-1.0, 1.0])).normalized()
        for distance in (72, 128, 196, 280):
            candidate = Vec2(zombie.pos.x + away.x * distance, zombie.pos.y + away.y * distance)
            candidate.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
            if not self._blocked_at(candidate, radius) and not self._near_building(candidate, 38):
                zombie.pos = candidate
                zombie.facing = math.atan2(away.y, away.x)
                return True
        return False

    def _random_edge_pos(self) -> Vec2:
        side = self.rng.choice(["top", "right", "bottom", "left"])
        if side == "top":
            return Vec2(self.rng.uniform(0, MAP_WIDTH), 40)
        if side == "right":
            return Vec2(MAP_WIDTH - 40, self.rng.uniform(0, MAP_HEIGHT))
        if side == "bottom":
            return Vec2(self.rng.uniform(0, MAP_WIDTH), MAP_HEIGHT - 40)
        return Vec2(40, self.rng.uniform(0, MAP_HEIGHT))

    def _move_circle(self, pos: Vec2, delta: Vec2, radius: float, floor: int) -> None:
        if delta.x:
            pos.x += delta.x
            if self._blocked_at(pos, radius, floor):
                pos.x -= delta.x
        if delta.y:
            pos.y += delta.y
            if self._blocked_at(pos, radius, floor):
                pos.y -= delta.y

    def _mark_geometry_dirty(self) -> None:
        with self._geometry_cache_lock:
            self._geometry_version += 1
            self._closed_walls_cache.clear()

    def _closed_walls(self, floor: int) -> tuple[RectState, ...]:
        cached = self._closed_walls_cache.get(floor)
        if cached and cached[0] == self._geometry_version:
            return cached[1]
        with self._geometry_cache_lock:
            cached = self._closed_walls_cache.get(floor)
            if cached and cached[0] == self._geometry_version:
                return cached[1]
            walls = tuple(all_closed_walls(self.buildings, floor))
            self._closed_walls_cache[floor] = (self._geometry_version, walls)
            return walls

    def _blocked_at(self, pos: Vec2, radius: float, floor: int = 0) -> bool:
        for wall in self._closed_walls(floor):
            if _circle_rect_intersects(pos, radius, wall):
                return True
        return False

    def _line_blocked(self, start: Vec2, end: Vec2, floor: int, sound: bool = False) -> bool:
        for wall in self._closed_walls(floor):
            if _segment_rect_intersects(start, end, wall):
                if sound and wall.w < 28 and wall.h < 90:
                    continue
                return True
        return False

    def snapshot(self) -> WorldSnapshot:
        with self._lock:
            return WorldSnapshot(
                time=self.time,
                map_width=MAP_WIDTH,
                map_height=MAP_HEIGHT,
                players=dict(self.players),
                zombies=dict(self.zombies),
                projectiles=dict(self.projectiles),
                grenades=dict(self.grenades),
                mines=dict(self.mines),
                poison_projectiles=dict(self.poison_projectiles),
                poison_pools=dict(self.poison_pools),
                loot=dict(self.loot),
                buildings=dict(self.buildings),
            )

    def zombie_count(self) -> int:
        with self._lock:
            return len(self.zombies)


def _angle_delta(a: float, b: float) -> float:
    return (b - a + math.pi) % (math.tau) - math.pi


def _clean_player_name(name: str) -> str:
    return "Operator" if not name.strip() else name.strip()[:18]


def _circle_rect_intersects(pos: Vec2, radius: float, rect: RectState) -> bool:
    closest_x = max(rect.x, min(pos.x, rect.x + rect.w))
    closest_y = max(rect.y, min(pos.y, rect.y + rect.h))
    dx = closest_x - pos.x
    dy = closest_y - pos.y
    return dx * dx + dy * dy <= radius * radius


def _segment_rect_intersects(start: Vec2, end: Vec2, rect: RectState) -> bool:
    min_x = min(start.x, end.x)
    max_x = max(start.x, end.x)
    min_y = min(start.y, end.y)
    max_y = max(start.y, end.y)
    if max_x < rect.x or min_x > rect.x + rect.w or max_y < rect.y or min_y > rect.y + rect.h:
        return False
    if rect.contains(start) or rect.contains(end):
        return True

    dx = end.x - start.x
    dy = end.y - start.y
    t0 = 0.0
    t1 = 1.0
    for p, q in (
        (-dx, start.x - rect.x),
        (dx, rect.x + rect.w - start.x),
        (-dy, start.y - rect.y),
        (dy, rect.y + rect.h - start.y),
    ):
        if abs(p) <= 0.000001:
            if q < 0.0:
                return False
            continue
        ratio = q / p
        if p < 0.0:
            if ratio > t1:
                return False
            if ratio > t0:
                t0 = ratio
        else:
            if ratio < t0:
                return False
            if ratio < t1:
                t1 = ratio
    return True
