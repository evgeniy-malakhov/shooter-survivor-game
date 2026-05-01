from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pygame


AudioCommandKind = Literal["master", "music", "effects", "menu_active", "play_action", "stop"]


@dataclass(frozen=True, slots=True)
class AudioCommand:
    kind: AudioCommandKind
    value: float | bool | dict[str, Any] | None = None


class AudioManager:
    """Small threaded audio facade so gameplay/UI never blocks on music IO."""

    def __init__(self, menu_music_path: Path, actions_dir: Path) -> None:
        self.menu_music_path = menu_music_path
        self.actions_dir = actions_dir
        self._commands: queue.Queue[AudioCommand] = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="audio-manager", daemon=True)
        self._closed = threading.Event()
        self._master_volume = 0.8
        self._music_volume = 0.55
        self._effects_volume = 0.8
        self._menu_active = False
        self._thread.start()

    @property
    def master_volume(self) -> float:
        return self._master_volume

    @property
    def music_volume(self) -> float:
        return self._music_volume

    @property
    def effects_volume(self) -> float:
        return self._effects_volume

    def set_master_volume(self, value: float) -> None:
        self._master_volume = _clamp_volume(value)
        self._post(AudioCommand("master", self._master_volume))

    def set_music_volume(self, value: float) -> None:
        self._music_volume = _clamp_volume(value)
        self._post(AudioCommand("music", self._music_volume))

    def set_effects_volume(self, value: float) -> None:
        self._effects_volume = _clamp_volume(value)
        self._post(AudioCommand("effects", self._effects_volume))

    def set_menu_music_active(self, active: bool) -> None:
        if self._menu_active == active:
            return
        self._menu_active = active
        self._post(AudioCommand("menu_active", active))

    def play_action_sound(self, sound_key: str, *, volume: float = 1.0, pan: float = 0.0) -> None:
        if not sound_key:
            return
        self._post(AudioCommand("play_action", {"key": sound_key, "volume": _clamp_volume(volume), "pan": max(-1.0, min(1.0, pan))}))

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        self._post(AudioCommand("stop"))
        self._thread.join(timeout=1.5)

    def _post(self, command: AudioCommand) -> None:
        try:
            self._commands.put_nowait(command)
        except queue.Full:
            pass

    def _run(self) -> None:
        initialized = False
        music_loaded = False
        action_sounds: dict[str, pygame.mixer.Sound] = {}
        master = self._master_volume
        music = self._music_volume
        effects = self._effects_volume
        menu_active = self._menu_active
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            initialized = True
        except pygame.error:
            initialized = False

        def effective_music_volume() -> float:
            return _clamp_volume(master * music)

        def apply_volume() -> None:
            if initialized:
                pygame.mixer.music.set_volume(effective_music_volume())

        def load_action_sounds() -> None:
            if not initialized or not self.actions_dir.exists():
                return
            for path in self.actions_dir.glob("*"):
                if not path.is_file() or path.suffix.lower() not in {".wav", ".ogg", ".mp3"}:
                    continue
                try:
                    action_sounds[path.stem] = pygame.mixer.Sound(str(path))
                except pygame.error:
                    continue

        def play_action(payload: dict[str, Any]) -> None:
            if not initialized:
                return
            sound = action_sounds.get(str(payload.get("key", "")))
            if not sound:
                return
            base_volume = _clamp_volume(float(payload.get("volume", 1.0))) * master * effects
            if base_volume <= 0.0:
                return
            pan = max(-1.0, min(1.0, float(payload.get("pan", 0.0))))
            left = base_volume * (1.0 - max(0.0, pan) * 0.72)
            right = base_volume * (1.0 + min(0.0, pan) * 0.72)
            try:
                channel = sound.play()
                if channel:
                    channel.set_volume(_clamp_volume(left), _clamp_volume(right))
            except pygame.error:
                pass

        def play_menu_music() -> None:
            nonlocal music_loaded
            if not initialized or not self.menu_music_path.exists():
                return
            try:
                if not music_loaded:
                    pygame.mixer.music.load(str(self.menu_music_path))
                    music_loaded = True
                apply_volume()
                if not pygame.mixer.music.get_busy():
                    pygame.mixer.music.play(loops=-1, fade_ms=900)
            except pygame.error:
                music_loaded = False

        def stop_menu_music() -> None:
            if initialized:
                try:
                    pygame.mixer.music.fadeout(700)
                except pygame.error:
                    pass

        load_action_sounds()

        while not self._closed.is_set():
            try:
                command = self._commands.get(timeout=0.25)
            except queue.Empty:
                if menu_active and initialized and not pygame.mixer.music.get_busy():
                    play_menu_music()
                continue
            if command.kind == "stop":
                break
            if command.kind == "master":
                master = _clamp_volume(float(command.value or 0.0))
                apply_volume()
            elif command.kind == "music":
                music = _clamp_volume(float(command.value or 0.0))
                apply_volume()
            elif command.kind == "effects":
                effects = _clamp_volume(float(command.value or 0.0))
            elif command.kind == "menu_active":
                menu_active = bool(command.value)
                if menu_active:
                    play_menu_music()
                else:
                    stop_menu_music()
            elif command.kind == "play_action" and isinstance(command.value, dict):
                play_action(command.value)
        if initialized:
            stop_menu_music()


def _clamp_volume(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
