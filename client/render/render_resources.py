from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pygame

from shared.models import LootState


@dataclass(slots=True)
class RenderFonts:
    normal: pygame.font.Font
    small: pygame.font.Font
    big: pygame.font.Font
    mid: pygame.font.Font
    label: pygame.font.Font
    hud_title: pygame.font.Font
    hud_value: pygame.font.Font
    emphasis: pygame.font.Font


@dataclass(slots=True)
class RenderText:
    tr: Callable[..., str]
    item_title: Callable[[str], str]
    weapon_title: Callable[[str], str]
    rarity_title: Callable[[str], str]
    loot_label: Callable[[LootState], str]
    floor_label: Callable[[int], str]

