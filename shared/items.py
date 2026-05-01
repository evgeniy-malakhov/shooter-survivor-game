from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from shared.models import ItemSpec

STACK_CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "item_stacks.json"


def _load_stack_sizes() -> dict[str, int]:
    if not STACK_CONFIG_PATH.exists():
        return {}
    data = json.loads(STACK_CONFIG_PATH.read_text(encoding="utf-8"))
    return {str(key): max(1, int(value)) for key, value in data.items()}


STACK_SIZES = _load_stack_sizes()


def _stack(key: str, fallback: int) -> int:
    return STACK_SIZES.get(key, fallback)


EQUIPMENT_SLOTS = ["head", "torso", "legs", "arms"]
ARMOR_LEVELS = {
    "light": {"title": "Light", "color": (152, 204, 255), "world": True},
    "medium": {"title": "Medium", "color": (177, 132, 255), "world": False},
    "heavy": {"title": "Heavy", "color": (126, 154, 255), "world": False},
}
SLOT_TITLES = {"head": "Helmet", "torso": "Vest", "arms": "Guards", "legs": "Plates"}


def _armor_items() -> dict[str, ItemSpec]:
    items: dict[str, ItemSpec] = {}
    for level, meta in ARMOR_LEVELS.items():
        for slot, title in SLOT_TITLES.items():
            key = f"{level}_{slot}"
            items[key] = ItemSpec(
                key,
                f"{meta['title']} {title}",
                "armor",
                stack_size=_stack(key, 1),
                equipment_slot=slot,
                armor_key=level,
                color=meta["color"],
            )
    return items


ITEMS: dict[str, ItemSpec] = {
    "apple": ItemSpec("apple", "Apple", "food", stack_size=_stack("apple", 8), heal_total=12, heal_seconds=5.0, color=(132, 232, 114)),
    "canned_food": ItemSpec("canned_food", "Canned Food", "food", stack_size=_stack("canned_food", 6), heal_total=24, heal_seconds=8.0, color=(235, 186, 92)),
    "energy_bar": ItemSpec("energy_bar", "Energy Bar", "food", stack_size=_stack("energy_bar", 10), heal_total=16, heal_seconds=4.0, color=(246, 220, 92)),
    "bandage": ItemSpec("bandage", "Bandage", "medical", stack_size=_stack("bandage", 6), heal_total=28, heal_seconds=7.0, color=(244, 244, 224)),
    "medicine": ItemSpec("medicine", "Medicine", "medical", stack_size=_stack("medicine", 4), heal_total=45, heal_seconds=10.0, color=(118, 226, 255)),
    "scrap": ItemSpec("scrap", "Scrap Metal", "resource", stack_size=_stack("scrap", 20), color=(154, 164, 178)),
    "cloth": ItemSpec("cloth", "Cloth", "resource", stack_size=_stack("cloth", 20), color=(192, 184, 160)),
    "duct_tape": ItemSpec("duct_tape", "Duct Tape", "resource", stack_size=_stack("duct_tape", 12), color=(164, 174, 198)),
    "circuit": ItemSpec("circuit", "Circuit Board", "resource", stack_size=_stack("circuit", 10), color=(80, 220, 150)),
    "gunpowder": ItemSpec("gunpowder", "Gunpowder", "resource", stack_size=_stack("gunpowder", 20), color=(96, 96, 106)),
    "ammo_pack": ItemSpec("ammo_pack", "Ammo Pack", "ammo", stack_size=_stack("ammo_pack", 12), color=(255, 210, 112)),
    "contact_grenade": ItemSpec("contact_grenade", "Impact Grenade", "grenade", stack_size=_stack("contact_grenade", 3), color=(103, 236, 190)),
    "grenade": ItemSpec("grenade", "Grenade", "grenade", stack_size=_stack("grenade", 4), color=(96, 180, 108)),
    "heavy_grenade": ItemSpec("heavy_grenade", "Heavy Grenade", "grenade", stack_size=_stack("heavy_grenade", 2), color=(255, 128, 92)),
    "mine_light": ItemSpec("mine_light", "Light Mine", "mine", stack_size=_stack("mine_light", 3), color=(120, 225, 255)),
    "mine_standard": ItemSpec("mine_standard", "Field Mine", "mine", stack_size=_stack("mine_standard", 3), color=(255, 210, 112)),
    "mine_heavy": ItemSpec("mine_heavy", "Heavy Mine", "mine", stack_size=_stack("mine_heavy", 2), color=(255, 91, 111)),
    "repair_kit": ItemSpec("repair_kit", "Repair Kit", "tool", stack_size=_stack("repair_kit", 4), color=(255, 146, 100)),
    "laser_module": ItemSpec("laser_module", "Laser Sight", "weapon_module", stack_size=_stack("laser_module", 1), color=(255, 84, 98)),
    "flashlight_module": ItemSpec("flashlight_module", "Flashlight", "weapon_module", stack_size=_stack("flashlight_module", 1), color=(255, 238, 148)),
    "silencer": ItemSpec("silencer", "Silencer", "weapon_module", stack_size=_stack("silencer", 1), color=(156, 198, 255)),
    "compensator": ItemSpec("compensator", "Compensator", "weapon_module", stack_size=_stack("compensator", 1), color=(255, 196, 142)),
    "extended_mag": ItemSpec("extended_mag", "Extended Magazine", "weapon_module", stack_size=_stack("extended_mag", 1), color=(116, 204, 255)),
    **_armor_items(),
}

