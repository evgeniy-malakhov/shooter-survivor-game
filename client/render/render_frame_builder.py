from __future__ import annotations

import time

import pygame

from client.core.frame_scratch import FrameScratch
from client.core.perf import ClientPerfStats
from client.visibility.spatial_index import RenderSpatialIndex, RenderSpatialItem
from client.visibility.render_culling import rect_visible
from shared.level import tunnel_segments
from shared.constants import SOLDIERS, ZOMBIES
from shared.models import PlayerState, Vec2, WorldSnapshot

from client.render.render_frame import ActorRenderItem, RenderFrame, RenderLOD


class RenderFrameBuilder:
    def __init__(self, margin: float = 360.0) -> None:
        self.margin = margin
        self.dynamic_index = RenderSpatialIndex(cell_size=512)
        self.scratch = FrameScratch()

    def build(
        self,
        snapshot: WorldSnapshot,
        view: pygame.Rect,
        local_player: PlayerState | None,
        perf: ClientPerfStats | None = None,
    ) -> RenderFrame:
        started = time.perf_counter()
        culling_started = started
        scratch = self.scratch
        scratch.reset()
        floor = local_player.floor if local_player else None
        origin = local_player.pos if local_player else None
        local_player_id = local_player.id if local_player else ""

        def lod_for(prefix: str, entity_id: str, pos: Vec2) -> None:
            if origin is None:
                actor_lod[f"{prefix}:{entity_id}"] = RenderLOD.FULL
                return
            distance = origin.distance_to(pos)
            if distance <= 900.0:
                lod = RenderLOD.FULL
            elif distance <= 1700.0:
                lod = RenderLOD.SIMPLE
            else:
                lod = RenderLOD.DOT
            actor_lod[f"{prefix}:{entity_id}"] = lod

        actor_lod: dict[str, RenderLOD] = {}

        for building in snapshot.buildings.values():
            if rect_visible(building.bounds, view, self.margin):
                scratch.visible_buildings.append(building)
        for tunnel in tunnel_segments(snapshot.buildings):
            if rect_visible(tunnel, view, self.margin):
                scratch.visible_tunnels.append(tunnel)
        spatial_started = time.perf_counter()
        self._fill_dynamic_spatial_items(snapshot, scratch.spatial_items)
        self.dynamic_index.rebuild(scratch.spatial_items)
        query_rect = view.inflate(int(self.margin * 2.0), int(self.margin * 2.0))
        self.dynamic_index.query_into(query_rect, scratch.visible_spatial_items, floor)
        spatial_query_ms = (time.perf_counter() - spatial_started) * 1000.0

        for item in scratch.visible_spatial_items:
            if item.kind == "loot":
                scratch.visible_loot.append(item.ref)
            elif item.kind == "projectile":
                scratch.visible_projectiles.append(item.ref)
            elif item.kind == "grenade":
                scratch.visible_grenades.append(item.ref)
            elif item.kind == "mine":
                scratch.visible_mines.append(item.ref)
            elif item.kind == "poison_projectile":
                scratch.visible_poison_projectiles.append(item.ref)
            elif item.kind == "poison_pool":
                scratch.visible_poison_pools.append(item.ref)
            elif item.kind == "zombie":
                scratch.visible_zombies.append(item.ref)
            elif item.kind == "soldier":
                scratch.visible_soldiers.append(item.ref)
            elif item.kind == "player":
                scratch.visible_players.append(item.ref)

        for zombie in scratch.visible_zombies:
            lod_for("zombie", zombie.id, zombie.pos)
            spec = ZOMBIES.get(zombie.kind, ZOMBIES["walker"])
            scratch.actor_items.append(
                ActorRenderItem(
                    id=zombie.id,
                    actor_type="zombie",
                    kind=zombie.kind,
                    x=zombie.pos.x,
                    y=zombie.pos.y,
                    floor=zombie.floor,
                    hp_ratio=zombie.health / max(1, spec.health),
                    armor_ratio=zombie.armor / max(1, spec.armor),
                    facing=zombie.facing,
                    radius=spec.radius,
                    color=spec.color,
                    lod=actor_lod.get(f"zombie:{zombie.id}", RenderLOD.FULL),
                    is_dead=False,
                    mode=zombie.mode,
                )
            )
        for soldier in scratch.visible_soldiers:
            lod_for("soldier", soldier.id, soldier.pos)
            spec = SOLDIERS.get(soldier.kind)
            if spec:
                scratch.actor_items.append(
                    ActorRenderItem(
                        id=soldier.id,
                        actor_type="soldier",
                        kind=soldier.kind,
                        x=soldier.pos.x,
                        y=soldier.pos.y,
                        floor=soldier.floor,
                        hp_ratio=soldier.health / max(1, spec.health),
                        armor_ratio=soldier.armor / max(1, spec.armor),
                        facing=soldier.facing,
                        radius=spec.radius,
                        color=(44, 124, 255),
                        lod=actor_lod.get(f"soldier:{soldier.id}", RenderLOD.FULL),
                        is_dead=False,
                        mode=soldier.mode,
                    )
                )
        for player in scratch.visible_players:
            lod_for("player", player.id, player.pos)
            scratch.actor_items.append(
                ActorRenderItem(
                    id=player.id,
                    actor_type="player",
                    kind="player",
                    x=player.pos.x,
                    y=player.pos.y,
                    floor=player.floor,
                    hp_ratio=player.health / 100.0,
                    armor_ratio=0.0,
                    facing=player.angle,
                    radius=24.0,
                    color=(76, 225, 255) if player.id == local_player_id else (92, 230, 155),
                    lod=actor_lod.get(f"player:{player.id}", RenderLOD.FULL),
                    is_local=player.id == local_player_id,
                    is_dead=not player.alive,
                    label=player.name,
                )
            )

        buildings = tuple(scratch.visible_buildings)
        tunnels = tuple(scratch.visible_tunnels)
        loot = tuple(scratch.visible_loot)
        projectiles = tuple(scratch.visible_projectiles)
        grenades = tuple(scratch.visible_grenades)
        mines = tuple(scratch.visible_mines)
        poison_projectiles = tuple(scratch.visible_poison_projectiles)
        poison_pools = tuple(scratch.visible_poison_pools)
        zombies = tuple(scratch.visible_zombies)
        soldiers = tuple(scratch.visible_soldiers)
        players = tuple(scratch.visible_players)
        actor_items = tuple(scratch.actor_items)

        if perf:
            perf.snapshot_total_players = len(snapshot.players)
            perf.snapshot_total_zombies = len(snapshot.zombies)
            perf.snapshot_total_soldiers = len(snapshot.soldiers)
            perf.snapshot_total_loot = len(snapshot.loot)
            perf.visible_players = len(players)
            perf.visible_zombies = len(zombies)
            perf.visible_soldiers = len(soldiers)
            perf.visible_loot = len(loot)
            elapsed = (time.perf_counter() - culling_started) * 1000.0
            perf.culling_ms = elapsed
            perf.spatial_query_ms = spatial_query_ms
            perf.render_frame_build_ms = (time.perf_counter() - started) * 1000.0

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
            actor_lod=actor_lod,
            actors=actor_items,
        )

    def _fill_dynamic_spatial_items(self, snapshot: WorldSnapshot, items: list[RenderSpatialItem]) -> None:
        def add_point(kind: str, entity_id: str, entity, radius: int) -> None:
            pos = entity.pos
            floor_value = int(getattr(entity, "floor", 0))
            rect = pygame.Rect(int(pos.x - radius), int(pos.y - radius), radius * 2, radius * 2)
            items.append(RenderSpatialItem(f"{kind}:{entity_id}", kind, rect, floor_value, entity))

        for key, item in snapshot.loot.items():
            add_point("loot", key, item, 28)
        for key, item in snapshot.projectiles.items():
            add_point("projectile", key, item, 18)
        for key, item in snapshot.grenades.items():
            add_point("grenade", key, item, 32)
        for key, item in snapshot.mines.items():
            add_point("mine", key, item, 32)
        for key, item in snapshot.poison_projectiles.items():
            add_point("poison_projectile", key, item, 28)
        for key, item in snapshot.poison_pools.items():
            add_point("poison_pool", key, item, max(36, int(getattr(item, "radius", 36))))
        for key, item in snapshot.zombies.items():
            add_point("zombie", key, item, 48)
        for key, item in snapshot.soldiers.items():
            add_point("soldier", key, item, 48)
        for key, item in snapshot.players.items():
            add_point("player", key, item, 48)
