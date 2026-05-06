from __future__ import annotations

from dataclasses import dataclass

import pygame


@dataclass(frozen=True, slots=True)
class DisplayConfig:
    virtual_size: tuple[int, int]
    min_window_size: tuple[int, int]
    caption: str


class DisplayManager:
    def __init__(self, config: DisplayConfig) -> None:
        self.config = config
        pygame.display.set_caption(config.caption)
        self.fullscreen = False
        self.windowed_size = config.virtual_size
        self.display = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        self.screen = pygame.Surface(config.virtual_size).convert()
        self.render_rect = pygame.Rect(0, 0, *config.virtual_size)
        self.render_scale = 1.0
        self.update_transform()

    @property
    def virtual_width(self) -> int:
        return self.config.virtual_size[0]

    @property
    def virtual_height(self) -> int:
        return self.config.virtual_size[1]

    def set_display_mode(self, fullscreen: bool) -> None:
        if fullscreen:
            desktop_sizes = pygame.display.get_desktop_sizes() if hasattr(pygame.display, "get_desktop_sizes") else []
            if desktop_sizes:
                size = desktop_sizes[0]
            else:
                info = pygame.display.Info()
                size = (max(1, info.current_w), max(1, info.current_h))
            self.display = pygame.display.set_mode(size, pygame.FULLSCREEN)
        else:
            min_w, min_h = self.config.min_window_size
            width = max(min_w, int(self.windowed_size[0]))
            height = max(min_h, int(self.windowed_size[1]))
            self.windowed_size = (width, height)
            self.display = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)

        self.fullscreen = fullscreen
        self.update_transform()

    def toggle_fullscreen(self) -> None:
        self.set_display_mode(not self.fullscreen)

    def resize_window(self, size: tuple[int, int]) -> None:
        if self.fullscreen:
            return

        min_w, min_h = self.config.min_window_size
        width = max(min_w, int(size[0]))
        height = max(min_h, int(size[1]))
        self.windowed_size = (width, height)
        self.display = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        self.update_transform()

    def update_transform(self) -> None:
        display_w, display_h = self.display.get_size()
        virtual_w, virtual_h = self.config.virtual_size
        scale = min(display_w / virtual_w, display_h / virtual_h)
        self.render_scale = max(0.1, scale)
        render_w = max(1, int(virtual_w * self.render_scale))
        render_h = max(1, int(virtual_h * self.render_scale))
        self.render_rect = pygame.Rect(
            (display_w - render_w) // 2,
            (display_h - render_h) // 2,
            render_w,
            render_h,
        )

    def display_to_screen(self, pos: tuple[int, int]) -> tuple[int, int]:
        x = int((pos[0] - self.render_rect.x) / self.render_scale)
        y = int((pos[1] - self.render_rect.y) / self.render_scale)
        return x, y

    def present(self) -> None:
        self.display.fill((0, 0, 0))
        if self.render_rect.size == self.config.virtual_size:
            self.display.blit(self.screen, self.render_rect)
        else:
            scaled = pygame.transform.smoothscale(self.screen, self.render_rect.size)
            self.display.blit(scaled, self.render_rect)
        pygame.display.flip()

