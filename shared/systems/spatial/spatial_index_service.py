from __future__ import annotations

from collections import defaultdict
from typing import Iterable, TypeVar

from shared.models import LootState, PlayerState, SoldierState, Vec2, ZombieState
from shared.world.world_state import WorldState
from shared.ai.context import SoundEvent


T = TypeVar("T")


class SpatialIndexService:
    def __init__(self, *, cell_size: int = 256) -> None:
        self.cell_size = cell_size

        self._players: dict[tuple[int, int, int], list[PlayerState]] = defaultdict(list)
        self._zombies: dict[tuple[int, int, int], list[ZombieState]] = defaultdict(list)
        self._soldiers: dict[tuple[int, int, int], list[SoldierState]] = defaultdict(list)
        self._loot: dict[tuple[int, int, int], list[LootState]] = defaultdict(list)
        self._sounds: dict[tuple[int, int, int], list[SoundEvent]] = defaultdict(list)

    def rebuild(self, state: WorldState) -> None:
        self._players.clear()
        self._zombies.clear()
        self._soldiers.clear()
        self._loot.clear()
        self._sounds.clear()

        for player in state.players.values():
            if player.alive:
                self._players[self._cell_key(player.pos, player.floor)].append(player)

        for zombie in state.zombies.values():
            if zombie.health > 0:
                self._zombies[self._cell_key(zombie.pos, zombie.floor)].append(zombie)

        for soldier in state.soldiers.values():
            if soldier.alive:
                self._soldiers[self._cell_key(soldier.pos, soldier.floor)].append(soldier)

        for loot in state.loot.values():
            self._loot[self._cell_key(loot.pos, loot.floor)].append(loot)

        for sound in state.sound_events:
            self._sounds[self._cell_key(sound.pos, sound.floor)].append(sound)

    def nearby_players(self, pos: Vec2, radius: float, floor: int) -> list[PlayerState]:
        return list(self._nearby(self._players, pos, radius, floor))

    def nearby_zombies(self, pos: Vec2, radius: float, floor: int) -> list[ZombieState]:
        return list(self._nearby(self._zombies, pos, radius, floor))

    def nearby_soldiers(self, pos: Vec2, radius: float, floor: int) -> list[SoldierState]:
        return list(self._nearby(self._soldiers, pos, radius, floor))

    def nearby_loot(self, pos: Vec2, radius: float, floor: int) -> list[LootState]:
        return list(self._nearby(self._loot, pos, radius, floor))

    def nearby_sounds(self, pos: Vec2, radius: float, floor: int) -> list[SoundEvent]:
        return list(self._nearby(self._sounds, pos, radius, floor))

    def _nearby(
        self,
        bucket: dict[tuple[int, int, int], list[T]],
        pos: Vec2,
        radius: float,
        floor: int,
    ) -> Iterable[T]:
        min_x = int((pos.x - radius) // self.cell_size)
        max_x = int((pos.x + radius) // self.cell_size)
        min_y = int((pos.y - radius) // self.cell_size)
        max_y = int((pos.y + radius) // self.cell_size)

        radius_sq = radius * radius

        for cy in range(min_y, max_y + 1):
            for cx in range(min_x, max_x + 1):
                for obj in bucket.get((floor, cx, cy), ()):
                    obj_pos = getattr(obj, "pos")

                    dx = obj_pos.x - pos.x
                    dy = obj_pos.y - pos.y

                    if dx * dx + dy * dy <= radius_sq:
                        yield obj

    def _cell_key(self, pos: Vec2, floor: int) -> tuple[int, int, int]:
        return (
            floor,
            int(pos.x // self.cell_size),
            int(pos.y // self.cell_size),
        )