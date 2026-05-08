from __future__ import annotations

import math

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.render_frame import RenderFrame
from client.render.world.render_utils import draw_item_icon, draw_text_fit, world_size, world_to_screen
from shared.explosives import DEFAULT_GRENADE, GRENADE_SPECS


class ExplosiveRenderer:
    def render(self, ctx: RenderContext, frame: RenderFrame) -> None:
        for grenade in frame.grenades:
            spec = GRENADE_SPECS.get(grenade.kind, DEFAULT_GRENADE)
            sx, sy = world_to_screen(ctx, grenade.pos)
            progress = max(0.0, min(1.0, 1.0 - grenade.timer / max(0.05, spec.timer)))
            pulse = int(7 + progress * 10)
            color = (103, 236, 190) if grenade.kind == "contact_grenade" else (255, 128, 92) if grenade.kind == "heavy_grenade" else palette.GREEN
            warning = palette.RED if grenade.timer <= 0.55 else color
            glow = pygame.Surface((84, 84), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*warning, int(44 + progress * 56)), (42, 42), 20 + int(progress * 14))
            ctx.screen.blit(glow, (sx - 42, sy - 42))
            pygame.draw.circle(ctx.screen, (10, 16, 12), (sx, sy), pulse + 6)
            pygame.draw.circle(ctx.screen, warning, (sx, sy), pulse + 1)
            pygame.draw.circle(ctx.screen, (255, 255, 255), (sx, sy), max(3, pulse - 4), 1)
            if spec.contact:
                pygame.draw.circle(ctx.screen, palette.CYAN, (sx, sy), pulse + 4, 1)
            blast_px = world_size(ctx, spec.blast_radius, 1)
            ring_alpha = int(36 + progress * 64)
            ring = pygame.Surface((blast_px * 2 + 20, blast_px * 2 + 20), pygame.SRCALPHA)
            center = (blast_px + 10, blast_px + 10)
            pygame.draw.circle(ring, (255, 214, 122, ring_alpha), center, blast_px, 1)
            pygame.draw.circle(ring, (255, 145, 96, max(10, ring_alpha - 24)), center, int(blast_px * (0.55 + 0.35 * progress)), 1)
            ctx.screen.blit(ring, (sx - center[0], sy - center[1]))
            shard_count = 10 if grenade.kind == "heavy_grenade" else 7 if grenade.kind == "grenade" else 5
            phase = frame.snapshot.time * 5.2 + progress * 3.4
            for index in range(shard_count):
                angle = phase + math.tau * index / shard_count
                inner = blast_px * (0.42 + 0.08 * math.sin(phase + index * 0.7))
                outer = blast_px * (0.92 + 0.09 * math.cos(phase * 1.2 + index))
                shard_color = (255, 196, 124) if grenade.kind != "heavy_grenade" else (255, 154, 108)
                pygame.draw.line(
                    ctx.screen,
                    shard_color,
                    (int(sx + math.cos(angle) * inner), int(sy + math.sin(angle) * inner)),
                    (int(sx + math.cos(angle) * outer), int(sy + math.sin(angle) * outer)),
                    2 if grenade.kind == "heavy_grenade" else 1,
                )

        for mine in frame.mines:
            sx, sy = world_to_screen(ctx, mine.pos)
            if not (-180 <= sx <= ctx.screen.get_width() + 180 and -180 <= sy <= ctx.screen.get_height() + 180):
                continue
            tier = self._mine_tier(mine.kind)
            tier_name = "I" if tier <= 1 else "II" if tier == 2 else "III"
            base_color = self._mine_tier_color(tier, mine.armed)
            blink = 0.5 + 0.5 * math.sin(frame.snapshot.time * 7.2 + mine.rotation)
            alpha = int((72 if mine.armed else 42) + blink * (70 if mine.armed else 18))
            self.paint_dashed_circle(ctx, (sx, sy), world_size(ctx, mine.trigger_radius, 8), base_color, mine.rotation, alpha)
            glow = pygame.Surface((74, 74), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*base_color, 54 if mine.armed else 26), (37, 37), 34)
            ctx.screen.blit(glow, (sx - 37, sy - 37))
            radius = world_size(ctx, 17 + tier * 2, 10)
            points = [
                (int(sx + math.cos(mine.rotation - math.pi / 2) * radius), int(sy + math.sin(mine.rotation - math.pi / 2) * radius)),
                (int(sx + math.cos(mine.rotation + math.pi * 0.16) * radius), int(sy + math.sin(mine.rotation + math.pi * 0.16) * radius)),
                (int(sx + math.cos(mine.rotation + math.pi * 0.84) * radius), int(sy + math.sin(mine.rotation + math.pi * 0.84) * radius)),
            ]
            pygame.draw.polygon(ctx.screen, (8, 11, 16), [(x + 2, y + 2) for x, y in points])
            pygame.draw.polygon(ctx.screen, base_color if mine.armed else palette.MUTED, points)
            pygame.draw.polygon(ctx.screen, palette.TEXT, points, 1)
            if mine.armed and blink > 0.55:
                pygame.draw.circle(ctx.screen, palette.RED, (sx, sy), 5)
            if not draw_item_icon(ctx, mine.kind, pygame.Rect(sx - 12, sy - 12, 24, 24)):
                pygame.draw.circle(ctx.screen, palette.BG, (sx, sy), 4)
            level_rect = pygame.Rect(sx - 14, sy + world_size(ctx, 24, 16), 28, 14)
            pygame.draw.rect(ctx.screen, (8, 12, 20), level_rect, border_radius=4)
            pygame.draw.rect(ctx.screen, base_color, level_rect, 1, border_radius=4)
            draw_text_fit(ctx, tier_name, level_rect.inflate(-2, -2), base_color, ctx.fonts.small if ctx.fonts else None, center=True)

    def _mine_tier(self, mine_kind: str) -> int:
        if "heavy" in mine_kind:
            return 3
        if "light" in mine_kind:
            return 1
        return 2

    def _mine_tier_color(self, tier: int, armed: bool) -> tuple[int, int, int]:
        if tier <= 1:
            return (86, 208, 172) if armed else (88, 136, 124)
        if tier == 2:
            return (145, 116, 228) if armed else (122, 112, 160)
        return (255, 128, 98) if armed else (164, 118, 108)

    def paint_dashed_circle(
        self,
        ctx: RenderContext,
        center: tuple[int, int],
        radius: int,
        color: tuple[int, int, int],
        phase: float,
        alpha: int,
    ) -> None:
        if radius <= 0:
            return
        surface = pygame.Surface((radius * 2 + 16, radius * 2 + 16), pygame.SRCALPHA)
        local_center = (radius + 8, radius + 8)
        for index in range(40):
            if index % 2:
                continue
            a1 = phase + math.tau * index / 40
            a2 = phase + math.tau * (index + 0.62) / 40
            p1 = (int(local_center[0] + math.cos(a1) * radius), int(local_center[1] + math.sin(a1) * radius))
            p2 = (int(local_center[0] + math.cos(a2) * radius), int(local_center[1] + math.sin(a2) * radius))
            pygame.draw.line(surface, (*color, alpha), p1, p2, 2)
        ctx.screen.blit(surface, (center[0] - radius - 8, center[1] - radius - 8))

