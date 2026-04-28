# Game Configuration Guide

All files in this folder are UTF-8 JSON, except this documentation file. Restart the game or server after changing balance configs, because they are loaded when Python modules are imported.

## Core Files

- `weapons.json` configures hand weapons.
- `zombies.json` configures enemy archetypes.
- `armors.json` configures base armor tiers.
- `rarities.json` configures item rarity colors and bonuses.
- `explosives.json` configures thrown grenades and placed mines.
- `weapon_modules.json` configures laser, flashlight and magazine modules.
- `backpack.json` configures the starting backpack.
- `item_stacks.json` configures stack sizes for backpack items.
- `icon_mapping.json` maps game ids to PNG filenames in `images/`.
- `difficulty/*.json` configures world difficulty presets.

## Items

Item definitions live in `shared/items.py`; stack limits live in `item_stacks.json`; display names live in `locales/en.json` and `locales/ru.json`; icons are loaded from `images/` by item key or by `icon_mapping.json`.

Current items:

- Food: `apple`, `canned_food`, `energy_bar`.
- Medical: `bandage`, `medicine`.
- Resources: `scrap`, `cloth`, `duct_tape`, `circuit`, `gunpowder`.
- Ammo/tool: `ammo_pack`, `repair_kit`.
- Grenades: `contact_grenade`, `grenade`, `heavy_grenade`.
- Mines: `mine_light`, `mine_standard`, `mine_heavy`.
- Weapon modules: `laser_module`, `flashlight_module`, `extended_mag`.
- Armor pieces: `light_head`, `light_torso`, `light_arms`, `light_legs`, `medium_head`, `medium_torso`, `medium_arms`, `medium_legs`, `heavy_head`, `heavy_torso`, `heavy_arms`, `heavy_legs`.

To add a new item:

1. Add its `ItemSpec` in `shared/items.py`.
2. Add a stack limit in `item_stacks.json`.
3. Add localized names in `locales/en.json` and `locales/ru.json` using `item.<key>`.
4. Add it to `HOUSE_LOOT` or `WORLD_LOOT` in `shared/items.py` if it should spawn.
5. Add a recipe in `RECIPES` if it should be craftable, and localize `recipe.<key>`.
6. Add a PNG to `images/<key>.png`, or add an entry to `icon_mapping.json` if another filename should be reused.

## Icon Mapping

`icon_mapping.json` is a simple object where each key is the game id and each value is the PNG filename without extension. The client first loads every `images/*.png` by filename, then applies this mapping as aliases.

Examples:

- `grenade` maps to `granade` because the current PNG filename is `granade.png`.
- `gunpowder` maps to `gun_powder`.
- `duct_tape` maps to `dust_type`.
- `light_head` maps to `light_helmet`.
- Rarity badges use `common`, `uncommon`, `rare` and `legendary`.

When adding a new item, prefer naming the PNG exactly like the item key. Use `icon_mapping.json` only for legacy filenames, shared icons, or deliberately reused visuals.

## Weapons

`weapons.json` entries are keyed by weapon id. Every weapon supports:

- `title`: fallback display name.
- `slot`: default quick slot, usually `1` to `0`.
- `damage`: base damage before difficulty and rarity multipliers.
- `magazine_size`: base magazine capacity.
- `fire_rate`: shots per second.
- `reload_time`: seconds to reload.
- `projectile_speed`: projectile velocity.
- `spread`: base inaccuracy in radians.
- `pellets`: projectile count per shot, useful for shotguns.

Current weapons:

- `pistol`: accurate starter weapon.
- `smg`: fast low-damage automatic weapon.
- `shotgun`: short-range multi-pellet burst weapon.
- `rifle`: higher-damage accurate weapon.

Weapon rarity is stored on each dropped or owned weapon. Rarity multiplies final weapon damage and reduces durability wear.

## Armors

`armors.json` entries are base armor tiers:

