from __future__ import annotations

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.world.render_utils import draw_item_icon, draw_text, draw_text_fit
from shared.items import RECIPES


class CraftingRenderer:
    def render(self, ctx: RenderContext) -> None:
        player = ctx.local_player
        if not player or not ctx.fonts or not ctx.text:
            return
        overlay = pygame.Surface(ctx.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((2, 5, 12, 190))
        ctx.screen.blit(overlay, (0, 0))
        panel = pygame.Rect(126, 56, 1028, 648)
        pygame.draw.rect(ctx.screen, palette.PANEL, panel, border_radius=10)
        pygame.draw.rect(ctx.screen, palette.GREEN, panel, 2, border_radius=10)
        draw_text(ctx, ctx.text.tr("craft.title"), panel.x + 34, panel.y + 24, palette.TEXT, ctx.fonts.big)
        y = panel.y + 118 - (ctx.overlay.craft_scroll if ctx.overlay else 0)
        for recipe in list(RECIPES.values())[:24]:
            rect = pygame.Rect(panel.x + 34, y, panel.w - 68, 58)
            if rect.colliderect(panel.inflate(0, -104)):
                pygame.draw.rect(ctx.screen, palette.PANEL_2, rect, border_radius=8)
                pygame.draw.rect(ctx.screen, palette.GREEN, rect, 1, border_radius=8)
                result_key, amount = recipe.result
                draw_item_icon(ctx, result_key, pygame.Rect(rect.x + 12, rect.y + 10, 36, 36), aura=False)
                draw_text_fit(ctx, ctx.text.tr(f"recipe.{recipe.key}") if ctx.text.tr(f"recipe.{recipe.key}") != f"recipe.{recipe.key}" else recipe.title, pygame.Rect(rect.x + 60, rect.y + 10, 330, 20), palette.TEXT, ctx.fonts.normal)
                req = "  ".join(f"{key} x{value}" for key, value in recipe.requires.items())
                draw_text_fit(ctx, f"=> {result_key} x{amount}    {req}", pygame.Rect(rect.x + 60, rect.y + 32, rect.w - 80, 18), palette.MUTED, ctx.fonts.small)
            y += 68
