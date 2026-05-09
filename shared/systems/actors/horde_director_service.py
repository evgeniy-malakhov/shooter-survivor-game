from __future__ import annotations

import math
import random

from shared.ai.memory import remember_threat
from shared.ai.zombie_ecology import HordePressureZone, ZombieInterest
from shared.constants import MAP_HEIGHT, MAP_WIDTH
from shared.models import Vec2, ZombieState
from shared.world.world_state import WorldState


class HordeDirectorService:
    def __init__(self, *, state: WorldState, rng: random.Random) -> None:
        self._state = state
        self._rng = rng
        self._spawn_accumulator = 0.0

    def update(self, ctx, dt: float) -> None:
        self._decay_zones(dt)
        self._ingest_sounds(ctx)
        self._refresh_density(ctx)
        self._propagate_group_interest(ctx)
        self._update_districts(dt)
        self._spawn_pressure(ctx, dt)

    def ecology_for(self, zombie: ZombieState) -> tuple[ZombieInterest, Vec2 | None]:
        zone = self._nearest_active_zone(zombie.pos, zombie.floor)
        if not zone:
            return ZombieInterest(), None

        distance = zombie.pos.distance_to(zone.center)
        falloff = max(0.0, 1.0 - distance / max(1.0, zone.radius * 1.65))
        horde_interest = zone.pressure * 0.72 * falloff + zone.aggression * 0.42
        sound_interest = max(0.0, zone.pressure * 0.35 * falloff)
        return ZombieInterest(sound=sound_interest, horde=horde_interest), (zone.target_pos or zone.center).copy()

    def pressure_for_position(self, pos: Vec2, floor: int) -> float:
        zone = self._nearest_active_zone(pos, floor)
        if not zone:
            return 0.0
        distance = pos.distance_to(zone.center)
        return max(0.0, zone.pressure * (1.0 - distance / max(1.0, zone.radius * 1.8)))

    def threat_level(self, pos: Vec2 | None = None, floor: int = 0) -> float:
        if pos:
            return min(1.0, self.pressure_for_position(pos, floor))
        return min(1.0, max((zone.pressure for zone in self._state.horde_pressure_zones.values()), default=0.0))

    def _decay_zones(self, dt: float) -> None:
        now = self._state.time
        expired: list[str] = []
        for zone_id, zone in self._state.horde_pressure_zones.items():
            decay = dt * (0.025 if zone.last_noise_at + 8.0 > now else 0.07)
            zone.pressure = max(0.0, zone.pressure - decay)
            zone.aggression = max(0.0, zone.aggression - dt * 0.045)
            if zone.pressure <= 0.02 or (zone.expires_at and zone.expires_at <= now):
                expired.append(zone_id)
        for zone_id in expired:
            self._state.horde_pressure_zones.pop(zone_id, None)

    def _ingest_sounds(self, ctx) -> None:
        for sound in self._state.sound_events:
            if sound.kind not in {"shot", "explosion", "grenade", "movement"}:
                continue
            if sound.kind == "movement" and sound.intensity < 0.4:
                continue

            pressure = min(1.0, sound.intensity * 0.26 + sound.radius / 4200.0)
            if sound.kind == "shot":
                pressure += 0.18
            elif sound.kind in {"explosion", "grenade"}:
                pressure += 0.38

            self._add_pressure(sound.pos, sound.floor, pressure=pressure, radius=max(820.0, sound.radius * 1.25), kind=sound.kind)

    def _add_pressure(self, pos: Vec2, floor: int, *, pressure: float, radius: float, kind: str) -> None:
        now = self._state.time
        zone = self._find_zone(pos, floor, radius * 0.8)
        if zone is None:
            zone_id = f"horde:{floor}:{int(pos.x // 700)}:{int(pos.y // 700)}"
            zone = HordePressureZone(
                id=zone_id,
                center=pos.copy(),
                floor=floor,
                radius=radius,
                pressure=0.0,
                aggression=0.0,
                target_pos=pos.copy(),
            )
            self._state.horde_pressure_zones[zone_id] = zone

        zone.center = Vec2(
            zone.center.x * 0.74 + pos.x * 0.26,
            zone.center.y * 0.74 + pos.y * 0.26,
        )
        zone.center.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
        zone.target_pos = pos.copy()
        zone.radius = max(zone.radius, radius)
        zone.pressure = min(1.0, zone.pressure + pressure)
        zone.aggression = min(1.0, zone.aggression + pressure * (1.1 if kind in {"shot", "explosion", "grenade"} else 0.55))
        zone.last_noise_at = now
        zone.expires_at = now + 34.0

    def _find_zone(self, pos: Vec2, floor: int, radius: float) -> HordePressureZone | None:
        best: HordePressureZone | None = None
        best_distance = radius
        for zone in self._state.horde_pressure_zones.values():
            if zone.floor != floor:
                continue
            distance = zone.center.distance_to(pos)
            if distance <= best_distance:
                best = zone
                best_distance = distance
        return best

    def _nearest_active_zone(self, pos: Vec2, floor: int) -> HordePressureZone | None:
        best: HordePressureZone | None = None
        best_score = 0.0
        for zone in self._state.horde_pressure_zones.values():
            if zone.floor != floor:
                continue
            distance = pos.distance_to(zone.center)
            score = zone.pressure * max(0.0, 1.0 - distance / max(1.0, zone.radius * 1.8))
            if score > best_score:
                best = zone
                best_score = score
        return best

    def _refresh_density(self, ctx) -> None:
        for zone in self._state.horde_pressure_zones.values():
            zone.density = sum(1 for zombie in ctx.spatial.nearby_zombies(zone.center, zone.radius, zone.floor) if zombie.health > 0)

    def _propagate_group_interest(self, ctx) -> None:
        now = self._state.time
        active_modes = {"chase", "frenzy", "migrate", "alerted", "investigate", "stalk"}
        for active in list(self._state.zombies.values()):
            if active.mode not in active_modes or active.health <= 0:
                continue
            if not active.last_known_pos:
                continue
            influence = 360.0 if active.kind == "coordinator" else 240.0
            for zombie in ctx.spatial.nearby_zombies(active.pos, influence, active.floor):
                if zombie.id == active.id or zombie.health <= 0:
                    continue
                if zombie.mode in {"chase", "frenzy"}:
                    continue
                zombie.mode = "alerted" if zombie.mode in {"patrol", "wander", "dormant"} else zombie.mode
                zombie.last_known_pos = active.last_known_pos.copy()
                zombie.alertness = min(1.0, zombie.alertness + (0.26 if active.kind == "coordinator" else 0.14))
                remember_threat(
                    zombie.ai_memory,
                    kind="horde_signal",
                    pos=active.last_known_pos,
                    floor=active.floor,
                    now=now,
                    danger=0.55 + zombie.alertness * 0.25,
                    source_actor_id=active.id,
                )

    def _update_districts(self, dt: float) -> None:
        for district in self._state.district_simulation.values():
            pressure = 0.0
            noise = 0.0
            for zone in self._state.horde_pressure_zones.values():
                if zone.floor != district.floor:
                    continue
                distance = district.center.distance_to(zone.center)
                if distance > district.radius + zone.radius:
                    continue
                weight = max(0.0, 1.0 - distance / max(1.0, district.radius + zone.radius))
                pressure = max(pressure, zone.pressure * weight)
                noise = max(noise, zone.aggression * weight)
            district.zombie_pressure = max(0.0, district.zombie_pressure * (1.0 - dt * 0.08) + pressure * 0.08)
            district.noise_level = max(0.0, district.noise_level * (1.0 - dt * 0.12) + noise * 0.1)
            district.danger_level = min(1.0, district.zombie_pressure * 0.65 + district.noise_level * 0.35)
            district.military_control = max(0.0, district.military_control - district.zombie_pressure * dt * 0.003)

    def _spawn_pressure(self, ctx, dt: float) -> None:
        self._spawn_accumulator += dt
        if self._spawn_accumulator < 2.5:
            return
        self._spawn_accumulator = 0.0
        if len(self._state.zombies) >= ctx.max_zombies:
            return

        zones = [zone for zone in self._state.horde_pressure_zones.values() if zone.pressure >= 0.68 and zone.density < 8]
        if not zones:
            return
        zone = max(zones, key=lambda item: item.pressure - item.density * 0.04)
        if self._rng.random() > zone.pressure * 0.35:
            return

        angle = self._rng.uniform(0.0, math.tau)
        distance = self._rng.uniform(zone.radius * 0.65, zone.radius * 1.15)
        pos = Vec2(
            zone.center.x + math.cos(angle) * distance,
            zone.center.y + math.sin(angle) * distance,
        )
        pos.clamp_to_map(MAP_WIDTH, MAP_HEIGHT)
        kind = "coordinator" if self._rng.random() < 0.08 else None
        zombie = ctx.spawning.spawn_zombie(kind=kind, pos=pos)
        if zombie:
            zombie.mode = "migrate"
            zombie.last_known_pos = (zone.target_pos or zone.center).copy()
            zombie.alertness = min(1.0, 0.35 + zone.pressure * 0.45)
