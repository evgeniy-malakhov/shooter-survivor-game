from __future__ import annotations

from dataclasses import dataclass

from shared.models import ItemSpec

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
                equipment_slot=slot,
                armor_key=level,
                color=meta["color"],
            )
    return items


ITEMS: dict[str, ItemSpec] = {
    "apple": ItemSpec("apple", "Apple", "food", stack_size=8, heal_total=12, heal_seconds=5.0, color=(132, 232, 114)),
    "canned_food": ItemSpec("canned_food", "Canned Food", "food", stack_size=6, heal_total=24, heal_seconds=8.0, color=(235, 186, 92)),
    "energy_bar": ItemSpec("energy_bar", "Energy Bar", "food", stack_size=10, heal_total=16, heal_seconds=4.0, color=(246, 220, 92)),
    "bandage": ItemSpec("bandage", "Bandage", "medical", stack_size=6, heal_total=28, heal_seconds=7.0, color=(244, 244, 224)),
    "medicine": ItemSpec("medicine", "Medicine", "medical", stack_size=4, heal_total=45, heal_seconds=10.0, color=(118, 226, 255)),
    "scrap": ItemSpec("scrap", "Scrap Metal", "resource", stack_size=20, color=(154, 164, 178)),
    "cloth": ItemSpec("cloth", "Cloth", "resource", stack_size=20, color=(192, 184, 160)),
    "duct_tape": ItemSpec("duct_tape", "Duct Tape", "resource", stack_size=12, color=(164, 174, 198)),
    "circuit": ItemSpec("circuit", "Circuit Board", "resource", stack_size=10, color=(80, 220, 150)),
    "gunpowder": ItemSpec("gunpowder", "Gunpowder", "resource", stack_size=20, color=(96, 96, 106)),
    "ammo_pack": ItemSpec("ammo_pack", "Ammo Pack", "ammo", stack_size=12, color=(255, 210, 112)),
    "grenade": ItemSpec("grenade", "Grenade", "grenade", stack_size=4, color=(96, 180, 108)),
    "repair_kit": ItemSpec("repair_kit", "Repair Kit", "tool", stack_size=4, color=(255, 146, 100)),
    "laser_module": ItemSpec("laser_module", "Laser Sight", "weapon_module", stack_size=1, color=(255, 84, 98)),
    "flashlight_module": ItemSpec("flashlight_module", "Flashlight", "weapon_module", stack_size=1, color=(255, 238, 148)),
    "extended_mag": ItemSpec("extended_mag", "Extended Magazine", "weapon_module", stack_size=1, color=(116, 204, 255)),
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
    "grenade": Recipe("grenade", "Grenade", {"scrap": 3, "gunpowder": 5, "duct_tape": 1}, ("grenade", 1)),
    "laser_module": Recipe("laser_module", "Laser Sight", {"circuit": 1, "scrap": 2, "duct_tape": 1}, ("laser_module", 1)),
    "flashlight_module": Recipe("flashlight_module", "Flashlight", {"circuit": 1, "scrap": 2, "cloth": 1}, ("flashlight_module", 1)),
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
    ("grenade", 1, 1),
    ("laser_module", 1, 1),
    ("flashlight_module", 1, 1),
    ("extended_mag", 1, 1),
    ("light_head", 1, 1),
    ("light_torso", 1, 1),
    ("light_arms", 1, 1),
    ("light_legs", 1, 1),
]

WORLD_LOOT = [
    ("apple", 1, 2),
    ("scrap", 1, 5),
    ("cloth", 1, 4),
    ("gunpowder", 1, 3),
    ("duct_tape", 1, 2),
    ("ammo_pack", 1, 4),
    ("grenade", 1, 1),
    ("flashlight_module", 1, 1),
    ("extended_mag", 1, 1),
    ("light_head", 1, 1),
    ("light_torso", 1, 1),
    ("light_arms", 1, 1),
    ("light_legs", 1, 1),
]
