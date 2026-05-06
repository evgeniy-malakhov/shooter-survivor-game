from __future__ import annotations

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.world.render_utils import draw_item_icon, draw_text, draw_text_fit
from shared.weapon_modules import WEAPON_MODULES


class WeaponCustomRenderer:
    def render(self, ctx: RenderContext) -> None:
        player = ctx.local_player
        if not player or not ctx.fonts or not ctx.text:
            return
        weapon = player.active_weapon()
        overlay = pygame.Surface(ctx.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((2, 5, 12, 184))
        ctx.screen.blit(overlay, (0, 0))
        panel = pygame.Rect(250, 88, 780, 560)
        pygame.draw.rect(ctx.screen, palette.PANEL, panel, border_radius=10)
        pygame.draw.rect(ctx.screen, palette.PURPLE, panel, 2, border_radius=10)
        draw_text(ctx, ctx.text.tr("backpack.customize"), panel.x + 34, panel.y + 24, palette.TEXT, ctx.fonts.big)
        if not weapon:
            draw_text_fit(ctx, ctx.text.tr("hud.unarmed"), panel.inflate(-80, -160), palette.MUTED, ctx.fonts.mid, center=True)
            return
        draw_item_icon(ctx, weapon.key, pygame.Rect(panel.x + 42, panel.y + 112, 72, 72))
        draw_text(ctx, ctx.text.weapon_title(weapon.key), panel.x + 132, panel.y + 120, palette.TEXT, ctx.fonts.mid)
        y = panel.y + 220
        for slot, module_key in weapon.modules.items():
            rect = pygame.Rect(panel.x + 42, y, panel.w - 84, 54)
            pygame.draw.rect(ctx.screen, palette.PANEL_2, rect, border_radius=8)
            pygame.draw.rect(ctx.screen, palette.CYAN, rect, 1, border_radius=8)
            title = WEAPON_MODULES.get(module_key).title if module_key and module_key in WEAPON_MODULES else "empty"
            if module_key:
                draw_item_icon(ctx, module_key, pygame.Rect(rect.x + 12, rect.y + 9, 36, 36), aura=False)
            draw_text(ctx, f"{slot}: {title}", rect.x + 62, rect.y + 16, palette.TEXT if module_key else palette.MUTED, ctx.fonts.normal)
            y += 66
