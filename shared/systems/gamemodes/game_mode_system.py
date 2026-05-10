from __future__ import annotations

import math

from shared.ai.squads import SquadIntent, SquadMode, SquadState
from shared.factions import FACTION_ASSAULT_ALPHA, FACTION_ASSAULT_BRAVO
from shared.game_modes import GameModeId, get_game_mode
from shared.models import SoldierState, Vec2
from shared.systems.base import WorldSystem
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


ASSAULT_TEAM_KINDS = ("rifleman", "rifleman", "medic", "heavy_grenadier")


class GameModeSystem(WorldSystem):
    def update(self, state: WorldState, ctx: WorldContext, dt: float) -> None:
        mode = get_game_mode(state.game_mode_id)
        if mode.id != GameModeId.ASSAULT.value:
            return
        self._update_assault(state, ctx)

    def _update_assault(self, state: WorldState, ctx: WorldContext) -> None:
        alpha_spawn, bravo_spawn = self._assault_spawns(state)
        alpha_target, bravo_target = bravo_spawn, alpha_spawn
        self._ensure_assault_team(
            state,
            ctx,
            faction=FACTION_ASSAULT_ALPHA,
            squad_id="assault:alpha",
            spawn=alpha_spawn,
            target=alpha_target,
        )
        self._ensure_assault_team(
            state,
            ctx,
            faction=FACTION_ASSAULT_BRAVO,
            squad_id="assault:bravo",
            spawn=bravo_spawn,
            target=bravo_target,
        )

    def _assault_spawns(self, state: WorldState) -> tuple[Vec2, Vec2]:
        margin_x = max(360.0, state.map_width * 0.08)
        y = state.map_height * 0.5
        return Vec2(margin_x, y), Vec2(max(margin_x, state.map_width - margin_x), y)

    def _ensure_assault_team(
        self,
        state: WorldState,
        ctx: WorldContext,
        *,
        faction: str,
        squad_id: str,
        spawn: Vec2,
        target: Vec2,
    ) -> None:
        squad = state.squads.setdefault(squad_id, SquadState(id=squad_id, faction=faction))
        squad.faction = faction
        squad.intent = SquadIntent(
            squad_id=squad_id,
            mode=SquadMode.ENGAGE_TARGET,
            target_pos=target.copy(),
            danger_score=0.55,
            expires_at=state.time + 8.0,
            issued_at=state.time,
        )
        live_members = [
            soldier
            for soldier in state.soldiers.values()
            if soldier.squad_id == squad_id and soldier.alive
        ]
        missing = max(0, len(ASSAULT_TEAM_KINDS) - len(live_members))
        cooldowns = state.grenade_cooldowns
        ready_key = f"assault_respawn:{squad_id}"
        if missing <= 0:
            cooldowns[ready_key] = state.time
            return
        initial_deploy = not any(member_id in state.soldiers for member_id in squad.member_ids)
        if not initial_deploy and state.time < cooldowns.get(ready_key, 0.0):
            return
        spawn_count = missing if initial_deploy else 1
        for _ in range(spawn_count):
            existing_kinds = [soldier.kind for soldier in live_members]
            kind = next((candidate for candidate in ASSAULT_TEAM_KINDS if existing_kinds.count(candidate) < ASSAULT_TEAM_KINDS.count(candidate)), ASSAULT_TEAM_KINDS[0])
            pos = self._spawn_pos_near(state, ctx, spawn, kind)
            soldier = ctx.spawning.spawn_soldier(
                kind=kind,
                pos=pos,
                guard_point=target,
                squad_id=squad_id,
                faction=faction,
            )
            soldier.mode = "advance"
            soldier.waypoint = target.copy()
            soldier.facing = pos.angle_to(target)
            live_members.append(soldier)
        cooldowns[ready_key] = state.time + 5.0

    def _spawn_pos_near(self, state: WorldState, ctx: WorldContext, center: Vec2, kind: str) -> Vec2:
        radius = 36.0
        for attempt in range(32):
            angle = ctx.rng.uniform(0.0, math.tau)
            distance = ctx.rng.uniform(0.0, 220.0)
            pos = Vec2(center.x + math.cos(angle) * distance, center.y + math.sin(angle) * distance)
            pos.clamp_to_map(state.map_width, state.map_height)
            if not ctx.geometry.blocked_at(pos, radius, 0):
                return pos
        return center.copy()
