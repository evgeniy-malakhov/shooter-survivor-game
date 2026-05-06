from __future__ import annotations

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.world.render_utils import draw_item_icon, draw_mini_durability, draw_rarity_badge, draw_rarity_frame, draw_text, draw_text_fit
from shared.constants import SLOTS, WEAPONS
from shared.items import EQUIPMENT_SLOTS


class InventoryRenderer:
    def render(self, ctx: RenderContext) -> None:
        player = ctx.local_player
        if not player or not ctx.fonts or not ctx.text:
            return
        overlay = pygame.Surface(ctx.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((2, 5, 12, 184))
        ctx.screen.blit(overlay, (0, 0))
        panel = pygame.Rect(82, 78, ctx.screen.get_width() - 164, ctx.screen.get_height() - 128)
        pygame.draw.rect(ctx.screen, palette.PANEL, panel, border_radius=10)
        pygame.draw.rect(ctx.screen, palette.CYAN, panel, 2, border_radius=10)
        draw_text(ctx, ctx.text.tr("backpack.title"), panel.x + 34, panel.y + 24, palette.TEXT, ctx.fonts.big)
        draw_text(ctx, ctx.text.tr("backpack.quickbar"), panel.x + 34, panel.y + 104, palette.CYAN, ctx.fonts.mid)
        for index, slot in enumerate(SLOTS):
            rect = pygame.Rect(panel.x + 34 + index * 76, panel.y + 146, 66, 58)
            active = player.active_slot == slot
            pygame.draw.rect(ctx.screen, palette.PANEL_2 if active else palette.BG, rect, border_radius=8)
            pygame.draw.rect(ctx.screen, palette.CYAN if active else (52, 68, 98), rect, 2 if active else 1, border_radius=8)
            draw_text(ctx, slot, rect.x + 6, rect.y + 5, palette.MUTED, ctx.fonts.small)
            weapon = player.weapons.get(slot)
            quick_item = player.quick_items.get(slot)
            if weapon:
                draw_rarity_frame(ctx, rect, weapon.rarity)
                draw_rarity_badge(ctx, rect, weapon.rarity, compact=True)
                draw_item_icon(ctx, weapon.key, pygame.Rect(rect.x + 16, rect.y + 13, 34, 34))
                draw_mini_durability(ctx, rect, weapon.durability)
            elif quick_item:
                draw_rarity_badge(ctx, rect, quick_item.rarity, compact=True)
                draw_item_icon(ctx, quick_item.key, pygame.Rect(rect.x + 16, rect.y + 13, 34, 34))
        draw_text(ctx, ctx.text.tr("backpack.body"), panel.x + 34, panel.y + 238, palette.PURPLE, ctx.fonts.mid)
        for index, slot in enumerate(EQUIPMENT_SLOTS):
            rect = pygame.Rect(panel.x + 34 + index * 158, panel.y + 282, 138, 74)
            item = player.equipment.get(slot)
            pygame.draw.rect(ctx.screen, palette.BG, rect, border_radius=8)
            pygame.draw.rect(ctx.screen, palette.PURPLE if item else (58, 58, 88), rect, 2, border_radius=8)
            draw_text(ctx, ctx.text.tr(f"slot.{slot}"), rect.x + 10, rect.y + 8, palette.MUTED, ctx.fonts.small)
            if item:
                draw_item_icon(ctx, item.key, pygame.Rect(rect.x + 48, rect.y + 22, 40, 40))
                draw_rarity_badge(ctx, rect, item.rarity, compact=True)
                draw_mini_durability(ctx, rect, item.durability)
        grid_x = panel.x + 34
        grid_y = panel.y + 398
        for index in range(30):
            rect = pygame.Rect(grid_x + (index % 10) * 74, grid_y + (index // 10) * 72, 62, 62)
            pygame.draw.rect(ctx.screen, palette.BG, rect, border_radius=8)
            pygame.draw.rect(ctx.screen, (52, 68, 98), rect, 1, border_radius=8)
            item = player.backpack[index] if index < len(player.backpack) else None
            if item:
                draw_item_icon(ctx, item.key if item.key not in WEAPONS else item.key, rect.inflate(-14, -16))
                draw_rarity_badge(ctx, rect, item.rarity, compact=True)
                if item.amount > 1:
                    draw_text_fit(ctx, str(item.amount), pygame.Rect(rect.right - 24, rect.bottom - 22, 20, 16), palette.YELLOW, ctx.fonts.small, center=True)
