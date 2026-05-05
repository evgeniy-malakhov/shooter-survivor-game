from __future__ import annotations

from shared.systems.commands.command_router import CommandRouter
from shared.systems.commands.handlers.craft_handler import CraftHandler
from shared.systems.commands.handlers.equip_armor_handler import EquipArmorHandler
from shared.systems.commands.handlers.interact_handler import InteractHandler
from shared.systems.commands.handlers.inventory_action_handler import InventoryActionHandler
from shared.systems.commands.handlers.pickup_handler import PickupHandler
from shared.systems.commands.handlers.reload_handler import ReloadHandler
from shared.systems.commands.handlers.repair_handler import RepairHandler
from shared.systems.commands.handlers.respawn_handler import RespawnHandler
from shared.systems.commands.handlers.select_slot_handler import SelectSlotHandler
from shared.systems.commands.handlers.throw_grenade_handler import ThrowGrenadeHandler
from shared.systems.commands.handlers.toggle_utility_handler import ToggleUtilityHandler
from shared.systems.commands.handlers.use_medkit_handler import UseMedkitHandler


def build_command_router() -> CommandRouter:
    router = CommandRouter()

    router.register("respawn", RespawnHandler())
    router.register("select_slot", SelectSlotHandler())
    router.register("use_medkit", UseMedkitHandler())
    router.register("reload", ReloadHandler())
    router.register("pickup", PickupHandler())
    router.register("interact", InteractHandler())
    router.register("toggle_utility", ToggleUtilityHandler())
    router.register("equip_armor", EquipArmorHandler())
    router.register("inventory_action", InventoryActionHandler())
    router.register("craft", CraftHandler())
    router.register("repair", RepairHandler())
    router.register("throw_grenade", ThrowGrenadeHandler())

    return router