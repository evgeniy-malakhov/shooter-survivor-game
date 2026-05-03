from __future__ import annotations

from shared.constants import MAP_HEIGHT, MAP_WIDTH, PLAYER_RADIUS, SOLDIERS, ZOMBIES
from shared.models import ProjectileState
from shared.systems.base import WorldSystem
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class ProjectileSystem(WorldSystem):
    def update(self, state: WorldState, ctx: WorldContext, dt: float) -> None:
        dead_projectiles: list[str] = []

        for projectile in list(state.projectiles.values()):
            projectile.life -= dt
            projectile.pos.add(projectile.velocity.scaled(dt))

            if self._should_remove_projectile(projectile, ctx):
                dead_projectiles.append(projectile.id)
                continue

            if self._hit_zombie(projectile, state, ctx):
                dead_projectiles.append(projectile.id)
                continue

            if self._hit_soldier(projectile, state, ctx):
                dead_projectiles.append(projectile.id)
                continue

            if self._hit_player(projectile, state, ctx):
                dead_projectiles.append(projectile.id)

        for projectile_id in dead_projectiles:
            state.projectiles.pop(projectile_id, None)

    def _should_remove_projectile(
        self,
        projectile: ProjectileState,
        ctx: WorldContext,
    ) -> bool:
        return (
            projectile.life <= 0.0
            or projectile.pos.x < 0
            or projectile.pos.y < 0
            or projectile.pos.x > MAP_WIDTH
            or projectile.pos.y > MAP_HEIGHT
            or ctx.geometry.blocked_at(
                projectile.pos,
                projectile.radius,
                projectile.floor,
            )
        )

    def _hit_zombie(
        self,
        projectile: ProjectileState,
        state: WorldState,
        ctx: WorldContext,
    ) -> bool:
        for zombie in list(state.zombies.values()):
            if zombie.floor != projectile.floor:
                continue

            spec = ZOMBIES[zombie.kind]

            if projectile.pos.distance_to(zombie.pos) <= spec.radius + projectile.radius:
                ctx.damage.damage_zombie(
                    zombie,
                    projectile.damage,
                    projectile.owner_id,
                )
                return True

        return False

    def _hit_soldier(
        self,
        projectile: ProjectileState,
        state: WorldState,
        ctx: WorldContext,
    ) -> bool:
        for soldier in list(state.soldiers.values()):
            if soldier.floor != projectile.floor:
                continue

            if projectile.owner_id == soldier.id:
                continue

            spec = SOLDIERS[soldier.kind]

            if projectile.pos.distance_to(soldier.pos) <= spec.radius + projectile.radius:
                ctx.damage.damage_soldier(
                    soldier,
                    projectile.damage,
                    projectile.owner_id,
                )
                return True

        return False

    def _hit_player(
        self,
        projectile: ProjectileState,
        state: WorldState,
        ctx: WorldContext,
    ) -> bool:
        for player in list(state.players.values()):
            if not player.alive:
                continue

            if player.floor != projectile.floor:
                continue

            if projectile.owner_id == player.id:
                continue

            if projectile.pos.distance_to(player.pos) <= PLAYER_RADIUS + projectile.radius:
                ctx.damage.damage_player(player, projectile.damage)
                return True

        return False