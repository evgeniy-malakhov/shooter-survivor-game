from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class WorldConfig:
    seed: int | None = None
    initial_zombies: int | None = None
    max_zombies: int | None = None
    difficulty_key: str = "medium"
    map_id: str = "forest_outpost"

    zombie_workers: int | None = None
    zombie_ai_decision_rate: float = 6.0
    zombie_ai_far_decision_rate: float = 2.0
    zombie_ai_active_radius: float = 1800.0
    zombie_ai_far_radius: float = 3200.0
    zombie_ai_batch_size: int = 8

    enable_process_pool: bool = True
    enable_thread_pool: bool = True

    actor_decision_sync_actor_limit: int = 32
    actor_decision_thread_actor_limit: int = 96
    actor_decision_process_actor_limit: int = 192
    actor_decision_enable_threads: bool = True
    actor_decision_enable_processes: bool = True
