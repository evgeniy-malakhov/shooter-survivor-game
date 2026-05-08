from __future__ import annotations

import pygame

from client.render import palette
from client.render.render_context import RenderContext


class DeathOverlayRenderer:
    def render(self, ctx: RenderContext, *, online: bool) -> None:
        player = ctx.local_player
        if player:
            self.paint_damage_flash(ctx)
        if player and not player.alive:
            self.paint_death_overlay(ctx, online=online)

    def paint_damage_flash(self, ctx: RenderContext) -> None:
        player = ctx.local_player
        if not player or not player.alive or not ctx.effects:
            return
        critical = max(0.0, (25.0 - player.health) / 25.0)
        hit = ctx.effects.damage_flash
        if hit <= 0.01 and critical <= 0.01:
            return
        import math
        pulse = (math.sin((ctx.now or 0.0) * 7.4) + 1.0) * 0.5
        overlay = pygame.Surface(ctx.screen.get_size(), pygame.SRCALPHA)
        if hit > 0.01:
            overlay.fill((120, 0, 8, int(44 * hit)))
        if critical > 0.01:
            overlay.fill((60, 0, 8, int((20 + 44 * pulse) * critical)), special_flags=pygame.BLEND_RGBA_ADD)
        ctx.screen.blit(overlay, (0, 0))

    def paint_death_overlay(self, ctx: RenderContext, *, online: bool) -> None:
        if not ctx.text or not ctx.fonts:
            return
        overlay = pygame.Surface(ctx.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((60, 4, 10, 126))
        ctx.screen.blit(overlay, (0, 0))
        title = ctx.text_cache.render(ctx.fonts.big, ctx.text.tr("death.title"), palette.TEXT) if ctx.text_cache else ctx.fonts.big.render(ctx.text.tr("death.title"), True, palette.TEXT)
        ctx.screen.blit(title, title.get_rect(center=(ctx.screen.get_width() // 2, ctx.screen.get_height() // 2 - 44)))
        hint_text = ctx.text.tr("death.online" if online else "death.single")
        hint = ctx.text_cache.render(ctx.fonts.mid, hint_text, palette.CYAN) if ctx.text_cache else ctx.fonts.mid.render(hint_text, True, palette.CYAN)
        ctx.screen.blit(hint, hint.get_rect(center=(ctx.screen.get_width() // 2, ctx.screen.get_height() // 2 + 22)))

