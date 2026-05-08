from __future__ import annotations

import pygame

from client.core.camera import CameraController
from shared.models import Vec2


def visible_world_rect(camera: CameraController, position: Vec2, margin: float = 320.0) -> pygame.Rect:
    return camera.visible_world_rect(position, margin=margin)


