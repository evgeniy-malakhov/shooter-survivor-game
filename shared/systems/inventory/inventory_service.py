from __future__ import annotations

import random
from typing import Any

from shared.constants import ARMORS, INTERACT_RADIUS, PICKUP_RADIUS, SLOTS, WEAPONS
from shared.crafting import roll_crafted_rarity
from shared.items import ITEMS, RECIPES
from shared.models import InventoryItem, LootState, PlayerState, WeaponRuntime
from shared.rarities import rarity_spec
from shared.world.world_state import WorldState


class InventoryService:
    def __init__(
        self,
        *,
        state: WorldState,
        rng: random.Random,
        backpack_config,
        loot,
        buildings,
        ids,
    ) -> None:
        self._state = state
        self._rng = rng
        self._backpack_config = backpack_config
        self._loot = loot
        self._buildings = buildings
        self._ids = ids

    def nearest_loot(self, player: PlayerState) -> LootState | None:
        best: LootState | None = None
        best_distance = float("inf")

        for loot in self._state.loot.values():
            if loot.floor != player.floor:
                continue

            distance = player.pos.distance_to(loot.pos)

            if distance <= PICKUP_RADIUS and distance < best_distance:
                best = loot
                best_distance = distance

        return best

    def pickup_nearby(self, player: PlayerState) -> bool:
        loot = self.nearest_loot(player)

        if not loot:
            return False

        if loot.kind == "weapon":
            weapon_spec = WEAPONS.get(loot.payload)
            if not weapon_spec:
                return False

            player.weapons[weapon_spec.slot] = WeaponRuntime(
                loot.payload,
                weapon_spec.magazine_size,
                0,
                rarity=loot.rarity,
            )

        elif loot.kind == "ammo":
            weapon = player.weapons.get(loot.payload)
            if weapon:
                weapon.reserve_ammo += loot.amount

        elif loot.kind == "medkit":
            player.medkits += loot.amount

        elif loot.kind in {"armor", "item"}:
            if not self.add_item(player, loot.payload, loot.amount, rarity=loot.rarity):
                self.set_notice(player, "inventory_full")
                return False

        else:
            return False

        self._state.loot.pop(loot.id, None)
        return True

    def equip_armor(self, player: PlayerState, armor_key: str) -> None:
        for index, item in enumerate(player.backpack):
            if not item or item.key != armor_key:
                continue

            spec = ITEMS.get(item.key)
            if not spec or not spec.equipment_slot:
                return

            displaced = player.equipment.get(spec.equipment_slot)
            player.equipment[spec.equipment_slot] = item
            player.backpack[index] = displaced

            if spec.armor_key:
                player.armor_key = spec.armor_key
                player.armor = self.effective_armor_points(item)

            return

    def apply_inventory_action(self, player: PlayerState, action: dict[str, Any]) -> None:
        action_type = str(action.get("type", ""))

        if action_type == "move":
            self.move_inventory_item(player, action)
        elif action_type == "quick_swap":
            self.quick_swap(player, action)
        elif action_type == "repair_drag":
            self.repair_with_kit(player, action)
        elif action_type == "unequip_module":
            self.unequip_module(player, action)
        elif action_type == "drop":
            self.drop_item(player, action)

    def move_inventory_item(self, player: PlayerState, action: dict[str, Any]) -> None:
        src = str(action.get("src", action.get("source", "backpack")))
        dst = str(action.get("dst", action.get("destination", "backpack")))

        src_index = int(action.get("src_index", action.get("source_index", action.get("index", -1))))
        dst_index = int(action.get("dst_index", action.get("destination_index", -1)))

        src_slot = str(action.get("src_slot", action.get("source_slot", action.get("slot", ""))))
        dst_slot = str(action.get("dst_slot", action.get("destination_slot", "")))

        src_module = str(action.get("src_module", action.get("module_slot", "")))
        dst_module = str(action.get("dst_module", action.get("module_slot", "")))

        if src == "weapon_slot":
            if dst != "backpack":
                return

            if not (0 <= dst_index < len(player.backpack)):
                return

            if player.backpack[dst_index] is not None:
                return

        item = self.take_item(player, src, src_index, src_slot, src_module)

        if not item:
            return

        displaced = self.place_item(player, dst, dst_index, dst_slot, item, dst_module)

        if displaced:
            returned = self.place_item(player, src, src_index, src_slot, displaced, src_module)

            if returned:
                self.add_item(player, returned.key, returned.amount, rarity=returned.rarity)

        self.recalculate_armor(player)

    def quick_swap(self, player: PlayerState, action: dict[str, Any]) -> None:
        a = str(action.get("a", ""))
        b = str(action.get("b", ""))

        if a not in SLOTS or b not in SLOTS:
            return

        player.weapons[a], player.weapons[b] = player.weapons.get(b), player.weapons.get(a)

        if player.weapons.get(a) is None:
            player.weapons.pop(a, None)

        if player.weapons.get(b) is None:
            player.weapons.pop(b, None)

        player.quick_items[a], player.quick_items[b] = (
            player.quick_items.get(b),
            player.quick_items.get(a),
        )

    def unequip_module(self, player: PlayerState, action: dict[str, Any]) -> None:
        slot = str(action.get("slot", ""))
        module_slot = str(action.get("module_slot", ""))

        item = self.take_item(
            player,
            "weapon_module",
            -1,
            slot,
            module_slot,
        )

        if not item:
            return

        if not self.add_item(player, item.key, item.amount, rarity=item.rarity):
            self.place_item(
                player,
                "weapon_module",
                -1,
                slot,
                item,
                module_slot,
            )

    def drop_item(self, player: PlayerState, action: dict[str, Any]) -> None:
        source = str(action.get("src", action.get("source", "backpack")))
        index = int(action.get("src_index", action.get("index", -1)))
        slot = str(action.get("src_slot", action.get("slot", "")))
        module_slot = str(action.get("src_module", action.get("module_slot", "")))

        item = self.take_item(player, source, index, slot, module_slot)

        if not item:
            return

        self._loot.spawn_loot(
            loot_id=self._ids.next("l"),
            pos=player.pos.copy(),
            kind="item",
            payload=item.key,
            amount=item.amount,
            floor=player.floor,
            rarity=item.rarity,
        )

    def take_item(
            self,
            player: PlayerState,
            source: str,
            index: int,
            slot: str,
            module_slot: str = "",
    ) -> InventoryItem | None:
        if source == "backpack" and 0 <= index < len(player.backpack):
            item = player.backpack[index]
            player.backpack[index] = None
            return item

        if source == "weapon_slot" and slot in player.weapons:
            weapon = player.weapons.pop(slot, None)

            if not weapon:
                return None

            if player.active_slot == slot:
                player.active_slot = next(
                    (slot_key for slot_key in SLOTS if player.weapons.get(slot_key)),
                    slot,
                )

            return self._new_item(
                weapon.key,
                1,
                rarity=weapon.rarity,
                durability=weapon.durability,
            )

        if source == "equipment" and slot in player.equipment:
            item = player.equipment.get(slot)
            player.equipment[slot] = None
            self.recalculate_armor(player)
            return item

        if source == "quick_item" and slot in SLOTS:
            item = player.quick_items.get(slot)
            player.quick_items[slot] = None
            return item

        if source == "weapon_module":
            weapon = player.weapons.get(slot)

            if not weapon or module_slot not in weapon.modules:
                return None

            module_key = weapon.modules.get(module_slot)

            if not module_key:
                return None

            weapon.modules[module_slot] = None

            if module_slot == "utility":
                weapon.utility_on = False

            if module_slot == "magazine":
                # если сняли расширенный магазин — обрезаем патроны до нового лимита
                base_magazine = WEAPONS[weapon.key].magazine_size
                weapon.ammo_in_mag = min(weapon.ammo_in_mag, base_magazine)

            return self._new_item(
                module_key,
                1,
                rarity=weapon.rarity,
            )

        return None

    def place_item(
            self,
            player: PlayerState,
            destination: str,
            index: int,
            slot: str,
            item: InventoryItem,
            module_slot: str = "",
    ) -> InventoryItem | None:
        if destination == "backpack" and 0 <= index < len(player.backpack):
            displaced = player.backpack[index]
            player.backpack[index] = item
            return displaced

        if destination == "weapon_slot":
            weapon_spec = WEAPONS.get(item.key)

            if not weapon_spec:
                return item

            displaced_weapon = player.weapons.get(weapon_spec.slot)

            player.weapons[weapon_spec.slot] = WeaponRuntime(
                item.key,
                weapon_spec.magazine_size,
                0,
                rarity=item.rarity,
                durability=item.durability,
            )

            if displaced_weapon:
                return self._new_item(
                    displaced_weapon.key,
                    1,
                    rarity=displaced_weapon.rarity,
                    durability=displaced_weapon.durability,
                )

            return None

        if destination == "weapon_module":
            weapon = player.weapons.get(slot)

            if not weapon:
                return item

            spec = ITEMS.get(item.key)

            if not spec or spec.kind != "weapon_module":
                return item

            if not module_slot:
                return item

            displaced_key = weapon.modules.get(module_slot)
            weapon.modules[module_slot] = item.key

            if module_slot == "utility" and item.key not in {"laser_module", "flashlight_module"}:
                weapon.utility_on = False

            if displaced_key:
                return self._new_item(
                    displaced_key,
                    1,
                    rarity=item.rarity,
                )

            return None

        if destination == "equipment":
            spec = ITEMS.get(item.key)

            if not spec or spec.equipment_slot != slot:
                return item

            displaced = player.equipment.get(slot)
            player.equipment[slot] = item

            self.recalculate_armor(player)

            return displaced

        if destination == "quick_item":
            spec = ITEMS.get(item.key)

            if not spec or spec.kind not in {"grenade", "mine"}:
                return item

            displaced = player.quick_items.get(slot)
            player.quick_items[slot] = item
            return displaced

        return item

    def use_item(self, player: PlayerState, item: InventoryItem) -> bool:
        spec = ITEMS.get(item.key)

        if not spec:
            return False

        if spec.kind in {"food", "medical"} and spec.heal_total > 0 and player.health < 100:
            player.healing_pool += float(spec.heal_total)
            player.healing_left = max(player.healing_left, max(0.1, spec.heal_seconds))
            player.healing_rate = spec.heal_total / max(0.1, spec.heal_seconds)
            player.healing_stacks = max(1, player.healing_stacks + 1)
            return True

        if spec.kind == "ammo":
            for weapon in player.weapons.values():
                weapon.reserve_ammo += 12 * item.amount
            return True

        return False

    def craft(self, player: PlayerState, recipe_key: str) -> None:
        if not self._buildings.nearest_prop(player.pos, INTERACT_RADIUS, player.floor):
            return

        recipe = RECIPES.get(recipe_key)

        if not recipe:
            return

        if any(self.count_item(player, key) < amount for key, amount in recipe.requires.items()):
            return

        result_key, result_amount = recipe.result
        result_spec = ITEMS.get(result_key)
        result_kind = result_spec.kind if result_spec else "item"
        result_rarity = roll_crafted_rarity(self._rng, recipe.key, result_kind)

        if not self.can_add_item(player, result_key, result_amount, result_rarity):
            self.set_notice(player, "inventory_full")
            return

        for key, amount in recipe.requires.items():
            self.remove_items(player, key, amount)

        self.add_item(
            player,
            result_key,
            result_amount,
            rarity=result_rarity,
        )

    def repair_armor(self, player: PlayerState, slot: str) -> None:
        if not self._buildings.nearest_prop(player.pos, INTERACT_RADIUS, player.floor):
            return

        item = player.equipment.get(slot)

        if not item:
            return

        if not self.remove_items(player, "repair_kit", 1):
            return

        spec = ITEMS.get(item.key)

        if spec and spec.armor_key and spec.armor_key in ARMORS:
            player.armor_key = spec.armor_key
            player.armor = min(
                self.effective_armor_points(item),
                player.armor + 35,
            )

    def repair_with_kit(self, player: PlayerState, action: dict[str, Any]) -> None:
        kit_index = int(action.get("kit_index", -1))
        target_source = str(action.get("target_source", ""))
        target_index = int(action.get("target_index", -1))
        target_slot = str(action.get("target_slot", ""))

        if not (0 <= kit_index < len(player.backpack)):
            return

        kit = player.backpack[kit_index]

        if not kit or kit.key != "repair_kit":
            return

        target = None

        if target_source == "backpack" and 0 <= target_index < len(player.backpack):
            target = player.backpack[target_index]
        elif target_source == "equipment" and target_slot in player.equipment:
            target = player.equipment[target_slot]
        elif target_source == "quick_item" and target_slot in SLOTS:
            target = player.quick_items.get(target_slot)
        elif target_source == "weapon_slot" and target_slot in player.weapons:
            weapon = player.weapons[target_slot]
            weapon.durability = 100.0
            kit.amount -= 1
            if kit.amount <= 0:
                player.backpack[kit_index] = None
            return

        if not target or target.durability >= 100.0:
            return

        target.durability = 100.0
        kit.amount -= 1

        if kit.amount <= 0:
            player.backpack[kit_index] = None

    def recalculate_armor(self, player: PlayerState) -> None:
        total = 0
        armor_key = "none"

        for item in player.equipment.values():
            if not item:
                continue

            spec = ITEMS.get(item.key)

            if not spec or not spec.armor_key:
                continue

            total += self.effective_armor_points(item)
            armor_key = spec.armor_key

        player.armor = total
        player.armor_key = armor_key

    def _new_item(
        self,
        key: str,
        amount: int = 1,
        *,
        rarity: str = "common",
        durability: float | None = None,
    ) -> InventoryItem:
        if durability is None:
            durability = rarity_spec(rarity).armor_durability_multiplier * 100.0

        return InventoryItem(
            self._ids.next("it"),
            key,
            amount,
            rarity=rarity,
            durability=durability,
        )

    def add_item(
        self,
        player: PlayerState,
        key: str,
        amount: int = 1,
        *,
        rarity: str = "common",
    ) -> bool:
        spec = ITEMS.get(key)

        if not spec or amount <= 0:
            return False

        remaining = amount

        for item in player.backpack:
            if item and item.key == key and item.rarity == rarity and item.amount < spec.stack_size:
                add = min(remaining, spec.stack_size - item.amount)
                item.amount += add
                remaining -= add

                if remaining <= 0:
                    return True

        for index, item in enumerate(player.backpack):
            if item is not None:
                continue

            add = min(remaining, spec.stack_size)
            print(f"adding {add} {key} to slot {index}")

            player.backpack[index] = self._new_item(
                key,
                add,
                rarity=rarity,
            )

            remaining -= add

            if remaining <= 0:
                return True

        return remaining <= 0

    def can_add_item(
        self,
        player: PlayerState,
        key: str,
        amount: int,
        rarity: str = "common",
    ) -> bool:
        spec = ITEMS.get(key)

        if not spec:
            return False

        remaining = amount

        for item in player.backpack:
            if item and item.key == key and item.rarity == rarity and item.amount < spec.stack_size:
                remaining -= min(remaining, spec.stack_size - item.amount)

                if remaining <= 0:
                    return True

        empty_slots = sum(1 for item in player.backpack if item is None)
        capacity = empty_slots * spec.stack_size

        return capacity >= remaining

    def remove_items(self, player: PlayerState, key: str, amount: int) -> bool:
        if self.count_item(player, key) < amount:
            return False

        remaining = amount

        for item in player.backpack:
            if not item or item.key != key:
                continue

            take = min(item.amount, remaining)
            item.amount -= take
            remaining -= take

            if item.amount <= 0:
                index = player.backpack.index(item)
                player.backpack[index] = None

            if remaining <= 0:
                return True

        return remaining <= 0

    def count_item(self, player: PlayerState, key: str) -> int:
        return sum(
            item.amount
            for item in player.backpack
            if item and item.key == key
        )

    def effective_armor_points(self, item: InventoryItem | None) -> int:
        spec = ITEMS.get(item.key) if item else None

        if not item or not spec or not spec.armor_key:
            return 0

        armor = ARMORS.get(spec.armor_key, ARMORS["none"])
        rarity = rarity_spec(item.rarity)

        return max(
            0,
            int(round(armor.armor_points * rarity.armor_points_multiplier)),
        )

    def set_notice(self, player: PlayerState, key: str, seconds: float = 2.2) -> None:
        player.notice = key
        player.notice_timer = max(player.notice_timer, seconds)