from __future__ import annotations

from shared.maps.presets.forest_outpost.builder import ForestOutpostBuilder


class AbandonedCityBuilder(ForestOutpostBuilder):
    def build(self, config):
        result = super().build(config)
        result.map_id = "abandoned_city"
        result.terrain = {"kind": "abandoned_city_placeholder"}
        return result
