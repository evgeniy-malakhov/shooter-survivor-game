from __future__ import annotations

from collections.abc import Iterable
from typing import Any


class DictEffectPool:
    def __init__(self, max_free: int = 128) -> None:
        self.max_free = max(0, int(max_free))
        self._free: list[dict[str, Any]] = []
        self.active = 0
        self.reused = 0
        self.created = 0

    @property
    def free_count(self) -> int:
        return len(self._free)

    def acquire(self, **values: Any) -> dict[str, Any]:
        if self._free:
            effect = self._free.pop()
            self.reused += 1
        else:
            effect = {}
            self.created += 1
        effect.clear()
        effect.update(values)
        self.active += 1
        return effect

    def release(self, effect: dict[str, Any]) -> None:
        effect.clear()
        self.active = max(0, self.active - 1)
        if len(self._free) < self.max_free:
            self._free.append(effect)

    def retain_active(self, effects: list[dict[str, Any]], active: Iterable[dict[str, Any]]) -> None:
        keep = set(map(id, active))
        write_index = 0
        for effect in effects:
            if id(effect) in keep:
                effects[write_index] = effect
                write_index += 1
            else:
                self.release(effect)
        del effects[write_index:]


