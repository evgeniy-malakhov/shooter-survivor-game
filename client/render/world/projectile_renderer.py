from __future__ import annotations

import math

import pygame

from client.render.render_context import RenderContext
from client.render.render_frame import RenderFrame
from client.render.world.render_utils import world_size, world_to_screen


class ProjectileRenderer:
    def render(self, ctx: RenderContext, frame: RenderFrame) -> None:
        for projectile in frame.projectiles:
            sx, sy = world_to_screen(ctx, projectile.pos)
            tail = projectile.pos.copy()
            tail.x -= projectile.velocity.x * 0.025
            tail.y -= projectile.velocity.y * 0.025
            tx, ty = world_to_screen(ctx, tail)
            pygame.draw.line(ctx.screen, (255, 244, 170), (tx, ty), (sx, sy), world_size(ctx, 4, 2))
            pygame.draw.circle(ctx.screen, (255, 255, 255), (sx, sy), world_size(ctx, projectile.radius, 2))

        for pool in frame.poison_pools:
            sx, sy = world_to_screen(ctx, pool.pos)
            radius = world_size(ctx, pool.radius * (0.72 + 0.12 * math.sin(frame.snapshot.time * 6.0 + sx)), 8)
            pool_surface = pygame.Surface((radius * 2 + 20, radius * 2 + 20), pygame.SRCALPHA)
            center = (pool_surface.get_width() // 2, pool_surface.get_height() // 2)
            pygame.draw.circle(pool_surface, (64, 255, 106, 64), center, radius)
            pygame.draw.circle(pool_surface, (170, 255, 140, 92), center, max(8, radius // 2), 2)
            ctx.screen.blit(pool_surface, (sx - center[0], sy - center[1]))

        for spit in frame.poison_projectiles:
            sx, sy = world_to_screen(ctx, spit.pos)
            pygame.draw.circle(ctx.screen, (28, 68, 24), (sx, sy), world_size(ctx, 13, 6))
            pygame.draw.circle(ctx.screen, (104, 255, 112), (sx, sy), world_size(ctx, 8, 4))
            pygame.draw.circle(ctx.screen, (220, 255, 180), (sx - 2, sy - 2), world_size(ctx, 3, 2))

