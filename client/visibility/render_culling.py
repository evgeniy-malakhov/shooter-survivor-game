from __future__ import annotations

import pygame

from shared.models import RectState, Vec2


def point_visible(pos: Vec2, rect: pygame.Rect, margin: float = 0.0) -> bool:
    if margin:
        rect = rect.inflate(int(margin * 2), int(margin * 2))
    return rect.collidepoint(int(pos.x), int(pos.y))


def rect_visible(rect: RectState, view: pygame.Rect, margin: float = 0.0) -> bool:
    query = pygame.Rect(int(rect.x), int(rect.y), max(1, int(rect.w)), max(1, int(rect.h)))
    if margin:
        query = query.inflate(int(margin * 2), int(margin * 2))
    return query.colliderect(view)

