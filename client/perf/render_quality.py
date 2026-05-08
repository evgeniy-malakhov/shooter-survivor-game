from __future__ import annotations

from dataclasses import dataclass


QUALITY_PRESETS = ("low", "balanced", "high", "ultra", "adaptive")


@dataclass(slots=True)
class RenderQualityProfile:
    render_radius_multiplier: float = 1.0
    actor_lod_bias: int = 0
    effects_quality: float = 1.0
    minimap_update_rate: float = 10.0
    particles_enabled: bool = True
    debug_overlays_enabled: bool = True

    def clamp(self) -> None:
        self.render_radius_multiplier = max(0.55, min(1.25, self.render_radius_multiplier))
        self.actor_lod_bias = max(0, min(4, int(self.actor_lod_bias)))
        self.effects_quality = max(0.25, min(1.0, self.effects_quality))
        self.minimap_update_rate = max(2.0, min(20.0, self.minimap_update_rate))

    def copy(self) -> RenderQualityProfile:
        return RenderQualityProfile(
            render_radius_multiplier=self.render_radius_multiplier,
            actor_lod_bias=self.actor_lod_bias,
            effects_quality=self.effects_quality,
            minimap_update_rate=self.minimap_update_rate,
            particles_enabled=self.particles_enabled,
            debug_overlays_enabled=self.debug_overlays_enabled,
        )


def quality_profile_for(name: str) -> RenderQualityProfile:
    key = name.lower().strip()
    if key == "low":
        return RenderQualityProfile(
            render_radius_multiplier=0.72,
            actor_lod_bias=2,
            effects_quality=0.45,
            minimap_update_rate=4.0,
            particles_enabled=False,
            debug_overlays_enabled=True,
        )
    if key == "balanced":
        return RenderQualityProfile(
            render_radius_multiplier=0.9,
            actor_lod_bias=1,
            effects_quality=0.75,
            minimap_update_rate=8.0,
            particles_enabled=True,
            debug_overlays_enabled=True,
        )
    if key == "high":
        return RenderQualityProfile(
            render_radius_multiplier=1.0,
            actor_lod_bias=0,
            effects_quality=1.0,
            minimap_update_rate=10.0,
            particles_enabled=True,
            debug_overlays_enabled=True,
        )
    if key == "ultra":
        return RenderQualityProfile(
            render_radius_multiplier=1.12,
            actor_lod_bias=0,
            effects_quality=1.0,
            minimap_update_rate=15.0,
            particles_enabled=True,
            debug_overlays_enabled=True,
        )
    return quality_profile_for("high")

