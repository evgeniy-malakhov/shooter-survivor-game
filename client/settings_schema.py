from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SettingsTab:
    key: str
    locale_key: str


SETTINGS_TABS: tuple[SettingsTab, ...] = (
    SettingsTab("general", "settings.tab.general"),
    SettingsTab("video", "settings.tab.video"),
    SettingsTab("audio", "settings.tab.audio"),
    SettingsTab("gameplay", "settings.tab.gameplay"),
)


def tab_toggle_keys(tab_key: str) -> list[str]:
    if tab_key == "video":
        return [
            "fullscreen",
            "bot_vision",
            "bot_vision_range",
            "ai_reactions",
            "health_bars",
            "noise_radius",
            "show_zombie_count",
        ]
    return []


def tab_has_camera_distance(tab_key: str) -> bool:
    return tab_key == "video"


def tab_has_language(tab_key: str) -> bool:
    return tab_key == "general"


def tab_has_audio_sliders(tab_key: str) -> bool:
    return tab_key == "audio"


def tab_is_stub(tab_key: str) -> bool:
    return tab_key in {"gameplay"}
