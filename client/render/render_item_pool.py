from __future__ import annotations

from client.render.render_frame import ActorRenderItem, RenderLOD


class ActorRenderItemPool:
    def __init__(self, max_entries: int = 4096) -> None:
        self.max_entries = max_entries
        self._items: dict[tuple[object, ...], ActorRenderItem] = {}

    def actor(
        self,
        *,
        id: str,
        actor_type: str,
        kind: str,
        x: float,
        y: float,
        floor: int,
        hp_ratio: float,
        armor_ratio: float,
        facing: float,
        radius: float,
        color: tuple[int, int, int],
        lod: RenderLOD,
        is_local: bool = False,
        is_dead: bool = False,
        label: str = "",
        mode: str = "",
    ) -> ActorRenderItem:
        key = (
            id,
            actor_type,
            kind,
            round(x, 2),
            round(y, 2),
            floor,
            round(hp_ratio, 3),
            round(armor_ratio, 3),
            round(facing, 3),
            radius,
            color,
            lod,
            is_local,
            is_dead,
            label,
            mode,
        )
        cached = self._items.get(key)
        if cached is not None:
            return cached
        if len(self._items) > self.max_entries:
            self._items.clear()
        item = ActorRenderItem(
            id=id,
            actor_type=actor_type,
            kind=kind,
            x=x,
            y=y,
            floor=floor,
            hp_ratio=hp_ratio,
            armor_ratio=armor_ratio,
            facing=facing,
            radius=radius,
            color=color,
            lod=lod,
            is_local=is_local,
            is_dead=is_dead,
            label=label,
            mode=mode,
        )
        self._items[key] = item
        return item


class ProjectileRenderItemPool:
    def __init__(self) -> None:
        self.reused = 0
