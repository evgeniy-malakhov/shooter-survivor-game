from __future__ import annotations

from dataclasses import dataclass

from client.core.assets import ClientAssets
from client.core.camera import CameraController
from client.core.display import DisplayManager


@dataclass(slots=True)
class ClientServices:
    display: DisplayManager
    assets: ClientAssets
    camera: CameraController


