from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TexturePack:
    id: str
    root: str
