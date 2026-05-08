from __future__ import annotations

import time
from client.render import palette
from client.render.render_context import RenderContext
from client.render.world.actor_renderer import ActorRenderer
from client.render.world.actor_sprite_cache import ActorSpriteCache
from client.render.world.effect_renderer import EffectRenderer
from client.render.world.explosive_renderer import ExplosiveRenderer
from client.render.world.loot_renderer import LootRenderer
from client.render.world.map_renderer import MapRenderer
from client.render.world.projectile_renderer import ProjectileRenderer
from client.render.world.static_world_cache import StaticWorldChunkCache


class WorldRenderer:
    def __init__(self, static_cache: StaticWorldChunkCache | None = None, actor_sprite_cache: ActorSpriteCache | None = None) -> None:
        self.map_renderer = MapRenderer(static_cache)
        self.loot_renderer = LootRenderer()
        self.projectile_renderer = ProjectileRenderer()
        self.explosive_renderer = ExplosiveRenderer()
        self.actor_renderer = ActorRenderer(actor_sprite_cache)
        self.effect_renderer = EffectRenderer()

    def render(self, ctx: RenderContext) -> None:
        started = time.perf_counter()
        ctx.screen.fill(palette.BG)
        frame = ctx.render_frame
        if not frame:
            if ctx.perf:
                ctx.perf.draw_world_ms = (time.perf_counter() - started) * 1000.0
            return
        self.map_renderer.render(ctx, frame)
        dynamic_started = time.perf_counter()
        self.loot_renderer.render(ctx, frame)
        projectile_started = time.perf_counter()
        self.projectile_renderer.render(ctx, frame)
        if ctx.perf:
            ctx.perf.projectiles_ms = (time.perf_counter() - projectile_started) * 1000.0
        self.explosive_renderer.render(ctx, frame)
        effects_started = time.perf_counter()
        self.effect_renderer.render_blood(ctx)
        self.actor_renderer.render(ctx, frame)
        self.effect_renderer.render_bodies(ctx)
        self.effect_renderer.render(ctx)
        if ctx.perf:
            ctx.perf.effects_ms = (time.perf_counter() - effects_started) * 1000.0
            ctx.perf.world_dynamic_ms = (time.perf_counter() - dynamic_started) * 1000.0
            ctx.perf.draw_world_ms = (time.perf_counter() - started) * 1000.0

