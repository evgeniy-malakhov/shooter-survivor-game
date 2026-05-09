from __future__ import annotations

from shared.ai.context import ActorTarget
from shared.ai.memory import (
    memory_pos,
    merge_threat_memory,
    most_relevant_threat,
    prune_memory,
    remember_seen_enemy,
)
from shared.ai.squads import SquadIntent, SquadMode, SquadRole, SquadState, role_for_soldier_kind
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
        if not squad.leader_id or squad.leader_id not in self._state.soldiers:
            if squad.leader_id:
                squad.leader_lost_until = max(squad.leader_lost_until, self._state.time + 8.0)
            squad.leader_id = soldier.id
        squad.role_by_member[soldier.id] = role_for_soldier_kind(soldier.kind, leader=squad.leader_id == soldier.id).value

    def rebuild(self) -> None:
        for squad in self._state.squads.values():
            squad.member_ids.clear()
        for soldier in self._state.soldiers.values():
            if soldier.alive:
                self.ensure_member(soldier)
        for squad in self._state.squads.values():
            self._refresh_squad_state(squad)

    def intent_for(self, soldier: SoldierState) -> SquadIntent | None:
        if not soldier.squad_id:
            return None
        squad = self._state.squads.get(soldier.squad_id)
        if not squad or not squad.intent:
            return None
        if squad.intent.expires_at and squad.intent.expires_at <= self._state.time:
            return None
        return squad.intent

    def role_for(self, soldier: SoldierState) -> str:
        if not soldier.squad_id:
            return role_for_soldier_kind(soldier.kind).value
        squad = self._state.squads.get(soldier.squad_id)
        if not squad:
            return role_for_soldier_kind(soldier.kind).value
        return squad.role_by_member.get(
            soldier.id,
            role_for_soldier_kind(soldier.kind, leader=squad.leader_id == soldier.id).value,
        )

    def memory_for(self, soldier: SoldierState) -> tuple[dict[str, object], ...]:
        if not soldier.squad_id:
            return ()
        squad = self._state.squads.get(soldier.squad_id)
        if not squad:
            return ()
        return tuple(dict(item) for item in squad.shared_memory)

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

    def _refresh_squad_state(self, squad: SquadState) -> None:
        members = self._members(squad)
        if not members:
            squad.intent = None
            squad.role_by_member.clear()
            squad.shared_memory.clear()
            return

        self._ensure_leader(squad, members)
        self._refresh_roles(squad, members)
        self._refresh_shared_memory(squad, members)
        self._refresh_morale(squad, members)
        squad.intent = self._choose_intent(squad, members)

    def _members(self, squad: SquadState) -> list[SoldierState]:
        members: list[SoldierState] = []
        for member_id in squad.member_ids:
            soldier = self._state.soldiers.get(member_id)
            if soldier and soldier.alive:
                members.append(soldier)
        return members

    def _ensure_leader(self, squad: SquadState, members: list[SoldierState]) -> None:
        current = next((member for member in members if member.id == squad.leader_id), None)
        if current and (current.kind != "medic" or all(member.kind == "medic" for member in members)):
            return
        priority = {"rifleman": 0, "heavy": 1, "heavy_grenadier": 2, "scout": 3, "medic": 4}
        leader = min(members, key=lambda soldier: priority.get(soldier.kind, 5))
        if squad.leader_id and squad.leader_id != leader.id:
            squad.leader_lost_until = max(squad.leader_lost_until, self._state.time + 4.0)
        squad.leader_id = leader.id

    def _refresh_roles(self, squad: SquadState, members: list[SoldierState]) -> None:
        live_ids = {member.id for member in members}
        squad.role_by_member = {
            member.id: role_for_soldier_kind(member.kind, leader=member.id == squad.leader_id).value
            for member in members
        }
        for member_id in list(squad.role_by_member):
            if member_id not in live_ids:
                squad.role_by_member.pop(member_id, None)

    def _refresh_shared_memory(self, squad: SquadState, members: list[SoldierState]) -> None:
        prune_memory(squad.shared_memory, now=self._state.time)
        for soldier in members:
            prune_memory(soldier.ai_memory, now=self._state.time)
            merge_threat_memory(squad.shared_memory, soldier.ai_memory, now=self._state.time, max_records=16)
            if soldier.last_known_pos and soldier.target_id:
                remember_seen_enemy(
                    squad.shared_memory,
                    actor_id=soldier.target_id,
                    actor_kind=soldier.target_kind or "unknown",
                    pos=soldier.last_known_pos,
                    floor=soldier.floor,
                    now=self._state.time,
                    danger=0.85 + soldier.alertness * 0.25,
                )

    def _refresh_morale(self, squad: SquadState, members: list[SoldierState]) -> None:
        medic_alive = any(member.kind == "medic" for member in members)
        leader_alive = bool(squad.leader_id and any(member.id == squad.leader_id for member in members))
        leader_recently_lost = squad.leader_lost_until > self._state.time
        wounded = 0
        for member in members:
            spec = SOLDIERS.get(member.kind)
            if spec and member.health / max(1, spec.health) < 0.45:
                wounded += 1

        recent_danger = 0.0
        for item in squad.shared_memory:
            age = max(0.0, self._state.time - float(item.get("time", self._state.time)))
            if age <= 6.0:
                recent_danger = max(recent_danger, float(item.get("danger", 0.0)))

        squad.suppression = min(1.0, recent_danger * 0.55 + wounded * 0.08)
        squad.morale = max(
            0.0,
            min(
                1.0,
                0.52
                + min(0.2, len(members) * 0.04)
                + (0.12 if medic_alive else 0.0)
                + (0.14 if leader_alive else -0.18)
                - (0.16 if leader_recently_lost else 0.0)
                - wounded * 0.07
                - squad.suppression * 0.32,
            ),
        )

    def _choose_intent(self, squad: SquadState, members: list[SoldierState]) -> SquadIntent:
        now = self._state.time
        decisions: list[tuple[float, SquadIntent]] = []
        anchor = self._leader_or_first(squad, members)

        wounded = self._most_wounded_member(members)
        if wounded:
            wounded_soldier, ratio = wounded
            decisions.append(
                (
                    235.0 + max(0.0, 0.45 - ratio) * 260.0,
                    SquadIntent(
                        squad_id=squad.id,
                        mode=SquadMode.EVACUATE_WOUNDED,
                        target_pos=wounded_soldier.pos.copy(),
                        target_actor_id=wounded_soldier.id,
                        danger_score=1.0 - ratio,
                        issued_at=now,
                        expires_at=now + 3.0,
                        commands_by_role=self._commands_for_mode(SquadMode.EVACUATE_WOUNDED),
                    ),
                )
            )

        if squad.morale < 0.28:
            decisions.append(
                (
                    220.0 + (0.28 - squad.morale) * 260.0,
                    SquadIntent(
                        squad_id=squad.id,
                        mode=SquadMode.FALLBACK,
                        target_pos=anchor.guard_point.copy() if anchor.guard_point else anchor.pos.copy(),
                        danger_score=1.0 - squad.morale,
                        issued_at=now,
                        expires_at=now + 2.5,
                        commands_by_role=self._commands_for_mode(SquadMode.FALLBACK),
                    ),
                )
            )
        elif squad.morale < 0.45:
            decisions.append(
                (
                    165.0 + (0.45 - squad.morale) * 180.0,
                    SquadIntent(
                        squad_id=squad.id,
                        mode=SquadMode.REGROUP,
                        target_pos=anchor.pos.copy(),
                        danger_score=squad.suppression,
                        issued_at=now,
                        expires_at=now + 2.0,
                        commands_by_role=self._commands_for_mode(SquadMode.REGROUP),
                    ),
                )
            )

        target_memory = most_relevant_threat(
            squad.shared_memory,
            now=now,
            floor=anchor.floor,
            kinds={"last_seen_enemy", "last_damage_source"},
        )
        target_pos = memory_pos(target_memory) if target_memory else None
        if target_memory and target_pos:
            danger = float(target_memory.get("danger", 0.0))
            decisions.append(
                (
                    190.0 + danger * 95.0,
                    SquadIntent(
                        squad_id=squad.id,
                        mode=SquadMode.ENGAGE_TARGET,
                        target_pos=target_pos,
                        target_actor_id=str(target_memory["actor_id"]) if target_memory.get("actor_id") else None,
                        danger_score=danger,
                        issued_at=now,
                        expires_at=now + 4.0,
                        commands_by_role=self._commands_for_mode(SquadMode.ENGAGE_TARGET),
                    ),
                )
            )

        sound_memory = most_relevant_threat(
            squad.shared_memory,
            now=now,
            floor=anchor.floor,
            kinds={"last_heard_sound", "sound"},
        )
        sound_pos = memory_pos(sound_memory) if sound_memory else None
        if sound_memory and sound_pos:
            danger = float(sound_memory.get("danger", 0.0))
            decisions.append(
                (
                    130.0 + danger * 80.0,
                    SquadIntent(
                        squad_id=squad.id,
                        mode=SquadMode.INVESTIGATE_SOUND,
                        target_pos=sound_pos,
                        target_actor_id=str(sound_memory["source_actor_id"]) if sound_memory.get("source_actor_id") else None,
                        danger_score=danger,
                        issued_at=now,
                        expires_at=now + 5.0,
                        commands_by_role=self._commands_for_mode(SquadMode.INVESTIGATE_SOUND),
                    ),
                )
            )

        decisions.append(
            (
                35.0,
                SquadIntent(
                    squad_id=squad.id,
                    mode=SquadMode.PATROL,
                    target_pos=anchor.guard_point.copy() if anchor.guard_point else None,
                    danger_score=0.0,
                    issued_at=now,
                    expires_at=now + 5.0,
                    commands_by_role=self._commands_for_mode(SquadMode.PATROL),
                ),
            )
        )

        return max(decisions, key=lambda item: item[0])[1]

    def _commands_for_mode(self, mode: SquadMode) -> dict[str, str]:
        if mode == SquadMode.ENGAGE_TARGET:
            return {
                SquadRole.LEADER.value: "engage",
                SquadRole.RIFLEMAN.value: "suppress",
                SquadRole.MEDIC.value: "stay_back",
                SquadRole.GRENADIER.value: "flush",
                SquadRole.HEAVY.value: "advance",
                SquadRole.SCOUT.value: "flank",
            }
        if mode == SquadMode.EVACUATE_WOUNDED:
            return {
                SquadRole.LEADER.value: "cover",
                SquadRole.RIFLEMAN.value: "cover",
                SquadRole.MEDIC.value: "heal",
                SquadRole.GRENADIER.value: "deny_area",
                SquadRole.HEAVY.value: "screen",
                SquadRole.SCOUT.value: "watch",
            }
        if mode in {SquadMode.FALLBACK, SquadMode.REGROUP}:
            return {
                SquadRole.LEADER.value: "regroup",
                SquadRole.RIFLEMAN.value: "fallback",
                SquadRole.MEDIC.value: "fallback",
                SquadRole.GRENADIER.value: "fallback",
                SquadRole.HEAVY.value: "cover_retreat",
                SquadRole.SCOUT.value: "watch",
            }
        if mode == SquadMode.INVESTIGATE_SOUND:
            return {
                SquadRole.LEADER.value: "investigate",
                SquadRole.RIFLEMAN.value: "advance_carefully",
                SquadRole.MEDIC.value: "trail",
                SquadRole.GRENADIER.value: "hold_grenade",
                SquadRole.HEAVY.value: "lead_entry",
                SquadRole.SCOUT.value: "scan",
            }
        return {
            SquadRole.LEADER.value: "patrol",
            SquadRole.RIFLEMAN.value: "patrol",
            SquadRole.MEDIC.value: "trail",
            SquadRole.GRENADIER.value: "patrol",
            SquadRole.HEAVY.value: "patrol",
            SquadRole.SCOUT.value: "scout",
        }

    def _leader_or_first(self, squad: SquadState, members: list[SoldierState]) -> SoldierState:
        if squad.leader_id:
            leader = self._state.soldiers.get(squad.leader_id)
            if leader and leader.alive:
                return leader
        return members[0]

    def _most_wounded_member(self, members: list[SoldierState]) -> tuple[SoldierState, float] | None:
        best: tuple[SoldierState, float] | None = None
        for soldier in members:
            spec = SOLDIERS.get(soldier.kind)
            if not spec:
                continue
            ratio = soldier.health / max(1, spec.health)
            if ratio >= 0.55:
                continue
            if best is None or ratio < best[1]:
                best = (soldier, ratio)
        return best
