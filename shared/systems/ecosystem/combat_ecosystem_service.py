from __future__ import annotations

import math
import random

from shared.ai.zombie_ecology import HordePressureZone
from shared.combat_ecosystem import (
    BattleEscalationState,
    ConvoyStatus,
    EscalationLevel,
    ReinforcementType,
    ResourceScarcityState,
    SafeZoneState,
    SafeZoneStatus,
    SupplyConvoyState,
    TerritoryOwner,
    reinforcement_for_level,
    territory_owner,
)
from shared.models import Vec2, clamp
from shared.world.world_state import WorldState


class CombatEcosystemService:
    def __init__(self, *, state: WorldState, rng: random.Random) -> None:
        self._state = state
        self._rng = rng

    def update(self, ctx, dt: float) -> None:
        self._ensure_district_states()
        for district_id, district in self._state.district_simulation.items():
            escalation = self._state.battle_escalation[district_id]
            scarcity = self._state.resource_scarcity[district_id]
            local_noise = self._noise_for_district(district)
            local_pressure = self._pressure_for_district(district)
            military_presence = self._military_presence(ctx, district.center, district.radius, district.floor)

            district.noise_level = max(0.0, min(1.0, district.noise_level * (1.0 - dt * 0.12) + local_noise * 0.1))
            district.zombie_pressure = max(0.0, min(1.0, district.zombie_pressure * (1.0 - dt * 0.035) + local_pressure * 0.055))
            district.military_control = max(0.0, min(1.0, district.military_control * (1.0 - district.zombie_pressure * dt * 0.004) + military_presence * dt * 0.01))
            district.danger_level = min(1.0, district.zombie_pressure * 0.52 + district.noise_level * 0.28 + (1.0 - district.military_control) * 0.2)

            owner = territory_owner(military_control=district.military_control, zombie_pressure=district.zombie_pressure)
            district.territory_owner = owner.value
            escalation.territory_owner = owner
            escalation.radio_activity = max(0.0, min(1.0, escalation.radio_activity * (1.0 - dt * 0.1) + (local_noise + military_presence) * 0.08))
            escalation.score = max(0.0, min(1.0, escalation.score * (1.0 - dt * 0.025) + district.danger_level * 0.035 + local_noise * 0.07))
            escalation.level = self._level(escalation.score)
            escalation.lockdown = escalation.level in {EscalationLevel.LOCKDOWN, EscalationLevel.COLLAPSE}
            district.lockdown = escalation.lockdown
            escalation.reinforcement_cooldown = max(0.0, escalation.reinforcement_cooldown - dt)
            escalation.wave_cooldown = max(0.0, escalation.wave_cooldown - dt)

            self._update_scarcity(scarcity, district, dt)
            self._update_persistent_consequences(district, scarcity, escalation, military_presence, dt)
            self._maybe_request_reinforcements(ctx, district_id, district, escalation)
            self._maybe_create_organic_wave(district_id, district, escalation)
            self._maybe_dispatch_supply_convoy(district_id, district, scarcity, escalation)
            self._update_safe_zone(district_id, district, escalation, dt)
        self._propagate_frontline(dt)
        self._update_supply_convoys(ctx, dt)

    def _ensure_district_states(self) -> None:
        for district_id, district in self._state.district_simulation.items():
            self._state.battle_escalation.setdefault(district_id, BattleEscalationState(district_id=district_id))
            self._state.resource_scarcity.setdefault(district_id, ResourceScarcityState(district_id=district_id))
            district.infestation_level = max(district.infestation_level, district.zombie_pressure)
            district.military_strength = max(district.military_strength, district.military_control)
            if district.civilian_population <= 0.0:
                district.civilian_population = 0.5 if "survivors" in district.tags else 0.18

    def _noise_for_district(self, district) -> float:
        best = district.noise_level
        for sound in self._state.sound_events:
            if sound.floor != district.floor:
                continue
            distance = sound.pos.distance_to(district.center)
            if distance > district.radius + sound.radius:
                continue
            weight = max(0.0, 1.0 - distance / max(1.0, district.radius + sound.radius))
            kind_bonus = 0.35 if sound.kind == "shot" else 0.55 if sound.kind in {"explosion", "grenade"} else 0.08
            best = max(best, sound.intensity * weight + kind_bonus)
        return min(1.0, best)

    def _pressure_for_district(self, district) -> float:
        pressure = district.zombie_pressure
        for zone in self._state.horde_pressure_zones.values():
            if zone.floor != district.floor:
                continue
            distance = zone.center.distance_to(district.center)
            if distance > zone.radius + district.radius:
                continue
            weight = max(0.0, 1.0 - distance / max(1.0, zone.radius + district.radius))
            pressure = max(pressure, zone.pressure * weight)
        return min(1.0, pressure)

    def _military_presence(self, ctx, center: Vec2, radius: float, floor: int) -> float:
        soldiers = sum(1 for soldier in ctx.spatial.nearby_soldiers(center, radius, floor) if soldier.alive)
        return min(1.0, soldiers / 8.0)

    def _level(self, score: float) -> EscalationLevel:
        if score >= 0.82:
            return EscalationLevel.COLLAPSE
        if score >= 0.62:
            return EscalationLevel.LOCKDOWN
        if score >= 0.38:
            return EscalationLevel.CONTACT
        if score >= 0.18:
            return EscalationLevel.TENSE
        return EscalationLevel.CALM

    def _update_scarcity(self, scarcity: ResourceScarcityState, district, dt: float) -> None:
        pressure = district.danger_level
        scarcity.ammo = min(1.0, scarcity.ammo + pressure * dt * 0.0008)
        scarcity.medicine = min(1.0, scarcity.medicine + pressure * dt * 0.0009)
        scarcity.food = min(1.0, scarcity.food + pressure * dt * 0.0006)
        scarcity.fuel = min(1.0, scarcity.fuel + pressure * dt * 0.0007)
        scarcity.last_update = self._state.time
        district.loot_remaining = max(0.0, district.loot_remaining - pressure * dt * 0.0005)

    def _update_persistent_consequences(
        self,
        district,
        scarcity: ResourceScarcityState,
        escalation: BattleEscalationState,
        military_presence: float,
        dt: float,
    ) -> None:
        pressure = clamp(district.zombie_pressure * 0.55 + district.noise_level * 0.25 + escalation.score * 0.2, 0.0, 1.0)
        stable = clamp(district.military_control * 0.42 + military_presence * 0.34 + district.morale * 0.24, 0.0, 1.0)
        damage_rate = pressure * dt * 0.0014
        recovery_rate = max(0.0, stable - pressure * 0.65) * dt * 0.0009

        district.infestation_level = clamp(district.infestation_level + pressure * dt * 0.0011 - stable * dt * 0.00045, 0.0, 1.0)
        district.zombie_pressure = clamp(district.zombie_pressure * 0.72 + district.infestation_level * 0.28, 0.0, 1.0)

        district.infrastructure_integrity = clamp(district.infrastructure_integrity - damage_rate + recovery_rate, 0.0, 1.0)
        district.electricity_level = clamp(
            district.electricity_level - damage_rate * 1.25 + recovery_rate * (1.35 if district.infrastructure_integrity > 0.45 else 0.45),
            0.0,
            1.0,
        )
        district.food_supply = clamp(district.food_supply - pressure * dt * 0.00075 + recovery_rate * 0.55, 0.0, 1.0)
        district.medical_supply = clamp(district.medical_supply - pressure * dt * 0.00085 + recovery_rate * 0.65, 0.0, 1.0)
        district.civilian_population = clamp(
            district.civilian_population - max(0.0, pressure - 0.35) * dt * 0.00055 + max(0.0, stable - 0.72) * dt * 0.00016,
            0.0,
            1.0,
        )
        district.military_strength = clamp(
            district.military_strength + military_presence * dt * 0.0009 - district.infestation_level * dt * 0.00072 - scarcity.ammo * dt * 0.00032,
            0.0,
            1.0,
        )
        district.military_control = clamp(district.military_control * 0.7 + district.military_strength * 0.3, 0.0, 1.0)
        district.morale = clamp(
            district.morale + (stable - pressure) * dt * 0.0009 - scarcity.food * dt * 0.00022 - scarcity.medicine * dt * 0.00018,
            0.0,
            1.0,
        )
        district.quarantine_level = clamp(
            district.quarantine_level + (0.0012 if escalation.lockdown else -0.00065) * dt + district.military_strength * dt * 0.00022,
            0.0,
            1.0,
        )
        district.danger_level = clamp(
            district.infestation_level * 0.38 + district.noise_level * 0.18 + (1.0 - district.military_strength) * 0.18
            + (1.0 - district.infrastructure_integrity) * 0.13 + (1.0 - district.morale) * 0.13,
            0.0,
            1.0,
        )
        scarcity.ammo = clamp(1.0 - district.military_strength * 0.55 - district.quarantine_level * 0.25, 0.0, 1.0)
        scarcity.medicine = clamp(1.0 - district.medical_supply, 0.0, 1.0)
        scarcity.food = clamp(1.0 - district.food_supply, 0.0, 1.0)
        scarcity.fuel = clamp(1.0 - max(district.electricity_level, district.infrastructure_integrity * 0.75), 0.0, 1.0)

    def _propagate_frontline(self, dt: float) -> None:
        districts = list(self._state.district_simulation.values())
        infestation_delta: dict[str, float] = {}
        military_delta: dict[str, float] = {}
        for source in districts:
            for target in districts:
                if source is target or source.floor != target.floor:
                    continue
                distance = source.center.distance_to(target.center)
                reach = max(1.0, (source.radius + target.radius) * 0.82)
                if distance > reach:
                    continue
                link = max(0.0, 1.0 - distance / reach)
                if source.infestation_level > 0.58:
                    pressure = source.infestation_level * link * dt * 0.00042
                    infestation_delta[target.id] = infestation_delta.get(target.id, 0.0) + pressure
                    target.noise_level = clamp(target.noise_level + pressure * 0.45, 0.0, 1.0)
                if source.military_strength > 0.62 and source.quarantine_level > 0.35:
                    support = source.military_strength * link * dt * 0.00022
                    military_delta[target.id] = military_delta.get(target.id, 0.0) + support
        for district_id, delta in infestation_delta.items():
            district = self._state.district_simulation.get(district_id)
            if district:
                district.infestation_level = clamp(district.infestation_level + delta, 0.0, 1.0)
        for district_id, delta in military_delta.items():
            district = self._state.district_simulation.get(district_id)
            if district:
                district.military_strength = clamp(district.military_strength + delta, 0.0, 1.0)

    def _maybe_dispatch_supply_convoy(
        self,
        district_id: str,
        district,
        scarcity: ResourceScarcityState,
        escalation: BattleEscalationState,
    ) -> None:
        active = any(
            convoy.district_id == district_id and self._state.time - convoy.started_at < 90.0
            for convoy in self._state.supply_convoys.values()
        )
        if active or district.military_strength < 0.28:
            return
        need = max(scarcity.ammo, scarcity.medicine, scarcity.food, scarcity.fuel)
        if need < 0.48 and escalation.level not in {EscalationLevel.LOCKDOWN, EscalationLevel.COLLAPSE}:
            return
        if self._rng.random() > 0.012:
            return
        edge_x = 120.0 if district.center.x > self._state.map_width * 0.5 else max(120.0, self._state.map_width - 120.0)
        edge_y = clamp(district.center.y + self._rng.uniform(-900.0, 900.0), 120.0, max(120.0, self._state.map_height - 120.0))
        convoy_id = f"convoy:{district_id}:{int(self._state.time)}"
        self._state.supply_convoys[convoy_id] = SupplyConvoyState(
            id=convoy_id,
            district_id=district_id,
            pos=Vec2(edge_x, edge_y),
            target_pos=district.center.copy(),
            floor=district.floor,
            ammo=0.22 + scarcity.ammo * 0.42,
            medicine=0.18 + scarcity.medicine * 0.42,
            food=0.18 + scarcity.food * 0.38,
            fuel=0.14 + scarcity.fuel * 0.38,
            guard_strength=clamp(0.32 + district.military_strength * 0.45, 0.2, 0.9),
            started_at=self._state.time,
            eta=self._state.time + 28.0 + self._rng.uniform(0.0, 18.0),
        )

    def _update_supply_convoys(self, ctx, dt: float) -> None:
        for convoy_id, convoy in list(self._state.supply_convoys.items()):
            if convoy.status != ConvoyStatus.EN_ROUTE:
                if self._state.time - max(convoy.eta, convoy.started_at) > 30.0:
                    self._state.supply_convoys.pop(convoy_id, None)
                continue
            to_target = Vec2(convoy.target_pos.x - convoy.pos.x, convoy.target_pos.y - convoy.pos.y)
            distance = max(0.001, to_target.length())
            step = min(distance, (95.0 + convoy.guard_strength * 65.0) * dt)
            direction = to_target.normalized()
            convoy.pos.x += direction.x * step
            convoy.pos.y += direction.y * step
            threat = self._convoy_threat(ctx, convoy)
            if threat > convoy.guard_strength + 0.38 and self._rng.random() < min(0.18, threat * dt * 0.012):
                convoy.status = ConvoyStatus.DESTROYED if threat > 0.82 else ConvoyStatus.RAIDED
                convoy.eta = self._state.time
                district = self._state.district_simulation.get(convoy.district_id)
                if district:
                    district.morale = clamp(district.morale - 0.12, 0.0, 1.0)
                    district.military_strength = clamp(district.military_strength - 0.08, 0.0, 1.0)
                continue
            if distance <= 42.0:
                convoy.status = ConvoyStatus.ARRIVED
                convoy.eta = self._state.time
                self._apply_convoy_arrival(convoy)

    def _convoy_threat(self, ctx, convoy: SupplyConvoyState) -> float:
        nearby_zombies = sum(1 for zombie in ctx.spatial.nearby_zombies(convoy.pos, 760.0, convoy.floor) if zombie.health > 0)
        horde_pressure = 0.0
        for zone in self._state.horde_pressure_zones.values():
            if zone.floor != convoy.floor:
                continue
            if zone.center.distance_to(convoy.pos) <= zone.radius + 360.0:
                horde_pressure = max(horde_pressure, zone.pressure)
        return clamp(nearby_zombies / 16.0 + horde_pressure * 0.65, 0.0, 1.0)

    def _apply_convoy_arrival(self, convoy: SupplyConvoyState) -> None:
        district = self._state.district_simulation.get(convoy.district_id)
        scarcity = self._state.resource_scarcity.get(convoy.district_id)
        if not district or not scarcity:
            return
        district.military_strength = clamp(district.military_strength + convoy.guard_strength * 0.12 + convoy.ammo * 0.09, 0.0, 1.0)
        district.food_supply = clamp(district.food_supply + convoy.food * 0.24, 0.0, 1.0)
        district.medical_supply = clamp(district.medical_supply + convoy.medicine * 0.26, 0.0, 1.0)
        district.electricity_level = clamp(district.electricity_level + convoy.fuel * 0.16, 0.0, 1.0)
        district.morale = clamp(district.morale + 0.09 + convoy.guard_strength * 0.05, 0.0, 1.0)
        district.quarantine_level = clamp(district.quarantine_level + convoy.guard_strength * 0.04, 0.0, 1.0)
        scarcity.ammo = clamp(scarcity.ammo - convoy.ammo * 0.48, 0.0, 1.0)
        scarcity.medicine = clamp(scarcity.medicine - convoy.medicine * 0.55, 0.0, 1.0)
        scarcity.food = clamp(scarcity.food - convoy.food * 0.5, 0.0, 1.0)
        scarcity.fuel = clamp(scarcity.fuel - convoy.fuel * 0.45, 0.0, 1.0)

    def _update_safe_zone(self, district_id: str, district, escalation: BattleEscalationState, dt: float) -> None:
        zone_id = f"safe:{district_id}"
        safe_zone = self._state.safe_zones.get(zone_id)
        stability = clamp(
            district.military_strength * 0.35 + district.infrastructure_integrity * 0.2 + district.electricity_level * 0.15
            + district.morale * 0.2 + district.civilian_population * 0.1 - district.infestation_level * 0.35,
            0.0,
            1.0,
        )
        collapse_risk = clamp(district.danger_level * 0.5 + escalation.score * 0.3 + district.infestation_level * 0.2, 0.0, 1.0)
        if safe_zone is None and stability >= 0.62 and collapse_risk <= 0.44:
            offset = min(420.0, district.radius * 0.24)
            safe_zone = SafeZoneState(
                id=zone_id,
                district_id=district_id,
                pos=Vec2(district.center.x - offset, district.center.y - offset * 0.35),
                floor=district.floor,
                radius=min(680.0, max(360.0, district.radius * 0.28)),
                status=SafeZoneStatus.FORMING,
                stability=stability,
                collapse_risk=collapse_risk,
            )
            self._state.safe_zones[zone_id] = safe_zone
        if safe_zone is None:
            return
        safe_zone.stability = clamp(safe_zone.stability + (stability - safe_zone.stability) * min(1.0, dt * 0.08), 0.0, 1.0)
        safe_zone.collapse_risk = clamp(safe_zone.collapse_risk + (collapse_risk - safe_zone.collapse_risk) * min(1.0, dt * 0.1), 0.0, 1.0)
        if safe_zone.collapse_risk >= 0.76:
            safe_zone.status = SafeZoneStatus.COLLAPSING
        elif safe_zone.stability >= 0.72 and safe_zone.collapse_risk <= 0.38:
            safe_zone.status = SafeZoneStatus.ACTIVE
        elif safe_zone.stability >= 0.54:
            safe_zone.status = SafeZoneStatus.FORMING
        elif safe_zone.collapse_risk >= 0.58:
            safe_zone.status = SafeZoneStatus.LOST
        else:
            safe_zone.status = SafeZoneStatus.INACTIVE
        active = safe_zone.status == SafeZoneStatus.ACTIVE
        forming = safe_zone.status == SafeZoneStatus.FORMING
        safe_zone.trader_active = active and district.food_supply > 0.35 and district.loot_remaining > 0.18
        safe_zone.medic_active = active and district.medical_supply > 0.28
        safe_zone.storage_active = active or forming
        safe_zone.mission_board_active = active and district.quarantine_level > 0.35

    def _maybe_request_reinforcements(self, ctx, district_id: str, district, escalation: BattleEscalationState) -> None:
        if escalation.reinforcement_cooldown > 0.0:
            return
        if district.military_control < 0.34:
            return
        if escalation.level not in {EscalationLevel.CONTACT, EscalationLevel.LOCKDOWN, EscalationLevel.COLLAPSE}:
            return
        if escalation.radio_activity < 0.22 and escalation.score < 0.5:
            return
        kind = reinforcement_for_level(escalation.level, escalation.territory_owner)
        if district.zombie_pressure > 0.78 and district.military_control > 0.55:
            kind = ReinforcementType.HEAVY_SQUAD
        ctx.reinforcements.request(
            district_id=district_id,
            kind=kind,
            target_pos=district.center,
            floor=district.floor,
            priority=escalation.score,
            delay=max(6.0, 18.0 - escalation.score * 10.0),
        )
        escalation.reinforcement_cooldown = 35.0 + self._rng.uniform(0.0, 18.0)

    def _maybe_create_organic_wave(self, district_id: str, district, escalation: BattleEscalationState) -> None:
        if escalation.wave_cooldown > 0.0:
            return
        if district.noise_level < 0.45 and escalation.score < 0.55:
            return
        if district.zombie_pressure < 0.38:
            return
        zone_id = f"surge:{district_id}:{int(self._state.time)}"
        angle = self._rng.uniform(0.0, math.tau)
        offset = self._rng.uniform(district.radius * 0.15, district.radius * 0.55)
        center = Vec2(district.center.x + math.cos(angle) * offset, district.center.y + math.sin(angle) * offset)
        self._state.horde_pressure_zones[zone_id] = HordePressureZone(
            id=zone_id,
            center=center,
            floor=district.floor,
            radius=min(2200.0, district.radius * 1.15),
            pressure=min(1.0, 0.45 + escalation.score * 0.45),
            aggression=min(1.0, 0.35 + district.noise_level * 0.55),
            target_pos=district.center.copy(),
            last_noise_at=self._state.time,
            expires_at=self._state.time + 42.0,
        )
        escalation.wave_cooldown = 24.0 + self._rng.uniform(0.0, 16.0)
