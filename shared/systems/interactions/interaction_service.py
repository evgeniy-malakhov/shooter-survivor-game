from __future__ import annotations

from shared.constants import INTERACT_RADIUS
from shared.level import nearest_stairs
from shared.models import PlayerState
from shared.world.world_state import WorldState


class InteractionService:
    def __init__(
        self,
        *,
        state: WorldState,
        buildings,
        geometry,
    ) -> None:
        self._state = state
        self._buildings = buildings
        self._geometry = geometry

    def interact(self, player: PlayerState) -> bool:
        door = self._buildings.nearest_door(
            player.pos,
            INTERACT_RADIUS,
            player.floor,
        )

        if door:
            door.open = not door.open
            self._geometry.mark_dirty()
            return True

        building = nearest_stairs(
            self._state.buildings,
            player.pos,
            INTERACT_RADIUS,
        )

        if building and building.bounds.contains(player.pos):
            player.floor += 1

            if player.floor > building.max_floor:
                player.floor = building.min_floor

            player.inside_building = building.id
            return True

        return False