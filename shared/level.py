from __future__ import annotations

from shared.models import BuildingState, DoorState, PropState, RectState, Vec2

WALL = 22.0


def make_buildings() -> dict[str, BuildingState]:
    specs = [
        ("b1", "Clinic", 1180, 980, 760, 520),
        ("b2", "Warehouse", 3860, 1320, 920, 620),
        ("b3", "Apartments", 6820, 840, 760, 700),
        ("b4", "Station", 2060, 4060, 820, 560),
        ("b5", "Market", 5740, 4260, 980, 600),
        ("b6", "Depot", 7960, 5120, 740, 520),
    ]
    return {building.id: building for building in (_make_building(*spec) for spec in specs)}


def tunnel_segments(buildings: dict[str, BuildingState]) -> list[RectState]:
    order = ["b1", "b2", "b3", "b5", "b6", "b4", "b1"]
    centers = [buildings[key].bounds.center for key in order if key in buildings]
    tunnels: list[RectState] = []
    width = 118.0
    for start, end in zip(centers, centers[1:]):
        mid = Vec2(end.x, start.y)
        tunnels.append(_corridor(start, mid, width))
        tunnels.append(_corridor(mid, end, width))
    return tunnels


def _make_building(building_id: str, name: str, x: float, y: float, w: float, h: float) -> BuildingState:
    bounds = RectState(x, y, w, h)
    first_inner_door_y = y + h * 0.30
    second_inner_door_y = y + h * 0.66
    walls = [
        RectState(x, y, w * 0.42, WALL),
        RectState(x + w * 0.58, y, w * 0.42, WALL),
        RectState(x, y + h - WALL, w, WALL),
        RectState(x, y, WALL, h),
        RectState(x + w - WALL, y, WALL, h),
        RectState(x + w * 0.48, y + 90, WALL, first_inner_door_y - (y + 90)),
        RectState(x + w * 0.48, first_inner_door_y + 76, WALL, second_inner_door_y - (first_inner_door_y + 76)),
        RectState(x + w * 0.48, second_inner_door_y + 76, WALL, y + h - 90 - (second_inner_door_y + 76)),
        RectState(x + 120, y + h * 0.52, w * 0.34, WALL),
        RectState(x + w * 0.56, y + h * 0.45, w * 0.30, WALL),
    ]
    doors = [
        DoorState(f"{building_id}-front", RectState(x + w * 0.42, y - 6, w * 0.16, WALL + 12)),
        DoorState(f"{building_id}-inside-a", RectState(x + w * 0.48 - 5, y + h * 0.30, WALL + 10, 76)),
        DoorState(f"{building_id}-inside-b", RectState(x + w * 0.48 - 5, y + h * 0.66, WALL + 10, 76)),
    ]
    props = [
        PropState(f"{building_id}-desk", "desk", RectState(x + 72, y + 90, 96, 48), floor=0),
        PropState(f"{building_id}-shelf", "shelf", RectState(x + w - 164, y + 92, 88, 146), floor=0),
        PropState(f"{building_id}-table", "table", RectState(x + w * 0.60, y + h * 0.62, 136, 72), floor=0),
        PropState(f"{building_id}-crate", "crate", RectState(x + 96, y + h - 166, 84, 84), floor=0),
        PropState(f"{building_id}-repair", "repair_table", RectState(x + 72, y + h - 96, 132, 58), floor=0),
        PropState(f"{building_id}-bench", "work_bench", RectState(x + w * 0.58, y + 84, 144, 62), floor=-1),
        PropState(f"{building_id}-basement-shelf", "shelf", RectState(x + 92, y + 96, 92, 160), floor=-1),
        PropState(f"{building_id}-upper-bed", "bed", RectState(x + 82, y + 90, 142, 74), floor=1),
        PropState(f"{building_id}-upper-cabinet", "cabinet", RectState(x + w - 150, y + 100, 86, 126), floor=2),
        PropState(f"{building_id}-barrel-a", "barrel", RectState(x - 84, y + h * 0.32, 46, 46), floor=0),
        PropState(f"{building_id}-barrel-b", "barrel", RectState(x + w + 42, y + h * 0.60, 48, 48), floor=0),
        PropState(f"{building_id}-pallet", "pallet", RectState(x + w * 0.18, y + h + 44, 126, 54), floor=0),
        PropState(f"{building_id}-roadblock", "roadblock", RectState(x + w * 0.68, y - 84, 152, 42), floor=0),
    ]
    stairs = [RectState(x + w - 150, y + h - 144, 94, 94)]
    return BuildingState(building_id, name, bounds, walls, doors, props, stairs, floors=4, min_floor=-1)


def _corridor(start: Vec2, end: Vec2, width: float) -> RectState:
    if abs(start.x - end.x) >= abs(start.y - end.y):
        x = min(start.x, end.x)
        return RectState(x, start.y - width * 0.5, abs(start.x - end.x), width)
    y = min(start.y, end.y)
    return RectState(start.x - width * 0.5, y, width, abs(start.y - end.y))


def point_building(buildings: dict[str, BuildingState], pos: Vec2) -> str | None:
    for building in buildings.values():
        if building.bounds.contains(pos):
            return building.id
    return None


def all_closed_walls(buildings: dict[str, BuildingState], floor: int = 0) -> list[RectState]:
    walls: list[RectState] = []
    for building in buildings.values():
        walls.extend(building.walls)
        walls.extend(prop.rect for prop in building.props if prop.floor == floor and prop.blocks)
        walls.extend(door.rect for door in building.doors if not door.open and door.floor == floor)
    return walls


def nearest_door(buildings: dict[str, BuildingState], pos: Vec2, radius: float, floor: int | None = None) -> DoorState | None:
    best: DoorState | None = None
    best_distance = radius
    for building in buildings.values():
        for door in building.doors:
            if floor is not None and door.floor != floor:
                continue
            distance = door.rect.center.distance_to(pos)
            if distance <= best_distance:
                best = door
                best_distance = distance
    return best


def nearest_stairs(buildings: dict[str, BuildingState], pos: Vec2, radius: float) -> BuildingState | None:
    for building in buildings.values():
        for stairs in building.stairs:
            if stairs.inflated(radius).contains(pos):
                return building
    return None


def nearest_prop(buildings: dict[str, BuildingState], pos: Vec2, radius: float, kind: str, floor: int) -> PropState | None:
    best: PropState | None = None
    best_distance = radius
    for building in buildings.values():
        for prop in building.props:
            if prop.kind != kind or prop.floor != floor:
                continue
            distance = prop.rect.center.distance_to(pos)
            if distance <= best_distance:
                best = prop
                best_distance = distance
    return best
