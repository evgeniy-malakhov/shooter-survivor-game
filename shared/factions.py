from __future__ import annotations

from dataclasses import dataclass


FACTION_SURVIVORS = "survivors"
FACTION_MILITARY = "military"
FACTION_ASSAULT_ALPHA = "assault_alpha"
FACTION_ASSAULT_BRAVO = "assault_bravo"
FACTION_INFECTED = "infected"
FACTION_NEUTRAL = "neutral"


@dataclass(frozen=True, slots=True)
class FactionSpec:
    key: str
    title: str
    hostile_to: frozenset[str]


FACTIONS: dict[str, FactionSpec] = {
    FACTION_SURVIVORS: FactionSpec(
        key=FACTION_SURVIVORS,
        title="Survivors",
        hostile_to=frozenset({FACTION_INFECTED}),
    ),
    FACTION_MILITARY: FactionSpec(
        key=FACTION_MILITARY,
        title="Military",
        hostile_to=frozenset({FACTION_INFECTED, FACTION_SURVIVORS}),
    ),
    FACTION_ASSAULT_ALPHA: FactionSpec(
        key=FACTION_ASSAULT_ALPHA,
        title="Assault Alpha",
        hostile_to=frozenset({FACTION_ASSAULT_BRAVO}),
    ),
    FACTION_ASSAULT_BRAVO: FactionSpec(
        key=FACTION_ASSAULT_BRAVO,
        title="Assault Bravo",
        hostile_to=frozenset({FACTION_ASSAULT_ALPHA}),
    ),
    FACTION_INFECTED: FactionSpec(
        key=FACTION_INFECTED,
        title="Infected",
        hostile_to=frozenset({FACTION_SURVIVORS, FACTION_MILITARY}),
    ),
    FACTION_NEUTRAL: FactionSpec(
        key=FACTION_NEUTRAL,
        title="Neutral",
        hostile_to=frozenset(),
    ),
}


def normalize_faction(value: object, fallback: str = FACTION_NEUTRAL) -> str:
    key = str(value or fallback)
    return key if key in FACTIONS else fallback


def hostile(faction: str, other: str) -> bool:
    spec = FACTIONS.get(faction)
    return bool(spec and other in spec.hostile_to)
