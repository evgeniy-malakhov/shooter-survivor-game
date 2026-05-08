from __future__ import annotations

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from client.render.world.render_utils import world_to_screen


class ContextPromptRenderer:
    def render(self, ctx: RenderContext) -> None:
        snapshot = ctx.snapshot
        player = ctx.local_player
        if not snapshot or not player or not player.alive or not ctx.text or not ctx.fonts:
            return
        prompt = ""
        for building in snapshot.buildings.values():
            for door in building.doors:
                if door.floor == player.floor and door.rect.center.distance_to(player.pos) <= 86:
                    prompt = ctx.text.tr("prompt.close_door") if door.open else ctx.text.tr("prompt.open_door")
            for stairs in building.stairs:
                if stairs.inflated(60).contains(player.pos):
                    prompt = f"{ctx.text.tr('prompt.stairs')} ({ctx.text.floor_label(player.floor)})"
            for prop in building.props:
                if prop.floor != player.floor:
                    continue
                if prop.rect.center.distance_to(player.pos) <= 92 and prop.kind == "work_bench":
                    prompt = ctx.text.tr("prompt.craft")
                elif prop.rect.center.distance_to(player.pos) <= 92 and prop.kind == "repair_table":
                    prompt = ctx.text.tr("prompt.repair")
        for item in snapshot.loot.values():
            if item.floor == player.floor and item.pos.distance_to(player.pos) <= 72:
                prompt = ctx.text.tr("prompt.pickup", item=ctx.text.loot_label(item))
                break
        if not prompt:
            return
        sx, sy = world_to_screen(ctx, player.pos)
        label = ctx.text_cache.render(ctx.fonts.normal, prompt, palette.TEXT) if ctx.text_cache else ctx.fonts.normal.render(prompt, True, palette.TEXT)
        bg = label.get_rect(center=(sx, sy - 72)).inflate(22, 12)
        pygame.draw.rect(ctx.screen, palette.PANEL, bg, border_radius=7)
        pygame.draw.rect(ctx.screen, palette.CYAN, bg, 1, border_radius=7)
        ctx.screen.blit(label, label.get_rect(center=bg.center))

