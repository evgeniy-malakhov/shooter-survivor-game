from dataclasses import dataclass

from shared.constants import MAP_HEIGHT, MAP_WIDTH
from shared.models import Vec2


@dataclass(frozen=True, slots=True)
class SoldierSpawnPoint:
    id: str
    pos: Vec2
    radius: float
    min_soldiers: int
    max_soldiers: int
    kinds: tuple[str, ...]
    weights: tuple[float, ...]

SOLDIER_SPAWN_POINTS = (
    #SoldierSpawnPoint("checkpoint_north", Vec2(1200, 500), 260, 4, ("rifleman", "rifleman", "heavy")),
    #SoldierSpawnPoint("warehouse_guard", Vec2(2600, 1800), 320, 5, ("rifleman", "scout", "heavy")),
    SoldierSpawnPoint("checkpoint_north", Vec2(1200, 500), 260, 1, 4, ("rifleman", "heavy_grenadier", "medic"), (0.66, 0.20, 0.14)),
    SoldierSpawnPoint("warehouse_guard", Vec2(2600, 1800), 320, 1, 5, ("rifleman", "heavy_grenadier", "medic"), (0.62, 0.24, 0.14)),
    SoldierSpawnPoint("center", Vec2(MAP_WIDTH * 0.5 + 500, MAP_HEIGHT * 0.5), 260, 1, 2, ("rifleman", "heavy_grenadier", "medic"), (0.72, 0.16, 0.12)),
)
