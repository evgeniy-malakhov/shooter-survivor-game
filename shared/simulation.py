from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared.systems.events.event_apply_system import EventApplySystem
from shared.world.world_config import WorldConfig
from shared.world.world_state import WorldState
from shared.world.world_composition import build_world_composition

from shared.constants import (
    MAP_HEIGHT,
    MAP_WIDTH,
)
from shared.difficulty import load_difficulty
from shared.maps.loading.loading_screen_state import LoadingScreenState
from shared.maps.loading.loading_stage import LoadingStage
from shared.models import (
    ClientCommand,
    InputCommand,
    PlayerState,
    Vec2,
    WorldSnapshot,
    ZombieState,
)


@dataclass(slots=True)
class _PoisonSpitEvent:
    owner_id: str
    pos: Vec2
    velocity: Vec2
    target: Vec2
    floor: int


@dataclass(slots=True)
class _ZombieUpdateResult:
    zombie: ZombieState
    player_hits: list[tuple[str, int]]
    poison_spits: list[_PoisonSpitEvent]
    soldier_hits: list[tuple[str, int]]


_COMMAND_EVENT_NAMES = {
    "pickup": "pickup_succeeded",
    "interact": "interact_succeeded",
    "inventory_action": "inventory_changed",
    "craft": "craft_finished",
    "repair": "repair_finished",
    "equip_armor": "armor_equipped",
    "select_slot": "slot_selected",
    "reload": "reload_started",
    "throw_grenade": "explosive_used",
    "toggle_utility": "utility_toggled",
    "use_medkit": "medkit_used",
    "respawn": "player_respawned",
}

