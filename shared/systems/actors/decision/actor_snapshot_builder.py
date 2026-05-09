from __future__ import annotations

import random
from dataclasses import replace

from shared.ai.memory import remember_sound
from shared.ai.context import SoundEvent
from shared.models import SoldierState, Vec2, ZombieState
from shared.systems.actors.decision.actor_decision_dto import ActorDecisionInput


class ActorSnapshotBuilder:
    def build_zombie_input(
        self,
        zombie: ZombieState,
        *,
        ctx,
        dt: float,
        rng: random.Random,
        living_players_count: int | None = None,
    ) -> ActorDecisionInput:
        targets = ctx.zombie_runtime.targets_near_zombie(zombie, ctx)
        nearby_players = tuple(target for target in targets if target.kind == "player")
        nearby_soldiers = tuple(target for target in targets if target.kind == "soldier")
        nearby_sounds = self._nearby_sounds_for_zombie(zombie, ctx)
        ecology_interest, horde_target = ctx.horde_director.ecology_for(zombie)
        self._remember_sounds(zombie.ai_memory, nearby_sounds, now=ctx.zombie_runtime.state_time, actor_pos=zombie.pos)

        return ActorDecisionInput(
            actor_type="zombie",
            actor_id=zombie.id,
            actor_kind=zombie.kind,
            actor_state=zombie.to_dict(),
            dt=dt,
            time=ctx.zombie_runtime.state_time,
            rng_seed=rng.randrange(1, 2**63),
            targets=targets,
            nearby_players=nearby_players,
            nearby_soldiers=nearby_soldiers,
            nearby_sounds=nearby_sounds,
            metadata={
                "living_players": (
                    sum(1 for player in ctx.zombie_runtime.living_players())
                    if living_players_count is None
                    else living_players_count
                ),
                "cpu_heavy": bool(targets),
                "ecology_interest": ecology_interest.to_dict(),
                "horde_target": horde_target.to_dict() if horde_target else None,
            },
        )

    def build_soldier_input(
        self,
        soldier: SoldierState,
        *,
        ctx,
        dt: float,
        rng: random.Random,
    ) -> ActorDecisionInput:
        targets = ctx.soldier_runtime.targets_near_soldier(soldier, ctx)
        nearby_players = tuple(target for target in targets if target.kind == "player")
        nearby_zombies = tuple(target for target in targets if target.kind == "zombie")
        squad_mates = ctx.squads.mates_for(soldier)
        squad_intent = ctx.squads.intent_for(soldier)
        nearby_sounds = self._nearby_sounds_for_soldier(soldier, ctx)
        self._remember_sounds(soldier.ai_memory, nearby_sounds, now=ctx.soldier_runtime.state_time, actor_pos=soldier.pos)

        return ActorDecisionInput(
            actor_type="soldier",
            actor_id=soldier.id,
            actor_kind=soldier.kind,
            actor_state=soldier.to_dict(),
            dt=dt,
            time=ctx.soldier_runtime.state_time,
            rng_seed=rng.randrange(1, 2**63),
            targets=targets,
            nearby_players=nearby_players,
            nearby_zombies=nearby_zombies,
            nearby_soldiers=squad_mates,
            nearby_sounds=nearby_sounds,
            squad_intent=squad_intent.to_dict() if squad_intent else None,
            squad_role=ctx.squads.role_for(soldier),
            squad_memory=ctx.squads.memory_for(soldier),
            metadata={
                "cpu_heavy": bool(targets),
            },
        )

    def build_zombie_inputs(
        self,
        zombies: list[ZombieState],
        *,
        ctx,
        dt: float,
        rng: random.Random,
    ) -> list[ActorDecisionInput]:
        living_players_count = len(ctx.zombie_runtime.living_players())
        return [
            self.build_zombie_input(
                zombie,
                ctx=ctx,
                dt=dt,
                rng=rng,
                living_players_count=living_players_count,
            )
            for zombie in zombies
            if zombie.health > 0
        ]

    def build_soldier_inputs(
        self,
        soldiers: list[SoldierState],
        *,
        ctx,
        dt: float,
        rng: random.Random,
    ) -> list[ActorDecisionInput]:
        return [
            self.build_soldier_input(soldier, ctx=ctx, dt=dt, rng=rng)
            for soldier in soldiers
            if soldier.alive
        ]

    def _nearby_sounds_for_zombie(self, zombie: ZombieState, ctx) -> tuple[SoundEvent, ...]:
        spec = ctx.zombie_runtime.zombie_spec(zombie.kind)
        radius = spec.hearing_range * max(0.1, spec.sensitivity) + 1800.0
        return tuple(
            replace(sound, pos=Vec2(sound.pos.x, sound.pos.y))
            for sound in ctx.spatial.nearby_sounds(zombie.pos, radius, zombie.floor)
        )

    def _nearby_sounds_for_soldier(self, soldier: SoldierState, ctx) -> tuple[SoundEvent, ...]:
        radius = ctx.soldier_runtime.soldier_hearing_query_radius(soldier.kind)
        return tuple(
            replace(sound, pos=Vec2(sound.pos.x, sound.pos.y))
            for sound in ctx.spatial.nearby_sounds(soldier.pos, radius, soldier.floor)
        )

    def _remember_sounds(
        self,
        memory: list[dict[str, object]],
        sounds: tuple[SoundEvent, ...],
        *,
        now: float,
        actor_pos: Vec2,
    ) -> None:
        for sound in sounds:
            if sound.kind in {"shot", "explosion", "grenade", "movement"}:
                remember_sound(memory, sound, now=now, actor_pos=actor_pos)
