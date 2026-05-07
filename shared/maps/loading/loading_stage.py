from __future__ import annotations

from enum import Enum


class LoadingStage(str, Enum):
    INIT = "init"
    LOAD_ASSETS = "load_assets"
    BUILD_TERRAIN = "build_terrain"
    BUILD_COLLISIONS = "build_collisions"
    BUILD_NAVIGATION = "build_navigation"
    SPAWN_ENTITIES = "spawn_entities"
    BUILD_CHUNKS = "build_chunks"
    PREPARE_MINIMAP = "prepare_minimap"
    WARM_ASSETS = "warm_assets"
    COMPOSE_WORLD = "compose_world"
    START_SESSION = "start_session"
    READY = "ready"
    FAILED = "failed"
