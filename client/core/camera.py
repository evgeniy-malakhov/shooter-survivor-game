from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from shared.models import PlayerState, RectState, Vec2


@dataclass(slots=True)
class CameraController:
    viewport_size: tuple[int, int]
    world_size: tuple[float, float]
    distance: float = 0.92
    zoom: float = 0.92

    def update_zoom(self, dt: float, player: PlayerState | None) -> float:
        sprint_target = self.distance * 0.9
        target = sprint_target if player and player.alive and player.sprinting else self.distance
        target = max(0.72, min(1.12, target))
        speed = 3.1 if target < self.zoom else 4.8
        blend = 1.0 - math.exp(-speed * max(0.0, dt))
        self.zoom += (target - self.zoom) * blend
        if abs(self.zoom - target) < 0.002:
            self.zoom = target
        return self.zoom

    def camera_for_player(self, player: PlayerState | None) -> Vec2:
        if not player:
            return Vec2(0, 0)
        viewport_w = self.viewport_size[0] / max(0.1, self.zoom)
        viewport_h = self.viewport_size[1] / max(0.1, self.zoom)
        world_w, world_h = self.world_size
        return Vec2(
            max(0.0, min(max(0.0, world_w - viewport_w), player.pos.x - viewport_w * 0.5)),
            max(0.0, min(max(0.0, world_h - viewport_h), player.pos.y - viewport_h * 0.5)),
        )

    def screen_to_world(self, screen_pos: tuple[int, int], camera: Vec2) -> Vec2:
        zoom = max(0.1, self.zoom)
        return Vec2(screen_pos[0] / zoom + camera.x, screen_pos[1] / zoom + camera.y)

    def world_to_screen(self, pos: Vec2, camera: Vec2) -> tuple[int, int]:
        zoom = max(0.1, self.zoom)
        return int((pos.x - camera.x) * zoom), int((pos.y - camera.y) * zoom)

    def world_to_screen_xy(self, x: float, y: float, camera: Vec2) -> tuple[int, int]:
        zoom = max(0.1, self.zoom)
        return int((x - camera.x) * zoom), int((y - camera.y) * zoom)

    def world_rect_to_screen(self, rect: RectState, camera: Vec2) -> pygame.Rect:
        zoom = max(0.1, self.zoom)
        return pygame.Rect(
            int((rect.x - camera.x) * zoom),
            int((rect.y - camera.y) * zoom),
            max(1, int(rect.w * zoom)),
            max(1, int(rect.h * zoom)),
        )

    def world_rect_to_screen_tuple(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        camera: Vec2,
    ) -> tuple[int, int, int, int]:
        zoom = max(0.1, self.zoom)
        return (
            int((x - camera.x) * zoom),
            int((y - camera.y) * zoom),
            max(1, int(w * zoom)),
            max(1, int(h * zoom)),
        )

    def world_size_to_screen(self, value: float, minimum: int = 1) -> int:
        return max(minimum, int(value * max(0.1, self.zoom)))

    def visible_world_rect(self, camera: Vec2, margin: float = 0.0) -> pygame.Rect:
        zoom = max(0.1, self.zoom)
        x = int(camera.x - margin)
        y = int(camera.y - margin)
        w = int(self.viewport_size[0] / zoom + margin * 2)
        h = int(self.viewport_size[1] / zoom + margin * 2)
        return pygame.Rect(x, y, max(1, w), max(1, h))
