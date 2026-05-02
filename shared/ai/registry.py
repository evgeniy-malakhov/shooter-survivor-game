from __future__ import annotations

from typing import cast

from shared.ai.base import ZombieAI
from shared.ai.zombies.leaper import LeaperZombieAI
from shared.ai.zombies.walker import WalkerZombieAI
from shared.ai.zombies.runner import RunnerZombieAI
from shared.ai.zombies.brute import BruteZombieAI

ZOMBIE_AI_REGISTRY: dict[str, ZombieAI] = {
    "walker": cast(ZombieAI, WalkerZombieAI()),
    "runner": cast(ZombieAI, RunnerZombieAI()),
    "brute": cast(ZombieAI, BruteZombieAI()),
    "leaper": cast(ZombieAI, LeaperZombieAI()),
}