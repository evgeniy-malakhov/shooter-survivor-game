from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AssetManifest:
    id: str
    assets: tuple[str, ...] = ()
