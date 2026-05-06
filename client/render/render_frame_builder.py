from __future__ import annotations

import pygame

from client.core.perf import ClientPerfStats
from client.visibility.render_culling import point_visible, rect_visible
from shared.level import tunnel_segments
from shared.models import PlayerState, WorldSnapshot

from client.render.render_frame import RenderFrame


class RenderFrameBuilder:
    def __init__(self, margin: float = 360.0) -> None:
        self.margin = margin

    def build(
        self,
        snapshot: WorldSnapshot,
        view: pygame.Rect,
        local_player: PlayerState | None,
        perf: ClientPerfStats | None = None,
    ) -> RenderFrame:
        floor = local_player.floor if local_player else None

        def same_floor(entity) -> bool:
            return floor is None or int(getattr(entity, "floor", 0)) == floor

        buildings = tuple(
            building
            for building in snapshot.buildings.values()
            if rect_visible(building.bounds, view, self.margin)
        )
        tunnels = tuple(
            tunnel
            for tunnel in tunnel_segments(snapshot.buildings)
            if rect_visible(tunnel, view, self.margin)
        )
        loot = tuple(
            item
            for item in snapshot.loot.values()
            if same_floor(item) and point_visible(item.pos, view, self.margin)
        )
        projectiles = tuple(
            item
            for item in snapshot.projectiles.values()
            if same_floor(item) and point_visible(item.pos, view, self.margin)
        )
        grenades = tuple(
            item
            for item in snapshot.grenades.values()
            if same_floor(item) and point_visible(item.pos, view, self.margin)
        )
        mines = tuple(
            item
            for item in snapshot.mines.values()
            if same_floor(item) and point_visible(item.pos, view, self.margin)
        )
        poison_projectiles = tuple(
            item
            for item in snapshot.poison_projectiles.values()
            if same_floor(item) and point_visible(item.pos, view, self.margin)
        )
        poison_pools = tuple(
            item
            for item in snapshot.poison_pools.values()
            if same_floor(item) and point_visible(item.pos, view, self.margin)
        )
        zombies = tuple(
            item
            for item in snapshot.zombies.values()
            if same_floor(item) and point_visible(item.pos, view, self.margin * 2.2)
        )
        soldiers = tuple(
            item
            for item in snapshot.soldiers.values()
            if same_floor(item) and point_visible(item.pos, view, self.margin * 2.2)
        )
        players = tuple(
            item
            for item in snapshot.players.values()
            if same_floor(item) and point_visible(item.pos, view, self.margin)
        )

        if perf:
            perf.visible_players = len(players)
            perf.visible_zombies = len(zombies)
            perf.visible_soldiers = len(soldiers)
            perf.visible_loot = len(loot)

        return RenderFrame(
            snapshot=snapshot,
            buildings=buildings,
            tunnels=tunnels,
            loot=loot,
            projectiles=projectiles,
            grenades=grenades,
            mines=mines,
            poison_projectiles=poison_projectiles,
            poison_pools=poison_pools,
            zombies=zombies,
            soldiers=soldiers,
            players=players,
        )

