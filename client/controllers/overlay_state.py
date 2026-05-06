from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class GameplayOverlayState:
    inventory_open: bool = False
    backpack_open: bool = False
    settings_open: bool = False
    craft_open: bool = False
    weapon_custom_open: bool = False
    minimap_big: bool = False

    drag_source: dict[str, object] | None = None
    craft_scroll: int = 0
    weapon_modules_scroll: int = 0
    scoreboard_scroll: int = 0
    custom_weapon_slot: str = "1"

    def any_modal_open(self) -> bool:
        return (
            self.backpack_open
            or self.settings_open
            or self.craft_open
            or self.weapon_custom_open
        )

    def close_gameplay_overlays(self) -> None:
        self.inventory_open = False
        self.backpack_open = False
        self.settings_open = False
        self.craft_open = False
        self.weapon_custom_open = False
        self.drag_source = None

