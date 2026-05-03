from __future__ import annotations

import math

from shared.constants import WEAPONS
from shared.models import PlayerState, WeaponRuntime
from shared.rarities import rarity_rank
from shared.weapon_modules import WEAPON_MODULES


class WeaponRuntimeService:
    def update_player_weapons(self, player: PlayerState, dt: float) -> None:
        for weapon in player.weapons.values():
            weapon.cooldown = max(0.0, weapon.cooldown - dt)

            if weapon.reload_left > 0.0:
                weapon.reload_left = max(0.0, weapon.reload_left - dt)

                if weapon.reload_left == 0.0:
                    self.finish_reload(weapon)

    def start_reload(self, player: PlayerState) -> None:
        weapon = player.active_weapon()

        if not weapon:
            return

        spec = WEAPONS[weapon.key]

        if (
            weapon.reload_left <= 0.0
            and weapon.reserve_ammo > 0
            and weapon.ammo_in_mag < self.magazine_size(weapon)
        ):
            weapon.reload_left = spec.reload_time

    def finish_reload(self, weapon: WeaponRuntime) -> None:
        needed = self.magazine_size(weapon) - weapon.ammo_in_mag
        loaded = min(needed, weapon.reserve_ammo)

        weapon.ammo_in_mag += loaded
        weapon.reserve_ammo -= loaded

    def magazine_size(self, weapon: WeaponRuntime) -> int:
        base = WEAPONS[weapon.key].magazine_size
        module_key = weapon.modules.get("magazine")
        module = WEAPON_MODULES.get(module_key or "")
        multiplier = module.magazine_multiplier if module else 1.0

        return max(base, int(math.ceil(base * multiplier)))

    def spread(self, weapon: WeaponRuntime) -> float:
        spread = WEAPONS[weapon.key].spread
        module_key = weapon.modules.get("utility")
        module = WEAPON_MODULES.get(module_key or "")

        if module_key == "laser_module" and weapon.utility_on and module:
            spread *= module.spread_multiplier
        elif module and module_key in {"silencer", "compensator"}:
            spread *= module.spread_multiplier

        return spread

    def fire_rate(self, weapon: WeaponRuntime) -> float:
        spec = WEAPONS[weapon.key]
        rate = spec.fire_rate
        module_key = weapon.modules.get("utility") or ""
        module = WEAPON_MODULES.get(module_key)

        if module and module_key == "compensator":
            rarity_step = rarity_rank(weapon.rarity)
            bonus = module.fire_rate_bonus + module.fire_rate_rarity_step * rarity_step
            rate *= 1.0 + max(0.0, bonus)

        return max(0.1, rate)

    def toggle_utility(self, player: PlayerState) -> bool:
        weapon = player.active_weapon()

        if not weapon:
            return False

        if weapon.modules.get("utility") not in {"laser_module", "flashlight_module"}:
            return False

        weapon.utility_on = not weapon.utility_on
        return True

    def projectile_life(self, projectile_speed: float) -> float:
        max_range = 1400.0
        return max(0.18, max_range / max(1.0, projectile_speed))