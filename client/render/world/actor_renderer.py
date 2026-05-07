from __future__ import annotations

import math

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.render_frame import ActorRenderItem, RenderFrame, RenderLOD
from client.render.world.render_utils import (
    draw_bar,
    draw_text,
    has_active_flashlight,
    world_size,
    world_to_screen,
)
from shared.constants import SOLDIERS, ZOMBIES
from shared.models import PlayerState
from shared.weapon_modules import WEAPON_MODULES


class ActorRenderer:
    def render(self, ctx: RenderContext, frame: RenderFrame) -> None:
        started = math.nan
        if ctx.perf:
            import time
            started = time.perf_counter()
        self.paint_zombies(ctx, frame)
        self.paint_players(ctx, frame)
        self.paint_soldiers(ctx, frame)
        self.paint_weapon_utilities(ctx, frame)
        if ctx.local_player:
            self.paint_tunnel_darkness(ctx, ctx.local_player)
        if ctx.perf:
            import time
            ctx.perf.actors_ms = (time.perf_counter() - started) * 1000.0

    def lod(self, frame: RenderFrame, prefix: str, entity_id: str) -> RenderLOD:
        return frame.actor_lod.get(f"{prefix}:{entity_id}", RenderLOD.FULL)

    def screen_pos(self, ctx: RenderContext, item: ActorRenderItem) -> tuple[int, int]:
        return ctx.camera_controller.world_to_screen_xy(item.x, item.y, ctx.camera)

    def paint_actor_dot(self, ctx: RenderContext, center: tuple[int, int], color: tuple[int, int, int], radius: int = 4) -> None:
        pygame.draw.circle(ctx.screen, (4, 7, 13), center, radius + 2)
        pygame.draw.circle(ctx.screen, color, center, radius)
        pygame.draw.circle(ctx.screen, palette.TEXT, center, radius, 1)

    def paint_zombies(self, ctx: RenderContext, frame: RenderFrame) -> None:
        for zombie in frame.actors:
            if zombie.actor_type != "zombie":
                continue
            spec = ZOMBIES.get(zombie.kind, ZOMBIES["walker"])
            sx, sy = self.screen_pos(ctx, zombie)
            if not (-80 <= sx <= ctx.screen.get_width() + 80 and -80 <= sy <= ctx.screen.get_height() + 80):
                continue
            lod = zombie.lod
            if lod == RenderLOD.DOT:
                self.paint_actor_dot(ctx, (sx, sy), zombie.color, 3)
                continue
            if lod == RenderLOD.FULL and ctx.settings.get("bot_vision") and (ctx.settings.get("bot_vision_range") or zombie.mode in {"chase", "investigate", "search"}):
                cone_len = spec.sight_range if ctx.settings.get("bot_vision_range") else min(spec.sight_range, 160)
                cone_len_screen = world_size(ctx, cone_len, 1)
                left = zombie.facing - math.radians(spec.fov_degrees * 0.5)
                right = zombie.facing + math.radians(spec.fov_degrees * 0.5)
                points = [
                    (sx, sy),
                    (int(sx + math.cos(left) * cone_len_screen), int(sy + math.sin(left) * cone_len_screen)),
                    (int(sx + math.cos(right) * cone_len_screen), int(sy + math.sin(right) * cone_len_screen)),
                ]
                cone = pygame.Surface((ctx.screen.get_width(), ctx.screen.get_height()), pygame.SRCALPHA)
                alpha = 18 if ctx.settings.get("bot_vision_range") else 34
                pygame.draw.polygon(cone, (*spec.color, alpha), points)
                pygame.draw.arc(
                    cone,
                    (*spec.color, 68),
                    pygame.Rect(sx - cone_len_screen, sy - cone_len_screen, cone_len_screen * 2, cone_len_screen * 2),
                    -right,
                    -left,
                    1,
                )
                ctx.screen.blit(cone, (0, 0))
            radius = world_size(ctx, zombie.radius, 8)
            pygame.draw.circle(ctx.screen, (12, 18, 28), (sx, sy), world_size(ctx, zombie.radius + 8, radius + 4))
            pygame.draw.circle(ctx.screen, zombie.color, (sx, sy), radius)
            pygame.draw.circle(ctx.screen, (255, 255, 255), (sx, sy), radius, 2)
            if lod == RenderLOD.SIMPLE:
                if ctx.settings.get("health_bars"):
                    draw_bar(ctx, pygame.Rect(sx - 16, sy - radius - 10, 32, 4), zombie.hp_ratio, palette.RED)
                continue
            nose_len = world_size(ctx, zombie.radius + 12, radius + 4)
            nose = (int(sx + math.cos(zombie.facing) * nose_len), int(sy + math.sin(zombie.facing) * nose_len))
            pygame.draw.line(ctx.screen, palette.TEXT, (sx, sy), nose, 2)
            if ctx.settings.get("health_bars"):
                draw_bar(ctx, pygame.Rect(sx - 24, sy - radius - 15, 48, 5), zombie.hp_ratio, palette.RED)
                if zombie.armor_ratio > 0:
                    draw_bar(ctx, pygame.Rect(sx - 24, sy - radius - 8, 48, 4), zombie.armor_ratio, palette.CYAN)
            if ctx.settings.get("ai_reactions"):
                mode_color = palette.RED if zombie.mode == "chase" else palette.YELLOW if zombie.mode in {"investigate", "search"} else palette.MUTED
                draw_text(ctx, zombie.mode, sx - 22, sy + radius + 8, mode_color, ctx.fonts.small if ctx.fonts else None)

    def paint_players(self, ctx: RenderContext, frame: RenderFrame) -> None:
        for player in frame.actors:
            if player.actor_type != "player":
                continue
            sx, sy = self.screen_pos(ctx, player)
            if player.is_dead:
                if not self._has_death_effect(ctx, "player", player.id):
                    self.paint_dead_player_cross(ctx, (sx, sy), 1.0, 210)
                continue
            lod = player.lod
            color = player.color
            if lod == RenderLOD.DOT:
                self.paint_actor_dot(ctx, (sx, sy), color, 4)
                continue
            body_radius = world_size(ctx, 24, 12)
            pygame.draw.circle(ctx.screen, (4, 8, 14), (sx, sy), world_size(ctx, 31, body_radius + 4))
            pygame.draw.circle(ctx.screen, color, (sx, sy), body_radius)
            pygame.draw.circle(ctx.screen, palette.TEXT, (sx, sy), body_radius, 2)
            if lod == RenderLOD.SIMPLE:
                continue
            muzzle_len = world_size(ctx, 42, 22)
            muzzle = (int(sx + math.cos(player.facing) * muzzle_len), int(sy + math.sin(player.facing) * muzzle_len))
            pygame.draw.line(ctx.screen, palette.TEXT, (sx, sy), muzzle, world_size(ctx, 5, 2))
            draw_text(ctx, player.label, sx - 28, sy - 48, palette.TEXT, ctx.fonts.small if ctx.fonts else None)

    def paint_soldiers(self, ctx: RenderContext, frame: RenderFrame) -> None:
        for soldier in frame.actors:
            if soldier.actor_type != "soldier":
                continue
            spec = SOLDIERS.get(soldier.kind)
            if not spec:
                continue
            sx, sy = self.screen_pos(ctx, soldier)
            if not (-80 <= sx <= ctx.screen.get_width() + 80 and -80 <= sy <= ctx.screen.get_height() + 80):
                continue
            lod = soldier.lod
            if lod == RenderLOD.DOT:
                self.paint_actor_dot(ctx, (sx, sy), soldier.color, 4)
                continue
            radius = world_size(ctx, soldier.radius, 9)
            points = []
            for i in range(5):
                angle = soldier.facing - math.pi / 2 + math.tau * i / 5
                scale = 1.25 if i == 0 else 1.0
                points.append((int(sx + math.cos(angle) * radius * scale), int(sy + math.sin(angle) * radius * scale)))
            pygame.draw.polygon(ctx.screen, (7, 12, 22), [(x + 2, y + 2) for x, y in points])
            pygame.draw.polygon(ctx.screen, (44, 124, 255), points)
            pygame.draw.polygon(ctx.screen, (184, 220, 255), points, 2)
            if lod == RenderLOD.SIMPLE:
                if ctx.settings.get("health_bars"):
                    draw_bar(ctx, pygame.Rect(sx - 16, sy - radius - 10, 32, 4), soldier.hp_ratio, palette.GREEN)
                continue
            muzzle_len = world_size(ctx, soldier.radius + 18, radius + 8)
            muzzle = (int(sx + math.cos(soldier.facing) * muzzle_len), int(sy + math.sin(soldier.facing) * muzzle_len))
            pygame.draw.line(ctx.screen, (210, 235, 255), (sx, sy), muzzle, 2)
            if ctx.settings.get("health_bars"):
                draw_bar(ctx, pygame.Rect(sx - 24, sy - radius - 15, 48, 5), soldier.hp_ratio, palette.GREEN)
                if soldier.armor_ratio > 0:
                    draw_bar(ctx, pygame.Rect(sx - 24, sy - radius - 8, 48, 4), soldier.armor_ratio, palette.CYAN)
            if ctx.settings.get("ai_reactions"):
                draw_text(ctx, soldier.mode, sx - 24, sy + radius + 8, palette.CYAN, ctx.fonts.small if ctx.fonts else None)

    def paint_weapon_utilities(self, ctx: RenderContext, frame: RenderFrame) -> None:
        for player in frame.players:
            if self.lod(frame, "player", player.id) != RenderLOD.FULL:
                continue
            weapon = player.active_weapon()
            if not weapon or not weapon.utility_on:
                continue
            utility = weapon.modules.get("utility")
            sx, sy = world_to_screen(ctx, player.pos)
            if utility == "laser_module":
                module = WEAPON_MODULES.get(utility)
                length = world_size(ctx, module.beam_length if module else 720, 1)
                end = (int(sx + math.cos(player.angle) * length), int(sy + math.sin(player.angle) * length))
                laser = pygame.Surface((ctx.screen.get_width(), ctx.screen.get_height()), pygame.SRCALPHA)
                pygame.draw.line(laser, (255, 64, 88, 76), (sx, sy), end, world_size(ctx, 5, 2))
                pygame.draw.line(laser, (255, 210, 220, 138), (sx, sy), end, 1)
                pygame.draw.circle(laser, (255, 68, 92, 150), end, world_size(ctx, 4, 2))
                ctx.screen.blit(laser, (0, 0))
            elif utility == "flashlight_module":
                self.paint_flashlight_cone(ctx, player, soft=True)

    def paint_flashlight_cone(self, ctx: RenderContext, player: PlayerState, *, soft: bool) -> None:
        module = WEAPON_MODULES.get("flashlight_module")
        cone_range = world_size(ctx, module.cone_range if module else 620, 1)
        half_angle = math.radians((module.cone_degrees if module else 58) * 0.5)
        sx, sy = world_to_screen(ctx, player.pos)
        cone = pygame.Surface((ctx.screen.get_width(), ctx.screen.get_height()), pygame.SRCALPHA)
        flicker = 0.95 + 0.05 * math.sin((ctx.now or 0.0) * 33.0 + player.pos.x * 0.0017)
        layers = 13 if soft else 6
        for index in range(layers, 0, -1):
            ratio = index / layers
            distance = int(cone_range * ratio * flicker)
            spread = half_angle * (0.68 + 0.32 * ratio)
            alpha = int((56 if soft else 124) * (1.0 - ratio * 0.58) * flicker)
            points = [
                (sx, sy),
                (int(sx + math.cos(player.angle - spread) * distance), int(sy + math.sin(player.angle - spread) * distance)),
                (int(sx + math.cos(player.angle + spread) * distance), int(sy + math.sin(player.angle + spread) * distance)),
            ]
            pygame.draw.polygon(cone, (255, 236, 164, max(8, alpha)), points)
        hot_radius = world_size(ctx, 108, 22)
        pygame.draw.circle(cone, (255, 248, 196, 62), (sx, sy), hot_radius)
        pygame.draw.circle(cone, (255, 255, 236, 36), (sx, sy), max(12, int(hot_radius * 0.46)))
        ctx.screen.blit(cone, (0, 0))

    def paint_tunnel_darkness(self, ctx: RenderContext, player: PlayerState) -> None:
        if player.floor >= 0:
            return
        active_flashlight = has_active_flashlight(player)
        darkness = pygame.Surface((ctx.screen.get_width(), ctx.screen.get_height()), pygame.SRCALPHA)
        darkness.fill((0, 0, 0, 228 if not active_flashlight else 198))
        if active_flashlight:
            module = WEAPON_MODULES.get("flashlight_module")
            cone_range = world_size(ctx, module.cone_range if module else 620, 1)
            half_angle = math.radians((module.cone_degrees if module else 58) * 0.5)
            sx, sy = world_to_screen(ctx, player.pos)
            light = pygame.Surface((ctx.screen.get_width(), ctx.screen.get_height()), pygame.SRCALPHA)
            flicker = 0.94 + 0.06 * math.sin((ctx.now or 0.0) * 32.0 + player.pos.y * 0.0021)
            for index in range(14, 0, -1):
                ratio = index / 14
                distance = int(cone_range * ratio * flicker)
                spread = half_angle * (0.66 + 0.34 * ratio)
                alpha = int(170 * (1.0 - ratio * 0.68) * flicker)
                points = [
                    (sx, sy),
                    (int(sx + math.cos(player.angle - spread) * distance), int(sy + math.sin(player.angle - spread) * distance)),
                    (int(sx + math.cos(player.angle + spread) * distance), int(sy + math.sin(player.angle + spread) * distance)),
                ]
                pygame.draw.polygon(light, (0, 0, 0, max(8, alpha)), points)
            pygame.draw.circle(light, (0, 0, 0, 126), (sx, sy), world_size(ctx, 142, 24))
            darkness.blit(light, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
        ctx.screen.blit(darkness, (0, 0))
        if ctx.text:
            label = ctx.text.tr("hud.dark_flashlight" if not active_flashlight else "hud.dark")
            badge = pygame.Rect(ctx.screen.get_width() - 288, ctx.screen.get_height() - 126, 260, 34)
            pygame.draw.rect(ctx.screen, palette.PANEL, badge, border_radius=7)
            pygame.draw.rect(ctx.screen, palette.YELLOW if not active_flashlight else palette.CYAN, badge, 1, border_radius=7)
            from client.render.world.render_utils import draw_text_fit
            draw_text_fit(ctx, label, badge.inflate(-16, -8), palette.TEXT, ctx.fonts.small if ctx.fonts else None, center=True)

    def _has_death_effect(self, ctx: RenderContext, entity_type: str, entity_id: str) -> bool:
        if not ctx.effects:
            return False
        key = f"{entity_type}:{entity_id}"
        now = ctx.now or 0.0
        corpse_seconds = float(getattr(ctx.death_tuning, "corpse_seconds", 5.0))
        return any(
            str(effect.get("key", "")) == key
            and now - float(effect.get("started", now)) <= corpse_seconds
            for effect in ctx.effects.death_effects
        )

    def paint_dead_player_cross(self, ctx: RenderContext, center: tuple[int, int], alpha_ratio: float, alpha: int) -> None:
        size = world_size(ctx, 30.0, 18)
        width = world_size(ctx, 6.0, 3)
        surface_size = size * 2 + 18
        surface = pygame.Surface((surface_size, surface_size), pygame.SRCALPHA)
        cx = cy = surface_size // 2
        pygame.draw.circle(surface, (80, 0, 8, int(90 * alpha_ratio)), (cx, cy), max(10, int(size * 0.62)))
        pygame.draw.line(surface, (10, 10, 14, alpha), (cx - size, cy - size), (cx + size, cy + size), width)
        pygame.draw.line(surface, (10, 10, 14, alpha), (cx - size, cy + size), (cx + size, cy - size), width)
        ctx.screen.blit(surface, (center[0] - cx, center[1] - cy))
