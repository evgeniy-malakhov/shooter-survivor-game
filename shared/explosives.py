from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "explosives.json"


@dataclass(frozen=True, slots=True)
class GrenadeSpec:
    key: str
    title: str
    timer: float
    contact: bool
    throw_distance: float
    blast_radius: float
    zombie_damage: int
    zombie_damage_bonus: int
    player_damage: int
    player_damage_bonus: int
    soldier_damage: int
    soldier_damage_bonus: int


@dataclass(frozen=True, slots=True)
class MineSpec:
    key: str
    title: str
    trigger_radius: float
    blast_radius: float
    zombie_damage: int
    zombie_damage_bonus: int
    player_damage: int
    player_damage_bonus: int
    soldier_damage: int
    soldier_damage_bonus: int


DEFAULT_GRENADE = GrenadeSpec(
    key="grenade",
    title="Fragmentation Grenade",
    timer=2.0,
    contact=False,
    throw_distance=420.0,
    blast_radius=220.0,
    zombie_damage=115,
    zombie_damage_bonus=28,
    player_damage=42,
    player_damage_bonus=8,
    soldier_damage=42,
    soldier_damage_bonus=8,
)

DEFAULT_MINE = MineSpec(
    key="mine_standard",
    title="Field Mine",
    trigger_radius=104.0,
    blast_radius=230.0,
    zombie_damage=125,
    zombie_damage_bonus=32,
    player_damage=48,
    player_damage_bonus=12,
    soldier_damage=48,
    soldier_damage_bonus=12,
)


def _load() -> tuple[dict[str, GrenadeSpec], dict[str, MineSpec]]:
    if not CONFIG_PATH.exists():
        return {DEFAULT_GRENADE.key: DEFAULT_GRENADE}, {DEFAULT_MINE.key: DEFAULT_MINE}
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    grenades = {
        key: GrenadeSpec(
            key=key,
            title=str(raw.get("title", key)),
            timer=max(0.05, float(raw.get("timer", DEFAULT_GRENADE.timer))),
            contact=bool(raw.get("contact", False)),
            throw_distance=max(80.0, float(raw.get("throw_distance", DEFAULT_GRENADE.throw_distance))),
            blast_radius=max(20.0, float(raw.get("blast_radius", DEFAULT_GRENADE.blast_radius))),
            zombie_damage=max(1, int(raw.get("zombie_damage", DEFAULT_GRENADE.zombie_damage))),
            zombie_damage_bonus=max(0, int(raw.get("zombie_damage_bonus", DEFAULT_GRENADE.zombie_damage_bonus))),
            player_damage=max(1, int(raw.get("player_damage", DEFAULT_GRENADE.player_damage))),
            player_damage_bonus=max(0, int(raw.get("player_damage_bonus", DEFAULT_GRENADE.player_damage_bonus))),
            soldier_damage=max(1, int(raw.get("soldier_damage", DEFAULT_GRENADE.soldier_damage))),
            soldier_damage_bonus=max(0, int(raw.get('soldier_damage_bonus', DEFAULT_GRENADE.soldier_damage_bonus)))
        )
        for key, raw in dict(data.get("grenades", {})).items()
    }
    mines = {
        key: MineSpec(
            key=key,
            title=str(raw.get("title", key)),
            trigger_radius=max(24.0, float(raw.get("trigger_radius", DEFAULT_MINE.trigger_radius))),
            blast_radius=max(40.0, float(raw.get("blast_radius", DEFAULT_MINE.blast_radius))),
            zombie_damage=max(1, int(raw.get("zombie_damage", DEFAULT_MINE.zombie_damage))),
            zombie_damage_bonus=max(0, int(raw.get("zombie_damage_bonus", DEFAULT_MINE.zombie_damage_bonus))),
            player_damage=max(1, int(raw.get("player_damage", DEFAULT_MINE.player_damage))),
            player_damage_bonus=max(0, int(raw.get("player_damage_bonus", DEFAULT_MINE.player_damage_bonus))),
            soldier_damage=max(1, int(raw.get("soldier_damage", DEFAULT_MINE.soldier_damage))),
            soldier_damage_bonus=max(0, int(raw.get('soldier_damage_bonus', DEFAULT_MINE.soldier_damage_bonus)))
        )
        for key, raw in dict(data.get("mines", {})).items()
    }
    grenades.setdefault(DEFAULT_GRENADE.key, DEFAULT_GRENADE)
    mines.setdefault(DEFAULT_MINE.key, DEFAULT_MINE)
    return grenades, mines


GRENADE_SPECS, MINE_SPECS = _load()
