from __future__ import annotations


class FrameScratch:
    def __init__(self) -> None:
        self.visible_buildings: list[object] = []
        self.visible_tunnels: list[object] = []
        self.visible_players: list[object] = []
        self.visible_zombies: list[object] = []
        self.visible_soldiers: list[object] = []
        self.visible_loot: list[object] = []
        self.visible_projectiles: list[object] = []
        self.visible_grenades: list[object] = []
        self.visible_mines: list[object] = []
        self.visible_poison_projectiles: list[object] = []
        self.visible_poison_pools: list[object] = []
        self.spatial_items: list[object] = []
        self.visible_spatial_items: list[object] = []
        self.actor_items: list[object] = []

    def reset(self) -> None:
        self.visible_buildings.clear()
        self.visible_tunnels.clear()
        self.visible_players.clear()
        self.visible_zombies.clear()
        self.visible_soldiers.clear()
        self.visible_loot.clear()
        self.visible_projectiles.clear()
        self.visible_grenades.clear()
        self.visible_mines.clear()
        self.visible_poison_projectiles.clear()
        self.visible_poison_pools.clear()
        self.spatial_items.clear()
        self.visible_spatial_items.clear()
        self.actor_items.clear()

