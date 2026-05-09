from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from shared.factions import FACTION_MILITARY
from shared.models import Vec2


class SquadMode(str, Enum):
    PATROL = "patrol"
    INVESTIGATE_SOUND = "investigate_sound"
    ENGAGE_TARGET = "engage_target"
    FALLBACK = "fallback"
    REGROUP = "regroup"
    CALL_REINFORCEMENT = "call_reinforcement"
    HOLD_POSITION = "hold_position"
    EVACUATE_WOUNDED = "evacuate_wounded"


class SquadRole(str, Enum):
    LEADER = "leader"
    RIFLEMAN = "rifleman"
    MEDIC = "medic"
    GRENADIER = "grenadier"
    HEAVY = "heavy"
    SCOUT = "scout"


@dataclass(slots=True)
class SquadIntent:
    squad_id: str
    mode: SquadMode
    target_pos: Vec2 | None = None
    target_actor_id: str | None = None
    danger_score: float = 0.0
    expires_at: float = 0.0
    issued_at: float = 0.0
    commands_by_role: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "squad_id": self.squad_id,
            "mode": self.mode.value,
            "target_pos": self.target_pos.to_dict() if self.target_pos else None,
            "target_actor_id": self.target_actor_id,
            "danger_score": round(self.danger_score, 3),
            "expires_at": round(self.expires_at, 3),
            "issued_at": round(self.issued_at, 3),
            "commands_by_role": dict(self.commands_by_role),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SquadIntent | None":
        if not data:
            return None
        raw_mode = str(data.get("mode", SquadMode.PATROL.value))
        try:
            mode = SquadMode(raw_mode)
        except ValueError:
            mode = SquadMode.PATROL
        raw_pos = data.get("target_pos")
        target_pos = Vec2.from_dict(raw_pos) if isinstance(raw_pos, dict) else None
        return cls(
            squad_id=str(data.get("squad_id", "")),
            mode=mode,
            target_pos=target_pos,
            target_actor_id=str(data["target_actor_id"]) if data.get("target_actor_id") else None,
            danger_score=float(data.get("danger_score", 0.0)),
            expires_at=float(data.get("expires_at", 0.0)),
            issued_at=float(data.get("issued_at", 0.0)),
            commands_by_role={
                str(role): str(command)
                for role, command in (data.get("commands_by_role") or {}).items()
            } if isinstance(data.get("commands_by_role"), dict) else {},
        )


@dataclass(slots=True)
class SquadState:
    id: str
    faction: str = FACTION_MILITARY
    leader_id: str | None = None
    member_ids: set[str] = field(default_factory=set)
    role_by_member: dict[str, str] = field(default_factory=dict)
    intent: SquadIntent | None = None
    shared_memory: list[dict[str, Any]] = field(default_factory=list)
    morale: float = 1.0
    suppression: float = 0.0
    formation: str = "wedge"
    leader_lost_until: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "faction": self.faction,
            "leader_id": self.leader_id,
            "member_ids": sorted(self.member_ids),
            "role_by_member": dict(self.role_by_member),
            "intent": self.intent.to_dict() if self.intent else None,
            "shared_memory": [dict(item) for item in self.shared_memory],
            "morale": round(self.morale, 3),
            "suppression": round(self.suppression, 3),
            "formation": self.formation,
            "leader_lost_until": round(self.leader_lost_until, 3),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "SquadState":
        return cls(
            id=str(data.get("id", "")),
            faction=str(data.get("faction", FACTION_MILITARY)),
            leader_id=str(data["leader_id"]) if data.get("leader_id") else None,
            member_ids={str(member_id) for member_id in data.get("member_ids", [])},
            role_by_member={str(member_id): str(role) for member_id, role in data.get("role_by_member", {}).items()},
            intent=SquadIntent.from_dict(data.get("intent") if isinstance(data.get("intent"), dict) else None),
            shared_memory=[dict(item) for item in data.get("shared_memory", []) if isinstance(item, dict)],
            morale=float(data.get("morale", 1.0)),
            suppression=float(data.get("suppression", 0.0)),
            formation=str(data.get("formation", "wedge")),
            leader_lost_until=float(data.get("leader_lost_until", 0.0)),
        )


def role_for_soldier_kind(kind: str, *, leader: bool = False) -> SquadRole:
    if leader:
        return SquadRole.LEADER
    if kind == "medic":
        return SquadRole.MEDIC
    if kind == "heavy_grenadier":
        return SquadRole.GRENADIER
    if kind == "heavy":
        return SquadRole.HEAVY
    if kind == "scout":
        return SquadRole.SCOUT
    return SquadRole.RIFLEMAN