LEGACY_LOOT_TO_ITEM = {
    "medkit": "medicine",
    "armor": "light_torso",
    "ammo": "ammo_pack",
}


@dataclass(frozen=True, slots=True)
class Recipe:
    key: str
    title: str
    requires: dict[str, int]
    result: tuple[str, int]


RECIPES: dict[str, Recipe] = {
    "bandage_bundle": Recipe("bandage_bundle", "Bandage Bundle", {"cloth": 3, "duct_tape": 1}, ("bandage", 2)),
    "repair_kit": Recipe("repair_kit", "Repair Kit", {"scrap": 4, "duct_tape": 2}, ("repair_kit", 1)),
    "ammo_pack": Recipe("ammo_pack", "Ammo Pack", {"scrap": 2, "gunpowder": 3}, ("ammo_pack", 2)),
    "contact_grenade": Recipe("contact_grenade", "Impact Grenade", {"scrap": 2, "gunpowder": 4, "circuit": 1}, ("contact_grenade", 1)),
    "grenade": Recipe("grenade", "Grenade", {"scrap": 3, "gunpowder": 5, "duct_tape": 1}, ("grenade", 1)),
    "heavy_grenade": Recipe("heavy_grenade", "Heavy Grenade", {"scrap": 5, "gunpowder": 9, "duct_tape": 2}, ("heavy_grenade", 1)),
    "mine_light": Recipe("mine_light", "Light Mine", {"scrap": 3, "gunpowder": 3, "circuit": 1}, ("mine_light", 1)),
    "mine_standard": Recipe("mine_standard", "Field Mine", {"scrap": 5, "gunpowder": 5, "circuit": 1, "duct_tape": 1}, ("mine_standard", 1)),
    "mine_heavy": Recipe("mine_heavy", "Heavy Mine", {"scrap": 8, "gunpowder": 8, "circuit": 2, "duct_tape": 2}, ("mine_heavy", 1)),
    "laser_module": Recipe("laser_module", "Laser Sight", {"circuit": 1, "scrap": 2, "duct_tape": 1}, ("laser_module", 1)),
    "flashlight_module": Recipe("flashlight_module", "Flashlight", {"circuit": 1, "scrap": 2, "cloth": 1}, ("flashlight_module", 1)),
    "silencer": Recipe("silencer", "Silencer", {"scrap": 3, "duct_tape": 2, "circuit": 1}, ("silencer", 1)),
    "compensator": Recipe("compensator", "Compensator", {"scrap": 4, "gunpowder": 2, "circuit": 1}, ("compensator", 1)),
    "extended_mag": Recipe("extended_mag", "Extended Magazine", {"scrap": 4, "duct_tape": 1}, ("extended_mag", 1)),
}

for slot, title in SLOT_TITLES.items():
    RECIPES[f"medium_{slot}"] = Recipe(
        f"medium_{slot}",
        f"Medium {title}",
        {"cloth": 4, "scrap": 5, "duct_tape": 2},
        (f"medium_{slot}", 1),
    )
    RECIPES[f"heavy_{slot}"] = Recipe(
        f"heavy_{slot}",
        f"Heavy {title}",
        {"cloth": 5, "scrap": 8, "duct_tape": 3, "circuit": 1},
        (f"heavy_{slot}", 1),
    )


HOUSE_LOOT = [
    ("apple", 1, 5),
    ("canned_food", 1, 4),
    ("energy_bar", 1, 5),
    ("bandage", 1, 3),
    ("medicine", 1, 2),
    ("cloth", 1, 4),
    ("duct_tape", 1, 3),
    ("scrap", 1, 5),
    ("circuit", 1, 2),
    ("repair_kit", 1, 1),
    ("contact_grenade", 1, 1),
    ("grenade", 1, 1),
    ("heavy_grenade", 1, 1),
    ("mine_light", 1, 1),
    ("mine_standard", 1, 1),
    ("laser_module", 1, 1),
    ("flashlight_module", 1, 1),
    ("silencer", 1, 1),
    ("compensator", 1, 1),
    ("extended_mag", 1, 1),
    ("light_head", 1, 1),
    ("light_torso", 1, 1),
    ("light_arms", 1, 1),
    ("light_legs", 1, 1),
]

BASEMENT_LOOT = [
    ("repair_kit", 1, 4),
    ("circuit", 1, 4),
    ("gunpowder", 1, 4),
    ("heavy_grenade", 1, 3),
    ("mine_standard", 1, 3),
    ("mine_heavy", 1, 2),
    ("laser_module", 1, 2),
    ("flashlight_module", 1, 2),
    ("silencer", 1, 2),
    ("compensator", 1, 2),
    ("extended_mag", 1, 2),
]

WORLD_LOOT = [
    ("apple", 1, 2),
    ("scrap", 1, 5),
    ("cloth", 1, 4),
    ("gunpowder", 1, 3),
    ("duct_tape", 1, 2),
    ("ammo_pack", 1, 4),
    ("contact_grenade", 1, 1),
    ("grenade", 1, 1),
    ("mine_light", 1, 1),
    ("mine_standard", 1, 1),
    ("mine_heavy", 1, 1),
    ("flashlight_module", 1, 1),
    ("silencer", 1, 1),
    ("compensator", 1, 1),
    ("extended_mag", 1, 1),
    ("light_head", 1, 1),
    ("light_torso", 1, 1),
    ("light_arms", 1, 1),
    ("light_legs", 1, 1),
]
