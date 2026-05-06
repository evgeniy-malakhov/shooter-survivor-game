from __future__ import annotations

from collections.abc import Callable

import pygame

from client.app.app_state import AppState, normalize_app_state
from client.render.render_context import RenderContext
from client.scenes.base import Scene


class SceneManager:
    def __init__(
        self,
        *,
        state_getter: Callable[[], str],
        state_setter: Callable[[str], None],
        on_quit: Callable[[], None],
        on_resize: Callable[[tuple[int, int]], None],
    ) -> None:
        self._state_getter = state_getter
        self._state_setter = state_setter
        self._on_quit = on_quit
        self._on_resize = on_resize
        self._scenes: dict[AppState, Scene] = {}

    @property
    def state(self) -> AppState:
        return normalize_app_state(self._state_getter())

    def register(self, state: AppState, scene: Scene) -> None:
        self._scenes[state] = scene

    def set_state(self, state: AppState | str) -> None:
        self._state_setter(normalize_app_state(state).value)

    def handle_events(self, events: list[pygame.event.Event]) -> None:
        delegated: list[pygame.event.Event] = []

        for event in events:
            if event.type == pygame.QUIT:
                self._on_quit()
                continue

            if event.type == pygame.VIDEORESIZE:
                self._on_resize((int(event.w), int(event.h)))
                continue

            delegated.append(event)

        scene = self.current_scene()
        if scene:
            scene.handle_events(delegated)

    def update(self, dt: float) -> None:
        scene = self.current_scene()
        if scene:
            scene.update(dt)

    def render(self, ctx: RenderContext) -> None:
        scene = self.current_scene()
        if scene:
            scene.render(ctx)

    def current_scene(self) -> Scene | None:
        return self._scenes.get(self.state)

