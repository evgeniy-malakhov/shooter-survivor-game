from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from shared.factions import FACTION_ASSAULT_ALPHA, FACTION_ASSAULT_BRAVO, FACTION_SURVIVORS


class GameModeId(str, Enum):
    SURVIVAL = "survival"
    ASSAULT = "assault"


@dataclass(frozen=True, slots=True)
class GameModeSpec:
    id: str
    title_key: str
    description_key: str
    player_factions: tuple[str, ...]
    default_player_faction: str
    uses_zombies: bool
    uses_soldiers: bool
    supports_bot_density: bool
    supports_difficulty: bool
    respawn_soldiers: bool = False
    soldier_respawn_cooldown: float = 5.0


GAME_MODES: dict[str, GameModeSpec] = {
    GameModeId.SURVIVAL.value: GameModeSpec(
        id=GameModeId.SURVIVAL.value,
        title_key="game_mode.survival.title",
        description_key="game_mode.survival.description",
        player_factions=(FACTION_SURVIVORS,),
        default_player_faction=FACTION_SURVIVORS,
        uses_zombies=True,
        uses_soldiers=True,
        supports_bot_density=True,
        supports_difficulty=True,
    ),
    GameModeId.ASSAULT.value: GameModeSpec(
        id=GameModeId.ASSAULT.value,
        title_key="game_mode.assault.title",
        description_key="game_mode.assault.description",
        player_factions=(FACTION_ASSAULT_ALPHA, FACTION_ASSAULT_BRAVO),
        default_player_faction=FACTION_ASSAULT_ALPHA,
        uses_zombies=False,
        uses_soldiers=True,
        supports_bot_density=True,
        supports_difficulty=True,
        respawn_soldiers=True,
        soldier_respawn_cooldown=5.0,
    ),
}

GAME_MODE_ORDER: tuple[str, ...] = (GameModeId.SURVIVAL.value, GameModeId.ASSAULT.value)


def get_game_mode(mode_id: str | None) -> GameModeSpec:
    return GAME_MODES.get(str(mode_id or ""), GAME_MODES[GameModeId.SURVIVAL.value])


def list_game_modes() -> tuple[GameModeSpec, ...]:
    return tuple(GAME_MODES[key] for key in GAME_MODE_ORDER)


def game_mode_kind(mode_id: str | None) -> Literal["survival", "assault"]:
    spec = get_game_mode(mode_id)
    return "assault" if spec.id == GameModeId.ASSAULT.value else "survival"
