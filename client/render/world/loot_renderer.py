from __future__ import annotations

import math

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.render_frame import RenderFrame
from client.render.world.render_utils import (
    draw_item_icon,
    draw_rarity_badge,
    draw_text,
    loot_icon_key,
    point_lit_by_flashlight,
    world_to_screen,
)
from shared.items import ITEMS
from shared.rarities import rarity_color, rarity_rank


class LootRenderer:
    def render(self, ctx: RenderContext, frame: RenderFrame) -> None:
        colors = {"weapon": palette.CYAN, "ammo": palette.YELLOW, "armor": palette.PURPLE, "medkit": palette.GREEN, "item": palette.TEXT}
        player = ctx.local_player
        for item in frame.loot:
            if player and player.floor < 0 and not point_lit_by_flashlight(player, item.pos):
                continue
            sx, sy = world_to_screen(ctx, item.pos)
            if not (-30 <= sx <= ctx.screen.get_width() + 30 and -30 <= sy <= ctx.screen.get_height() + 30):
                continue
            color = colors.get(item.kind, palette.TEXT)
            icon_key = loot_icon_key(ctx, item.kind, item.payload)
            if item.kind == "item" and item.payload in ITEMS:
                color = ITEMS[item.payload].color
            spec = ITEMS.get(item.payload)
            rare_visual = item.kind in {"weapon", "armor"} or bool(spec and spec.kind == "armor")
            if rare_visual and rarity_rank(item.rarity) > 0:
                color = rarity_color(item.rarity)
            frame_rect = self.paint_world_item_frame(ctx, (sx, sy), item.rarity, color, frame.snapshot.time)
            if rare_visual:
                draw_rarity_badge(ctx, frame_rect, item.rarity, compact=True)
            if not draw_item_icon(ctx, icon_key, pygame.Rect(sx - 14, sy - 14, 28, 28), aura=False):
                pygame.draw.circle(ctx.screen, color, (sx, sy), 10)
            label = ctx.text.loot_label(item) if ctx.text else item.payload
            fonts = ctx.fonts
            draw_text(ctx, label, sx + 14, sy - 11, color, fonts.small if fonts else None)

    def paint_world_item_frame(
        self,
        ctx: RenderContext,
        center: tuple[int, int],
        rarity: str,
        accent: tuple[int, int, int],
        world_time: float,
    ) -> pygame.Rect:
        rank = rarity_rank(rarity)
        rarity_accent = rarity_color(rarity) if rank > 0 else accent
        pulse = (math.sin(world_time * 4.6 + center[0] * 0.017) + 1.0) * 0.5
        size = 42 + min(rank, 3) * 3
        rect = pygame.Rect(0, 0, size, size)
        rect.center = center
        glow_rect = rect.inflate(22 + rank * 6, 22 + rank * 6)
        glow = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
        for layer in range(3 + min(rank, 2)):
            inset = layer * 5
            alpha = max(8, int(42 + rank * 22 + pulse * 26) - layer * 18)
            pygame.draw.rect(glow, (*rarity_accent, alpha), glow.get_rect().inflate(-inset, -inset), 2, border_radius=10)
        pygame.draw.rect(glow, (*accent, 24 + rank * 8), glow.get_rect().inflate(-12, -12), border_radius=9)
        ctx.screen.blit(glow, glow_rect)
        pygame.draw.rect(ctx.screen, (7, 11, 19), rect, border_radius=7)
        pygame.draw.rect(ctx.screen, accent, rect, 1, border_radius=7)
        pygame.draw.rect(ctx.screen, rarity_accent, rect.inflate(4, 4), 2 + (1 if rank >= 2 else 0), border_radius=8)
        corner = 8 + rank * 2
        width = 2 + (1 if rank >= 3 else 0)
        for sx, sy in ((rect.left, rect.top), (rect.right, rect.top), (rect.left, rect.bottom), (rect.right, rect.bottom)):
            x_dir = 1 if sx == rect.left else -1
            y_dir = 1 if sy == rect.top else -1
            pygame.draw.line(ctx.screen, rarity_accent, (sx, sy), (sx + corner * x_dir, sy), width)
            pygame.draw.line(ctx.screen, rarity_accent, (sx, sy), (sx, sy + corner * y_dir), width)
        return rect