class GameWorld:
    def __init__(
        self,
        seed: int | None = None,
        initial_zombies: int | None = None,
        max_zombies: int | None = None,
        difficulty_key: str = "medium",
        zombie_workers: int | None = None,
        zombie_ai_decision_rate: float = 6.0,
        zombie_ai_far_decision_rate: float = 2.0,
        zombie_ai_active_radius: float = 1800.0,
        zombie_ai_far_radius: float = 3200.0,
        zombie_ai_batch_size: int = 8,
        map_id: str = "forest_outpost",
        loading_state: LoadingScreenState | None = None,
        config: WorldConfig | None = None,
    ) -> None:
        if config is None:
            config = WorldConfig(
                seed=seed,
                initial_zombies=initial_zombies,
                max_zombies=max_zombies,
                difficulty_key=difficulty_key,
                map_id=map_id,
                zombie_workers=zombie_workers,
                zombie_ai_decision_rate=zombie_ai_decision_rate,
                zombie_ai_far_decision_rate=zombie_ai_far_decision_rate,
                zombie_ai_active_radius=zombie_ai_active_radius,
                zombie_ai_far_radius=zombie_ai_far_radius,
                zombie_ai_batch_size=zombie_ai_batch_size,
            )

        self.state = WorldState()

        difficulty = load_difficulty(config.difficulty_key)

        self.time = self.state.time

        self.players = self.state.players
        self.zombies = self.state.zombies
        self.soldiers = self.state.soldiers

        self.projectiles = self.state.projectiles
        self.grenades = self.state.grenades
        self.mines = self.state.mines
        self.poison_projectiles = self.state.poison_projectiles
        self.poison_pools = self.state.poison_pools

        self.loot = self.state.loot
        self.inputs = self.state.inputs
        self.sound_events = self.state.sound_events
        self._domain_events = self.state.domain_events
        self._grenade_cooldowns = self.state.grenade_cooldowns
        self.buildings = self.state.buildings

        self.initial_zombies = (
            difficulty.initial_zombies
            if config.initial_zombies is None
            else config.initial_zombies
        )
        self.max_zombies = (
            difficulty.max_zombies
            if config.max_zombies is None
            else config.max_zombies
        )

        composition = build_world_composition(
            config=config,
            get_time=lambda: self.time,
            initial_zombies=self.initial_zombies,
            max_zombies=self.max_zombies,
            loading_state=loading_state,
        )

        self.command_router = composition.command_router
        self.state = composition.state
        self.ctx = composition.ctx
        self.systems = composition.systems

        self.players = self.state.players
        self.zombies = self.state.zombies
        self.soldiers = self.state.soldiers

        self.projectiles = self.state.projectiles
        self.grenades = self.state.grenades
        self.mines = self.state.mines
        self.poison_projectiles = self.state.poison_projectiles
        self.poison_pools = self.state.poison_pools

        self.loot = self.state.loot
        self.inputs = self.state.inputs
        self.sound_events = self.state.sound_events
        self._domain_events = self.state.domain_events
        self._grenade_cooldowns = self.state.grenade_cooldowns
        self.buildings = self.state.buildings

        self._lock = self.ctx.lock
        self.rng = self.ctx.rng
        self.difficulty = composition.difficulty
        self.backpack_config = composition.backpack_config

        self._zombie_executor = self.ctx.process_pool.executor
        self._zombie_pool_workers = composition.executor_config.process_workers
        self._zombie_ai_max_pending_batches = max(2, composition.executor_config.process_workers * 2)

        composition.map_bootstrap.bootstrap()
        EventApplySystem().update(self.state, self.ctx, 0.0)
        self.ctx.spatial.rebuild(self.state)
        if loading_state is not None:
            loading_state.update(LoadingStage.READY, "Ready", 1.0)

    def close(self) -> None:
        self.ctx.process_pool.close()
        self.ctx.thread_pool.close()

        self._zombie_executor = None
        #self._zombie_ai_pending.clear()
        #self._zombie_ai_futures.clear()

    def update(self, dt: float) -> None:
        with self._lock:
            self._update_unlocked(dt)

    def _update_unlocked(self, dt: float) -> None:
        self.time += dt
        self.state.time = self.time

        if dt <= 0.0:
            return

        self.systems.update_all(self.state, self.ctx, dt)

    def add_player(self, name: str, player_id: str | None = None) -> PlayerState:
        with self._lock:
            return self.ctx.player_service.create_player(name, player_id)

    def remove_player(self, player_id: str) -> None:
        with self._lock:
            self.players.pop(player_id, None)
            self.inputs.pop(player_id, None)
            self._grenade_cooldowns.pop(player_id, None)

    def rename_player(self, player_id: str, name: str) -> None:
        with self._lock:
            player = self.players.get(player_id)
            if player:
                player.name = _clean_player_name(name)

    def set_input(self, command: InputCommand) -> None:
        with self._lock:
            if command.player_id in self.players:
                self.inputs[command.player_id] = command

    def apply_client_command(self, command: ClientCommand) -> tuple[bool, str]:
        with self._lock:
            player = self.players.get(command.player_id)
            if not player:
                return False, "player_missing"
            ok, reason = self._apply_client_command_unlocked(player.id, command)
            self._push_command_event(command, ok, reason)
            return ok, reason

    def drain_domain_events(self) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._domain_events)
            self._domain_events.clear()
            return events

    def _push_command_event(self, command: ClientCommand, ok: bool, reason: str) -> None:
        event_kind = _COMMAND_EVENT_NAMES.get(command.kind, command.kind)
        self._domain_events.append(
            {
                "kind": event_kind if ok else f"{command.kind}_rejected",
                "player_id": command.player_id,
                "command_id": command.command_id,
                "command_kind": command.kind,
                "ok": ok,
                "reason": reason,
                "time": round(self.time, 3),
            }
        )

    def _apply_client_command_unlocked(
        self,
        player_id: str,
        command: ClientCommand,
    ) -> tuple[bool, str]:
        player = self.players.get(player_id)

        if not player:
            return False, "player_missing"

        if self.command_router.has_handler(command.kind):
            return self.command_router.handle(
                self.state,
                self.ctx,
                player,
                command,
            )

        return self._apply_client_command_legacy(player, command)

    def _apply_client_command_legacy(
            self,
            player: PlayerState,
            command: ClientCommand,
    ) -> tuple[bool, str]:
        if not player.alive:
            return False, "player_dead"
        return False, "unknown_command"

    def spawn_zombie(self, kind: str | None = None, pos: Vec2 | None = None) -> ZombieState | None:
        return self.ctx.spawning.spawn_zombie(kind=kind, pos=pos)

    def snapshot(self) -> WorldSnapshot:
        with self._lock:
            return WorldSnapshot(
                time=self.time,
                map_width=self.state.map_width or MAP_WIDTH,
                map_height=self.state.map_height or MAP_HEIGHT,
                players=dict(self.players),
                zombies=dict(self.zombies),
                soldiers=dict(self.soldiers),
                projectiles=dict(self.projectiles),
                grenades=dict(self.grenades),
                mines=dict(self.mines),
                poison_projectiles=dict(self.poison_projectiles),
                poison_pools=dict(self.poison_pools),
                loot=dict(self.loot),
                buildings=dict(self.buildings),
                horde_pressure_zones=dict(self.state.horde_pressure_zones),
                district_simulation=dict(self.state.district_simulation),
                battle_escalation=dict(self.state.battle_escalation),
                reinforcement_requests=dict(self.state.reinforcement_requests),
                civilians=dict(self.state.civilians),
                resource_scarcity=dict(self.state.resource_scarcity),
                supply_convoys=dict(self.state.supply_convoys),
                safe_zones=dict(self.state.safe_zones),
            )

    def zombie_count(self) -> int:
        with self._lock:
            return len(self.zombies)


def _clean_player_name(name: str) -> str:
    return "Operator" if not name.strip() else name.strip()[:18]
