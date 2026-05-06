from __future__ import annotations

import time

from client.render.render_context import RenderContext
from client.render.ui.crafting_renderer import CraftingRenderer
from client.render.ui.inventory_renderer import InventoryRenderer
from client.render.ui.settings_overlay_renderer import SettingsOverlayRenderer
from client.render.ui.weapon_custom_renderer import WeaponCustomRenderer


class OverlayRouter:
    def __init__(
        self,
        inventory: InventoryRenderer,
        crafting: CraftingRenderer,
        settings: SettingsOverlayRenderer,
        weapon_custom: WeaponCustomRenderer,
    ) -> None:
        self.inventory = inventory
        self.crafting = crafting
        self.settings = settings
        self.weapon_custom = weapon_custom

    def render(self, ctx: RenderContext) -> None:
        started = time.perf_counter()
        overlay = ctx.overlay
        if overlay:
            if overlay.settings_open:
                self.settings.render(ctx)
            elif overlay.weapon_custom_open:
                self.weapon_custom.render(ctx)
            elif overlay.backpack_open or overlay.inventory_open:
                self.inventory.render(ctx)
            elif overlay.craft_open:
                self.crafting.render(ctx)
        if ctx.perf:
            ctx.perf.overlay_ms = (time.perf_counter() - started) * 1000.0