- `none`: no armor.
- `light`: findable light armor tier.
- `medium`: craft-focused medium tier.
- `tactical`: legacy tactical tier used by older loot paths.
- `heavy`: high-protection armor tier.

Fields:

- `title`: fallback display name.
- `mitigation`: damage reduction ratio before rarity.
- `armor_points`: armor bar capacity before rarity.

Armor items store their own rarity. Rarity increases armor points, mitigation and durability resistance.

## Rarities

`rarities.json` controls rarity balance for weapons and armor:

- `common`: gray, baseline stats.
- `uncommon`: blue, modest stat and durability bonus.
- `rare`: purple, strong stat and durability bonus.
- `legendary`: gold, highest bonus and lowest spawn chance.

Fields:

- `title`: fallback title.
- `color`: `[red, green, blue]` used on map, backpack, quickbar and drag preview.
- `loot_weight`: weighted spawn chance for weapon and armor loot.
- `weapon_damage_multiplier`: multiplies weapon damage.
- `weapon_durability_multiplier`: divides weapon wear.
- `armor_points_multiplier`: multiplies armor bar capacity.
- `armor_mitigation_multiplier`: multiplies armor damage reduction.
- `armor_durability_multiplier`: divides armor wear.

Higher rarity weapons and armor are shown with their rarity color on the map and in inventory UI.

## Explosives

`explosives.json` has two sections: `grenades` and `mines`.

Grenade fields:

- `title`: fallback display name.
- `timer`: detonation timer in seconds.
- `contact`: if true, detonates on wall or actor contact.
- `throw_distance`: initial throw velocity/distance feel.
- `blast_radius`: damage radius.
- `zombie_damage`, `zombie_damage_bonus`: scaled damage to enemies.
- `player_damage`, `player_damage_bonus`: scaled damage to players.

Current hand-carried grenades:

- `contact_grenade`: explodes on contact and throws farther.
- `grenade`: standard 2-second fragmentation grenade.
- `heavy_grenade`: 3-second heavy grenade with double standard radius and damage.

Mine fields:

- `trigger_radius`: radius that arms/triggers the mine.
- `blast_radius`: explosion damage radius.
- Damage fields match grenade damage fields.

Current mines:

- `mine_light`: smaller trigger and blast radius, easier to carry.
- `mine_standard`: balanced field mine.
- `mine_heavy`: larger radius and damage, rarer and heavier in stack limits.

Mines are selected in a quick slot and placed with left mouse. A placed mine becomes active only after the owner leaves its trigger radius. Once active, enemies or players entering the trigger radius detonate it.

## Zombies

`zombies.json` entries are keyed by enemy type:

- `walker`: standard balanced enemy.
- `runner`: fast, low-health enemy.
- `brute`: slow armored enemy.
- `leaper`: chase-specialist enemy with sidestep movement and poison spit.

Fields:

- `title`: fallback display name.
- `health`, `armor`, `speed`, `damage`, `radius`: combat stats.
- `color`: `[red, green, blue]` for rendering.
- `sight_range`: maximum vision range.
- `hearing_range`: base hearing range.
- `fov_degrees`: field of view cone.
- `sensitivity`: reaction multiplier for noise.
- `suspicion_time`: tuning value for detection behavior.

If you add a zombie key, also add localized scoreboard labels if you want it displayed separately.

## Starting Backpack

`backpack.json`:

- `slots`: backpack cell count.
- `starting_weapon.key`: weapon key from `weapons.json`.
- `starting_weapon.reserve_ammo`: reserve ammo.
- `starting_items`: list of `{ "key": "...", "amount": N }`.

Starting items are created as common rarity.

## Stack Sizes

`item_stacks.json` maps item keys to maximum stack amounts. Armor and modules usually stay at `1`. Explosives are intentionally lower than resources.

## Difficulty

`difficulty/*.json` controls the world-level multipliers:

- zombie count, health, armor, speed and damage;
- weapon and armor wear;
- global and per-weapon damage multipliers;
- loot spawn amount and spawn interval.

Difficulty is applied by the authoritative server in online mode.
