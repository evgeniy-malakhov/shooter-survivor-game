from __future__ import annotations

from typing import Any

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.ui.components.button import draw_button
from client.render.world.render_utils import draw_item_icon, draw_rarity_badge, draw_rarity_frame, draw_text, draw_text_fit
from shared.constants import SLOTS
from shared.rarities import rarity_color
from shared.weapon_modules import WEAPON_MODULES, WEAPON_MODULE_SLOTS


class WeaponCustomRenderer:
    def __init__(self, app: Any) -> None:
        self.app = app

    def render(self, ctx: RenderContext) -> None:
        player = ctx.local_player
        if not player or not ctx.fonts or not ctx.text:
            return
        app = self.app
        overlay = pygame.Surface(ctx.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((3, 6, 14, 148))
        ctx.screen.blit(overlay, (0, 0))
        panel = app._weapon_custom_panel_rect()
        pygame.draw.rect(ctx.screen, palette.PANEL, panel, border_radius=10)
        pygame.draw.rect(ctx.screen, (55, 38, 88), panel.inflate(8, 8), 1, border_radius=12)
        pygame.draw.rect(ctx.screen, palette.PURPLE, panel, 2, border_radius=10)
        draw_text_fit(ctx, ctx.text.tr("weaponmods.title"), pygame.Rect(panel.x + 28, panel.y + 18, 420, 44), palette.TEXT, ctx.fonts.mid)
        draw_text_fit(ctx, ctx.text.tr("weaponmods.click_install"), pygame.Rect(panel.x + 32, panel.y + 54, 560, 20), palette.MUTED, ctx.fonts.small)
        close_rect = app._weapon_custom_close_rect()
        draw_button(ctx, close_rect, ctx.text.tr("weaponmods.close"), close_rect.collidepoint(ctx.mouse_pos))

        draw_text(ctx, ctx.text.tr("weaponmods.weapon"), panel.x + 34, panel.y + 76, palette.MUTED, ctx.fonts.small)
        selected_slot = app._custom_weapon_slot(player)
        for index, slot in enumerate(SLOTS):
            rect = app._weapon_custom_slot_rect(index)
            weapon = player.weapons.get(slot)
            selected = slot == selected_slot
            pygame.draw.rect(ctx.screen, palette.PANEL_2 if selected else palette.BG, rect, border_radius=8)
            pygame.draw.rect(ctx.screen, palette.CYAN if selected else (52, 68, 98), rect, 2 if selected else 1, border_radius=8)
            draw_text(ctx, slot, rect.x + 6, rect.y + 5, palette.MUTED, ctx.fonts.small)
            if weapon:
                if selected:
                    draw_rarity_frame(ctx, rect, weapon.rarity)
                draw_item_icon(ctx, weapon.key, pygame.Rect(rect.x + 28, rect.y + 7, 38, 28), aura=False)
                draw_text_fit(ctx, ctx.text.weapon_title(weapon.key).split()[0], pygame.Rect(rect.x + 8, rect.bottom - 18, rect.w - 16, 14), palette.TEXT, ctx.fonts.small, center=True)
            else:
                draw_text_fit(ctx, slot, rect.inflate(-8, -10), palette.MUTED, ctx.fonts.small, center=True)

        weapon = player.weapons.get(selected_slot)
        if not weapon:
            empty = pygame.Rect(panel.x + 34, panel.y + 168, panel.w - 68, 180)
            pygame.draw.rect(ctx.screen, palette.BG, empty, border_radius=10)
            pygame.draw.rect(ctx.screen, (58, 68, 92), empty, 1, border_radius=10)
            draw_text_fit(ctx, ctx.text.tr("weaponmods.empty"), empty.inflate(-40, -40), palette.MUTED, ctx.fonts.normal, center=True)
            return

        self._render_weapon_info(ctx, player, selected_slot, weapon)
        self._render_installed_modules(ctx, selected_slot, weapon)
        self._render_available_modules(ctx, player, weapon)

    def _render_weapon_info(self, ctx: RenderContext, player: Any, slot: str, weapon: Any) -> None:
        app = self.app
        panel = app._weapon_custom_panel_rect()
        mag_size = app._client_weapon_magazine_size(weapon)
        info = pygame.Rect(panel.x + 34, panel.y + 164, 312, 210)
        pygame.draw.rect(ctx.screen, (12, 17, 29), info, border_radius=10)
        pygame.draw.rect(ctx.screen, rarity_color(weapon.rarity), info, 2, border_radius=10)
        weapon_rect = pygame.Rect(info.x + 16, info.y + 34, 94, 88)
        draw_rarity_frame(ctx, weapon_rect, weapon.rarity)
        draw_rarity_badge(ctx, weapon_rect, weapon.rarity, compact=True)
        draw_item_icon(ctx, weapon.key, weapon_rect.inflate(-14, -18))
        draw_text_fit(
            ctx,
            f"{ctx.text.rarity_title(weapon.rarity)} {ctx.text.weapon_title(weapon.key)}",
            pygame.Rect(info.x + 120, info.y + 34, 178, 34),
            rarity_color(weapon.rarity),
            ctx.fonts.normal,
        )
        draw_text_fit(ctx, f"{ctx.text.tr('weaponmods.magazine')}: {mag_size}", pygame.Rect(info.x + 120, info.y + 78, 178, 18), palette.MUTED, ctx.fonts.small)
        utility_title = app.item_title(weapon.modules["utility"]) if weapon.modules.get("utility") else ctx.text.tr("weaponmods.empty_slot")
        magazine_title = app.item_title(weapon.modules["magazine"]) if weapon.modules.get("magazine") else ctx.text.tr("weaponmods.empty_slot")
        draw_text_fit(ctx, f"{ctx.text.tr('weaponmods.slot.utility')}: {utility_title}", pygame.Rect(info.x + 20, info.y + 142, 250, 18), palette.TEXT, ctx.fonts.small)
        draw_text_fit(ctx, f"{ctx.text.tr('weaponmods.slot.magazine')}: {magazine_title}", pygame.Rect(info.x + 20, info.y + 166, 250, 18), palette.TEXT, ctx.fonts.small)

    def _render_installed_modules(self, ctx: RenderContext, weapon_slot: str, weapon: Any) -> None:
        app = self.app
        for module_slot in WEAPON_MODULE_SLOTS:
            rect = app._weapon_module_rect(module_slot)
            module_key = weapon.modules.get(module_slot)
            pygame.draw.rect(ctx.screen, palette.PANEL_2 if module_key else palette.BG, rect, border_radius=10)
            pygame.draw.rect(ctx.screen, palette.GREEN if module_key else (58, 68, 92), rect, 2, border_radius=10)
            draw_text_fit(ctx, ctx.text.tr(f"weaponmods.slot.{module_slot}"), pygame.Rect(rect.x + 14, rect.y + 12, rect.w - 28, 18), palette.MUTED, ctx.fonts.small)
            dragging_this_module = (
                ctx.overlay
                and ctx.overlay.drag_source
                and ctx.overlay.drag_source.get("source") == "weapon_module"
                and ctx.overlay.drag_source.get("slot") == weapon_slot
                and ctx.overlay.drag_source.get("module_slot") == module_slot
            )
            if module_key and not dragging_this_module:
                draw_item_icon(ctx, module_key, pygame.Rect(rect.x + 18, rect.y + 38, 58, 54))
                draw_text_fit(ctx, app.item_title(module_key), pygame.Rect(rect.x + 86, rect.y + 42, rect.w - 100, 20), palette.TEXT, ctx.fonts.normal)
                draw_text_fit(ctx, app._module_effect_text(module_key), pygame.Rect(rect.x + 86, rect.y + 70, rect.w - 100, 18), palette.GREEN, ctx.fonts.small)
                draw_text_fit(ctx, ctx.text.tr("weaponmods.drag_remove"), pygame.Rect(rect.x + 18, rect.bottom - 24, rect.w - 36, 16), palette.MUTED, ctx.fonts.small)
            else:
                draw_text_fit(ctx, ctx.text.tr("weaponmods.empty_slot"), pygame.Rect(rect.x + 18, rect.y + 48, rect.w - 36, 28), palette.MUTED, ctx.fonts.normal, center=True)

        return_rect = app._weapon_module_return_rect()
        return_hot = bool(ctx.overlay and ctx.overlay.drag_source and ctx.overlay.drag_source.get("source") == "weapon_module")
        pygame.draw.rect(ctx.screen, (12, 17, 29), return_rect, border_radius=9)
        pygame.draw.rect(ctx.screen, palette.CYAN if return_hot else (58, 68, 92), return_rect, 2 if return_hot else 1, border_radius=9)
        draw_text_fit(ctx, ctx.text.tr("weaponmods.return_bay"), return_rect.inflate(-24, -12), palette.CYAN if return_hot else palette.MUTED, ctx.fonts.small, center=True)

    def _render_available_modules(self, ctx: RenderContext, player: Any, weapon: Any) -> None:
        app = self.app
        panel = app._weapon_custom_panel_rect()
        draw_text(ctx, ctx.text.tr("weaponmods.available"), panel.x + 34, panel.y + 388, palette.TEXT, ctx.fonts.mid)
        draw_text_fit(ctx, ctx.text.tr("weaponmods.click_install"), pygame.Rect(panel.x + 250, panel.y + 396, 490, 18), palette.MUTED, ctx.fonts.small)
        viewport = app._weapon_module_viewport_rect()
        pygame.draw.rect(ctx.screen, (9, 13, 23), viewport.inflate(10, 10), border_radius=10)
        pygame.draw.rect(ctx.screen, (42, 57, 82), viewport.inflate(10, 10), 1, border_radius=10)
        previous_clip = ctx.screen.get_clip()
        ctx.screen.set_clip(viewport)
        for module_key, indices in app._available_module_groups(player):
            rect = app._available_module_rect(module_key)
            if not rect.colliderect(viewport.inflate(20, 20)):
                continue
            module = WEAPON_MODULES[module_key]
            available = len(indices)
            installed_here = weapon.modules.get(module.slot) == module_key
            accent = palette.CYAN if installed_here else palette.GREEN if available else palette.MUTED
            pygame.draw.rect(ctx.screen, palette.PANEL_2 if available else palette.BG, rect, border_radius=10)
            pygame.draw.rect(ctx.screen, accent, rect, 2 if available or installed_here else 1, border_radius=10)
            draw_item_icon(ctx, module_key, pygame.Rect(rect.x + 14, rect.y + 22, 54, 50), aura=False)
            draw_text_fit(ctx, app.item_title(module_key), pygame.Rect(rect.x + 76, rect.y + 18, rect.w - 88, 20), palette.TEXT if available else palette.MUTED, ctx.fonts.normal)
            draw_text_fit(ctx, app._module_effect_text(module_key), pygame.Rect(rect.x + 76, rect.y + 44, rect.w - 88, 18), palette.GREEN if available else palette.MUTED, ctx.fonts.small)
            count_text = ctx.text.tr("weaponmods.installed") if installed_here and not available else f"x{available}"
            draw_text_fit(ctx, count_text, pygame.Rect(rect.x + 76, rect.y + 68, rect.w - 88, 18), palette.CYAN if installed_here else palette.YELLOW if available else palette.MUTED, ctx.fonts.small)
        ctx.screen.set_clip(previous_clip)
        self._render_scrollbar(ctx)

    def _render_scrollbar(self, ctx: RenderContext) -> None:
        app = self.app
        viewport = app._weapon_module_viewport_rect()
        track = pygame.Rect(viewport.right + 8, viewport.y, 10, viewport.h)
        pygame.draw.rect(ctx.screen, (8, 12, 20), track, border_radius=5)
        pygame.draw.rect(ctx.screen, (52, 68, 98), track, 1, border_radius=5)
        max_scroll = app._weapon_modules_max_scroll()
        if max_scroll <= 0:
            pygame.draw.rect(ctx.screen, palette.PURPLE, track.inflate(-2, -2), border_radius=4)
            return
        knob_h = max(38, int(track.h * track.h / max(track.h, app._weapon_modules_content_height())))
        knob_y = track.y + int((track.h - knob_h) * (app.overlay_state.weapon_modules_scroll / max_scroll))
        knob = pygame.Rect(track.x + 2, knob_y, track.w - 4, knob_h)
        pygame.draw.rect(ctx.screen, palette.PURPLE, knob, border_radius=4)
        pygame.draw.rect(ctx.screen, (236, 222, 255), knob, 1, border_radius=4)

