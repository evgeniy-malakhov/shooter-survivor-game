from __future__ import annotations


class IdGenerator:
    def __init__(self, start: int = 1) -> None:
        self._next_id = start

    def next(self, prefix: str) -> str:
        value = f"{prefix}{self._next_id}"
        self._next_id += 1
        return value
