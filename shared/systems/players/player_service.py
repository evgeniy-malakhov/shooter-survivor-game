from shared.constants import WEAPONS, MAP_WIDTH, MAP_HEIGHT
from shared.factions import normalize_faction
from shared.models import WeaponRuntime, Vec2, PlayerState


class PlayerService:
    def __init__(
        self,
        *,
        state,
        rng,
        backpack_config,
        ids,
        inventory,
    ) -> None:
        self._state = state
        self._rng = rng
        self._backpack_config = backpack_config
        self._ids = ids
        self._inventory = inventory

    def create_player(self, name: str, player_id: str | None = None, faction: str | None = None):
        player_id = player_id or self._ids.next("p")

        player = PlayerState(
            id=player_id,
            name=name,
            pos=self._random_spawn_pos(),
            faction=normalize_faction(faction, "survivors"),
            kills_by_kind={},
            backpack=[None] * self._backpack_config.slots,
        )

        self._setup_starting_loadout(player)

        self._state.players[player_id] = player
        return player

    def _setup_starting_loadout(self, player):
        weapon_key = self._backpack_config.starting_weapon.key

        if weapon_key not in WEAPONS:
            weapon_key = "pistol"

        weapon_spec = WEAPONS[weapon_key]

        player.weapons[weapon_spec.slot] = WeaponRuntime(
            weapon_key,
            weapon_spec.magazine_size,
            self._backpack_config.starting_weapon.reserve_ammo,
            rarity="common",
        )

        for item in self._backpack_config.starting_items:
            self._inventory.add_item(player, item.key, item.amount)

    def _random_spawn_pos(self):
        return Vec2(
            MAP_WIDTH * 0.5 + self._rng.uniform(-300, 300),
            MAP_HEIGHT * 0.5 + self._rng.uniform(-300, 300),
        )
