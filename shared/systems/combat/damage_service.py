from __future__ import annotations

import math
import random

from shared.constants import ARMORS, MAP_HEIGHT, MAP_WIDTH, SEARCH_DURATION
from shared.difficulty import DifficultyConfig
from shared.items import ITEMS
from shared.models import PlayerState, SoldierState, Vec2, ZombieState
from shared.rarities import rarity_spec


class DamageService:
    def __init__(
        self,
        *,
        players: dict[str, PlayerState],
        zombies: dict[str, ZombieState],
        soldiers: dict[str, SoldierState],
        difficulty: DifficultyConfig,
        rng: random.Random,
        drop_from_zombie,
        zombie_ai_generation: dict[str, int],
        zombie_ai_pending: dict,
        zombie_ai_next_at: dict[str, float],
        get_time,
    ) -> None:
        self._players = players
        self._zombies = zombies
        self._soldiers = soldiers
        self._difficulty = difficulty
        self._rng = rng
        self._drop_from_zombie = drop_from_zombie

        self._zombie_ai_generation = zombie_ai_generation
        self._zombie_ai_pending = zombie_ai_pending
        self._zombie_ai_next_at = zombie_ai_next_at
        self._get_time = get_time

    def damage_player(self, player: PlayerState, damage: int) -> None:
        player.healing_left = 0.0
        player.healing_pool = 0.0
        player.healing_rate = 0.0
        player.healing_stacks = 0

        mitigation = self.player_armor_mitigation(player)
        mitigated = int(damage * mitigation)
        remaining = max(1, damage - mitigated)

        if player.armor > 0:
            absorbed = min(player.armor, max(1, mitigated + damage // 4))
            player.armor -= absorbed
            remaining = max(1, remaining - absorbed // 4)

            for item in player.equipment.values():
                if not item:
                    continue

                rarity = rarity_spec(item.rarity)
                wear = (
                    max(0.4, damage * 0.08)
                    * self._difficulty.armor_wear_multiplier
                    / rarity.armor_durability_multiplier
                )
                item.durability = max(0.0, item.durability - wear)

        player.health -= remaining

        if player.health <= 0:
            player.health = 0
            player.alive = False

    def damage_soldier(self, soldier: SoldierState, damage: int, owner_id: str) -> None:
        if not soldier.alive:
            return

        if soldier.armor > 0:
            blocked = min(soldier.armor, math.ceil(damage * 0.55))
            soldier.armor -= blocked
            damage -= blocked // 2

        soldier.health -= max(1, damage)

        if soldier.health > 0:
            return

        soldier.health = 0
        soldier.alive = False
        self._soldiers.pop(soldier.id, None)

    def damage_zombie(
        self,
        zombie: ZombieState,
        damage: int,
        owner_id: str,
        *,
        source_pos: Vec2 | None = None,
        reveal_owner: bool = True,
    ) -> None:
        if zombie.armor > 0:
            blocked = min(zombie.armor, math.ceil(damage * 0.55))
            zombie.armor -= blocked
            damage -= blocked // 2

        zombie.health -= max(1, damage)

        if zombie.health <= 0:
            self._kill_zombie(zombie, owner_id)
            return

        self.alert_zombie_from_damage(
            zombie,
            owner_id,
            source_pos=source_pos,
            reveal_owner=reveal_owner,
        )

    def player_armor_mitigation(self, player: PlayerState) -> float:
        best = 0.0

        for item in player.equipment.values():
            spec = ITEMS.get(item.key) if item else None

            if not item or not spec or not spec.armor_key or item.durability <= 0:
                continue

            armor = ARMORS.get(spec.armor_key, ARMORS["none"])
            rarity = rarity_spec(item.rarity)
            best = max(best, armor.mitigation * rarity.armor_mitigation_multiplier)

        return min(0.88, best)

    def alert_zombie_from_damage(
        self,
        zombie: ZombieState,
        owner_id: str,
        *,
        source_pos: Vec2 | None = None,
        reveal_owner: bool = True,
    ) -> None:
        owner = self._players.get(owner_id) if reveal_owner else None

        if owner and owner.alive:
            alert_pos = source_pos.copy() if source_pos else owner.pos.copy()

            if owner.floor == zombie.floor:
                zombie.mode = "chase"
                zombie.target_player_id = owner.id
            else:
                zombie.mode = "search"
                zombie.target_player_id = None

        elif source_pos:
            alert_pos = source_pos.copy()
            zombie.mode = "investigate"
            zombie.target_player_id = None
        else:
            return

        alert_pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)

        zombie.last_known_pos = alert_pos
        zombie.waypoint = None
        zombie.search_look_timer = 0.0
        zombie.idle_timer = 0.0
        zombie.search_timer = SEARCH_DURATION
        zombie.alertness = 1.0
        zombie.facing = zombie.pos.angle_to(alert_pos)

        self._zombie_ai_generation[zombie.id] = self._zombie_ai_generation.get(zombie.id, 0) + 1
        self._zombie_ai_pending.pop(zombie.id, None)
        self._zombie_ai_next_at[zombie.id] = self._get_time()

    def _kill_zombie(self, zombie: ZombieState, owner_id: str) -> None:
        self._zombies.pop(zombie.id, None)

        player = self._players.get(owner_id)

        if player:
            player.score += 1
            player.kills_by_kind[zombie.kind] = player.kills_by_kind.get(zombie.kind, 0) + 1

        if self._rng.random() < 0.45:
            self._drop_from_zombie(zombie.pos)

        self._zombie_ai_generation.pop(zombie.id, None)
        self._zombie_ai_pending.pop(zombie.id, None)
        self._zombie_ai_next_at.pop(zombie.id, None)