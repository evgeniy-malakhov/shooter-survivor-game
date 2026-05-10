from __future__ import annotations

import math

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.ui.minimap_renderer import MinimapRenderer
from client.render.world.render_utils import draw_item_icon, draw_text_fit


class StatusRenderer:
    def __init__(self, minimap: MinimapRenderer) -> None:
        self.minimap = minimap

    def render(self, ctx: RenderContext, *, connection_quality: str = "stable-connection", error: str = "") -> None:
        if ctx.snapshot and ctx.settings.get("show_zombie_count", False):
            self.paint_zombie_counter(ctx)
        if ctx.snapshot:
            self.paint_threat_level(ctx)
        if ctx.online_player_id:
            self.paint_connection_status(ctx, connection_quality)
            self.paint_network_notice(ctx, connection_quality, error)

    def paint_zombie_counter(self, ctx: RenderContext) -> None:
        if not ctx.snapshot or not ctx.text or not ctx.fonts:
            return
        minimap = self.minimap.rect(ctx)
        rect = pygame.Rect(minimap.x, minimap.bottom + 12, minimap.w, 42)
        pulse = (math.sin((ctx.now or 0.0) * 3.6) + 1.0) * 0.5
        bg = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (20, 13, 24, 220), bg.get_rect(), border_radius=9)
        pygame.draw.rect(bg, (255, 91, 111, int(110 + pulse * 70)), bg.get_rect(), 2, border_radius=9)
        ctx.screen.blit(bg, rect)
        icon_rect = pygame.Rect(rect.x + 12, rect.y + 8, 26, 26)
        if not draw_item_icon(ctx, "dead", icon_rect, aura=False, shadow=False):
            pygame.draw.circle(ctx.screen, palette.RED, icon_rect.center, 10)
        draw_text_fit(ctx, ctx.text.tr("hud.zombies"), pygame.Rect(rect.x + 44, rect.y + 7, rect.w - 96, 15), palette.MUTED, ctx.fonts.small)
        draw_text_fit(ctx, str(len(ctx.snapshot.zombies)), pygame.Rect(rect.right - 58, rect.y + 5, 42, 30), palette.RED, ctx.fonts.mid, center=True)

    def paint_threat_level(self, ctx: RenderContext) -> None:
        if not ctx.snapshot or not ctx.fonts or not ctx.local_player:
            return
        threat = 0.0
        player = ctx.local_player
        for zone in getattr(ctx.snapshot, "horde_pressure_zones", {}).values():
            if not isinstance(zone, dict):
                zone = zone.to_dict()
            if int(zone.get("floor", 0)) != player.floor:
                continue
            center_raw = zone.get("center")
            if not isinstance(center_raw, dict):
                continue
            dx = float(center_raw.get("x", 0.0)) - player.pos.x
            dy = float(center_raw.get("y", 0.0)) - player.pos.y
            distance = math.hypot(dx, dy)
            radius = max(1.0, float(zone.get("radius", 900.0)) * 1.8)
            local = float(zone.get("pressure", 0.0)) * max(0.0, 1.0 - distance / radius)
            threat = max(threat, local)
        minimap = self.minimap.rect(ctx)
        rect = pygame.Rect(minimap.x, minimap.bottom + 60, minimap.w, 50)
        color = palette.GREEN if threat < 0.3 else palette.YELLOW if threat < 0.65 else palette.RED
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(surface, (12, 16, 26, 216), surface.get_rect(), border_radius=8)
        pygame.draw.rect(surface, (*color, 170), surface.get_rect(), 1, border_radius=8)
        fill = pygame.Rect(8, rect.h - 10, max(4, int((rect.w - 16) * max(0.0, min(1.0, threat)))), 4)
        pygame.draw.rect(surface, (*color, 160), fill, border_radius=2)
        ctx.screen.blit(surface, rect)
        threat_text = ctx.text.tr("hud.threat", value=int(threat * 100)) if ctx.text else f"Threat {int(threat * 100):02d}%"
        draw_text_fit(ctx, threat_text, pygame.Rect(rect.x + 10, rect.y + 6, rect.w - 20, 14), color, ctx.fonts.small, center=True)
        radio_key = "hud.radio.clear" if threat < 0.3 else "hud.radio.movement" if threat < 0.65 else "hud.radio.horde"
        radio = ctx.text.tr(radio_key) if ctx.text else radio_key
        squad = sum(1 for soldier in ctx.snapshot.soldiers.values() if soldier.floor == player.floor)
        escalation = self._local_escalation(ctx)
        tactical = self._tactical_summary(ctx)
        suffix = f"  {escalation}" if escalation else ""
        if tactical:
            suffix = f"{suffix}  {tactical}"
        squad_text = ctx.text.tr("hud.squad_count", count=squad) if ctx.text else f"Squad {squad}"
        draw_text_fit(ctx, f"{radio}  {squad_text}{suffix}", pygame.Rect(rect.x + 10, rect.y + 23, rect.w - 20, 13), palette.MUTED, ctx.fonts.small, center=True)

    def _local_escalation(self, ctx: RenderContext) -> str:
        if not ctx.snapshot:
            return ""
        best = None
        best_score = -1.0
        for state in getattr(ctx.snapshot, "battle_escalation", {}).values():
            data = state if isinstance(state, dict) else state.to_dict()
            score = float(data.get("score", 0.0))
            if score > best_score:
                best = data
                best_score = score
        if not best:
            return ""
        level_raw = str(best.get("level", "calm"))
        owner_raw = str(best.get("territory_owner", "neutral"))
        if ctx.text:
            level = ctx.text.tr(f"ecosystem.level.{level_raw}")
            owner = ctx.text.tr(f"ecosystem.owner.{owner_raw}")
        else:
            level = level_raw.upper()
            owner = owner_raw
        return f"{level}/{owner}"

    def _tactical_summary(self, ctx: RenderContext) -> str:
        if not ctx.snapshot or not ctx.text:
            return ""
        missions = sum(1 for mission in getattr(ctx.snapshot, "missions", {}).values() if str((mission if isinstance(mission, dict) else mission.to_dict()).get("status", "")) in {"available", "active"})
        extractions = sum(1 for point in getattr(ctx.snapshot, "extraction_points", {}).values() if str((point if isinstance(point, dict) else point.to_dict()).get("status", "closed")) != "closed")
        director = getattr(ctx.snapshot, "director", {}) or {}
        pressure = str(director.get("pressure", "")) if isinstance(director, dict) else ""
        pieces: list[str] = []
        if missions:
            pieces.append(ctx.text.tr("hud.missions_count", count=missions))
        if extractions:
            pieces.append(ctx.text.tr("hud.extractions_count", count=extractions))
        if pressure:
            pieces.append(ctx.text.tr(f"director.pressure.{pressure}"))
        return " ".join(pieces)

    def paint_connection_status(self, ctx: RenderContext, quality: str) -> None:
        if quality == "stable-connection":
            return
        minimap = self.minimap.rect(ctx)
        rect = pygame.Rect(minimap.x - 54, minimap.y + 8, 38, 38)
        color = {
            "stable-connection": palette.GREEN,
            "unstable-connection": palette.YELLOW,
            "packet-lost": palette.RED,
            "lost-connection": palette.RED,
        }.get(quality, palette.MUTED)
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(surface, (10, 16, 28, 206), surface.get_rect(), border_radius=8)
        pygame.draw.rect(surface, (*color, 170), surface.get_rect(), 1, border_radius=8)
        ctx.screen.blit(surface, rect)
        icon_rect = pygame.Rect(rect.x + 7, rect.y + 7, 24, 24)
        if not draw_item_icon(ctx, quality, icon_rect, aura=False, shadow=False):
            pygame.draw.circle(ctx.screen, color, icon_rect.center, 8)

    def paint_network_notice(self, ctx: RenderContext, quality: str, error: str) -> None:
        if not ctx.text or not ctx.fonts:
            return
        if quality == "stable-connection" and not error:
            return
        color = {"unstable-connection": palette.YELLOW, "packet-lost": palette.RED, "lost-connection": palette.RED}.get(quality, palette.CYAN)
        key = {
            "unstable-connection": "online.notice.unstable",
            "packet-lost": "online.notice.packet_loss",
            "lost-connection": "online.notice.lost",
        }.get(quality, "online.notice.reconnecting")
        text = error if error and quality == "lost-connection" else ctx.text.tr(key)
        rect = pygame.Rect(0, 0, 420, 38)
        rect.center = (ctx.screen.get_width() // 2, 34)
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(surface, (9, 14, 26, 220), surface.get_rect(), border_radius=10)
        pygame.draw.rect(surface, (*color, 180), surface.get_rect(), 1, border_radius=10)
        ctx.screen.blit(surface, rect)
        icon_rect = pygame.Rect(rect.x + 14, rect.y + 7, 24, 24)
        if not draw_item_icon(ctx, quality, icon_rect, aura=False, shadow=False):
            pygame.draw.circle(ctx.screen, color, icon_rect.center, 8)
        draw_text_fit(ctx, text, pygame.Rect(rect.x + 46, rect.y + 9, rect.w - 62, 18), palette.TEXT, ctx.fonts.small, center=True)

