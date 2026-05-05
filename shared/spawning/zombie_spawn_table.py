from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ZombieSpawnRule:
    kind: str
    weight: float
    min_time: float = 0.0
    max_count_ratio: float = 1.0


class ZombieSpawnTable:
    def __init__(self, rules: tuple[ZombieSpawnRule, ...]) -> None:
        self.rules = rules

    def choose(
        self,
        rng: random.Random,
        *,
        current_time: float,
        current_counts: dict[str, int],
        total_zombies: int,
        max_zombies: int,
    ) -> str:
        allowed: list[ZombieSpawnRule] = []

        for rule in self.rules:
            if current_time < rule.min_time:
                continue

            current_count = current_counts.get(rule.kind, 0)
            max_allowed = max(1, int(max_zombies * rule.max_count_ratio))

            if current_count >= max_allowed:
                continue

            allowed.append(rule)

        if not allowed:
            return "walker"

        return rng.choices(
            [rule.kind for rule in allowed],
            weights=[rule.weight for rule in allowed],
            k=1,
        )[0]


DEFAULT_ZOMBIE_SPAWN_TABLE = ZombieSpawnTable(
    rules=(
        ZombieSpawnRule("walker", weight=0.52, min_time=0.0, max_count_ratio=1.0),
        ZombieSpawnRule("runner", weight=0.24, min_time=20.0, max_count_ratio=0.45),
        ZombieSpawnRule("brute", weight=0.12, min_time=45.0, max_count_ratio=0.25),
        ZombieSpawnRule("leaper", weight=0.12, min_time=70.0, max_count_ratio=0.20),
    )
)