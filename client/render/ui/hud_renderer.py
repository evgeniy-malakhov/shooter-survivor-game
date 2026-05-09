from __future__ import annotations

import math
import time

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.world.render_utils import (
    client_armor_max,
    draw_bar,
    draw_item_icon,
    draw_mini_durability,
    draw_rarity_badge,
    draw_rarity_frame,
    draw_text,
    draw_text_fit,
)
from shared.constants import SLOTS
from shared.status_effects import STATUS_EFFECTS


class HudRenderer:
    def render(self, ctx: RenderContext) -> None:
        started = time.perf_counter()
        if ctx.snapshot and ctx.local_player:
            self.paint_hud(ctx)
        if ctx.perf:
            ctx.perf.hud_ms = (time.perf_counter() - started) * 1000.0

    def paint_hud(self, ctx: RenderContext) -> None:
        snapshot = ctx.snapshot
        player = ctx.local_player
        if not snapshot or not player or not ctx.fonts or not ctx.text:
            return
        panel = pygame.Rect(18, 18, 348, 132)
        pygame.draw.rect(ctx.screen, palette.PANEL, panel, border_radius=8)
        glow = pygame.Surface((panel.w + 8, panel.h + 8), pygame.SRCALPHA)
        pygame.draw.rect(glow, (66, 118, 182, 28), glow.get_rect(), border_radius=10)
        ctx.screen.blit(glow, (panel.x - 4, panel.y - 4))
        panel_pulse = 0.5 + 0.5 * math.sin(snapshot.time * 3.1)
        pygame.draw.rect(ctx.screen, (80, 140, 210), panel, 1, border_radius=8)
        pulse_glow = pygame.Surface((panel.w + 14, panel.h + 14), pygame.SRCALPHA)
        pygame.draw.rect(pulse_glow, (110, 184, 255, int(58 + panel_pulse * 34)), pulse_glow.get_rect(), 1, border_radius=12)
        ctx.screen.blit(pulse_glow, (panel.x - 7, panel.y - 7))
        draw_text(ctx, player.name, 74, 30, palette.TEXT, ctx.fonts.hud_title)

        critical = player.alive and player.health < 25
        pulse = (math.sin((ctx.now or 0.0) * 8.0) + 1.0) * 0.5 if critical else 0.0
        heart_size = 24 + int(7 * pulse if critical else 0)
        heart_rect = pygame.Rect(43 - heart_size // 2, 79 - heart_size // 2, heart_size, heart_size)
        if critical:
            glow = pygame.Surface((58, 58), pygame.SRCALPHA)
            pygame.draw.circle(glow, (255, 42, 58, int(72 + pulse * 70)), (29, 29), int(18 + pulse * 10))
            ctx.screen.blit(glow, (14, 50))
        if not draw_item_icon(ctx, "heart", heart_rect):
            pygame.draw.circle(ctx.screen, palette.RED, (42, 78), 9)

        health_color = (255, int(72 + pulse * 72), int(82 + pulse * 28)) if critical else palette.RED
        if critical:
            pygame.draw.rect(ctx.screen, (122, 0, 18), pygame.Rect(58, 66, 278, 24), 2, border_radius=7)
        draw_bar(ctx, pygame.Rect(62, 70, 270, 16), player.health / 100.0, health_color)
        if player.poison_left > 0:
            poison_alpha = int(90 + 70 * ((math.sin((ctx.now or 0.0) * 5.5) + 1.0) * 0.5))
            pygame.draw.rect(ctx.screen, (92, 255, 114), pygame.Rect(58, 66, 278, 24), 2, border_radius=7)
            pygame.draw.circle(ctx.screen, (30, 92, 34), (342, 78), 12)
            pygame.draw.circle(ctx.screen, (110, 255, 118, poison_alpha), (342, 78), 8)
        if not draw_item_icon(ctx, "shield", pygame.Rect(31, 92, 24, 24)):
            pygame.draw.rect(ctx.screen, palette.CYAN, pygame.Rect(34, 91, 18, 18), 2, border_radius=3)
        draw_bar(ctx, pygame.Rect(62, 97, 270, 12), player.armor / client_armor_max(player), palette.CYAN)
        draw_text(ctx, f"{ctx.text.tr('hud.score')} {player.score}   {ctx.text.tr('hud.medkits')} {player.medkits}", 34, 116, palette.MUTED, ctx.fonts.small)
        noise_w = min(270, int(player.noise / 900 * 270))
        pygame.draw.rect(ctx.screen, (33, 40, 58), pygame.Rect(62, 134, 270, 5), border_radius=2)
        pygame.draw.rect(ctx.screen, palette.YELLOW if player.sprinting else palette.GREEN, pygame.Rect(62, 134, noise_w, 5), border_radius=2)
        self.paint_status_effects(ctx)

        start_x = 380
        y = ctx.screen.get_height() - 72
        for index, slot in enumerate(SLOTS):
            rect = pygame.Rect(start_x + index * 82, y, 72, 50)
            active = slot == player.active_slot
            pygame.draw.rect(ctx.screen, palette.PANEL_2 if active else palette.PANEL, rect, border_radius=8)
            pygame.draw.rect(ctx.screen, palette.CYAN if active else (47, 61, 91), rect, 2, border_radius=8)
            if active:
                glow = pygame.Surface((rect.w + 10, rect.h + 10), pygame.SRCALPHA)
                alpha = int(52 + (0.5 + 0.5 * math.sin(snapshot.time * 7.0 + index)) * 66)
                pygame.draw.rect(glow, (86, 226, 255, alpha), glow.get_rect(), 2, border_radius=10)
                ctx.screen.blit(glow, (rect.x - 5, rect.y - 5))
            label = slot
            weapon = player.weapons.get(slot)
            quick_item = player.quick_items.get(slot)
            if weapon:
                label = f"{slot} {ctx.text.weapon_title(weapon.key).split()[0]}"
                draw_rarity_frame(ctx, rect, weapon.rarity)
                draw_rarity_badge(ctx, rect, weapon.rarity, compact=True)
                draw_mini_durability(ctx, rect, weapon.durability)
            elif quick_item:
                label = f"{slot} {ctx.text.item_title(quick_item.key).split()[0]}"
                draw_rarity_badge(ctx, rect, quick_item.rarity, compact=True)
                draw_item_icon(ctx, quick_item.key, pygame.Rect(rect.x + 22, rect.y + 6, 28, 28))
            draw_text_fit(ctx, label, rect.inflate(-10, -12), palette.TEXT if weapon or quick_item else palette.MUTED, ctx.fonts.small, center=True)
        self.paint_weapon_widget(ctx)

    def paint_status_effects(self, ctx: RenderContext) -> None:
        player = ctx.local_player
        if not player or not ctx.text or not ctx.fonts:
            return
        effects: list[tuple[str, str, tuple[int, int, int], float]] = []
        if player.poison_left > 0.0:
            effects.append(("poisoned", ctx.text.tr("hud.poisoned"), (95, 220, 122), player.poison_left))
        for key, left in getattr(player, "status_effects", {}).items():
            if left <= 0.0:
                continue
            spec = STATUS_EFFECTS.get(key)
            if not spec:
                continue
            color = (116, 230, 160) if spec.buff else (255, 120, 104)
            effects.append((key, spec.title, color, float(left)))
            if len(effects) >= 5:
                break
        if not effects:
            return
        width = max(180, len(effects) * 76 + 24)
        panel = pygame.Rect((ctx.screen.get_width() - width) // 2, 16, width, 64)
        pygame.draw.rect(ctx.screen, (12, 18, 30), panel, border_radius=10)
        pygame.draw.rect(ctx.screen, (72, 98, 138), panel, 2, border_radius=10)
        pulse = (math.sin((ctx.now or 0.0) * 6.2) + 1.0) * 0.5
        for index, (icon_key, title, color, left_seconds) in enumerate(effects):
            icon_cell = pygame.Rect(panel.x + 14 + index * 76, panel.y + 10, 56, 44)
            pygame.draw.rect(ctx.screen, palette.PANEL, icon_cell, border_radius=9)
            pygame.draw.rect(ctx.screen, color, icon_cell, 2, border_radius=9)
            glow = pygame.Surface(icon_cell.inflate(10, 10).size, pygame.SRCALPHA)
            pygame.draw.rect(glow, (*color, int(24 + pulse * 58)), glow.get_rect(), 1, border_radius=11)
            ctx.screen.blit(glow, icon_cell.inflate(10, 10))
            draw_item_icon(ctx, icon_key, icon_cell.inflate(-11, -8), aura=False, shadow=False)
            draw_text_fit(ctx, f"{left_seconds:.1f}s", pygame.Rect(icon_cell.x, icon_cell.bottom - 14, icon_cell.w, 12), color, ctx.fonts.small, center=True)
            draw_text_fit(ctx, title, pygame.Rect(icon_cell.right + 8, icon_cell.y + 6, panel.right - icon_cell.right - 16, 30), color, ctx.fonts.small)
        if player.notice and player.notice_timer > 0.0:
            text = ctx.text.tr(player.notice)
            alpha = int(90 + min(1.0, player.notice_timer / 0.5) * 120)
            rect = pygame.Rect(0, 0, 430, 42)
            rect.center = (ctx.screen.get_width() // 2, 92)
            surface = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(surface, (20, 24, 36, alpha), surface.get_rect(), border_radius=10)
            pygame.draw.rect(surface, (*palette.YELLOW, min(255, alpha + 30)), surface.get_rect(), 2, border_radius=10)
            ctx.screen.blit(surface, rect)
            draw_text_fit(ctx, text, rect.inflate(-24, -10), palette.TEXT, ctx.fonts.normal, center=True)

    def paint_weapon_widget(self, ctx: RenderContext) -> None:
        player = ctx.local_player
        if not player or not ctx.text or not ctx.fonts:
            return
        weapon = player.active_weapon()
        quick_item = player.quick_items.get(player.active_slot)
        rect = pygame.Rect(22, ctx.screen.get_height() - 168, 300, 86)
        rarity = weapon.rarity if weapon else quick_item.rarity if quick_item else "common"
        from shared.rarities import rarity_color
        accent = rarity_color(rarity) if weapon or quick_item else palette.MUTED
        pulse = (math.sin((ctx.now or 0.0) * 5.6) + 1.0) * 0.5
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(surface, (10, 16, 28, 224), surface.get_rect(), border_radius=11)
        pygame.draw.rect(surface, (*accent, int(130 + pulse * 60)), surface.get_rect(), 2, border_radius=11)
        ctx.screen.blit(surface, rect)
        icon_rect = pygame.Rect(rect.x + 16, rect.y + 14, 58, 58)
        pygame.draw.rect(ctx.screen, (8, 12, 22), icon_rect, border_radius=9)
        if weapon:
            draw_rarity_frame(ctx, icon_rect, weapon.rarity)
            draw_item_icon(ctx, weapon.key, icon_rect.inflate(-9, -12), aura=False)
            title = ctx.text.weapon_title(weapon.key)
            ammo = f"{weapon.ammo_in_mag}/{weapon.reserve_ammo}"
            subtitle = ctx.text.rarity_title(weapon.rarity)
            draw_mini_durability(ctx, pygame.Rect(rect.x + 88, rect.y + 60, 182, 18), weapon.durability)
        elif quick_item:
            draw_item_icon(ctx, quick_item.key, icon_rect.inflate(-10, -10), aura=False)
            title = ctx.text.item_title(quick_item.key)
            ammo = f"x{quick_item.amount}"
            subtitle = ctx.text.rarity_title(quick_item.rarity)
        else:
            title = ctx.text.tr("hud.unarmed")
            ammo = "--"
            subtitle = ctx.text.floor_label(player.floor)
            pygame.draw.circle(ctx.screen, palette.MUTED, icon_rect.center, 14, 2)
        draw_text_fit(ctx, title, pygame.Rect(rect.x + 88, rect.y + 14, 160, 22), palette.TEXT, ctx.fonts.hud_title)
        draw_text_fit(ctx, subtitle, pygame.Rect(rect.x + 88, rect.y + 38, 120, 18), accent, ctx.fonts.small)
        draw_text_fit(ctx, ammo, pygame.Rect(rect.right - 86, rect.y + 52, 64, 24), palette.YELLOW if weapon or quick_item else palette.MUTED, ctx.fonts.hud_value, center=True)

