from __future__ import annotations

import math

from shared.combat_ecosystem import ConvoyStatus, SafeZoneStatus
from shared.models import RectState, Vec2, clamp
from shared.systems.base import WorldSystem
from shared.tactical_gameplay import (
    BuildingPowerState,
    BuildingRoomState,
    BuildingTacticalState,
    DirectorPressure,
    ExtractionPointState,
    ExtractionStatus,
    MissionKind,
    MissionState,
    MissionStatus,
)
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class TacticalGameplaySystem(WorldSystem):
    def update(self, state: WorldState, ctx: WorldContext, dt: float) -> None:
        self._ensure_building_tactics(state)
        self._update_building_tactics(state, dt)
        self._update_power_states(state)
        self._generate_missions(state)
        self._update_extractions(state, dt)
        self._update_director(state, ctx, dt)

    def _ensure_building_tactics(self, state: WorldState) -> None:
        for building in state.buildings.values():
            if building.id in state.building_tactics:
                continue
            state.building_tactics[building.id] = BuildingTacticalState(
                id=building.id,
                rooms=self._build_rooms(building.id, building.bounds, building.min_floor, building.max_floor),
                windows=self._build_windows(building.bounds),
                breach_points=[door.rect for door in building.doors],
            )

    def _build_rooms(self, building_id: str, bounds: RectState, min_floor: int, max_floor: int) -> list[BuildingRoomState]:
        rooms: list[BuildingRoomState] = []
        cols = 2 if bounds.w >= 260 else 1
        rows = 3 if bounds.h >= 420 else 2
        for floor in range(min_floor, max_floor + 1):
            if floor > 0:
                continue
            for row in range(rows):
                for col in range(cols):
                    rect = RectState(
                        bounds.x + bounds.w * col / cols + 18.0,
                        bounds.y + bounds.h * row / rows + 18.0,
                        max(30.0, bounds.w / cols - 36.0),
                        max(30.0, bounds.h / rows - 36.0),
                    )
                    room_id = f"{building_id}:f{floor}:r{row}c{col}"
                    edge_room = row in {0, rows - 1} or col in {0, cols - 1}
                    rooms.append(BuildingRoomState(room_id, building_id, rect, floor=floor, loot_zone=edge_room))
        return rooms

    def _build_windows(self, bounds: RectState) -> list[RectState]:
        return [
            RectState(bounds.x + bounds.w * 0.18, bounds.y - 5.0, 46.0, 10.0),
            RectState(bounds.x + bounds.w * 0.68, bounds.y - 5.0, 46.0, 10.0),
            RectState(bounds.x - 5.0, bounds.y + bounds.h * 0.34, 10.0, 46.0),
            RectState(bounds.x + bounds.w - 5.0, bounds.y + bounds.h * 0.58, 10.0, 46.0),
        ]

    def _update_building_tactics(self, state: WorldState, dt: float) -> None:
        for tactical in state.building_tactics.values():
            building = state.buildings.get(tactical.id)
            if not building:
                continue
            occupants: list[str] = []
            for room in tactical.rooms:
                room.occupants.clear()
                danger = 0.0
                for player in state.players.values():
                    if player.alive and player.floor == room.floor and room.rect.contains(player.pos):
                        room.occupants.append(player.id)
                for soldier in state.soldiers.values():
                    if soldier.alive and soldier.floor == room.floor and room.rect.contains(soldier.pos):
                        room.occupants.append(soldier.id)
                for zombie in state.zombies.values():
                    if zombie.health > 0 and zombie.floor == room.floor and room.rect.contains(zombie.pos):
                        room.occupants.append(zombie.id)
                        danger += 0.18
                room.danger_score = clamp(room.danger_score * (1.0 - dt * 0.45) + danger, 0.0, 1.0)
                occupants.extend(room.occupants)
            tactical.occupants = occupants[:32]
            tactical.noise_level = clamp(tactical.noise_level * (1.0 - dt * 0.18) + self._building_noise(state, building.bounds), 0.0, 1.0)

    def _building_noise(self, state: WorldState, bounds: RectState) -> float:
        noise = 0.0
        for sound in state.sound_events:
            if bounds.inflated(sound.radius * 0.35).contains(sound.pos):
                noise = max(noise, min(1.0, sound.intensity))
        return noise

    def _update_power_states(self, state: WorldState) -> None:
        for tactical in state.building_tactics.values():
            building = state.buildings.get(tactical.id)
            if not building:
                continue
            district = self._district_for_pos(state, building.bounds.center, 0)
            electricity = float(getattr(district, "electricity_level", 1.0)) if district else 1.0
            if electricity >= 0.72:
                tactical.light_state = BuildingPowerState.POWERED
            elif electricity >= 0.42:
                tactical.light_state = BuildingPowerState.PARTIAL
            elif electricity >= 0.18:
                tactical.light_state = BuildingPowerState.EMERGENCY
            else:
                tactical.light_state = BuildingPowerState.BLACKOUT

    def _generate_missions(self, state: WorldState) -> None:
        active_count_by_district: dict[str, int] = {}
        for mission_id, mission in list(state.missions.items()):
            if mission.status in {MissionStatus.COMPLETED, MissionStatus.FAILED} and state.time > mission.expires_at + 30.0:
                state.missions.pop(mission_id, None)
                continue
            if mission.expires_at > 0.0 and mission.status == MissionStatus.AVAILABLE and state.time > mission.expires_at:
                mission.status = MissionStatus.EXPIRED
                continue
            if mission.status in {MissionStatus.AVAILABLE, MissionStatus.ACTIVE}:
                active_count_by_district[mission.district_id] = active_count_by_district.get(mission.district_id, 0) + 1
        for safe_zone in state.safe_zones.values():
            if safe_zone.status != SafeZoneStatus.ACTIVE or not safe_zone.mission_board_active:
                continue
            district = state.district_simulation.get(safe_zone.district_id)
            if not district or active_count_by_district.get(district.id, 0) >= 3:
                continue
            kind = self._mission_kind_for_district(state, district.id)
            mission_id = f"mission:{district.id}:{kind.value}:{int(state.time // 45)}"
            if mission_id in state.missions:
                continue
            target = self._mission_target(state, district.center, district.floor)
            risk = clamp(district.danger_level * 0.55 + district.infestation_level * 0.3 + district.noise_level * 0.15, 0.0, 1.0)
            state.missions[mission_id] = MissionState(
                id=mission_id,
                kind=kind,
                district_id=district.id,
                title_key=f"mission.{kind.value}.title",
                objective_key=f"mission.{kind.value}.objective",
                target_pos=target,
                floor=district.floor,
                risk=risk,
                reward_score=round(100.0 + risk * 260.0 + district.loot_remaining * 80.0, 2),
                source_safe_zone_id=safe_zone.id,
                expires_at=state.time + 420.0,
            )

    def _mission_kind_for_district(self, state: WorldState, district_id: str) -> MissionKind:
        district = state.district_simulation[district_id]
        scarcity = state.resource_scarcity.get(district_id)
        destroyed_convoy = any(convoy.district_id == district_id and convoy.status in {ConvoyStatus.DESTROYED, ConvoyStatus.RAIDED} for convoy in state.supply_convoys.values())
        if destroyed_convoy:
            return MissionKind.RETRIEVE_AMMO
        if district.medical_supply < 0.32 or (scarcity and scarcity.medicine > 0.65):
            return MissionKind.RETRIEVE_MEDICINE
        if district.civilian_population < 0.22:
            return MissionKind.RESCUE_CIVILIAN
        if district.electricity_level < 0.35:
            return MissionKind.RESTORE_POWER
        if district.infestation_level > 0.7:
            return MissionKind.CLEAR_INFESTATION
        if district.danger_level > 0.62:
            return MissionKind.DEFEND_SAFE_ZONE
        return MissionKind.ESCORT_CONVOY

    def _mission_target(self, state: WorldState, fallback: Vec2, floor: int) -> Vec2:
        candidates = [
            building.bounds.center
            for building in state.buildings.values()
            if building.min_floor <= floor <= building.max_floor
        ]
        if not candidates:
            return fallback.copy()
        return min(candidates, key=lambda pos: pos.distance_to(fallback)).copy()

    def _update_extractions(self, state: WorldState, dt: float) -> None:
        for district_id, district in state.district_simulation.items():
            mission_pressure = sum(1 for mission in state.missions.values() if mission.district_id == district_id and mission.status in {MissionStatus.AVAILABLE, MissionStatus.ACTIVE})
            should_open = mission_pressure > 0 or district.danger_level > 0.58
            point_id = f"extract:{district_id}"
            point = state.extraction_points.get(point_id)
            if not point and should_open:
                state.extraction_points[point_id] = ExtractionPointState(
                    id=point_id,
                    district_id=district_id,
                    pos=self._extraction_pos(state, district.center),
                    floor=district.floor,
                    status=ExtractionStatus.OPEN,
                    opens_at=state.time,
                    closes_at=state.time + 480.0,
                )
                continue
            if not point:
                continue
            pressure = clamp(district.danger_level * 0.55 + district.infestation_level * 0.45, 0.0, 1.0)
            point.pressure = clamp(point.pressure + (pressure - point.pressure) * min(1.0, dt * 0.2), 0.0, 1.0)
            if point.pressure >= 0.78:
                point.status = ExtractionStatus.CONTESTED
            elif state.time >= point.closes_at and not should_open:
                point.status = ExtractionStatus.CLOSED
            else:
                point.status = ExtractionStatus.OPEN

    def _extraction_pos(self, state: WorldState, center: Vec2) -> Vec2:
        margin = 220.0
        x = margin if center.x > state.map_width * 0.5 else max(margin, state.map_width - margin)
        y = clamp(center.y, margin, max(margin, state.map_height - margin))
        return Vec2(x, y)

    def _update_director(self, state: WorldState, ctx: WorldContext, dt: float) -> None:
        danger = max((district.danger_level for district in state.district_simulation.values()), default=0.0)
        horde = max((zone.pressure for zone in state.horde_pressure_zones.values()), default=0.0)
        active_missions = sum(1 for mission in state.missions.values() if mission.status in {MissionStatus.AVAILABLE, MissionStatus.ACTIVE})
        score = clamp(danger * 0.46 + horde * 0.34 + min(1.0, active_missions / 4.0) * 0.2, 0.0, 1.0)
        state.director.score = clamp(state.director.score + (score - state.director.score) * min(1.0, dt * 0.12), 0.0, 1.0)
        if state.director.score >= 0.82:
            state.director.pressure = DirectorPressure.RELIEF
        elif state.director.score >= 0.58:
            state.director.pressure = DirectorPressure.HIGH
        elif state.director.score >= 0.28:
            state.director.pressure = DirectorPressure.MEDIUM
        else:
            state.director.pressure = DirectorPressure.LOW
        if state.time < state.director.next_action_at:
            return
        if state.director.pressure == DirectorPressure.LOW:
            state.director.last_action = "send_patrol_or_noise"
            state.director.next_action_at = state.time + 32.0
        elif state.director.pressure == DirectorPressure.MEDIUM:
            state.director.last_action = "horde_movement_or_panic"
            state.director.next_action_at = state.time + 26.0
        elif state.director.pressure == DirectorPressure.HIGH:
            state.director.last_action = "reinforcement_blackout_surge"
            state.director.next_action_at = state.time + 22.0
        else:
            state.director.last_action = "relief_route_or_loot_window"
            state.director.next_action_at = state.time + 18.0

    def _district_for_pos(self, state: WorldState, pos: Vec2, floor: int):
        best = None
        best_dist = math.inf
        for district in state.district_simulation.values():
            if district.floor != floor:
                continue
            distance = district.center.distance_to(pos)
            if distance <= district.radius and distance < best_dist:
                best = district
                best_dist = distance
        return best
