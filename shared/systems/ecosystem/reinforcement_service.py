from __future__ import annotations

import math
import random

from shared.combat_ecosystem import ReinforcementRequest, ReinforcementType
from shared.constants import MAP_HEIGHT, MAP_WIDTH, SOLDIERS
from shared.models import Vec2
from shared.world.world_state import WorldState


class ReinforcementService:
    def __init__(self, *, state: WorldState, rng: random.Random) -> None:
        self._state = state
        self._rng = rng

    def request(
        self,
        *,
        district_id: str,
        kind: ReinforcementType,
        target_pos: Vec2,
        floor: int,
        priority: float,
        delay: float,
    ) -> ReinforcementRequest:
        request_id = f"reinforcement:{district_id}:{kind.value}:{int(self._state.time * 10)}"
        existing = self._state.reinforcement_requests.get(request_id)
        if existing:
            return existing
        request = ReinforcementRequest(
            id=request_id,
            district_id=district_id,
            kind=kind,
            target_pos=target_pos.copy(),
            floor=floor,
            priority=priority,
            requested_at=self._state.time,
            arrives_at=self._state.time + delay,
            squad_id=f"reinforcement:{district_id}:{int(self._state.time)}",
        )
        self._state.reinforcement_requests[request.id] = request
        return request

    def update(self, ctx, dt: float) -> None:
        for request in list(self._state.reinforcement_requests.values()):
            if request.status != "pending":
                continue
            if request.arrives_at > self._state.time:
                continue
            self._spawn_request(ctx, request)
            request.status = "deployed"

    def _spawn_request(self, ctx, request: ReinforcementRequest) -> None:
        composition = self._composition(request.kind)
        entry = self._entry_position(request.target_pos, request.floor)
        for index, kind in enumerate(composition):
            pos = self._near(entry, request.floor, 80.0 + index * 34.0)
            if ctx.geometry.blocked_at(pos, SOLDIERS[kind].radius, request.floor):
                pos = entry.copy()
            soldier = ctx.spawning.spawn_soldier(
                kind=kind,
                pos=pos,
                guard_point=request.target_pos,
                squad_id=request.squad_id,
            )
            soldier.floor = request.floor
            soldier.mode = "squad"
            soldier.last_known_pos = request.target_pos.copy()
            soldier.alertness = 0.85

    def _composition(self, kind: ReinforcementType) -> tuple[str, ...]:
        if kind == ReinforcementType.HEAVY_SQUAD:
            return ("rifleman", "heavy", "heavy_grenadier", "medic")
        if kind == ReinforcementType.EXTRACTION_UNIT:
            return ("rifleman", "rifleman", "medic")
        if kind == ReinforcementType.SNIPER_TEAM:
            return ("rifleman", "rifleman")
        if kind == ReinforcementType.APC_CONVOY:
            return ("heavy", "heavy", "heavy_grenadier", "medic")
        return ("rifleman", "rifleman")

    def _entry_position(self, target: Vec2, floor: int) -> Vec2:
        if floor < 0:
            return target.copy()
        candidates = [
            Vec2(80.0, target.y),
            Vec2(MAP_WIDTH - 80.0, target.y),
            Vec2(target.x, 80.0),
            Vec2(target.x, MAP_HEIGHT - 80.0),
        ]
        best = min(candidates, key=lambda pos: pos.distance_to(target))
        best.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
        return best

    def _near(self, center: Vec2, floor: int, radius: float) -> Vec2:
        angle = self._rng.uniform(0.0, math.tau)
        distance = self._rng.uniform(0.0, radius)
        pos = Vec2(center.x + math.cos(angle) * distance, center.y + math.sin(angle) * distance)
        pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
        return pos
