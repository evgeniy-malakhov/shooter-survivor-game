from __future__ import annotations

from typing import Any

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.world.render_utils import draw_item_icon, draw_mini_durability, draw_rarity_badge, draw_rarity_frame, draw_text, draw_text_fit
from shared.constants import SLOTS, WEAPONS
from shared.items import EQUIPMENT_SLOTS, ITEMS


class InventoryRenderer:
    def render(self, ctx: RenderContext) -> None:
        player = ctx.local_player
        overlay_state = ctx.overlay
        if not player or not overlay_state or not ctx.fonts or not ctx.text:
            return

        overlay = pygame.Surface(ctx.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((2, 5, 12, 184))
        ctx.screen.blit(overlay, (0, 0))

        panel = self._backpack_panel_rect()
        pygame.draw.rect(ctx.screen, palette.PANEL, panel, border_radius=10)
        pygame.draw.rect(ctx.screen, palette.CYAN, panel, 2, border_radius=10)

        draw_text(ctx, ctx.text.tr("backpack.title"), panel.x + 34, panel.y + 24, palette.TEXT, ctx.fonts.big)
        draw_text(ctx, ctx.text.tr("backpack.body"), panel.x + 54, panel.y + 116, palette.PURPLE, ctx.fonts.mid)
        draw_text_fit(
            ctx,
            ctx.text.tr("backpack.help"),
            pygame.Rect(panel.x + 352, panel.y + 42, panel.w - 390, 40),
            palette.MUTED,
            ctx.fonts.small,
        )

        draw_text(ctx, ctx.text.tr("backpack.quickbar"), 390, 106, palette.CYAN, ctx.fonts.mid)
        for index, slot in enumerate(SLOTS):
            rect = self._quick_rect(index)
            active = player.active_slot == slot
            pygame.draw.rect(ctx.screen, palette.PANEL_2 if active else palette.BG, rect, border_radius=8)
            pygame.draw.rect(ctx.screen, palette.CYAN if active else (52, 68, 98), rect, 2 if active else 1, border_radius=8)
            draw_text(ctx, slot, rect.x + 6, rect.y + 5, palette.MUTED, ctx.fonts.small)
            weapon = player.weapons.get(slot)
            quick_item = player.quick_items.get(slot)
            if weapon and not self._is_dragging(overlay_state.drag_source, "weapon_slot", slot=slot):
                draw_rarity_frame(ctx, rect, weapon.rarity)
                draw_rarity_badge(ctx, rect, weapon.rarity, compact=True)
                draw_item_icon(ctx, weapon.key, pygame.Rect(rect.x + 16, rect.y + 11, 34, 34))
                draw_mini_durability(ctx, rect, weapon.durability)
            elif quick_item and not self._is_dragging(overlay_state.drag_source, "quick_item", slot=slot):
                self._draw_item(ctx, quick_item.key, quick_item.amount, rect, quick_item.rarity, quick_item.durability)

        for slot in EQUIPMENT_SLOTS:
            rect = self._equipment_rect(slot)
            item = player.equipment.get(slot)
            pygame.draw.rect(ctx.screen, palette.BG, rect, border_radius=8)
            pygame.draw.rect(ctx.screen, palette.PURPLE if item else (58, 58, 88), rect, 2, border_radius=8)
            draw_text(ctx, ctx.text.tr(f"slot.{slot}"), rect.x + 12, rect.y + 10, palette.MUTED, ctx.fonts.small)
            if item and not self._is_dragging(overlay_state.drag_source, "equipment", slot=slot):
                self._draw_item(ctx, item.key, item.amount, rect, item.rarity, item.durability)
            repair = pygame.Rect(rect.right + 12, rect.y + 12, 70, 34)
            pygame.draw.rect(ctx.screen, palette.PANEL_2, repair, border_radius=6)
            pygame.draw.rect(ctx.screen, palette.YELLOW, repair, 1, border_radius=6)
            draw_text(ctx, ctx.text.tr("backpack.repair"), repair.x + 10, repair.y + 8, palette.TEXT, ctx.fonts.small)

        for index in range(30):
            rect = self._backpack_rect(index)
            pygame.draw.rect(ctx.screen, palette.BG, rect, border_radius=8)
            pygame.draw.rect(ctx.screen, (52, 68, 98), rect, 1, border_radius=8)
            item = player.backpack[index] if index < len(player.backpack) else None
            if item and not self._is_dragging(overlay_state.drag_source, "backpack", index=index):
                self._draw_item(ctx, item.key, item.amount, rect, item.rarity, item.durability)

        drop = self._drop_rect()
        mouse_pos = ctx.mouse_pos
        drop_hovered = bool(overlay_state.drag_source and drop.collidepoint(mouse_pos))
        pygame.draw.rect(ctx.screen, (60, 22, 30), drop, border_radius=8)
        pygame.draw.rect(ctx.screen, palette.YELLOW if drop_hovered else palette.RED, drop, 2, border_radius=8)
        draw_text(ctx, ctx.text.tr("backpack.drop"), drop.x + 44, drop.y + 20, palette.TEXT, ctx.fonts.mid)

        customize = self._customize_button_rect()
        pygame.draw.rect(ctx.screen, palette.PANEL_2, customize, border_radius=8)
        pygame.draw.rect(ctx.screen, palette.PURPLE if overlay_state.weapon_custom_open else palette.CYAN, customize, 2, border_radius=8)
        draw_text_fit(ctx, ctx.text.tr("backpack.customize"), customize.inflate(-18, -8), palette.TEXT, ctx.fonts.mid, center=True)

        self._draw_drag_preview(ctx, player, overlay_state.drag_source)

    def _draw_item(self, ctx: RenderContext, key: str, amount: int, rect: pygame.Rect, rarity: str = "common", durability: float | None = None) -> None:
        spec = ITEMS.get(key)
        rarity_highlight = key in WEAPONS or bool(spec and spec.kind == "armor") or rarity != "common"
        if rarity_highlight:
            draw_rarity_frame(ctx, rect, rarity)
        icon_rect = pygame.Rect(rect.x + 12, rect.y + 8, min(36, rect.w - 18), min(36, rect.h - 20))
        if not draw_item_icon(ctx, key, icon_rect):
            color = palette.YELLOW if key in WEAPONS else spec.color if spec else palette.TEXT
            pygame.draw.circle(ctx.screen, color, rect.center, min(rect.w, rect.h) // 4)
            pygame.draw.circle(ctx.screen, (255, 255, 255), rect.center, min(rect.w, rect.h) // 4, 1)
        draw_rarity_badge(ctx, rect, rarity)
        title = self._item_title(ctx, key)
        draw_text_fit(
            ctx,
            title,
            pygame.Rect(rect.x + 4, rect.y + rect.h - 20, rect.w - 8, 16),
            palette.YELLOW if key in WEAPONS else palette.TEXT,
            ctx.fonts.small,
            center=True,
        )
        if amount > 1:
            draw_text(ctx, str(amount), rect.right - 26, rect.bottom - 36, palette.YELLOW, ctx.fonts.small)
        if durability is not None:
            draw_mini_durability(ctx, rect, durability)

    def _draw_drag_preview(self, ctx: RenderContext, player: Any, drag_source: dict[str, object] | None) -> None:
        payload = self._dragged_payload(player, drag_source)
        if not payload:
            return
        key, amount, durability, rarity = payload
        mx, my = ctx.mouse_pos
        rect = pygame.Rect(mx - 28, my - 28, 56, 52)
        preview = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(preview, (*palette.PANEL_2, 218), preview.get_rect(), border_radius=8)
        ctx.screen.blit(preview, rect.topleft)
        pygame.draw.rect(ctx.screen, palette.CYAN, rect, 2, border_radius=8)
        self._draw_item(ctx, key, amount, rect, rarity, durability)

    def _dragged_payload(self, player: Any, drag_source: dict[str, object] | None) -> tuple[str, int, float | None, str] | None:
        if not player or not drag_source:
            return None
        source = str(drag_source.get("source", ""))
        if source == "backpack":
            index = int(drag_source.get("index", -1))
            item = player.backpack[index] if 0 <= index < len(player.backpack) else None
            return (item.key, item.amount, item.durability, item.rarity) if item else None
        if source == "equipment":
            item = player.equipment.get(str(drag_source.get("slot", "")))
            return (item.key, item.amount, item.durability, item.rarity) if item else None
        if source == "quick_item":
            item = player.quick_items.get(str(drag_source.get("slot", "")))
            return (item.key, item.amount, item.durability, item.rarity) if item else None
        if source == "weapon_slot":
            weapon = player.weapons.get(str(drag_source.get("slot", "")))
            return (weapon.key, 1, weapon.durability, weapon.rarity) if weapon else None
        if source == "weapon_module":
            weapon = player.weapons.get(str(drag_source.get("slot", "")))
            module_key = weapon.modules.get(str(drag_source.get("module_slot", ""))) if weapon else None
            return (module_key, 1, 100.0, "common") if module_key else None
        return None

    def _is_dragging(self, drag_source: dict[str, object] | None, source: str, *, index: int | None = None, slot: str | None = None) -> bool:
        if not drag_source or drag_source.get("source") != source:
            return False
        if index is not None and drag_source.get("index") != index:
            return False
        if slot is not None and drag_source.get("slot") != slot:
            return False
        return True

    def _item_title(self, ctx: RenderContext, key: str) -> str:
        if key in WEAPONS:
            return ctx.text.tr(f"weapon.{key}") if ctx.text else key
        return ctx.text.tr(f"item.{key}") if ctx.text else key

    def _backpack_rect(self, index: int) -> pygame.Rect:
        col = index % 6
        row = index // 6
        return pygame.Rect(390 + col * 92, 210 + row * 78, 74, 62)

    def _quick_rect(self, index: int) -> pygame.Rect:
        return pygame.Rect(390 + index * 72, 142, 58, 54)

    def _backpack_panel_rect(self) -> pygame.Rect:
        return pygame.Rect(76, 58, 1128, 642)

    def _drop_rect(self) -> pygame.Rect:
        return pygame.Rect(1020, 590, 190, 64)

    def _customize_button_rect(self) -> pygame.Rect:
        return pygame.Rect(1020, 514, 190, 54)

    def _equipment_rect(self, slot: str) -> pygame.Rect:
        order = {"head": 0, "torso": 1, "arms": 2, "legs": 3}
        return pygame.Rect(126, 170 + order[slot] * 94, 134, 72)

