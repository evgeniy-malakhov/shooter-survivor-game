from __future__ import annotations

from shared.maps.presets.forest_outpost.builder import ForestOutpostBuilder


class MilitaryBaseBuilder(ForestOutpostBuilder):
    def build(self, config):
        result = super().build(config)
        result.map_id = "military_base"
        result.terrain = {"kind": "military_base_placeholder"}
        return result
