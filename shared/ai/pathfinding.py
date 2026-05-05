from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

from shared.models import RectState, Vec2


@dataclass(frozen=True, slots=True)
class GridNode:
    x: int
    y: int


class GridPathfinder:
    def __init__(self, cell_size: int = 96) -> None:
        self.cell_size = cell_size

    def find_path(
        self,
        start: Vec2,
        goal: Vec2,
        walls: tuple[RectState, ...],
        map_width: float,
        map_height: float,
    ) -> list[Vec2]:
        start_node = self._to_node(start)
        goal_node = self._to_node(goal)

        open_heap: list[tuple[float, GridNode]] = []
        heapq.heappush(open_heap, (0.0, start_node))

        came_from: dict[GridNode, GridNode] = {}
        g_score: dict[GridNode, float] = {start_node: 0.0}

        visited: set[GridNode] = set()

        while open_heap:
            _, current = heapq.heappop(open_heap)

            if current in visited:
                continue

            visited.add(current)

            if current == goal_node:
                return self._reconstruct_path(came_from, current)

            for neighbor in self._neighbors(current):
                if neighbor in visited:
                    continue

                point = self._to_world(neighbor)

                if point.x < 0 or point.y < 0 or point.x > map_width or point.y > map_height:
                    continue

                if self._blocked(point, walls):
                    continue

                tentative_g = g_score[current] + self._cost(current, neighbor)

                if tentative_g < g_score.get(neighbor, float("inf")):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f = tentative_g + self._heuristic(neighbor, goal_node)
                    heapq.heappush(open_heap, (f, neighbor))

        return []

    def _to_node(self, pos: Vec2) -> GridNode:
        return GridNode(
            int(pos.x // self.cell_size),
            int(pos.y // self.cell_size),
        )

    def _to_world(self, node: GridNode) -> Vec2:
        return Vec2(
            node.x * self.cell_size + self.cell_size * 0.5,
            node.y * self.cell_size + self.cell_size * 0.5,
        )

    def _neighbors(self, node: GridNode) -> tuple[GridNode, ...]:
        return (
            GridNode(node.x + 1, node.y),
            GridNode(node.x - 1, node.y),
            GridNode(node.x, node.y + 1),
            GridNode(node.x, node.y - 1),
            GridNode(node.x + 1, node.y + 1),
            GridNode(node.x - 1, node.y - 1),
            GridNode(node.x + 1, node.y - 1),
            GridNode(node.x - 1, node.y + 1),
        )

    def _blocked(self, point: Vec2, walls: tuple[RectState, ...]) -> bool:
        return any(wall.inflated(26).contains(point) for wall in walls)

    def _cost(self, a: GridNode, b: GridNode) -> float:
        dx = abs(a.x - b.x)
        dy = abs(a.y - b.y)
        return 1.414 if dx and dy else 1.0

    def _heuristic(self, a: GridNode, b: GridNode) -> float:
        return math.hypot(a.x - b.x, a.y - b.y)

    def _reconstruct_path(
        self,
        came_from: dict[GridNode, GridNode],
        current: GridNode,
    ) -> list[Vec2]:
        nodes = [current]

        while current in came_from:
            current = came_from[current]
            nodes.append(current)

        nodes.reverse()
        return [self._to_world(node) for node in nodes]