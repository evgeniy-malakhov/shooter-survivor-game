from __future__ import annotations

from dataclasses import dataclass, field

from client.core.perf import ClientPerfStats
from client.perf.render_quality import RenderQualityProfile


@dataclass(slots=True)
class AdaptivePerformanceState:
    observe_only: bool = True
    recommendation: str = "stable"
    actions: list[str] = field(default_factory=list)
    over_budget_streak: int = 0
    recovery_streak: int = 0


class AdaptivePerformanceController:
    def __init__(self, profile: RenderQualityProfile, *, observe_only: bool = True) -> None:
        self.profile = profile
        self.state = AdaptivePerformanceState(observe_only=observe_only)

    def set_observe_only(self, value: bool) -> None:
        self.state.observe_only = bool(value)

    def observe(self, stats: ClientPerfStats) -> AdaptivePerformanceState:
        actions: list[str] = []
        heavy = False

        if stats.frame_p95_ms > 22.0:
            heavy = True
            actions.append("lower render radius")
            if not self.state.observe_only:
                self.profile.render_radius_multiplier -= 0.02

        if stats.actors_ms > 6.0:
            heavy = True
            actions.append("increase actor LOD bias")
            if not self.state.observe_only:
                self.profile.actor_lod_bias += 1

        if stats.effects_ms > 2.0:
            heavy = True
            actions.append("reduce effects quality")
            if not self.state.observe_only:
                self.profile.effects_quality -= 0.08

        if stats.minimap_ms > 1.5:
            heavy = True
            actions.append("lower minimap update rate")
            if not self.state.observe_only:
                self.profile.minimap_update_rate -= 1.0

        if heavy:
            self.state.over_budget_streak += 1
            self.state.recovery_streak = 0
            self.state.recommendation = ", ".join(actions)
        elif stats.frame_p95_ms < 13.0 and stats.frame_ms < 16.0:
            self.state.recovery_streak += 1
            self.state.over_budget_streak = max(0, self.state.over_budget_streak - 1)
            actions.append("restore quality slowly")
            self.state.recommendation = actions[-1]
            if not self.state.observe_only and self.state.recovery_streak >= 90:
                self.profile.render_radius_multiplier += 0.01
                self.profile.effects_quality += 0.03
                self.profile.minimap_update_rate += 0.5
                if self.profile.actor_lod_bias > 0:
                    self.profile.actor_lod_bias -= 1
                self.state.recovery_streak = 0
        else:
            self.state.recommendation = "stable"
            self.state.over_budget_streak = max(0, self.state.over_budget_streak - 1)
            self.state.recovery_streak = 0

        self.profile.clamp()
        self.state.actions = actions
        stats.quality_render_radius_multiplier = self.profile.render_radius_multiplier
        stats.quality_actor_lod_bias = self.profile.actor_lod_bias
        stats.quality_effects_quality = self.profile.effects_quality
        stats.quality_minimap_update_rate = self.profile.minimap_update_rate
        stats.quality_recommendation = self.state.recommendation
        stats.quality_observe_only = self.state.observe_only
        return self.state

