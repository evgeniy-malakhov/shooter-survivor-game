from __future__ import annotations

import importlib
from typing import Any

from shared.maps.core.map_config import MapConfig
from shared.maps.core.map_manifest import MapManifest
from shared.maps.core.map_types import MapBuildResult


class MapLoader:
    def load_config(self, manifest: MapManifest) -> MapConfig:
        config = self._load_symbol(manifest.config_path)
        if isinstance(config, type):
            config = config()
        return config

    def load_builder(self, manifest: MapManifest):
        builder_cls = self._load_symbol(manifest.builder_path)
        return builder_cls()

    def load(self, manifest: MapManifest) -> MapBuildResult:
        config = self.load_config(manifest)
        return self.load_builder(manifest).build(config)

    def _load_symbol(self, path: str) -> Any:
        module_name, symbol_name = path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        return getattr(module, symbol_name)
