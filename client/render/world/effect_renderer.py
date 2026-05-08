from __future__ import annotations

import math

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.world.render_utils import world_size, world_to_screen
from shared.constants import ZOMBIES
from shared.models import Vec2


class EffectRenderer:
    def render_blood(self, ctx: RenderContext) -> None:
        if not ctx.effects:
            return
        if ctx.quality and not ctx.quality.particles_enabled:
            return
        now = ctx.now or 0.0
        tuning = ctx.death_tuning
        blood_seconds = float(getattr(tuning, "blood_seconds", 4.0))
        effects = ctx.effects.death_effects
        if ctx.quality:
            effects = effects[: max(2, int(len(effects) * ctx.quality.effects_quality))]
        for effect in effects:
            if ctx.local_player and int(effect.get("floor", 0)) != ctx.local_player.floor:
                continue
            age = now - float(effect.get("started", now))
            if age < 0.0 or age > blood_seconds:
                continue
            pos = effect.get("pos")
            if isinstance(pos, Vec2):
                self.paint_blood_pool(ctx, world_to_screen(ctx, pos), effect, age)

    def render_bodies(self, ctx: RenderContext) -> None:
        if not ctx.effects:
            return
        now = ctx.now or 0.0
        tuning = ctx.death_tuning
        corpse_seconds = float(getattr(tuning, "corpse_seconds", 6.0))
        corpse_fade_seconds = max(0.01, float(getattr(tuning, "corpse_fade_seconds", 1.2)))
        for effect in ctx.effects.death_effects:
            if ctx.local_player and int(effect.get("floor", 0)) != ctx.local_player.floor:
                continue
            age = now - float(effect.get("started", now))
            if age < 0.0 or age > corpse_seconds:
                continue
            fade_start = max(0.0, corpse_seconds - corpse_fade_seconds)
            alpha_ratio = 1.0 if age <= fade_start else max(0.0, (corpse_seconds - age) / corpse_fade_seconds)
            if alpha_ratio <= 0.0:
                continue
            pos = effect.get("pos")
            if not isinstance(pos, Vec2):
                continue
            center = world_to_screen(ctx, pos)
            if str(effect.get("entity_type", "")) == "player":
                self.paint_dead_player_cross(ctx, center, alpha_ratio, int(225 * alpha_ratio))
            else:
                self.paint_dead_zombie_body(ctx, center, effect, alpha_ratio)

    def render(self, ctx: RenderContext) -> None:
        self.paint_explosion_effects(ctx)

    def paint_blood_pool(self, ctx: RenderContext, center: tuple[int, int], effect: dict[str, object], age: float) -> None:
        tuning = ctx.death_tuning
        blood_spread_seconds = max(0.01, float(getattr(tuning, "blood_spread_seconds", 0.8)))
        blood_seconds = float(getattr(tuning, "blood_seconds", 4.0))
        blood_fade_seconds = max(0.01, float(getattr(tuning, "blood_fade_seconds", 1.0)))
        blood_alpha = float(getattr(tuning, "blood_alpha", 120))
        start_radius = float(getattr(tuning, "blood_start_radius", 18.0))
        end_radius = float(getattr(tuning, "blood_end_radius", 42.0))
        spread = min(1.0, age / blood_spread_seconds)
        spread = spread * spread * (3.0 - 2.0 * spread)
        fade_start = max(0.01, blood_seconds - blood_fade_seconds)
        fade = 1.0 if age <= fade_start else max(0.0, (blood_seconds - age) / blood_fade_seconds)
        alpha = int(blood_alpha * fade)
        if alpha <= 0:
            return
        radius = world_size(ctx, start_radius + (end_radius - start_radius) * spread, 8)
        size = radius * 2 + 34
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        cx = cy = size // 2
        seed = int(effect.get("seed", 1))
        base_rect = pygame.Rect(cx - radius, cy - int(radius * 0.62), radius * 2, max(2, int(radius * 1.24)))
        pygame.draw.ellipse(surface, (68, 3, 12, int(alpha * 0.64)), base_rect)
        pygame.draw.ellipse(surface, (132, 12, 22, int(alpha * 0.68)), base_rect.inflate(-int(radius * 0.3), -int(radius * 0.2)))
        for index in range(7):
            wave = 0.5 + 0.5 * math.sin(seed * 0.037 + index * 2.17)
            angle = seed * 0.011 + index * 0.93
            distance = radius * (0.14 + 0.22 * wave) * spread
            lobe_radius = max(3, int(radius * (0.16 + 0.14 * (1.0 - wave))))
            lx = int(cx + math.cos(angle) * distance)
            ly = int(cy + math.sin(angle) * distance * 0.72)
            lobe = pygame.Rect(lx - lobe_radius, ly - int(lobe_radius * 0.65), lobe_radius * 2, max(2, int(lobe_radius * 1.3)))
            pygame.draw.ellipse(surface, (114, 4, 18, int(alpha * (0.42 + 0.3 * wave))), lobe)
        pygame.draw.ellipse(surface, (218, 32, 38, int(alpha * 0.18)), base_rect.inflate(-int(radius * 0.75), -int(radius * 0.72)))
        ctx.screen.blit(surface, (center[0] - cx, center[1] - cy))

    def paint_dead_zombie_body(self, ctx: RenderContext, center: tuple[int, int], effect: dict[str, object], alpha_ratio: float) -> None:
        kind = str(effect.get("kind", "walker"))
        spec = ZOMBIES.get(kind, ZOMBIES["walker"])
        radius = world_size(ctx, spec.radius, 8)
        size = radius * 3 + 28
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        cx = cy = size // 2
        alpha = int(255 * alpha_ratio)
        tuning = ctx.death_tuning
        dark_alpha = int(float(getattr(tuning, "corpse_dark_alpha", 160)) * alpha_ratio)
        outline_alpha = int(float(getattr(tuning, "corpse_outline_alpha", 190)) * alpha_ratio)
        pygame.draw.ellipse(surface, (0, 0, 0, int(86 * alpha_ratio)), pygame.Rect(cx - radius - 8, cy - int(radius * 0.62), radius * 2 + 16, int(radius * 1.24)))
        pygame.draw.circle(surface, (*spec.color, int(96 * alpha_ratio)), (cx, cy), radius)
        pygame.draw.circle(surface, (2, 4, 8, dark_alpha), (cx, cy), radius)
        pygame.draw.circle(surface, (0, 0, 0, outline_alpha), (cx, cy), radius, max(1, world_size(ctx, 3, 1)))
        facing = float(effect.get("facing", 0.0))
        nose = (int(cx + math.cos(facing) * radius * 0.78), int(cy + math.sin(facing) * radius * 0.78))
        pygame.draw.line(surface, (18, 0, 4, alpha), (cx, cy), nose, max(2, world_size(ctx, 5, 2)))
        ctx.screen.blit(surface, (center[0] - cx, center[1] - cy))

    def paint_dead_player_cross(self, ctx: RenderContext, center: tuple[int, int], alpha_ratio: float, alpha: int) -> None:
        tuning = ctx.death_tuning
        size = world_size(ctx, float(getattr(tuning, "player_cross_size", 30.0)), 18)
        width = world_size(ctx, float(getattr(tuning, "player_cross_width", 6.0)), 3)
        surface_size = size * 2 + 18
        surface = pygame.Surface((surface_size, surface_size), pygame.SRCALPHA)
        cx = cy = surface_size // 2
        pygame.draw.circle(surface, (80, 0, 8, int(90 * alpha_ratio)), (cx, cy), max(10, int(size * 0.62)))
        pygame.draw.line(surface, (10, 10, 14, alpha), (cx - size, cy - size), (cx + size, cy + size), width)
        pygame.draw.line(surface, (10, 10, 14, alpha), (cx - size, cy + size), (cx + size, cy - size), width)
        ctx.screen.blit(surface, (center[0] - cx, center[1] - cy))

    def paint_explosion_effects(self, ctx: RenderContext) -> None:
        if not ctx.effects:
            return
        if ctx.quality and ctx.quality.effects_quality <= 0.3:
            return
        now = ctx.now or 0.0
        effects = ctx.effects.explosion_effects
        if ctx.quality:
            effects = effects[: max(1, int(len(effects) * ctx.quality.effects_quality))]
        for fx in effects:
            if ctx.local_player and int(fx.get("floor", 0)) != ctx.local_player.floor:
                continue
            pos = fx.get("pos")
            if not isinstance(pos, Vec2):
                continue
            sx, sy = world_to_screen(ctx, pos)
            radius = world_size(ctx, float(fx.get("radius", 120.0)), 1)
            duration = max(0.01, float(fx.get("duration", 0.34)))
            age = max(0.0, min(1.0, (now - float(fx.get("start", now))) / duration))
            spike = 1.0 - age
            color = fx.get("color", (255, 168, 118))
            if not isinstance(color, tuple):
                color = (255, 168, 118)
            flash_radius = int(radius * (0.18 + age * 0.86))
            blast = pygame.Surface((flash_radius * 2 + 48, flash_radius * 2 + 48), pygame.SRCALPHA)
            center = (blast.get_width() // 2, blast.get_height() // 2)
            pygame.draw.circle(blast, (*color, int(84 * spike)), center, max(12, flash_radius))
            pygame.draw.circle(blast, (255, 238, 210, int(120 * spike)), center, max(8, int(flash_radius * 0.55)))
            pygame.draw.circle(blast, (*color, int(66 * spike)), center, max(10, int(flash_radius * 1.16)), 2)
            ctx.screen.blit(blast, (sx - center[0], sy - center[1]))

