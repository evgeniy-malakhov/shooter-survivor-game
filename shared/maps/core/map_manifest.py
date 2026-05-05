from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MapManifest:
    id: str
    title: str
    description: str
    preview_image: str | None
    difficulty: str
    size: tuple[int, int]
    builder_path: str
    config_path: str
