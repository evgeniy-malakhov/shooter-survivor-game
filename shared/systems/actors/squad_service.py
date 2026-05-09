from __future__ import annotations

from shared.ai.context import ActorTarget
from shared.ai.squads import SquadState
from shared.constants import SOLDIERS
from shared.models import SoldierState
from shared.world.world_state import WorldState


class SquadService:
    def __init__(self, *, state: WorldState) -> None:
        self._state = state

    def ensure_member(self, soldier: SoldierState, squad_id: str | None = None) -> None:
        resolved = squad_id or soldier.squad_id or f"{soldier.faction}:default"
        soldier.squad_id = resolved
        squad = self._state.squads.setdefault(resolved, SquadState(id=resolved, faction=soldier.faction))
        squad.member_ids.add(soldier.id)
        if not squad.leader_id:
            squad.leader_id = soldier.id

    def rebuild(self) -> None:
        for squad in self._state.squads.values():
            squad.member_ids.clear()
        for soldier in self._state.soldiers.values():
            if soldier.alive:
                self.ensure_member(soldier)

    def mates_for(self, soldier: SoldierState, *, radius: float = 900.0) -> tuple[ActorTarget, ...]:
        if not soldier.squad_id:
            return ()
        squad = self._state.squads.get(soldier.squad_id)
        if not squad:
            return ()
        mates: list[ActorTarget] = []
        for member_id in squad.member_ids:
            if member_id == soldier.id:
                continue
            mate = self._state.soldiers.get(member_id)
            if not mate or not mate.alive or mate.floor != soldier.floor:
                continue
            if soldier.pos.distance_to(mate.pos) > radius:
                continue
            spec = SOLDIERS.get(mate.kind)
            if not spec:
                continue
            mates.append(
                ActorTarget(
                    id=mate.id,
                    kind="soldier",
                    pos=mate.pos.copy(),
                    floor=mate.floor,
                    alive=mate.alive,
                    radius=spec.radius,
                    actor_kind=mate.kind,
                    health=mate.health,
                    faction=mate.faction,
                )
            )
        return tuple(mates)
