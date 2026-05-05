from typing import Protocol
from shared.models import ZombieState

class ZombieAI(Protocol):
    kind: str

    def update(self, ctx: "ZombieContext") -> "ZombieActionResult":
        ...
