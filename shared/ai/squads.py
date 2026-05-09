from __future__ import annotations

from dataclasses import dataclass, field

from shared.factions import FACTION_MILITARY


@dataclass(slots=True)
class SquadState:
    id: str
    faction: str = FACTION_MILITARY
    leader_id: str | None = None
    member_ids: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "faction": self.faction,
            "leader_id": self.leader_id,
            "member_ids": sorted(self.member_ids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "SquadState":
        return cls(
            id=str(data.get("id", "")),
            faction=str(data.get("faction", FACTION_MILITARY)),
            leader_id=str(data["leader_id"]) if data.get("leader_id") else None,
            member_ids={str(member_id) for member_id in data.get("member_ids", [])},
        )
