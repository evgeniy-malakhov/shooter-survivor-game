from __future__ import annotations

from enum import Enum


class LoadingStage(str, Enum):
    INIT = "init"
    LOAD_ASSETS = "load_assets"
    BUILD_TERRAIN = "build_terrain"
    BUILD_COLLISIONS = "build_collisions"
    BUILD_NAVIGATION = "build_navigation"
    SPAWN_ENTITIES = "spawn_entities"
    COMPOSE_WORLD = "compose_world"
    READY = "ready"
    FAILED = "failed"
