from shared.ai.zombies.base_zombie import BaseZombieAI


class SpitterZombieAI(BaseZombieAI):
    kind = "spitter"

    def update(self, ctx):
        result = super().update(ctx)

        target = self._select_target(ctx)
        if not target:
            return result

        distance = ctx.zombie.pos.distance_to(target.pos)

        if (
            ctx.zombie.special_cooldown <= 0
            and 180 <= distance <= 720
            and not ctx.line_blocked(ctx.zombie.pos, target.pos, ctx.zombie.floor)
        ):
            result.poison_spits.append({
                "owner_id": ctx.zombie.id,
                "from": ctx.zombie.pos.copy(),
                "target": target.pos.copy(),
                "floor": ctx.zombie.floor,
            })
            ctx.zombie.special_cooldown = ctx.rng.uniform(2.8, 4.2)

        return result