from __future__ import annotations

from shared.maps import list_available_maps

MAP_OPTIONS: tuple[str, ...] = tuple(manifest.id for manifest in list_available_maps())

DENSITY_ORDER: tuple[str, ...] = ("low", "normal", "high")
