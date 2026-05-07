from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pygame

from client.core.surface_cache import IconScaleCache


@dataclass(slots=True)
class LoadingAssets:
    poster: pygame.Surface | None
    spinner: pygame.Surface | None


class ClientAssets:
    def __init__(
        self,
        *,
        root: Path,
        default_icon_mapping: dict[str, str],
        icon_mapping_path: Path,
    ) -> None:
        self.root = root
        self.default_icon_mapping = default_icon_mapping
        self.icon_mapping_path = icon_mapping_path
        self.icon_mapping = self.load_icon_mapping()
        self.item_images = self.load_item_images()
        self.loading = self.load_loading_assets()
        self.scale_cache = IconScaleCache()

    @property
    def icon_cache(self) -> dict[tuple[str, int, int], pygame.Surface]:
        return self.scale_cache.raw

    def load_icon_mapping(self) -> dict[str, str]:
        mapping = dict(self.default_icon_mapping)
        if not self.icon_mapping_path.exists():
            return mapping
        try:
            raw = json.loads(self.icon_mapping_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return mapping
        if not isinstance(raw, dict):
            return mapping
        for key, value in raw.items():
            image_key = Path(str(value)).stem
            if image_key:
                mapping[str(key)] = image_key
        return mapping

    def load_item_images(self) -> dict[str, pygame.Surface]:
        images: dict[str, pygame.Surface] = {}
        image_dir = self.root / "images"
        for path in image_dir.rglob("*.png"):
            if path.exists():
                try:
                    images[path.stem] = self.load_alpha_image(path)
                except pygame.error:
                    pass
        for key, image_key in self.icon_mapping.items():
            path = image_dir / f"{image_key}.png"
            if not path.exists():
                continue
            try:
                images[key] = self.load_alpha_image(path)
            except pygame.error:
                pass
        return images

    def load_alpha_image(self, path: Path) -> pygame.Surface:
        image = pygame.image.load(str(path))
        return image.convert_alpha()

    def load_loading_assets(self) -> LoadingAssets:
        return LoadingAssets(
            poster=self.try_load_image(
                self.root / "images" / "load" / "load.png",
                self.root / "images" / "screen" / "load.png",
            ),
            spinner=self.try_load_image(self.root / "images" / "screen" / "loader.gif"),
        )

    def try_load_image(self, *paths: Path) -> pygame.Surface | None:
        for path in paths:
            if not path.exists():
                continue
            try:
                return pygame.image.load(str(path)).convert_alpha()
            except pygame.error:
                continue
        return None

    def scaled_icon(self, key: str, size: tuple[int, int]) -> pygame.Surface | None:
        source = self.item_images.get(key) or self.item_images.get(self.icon_mapping.get(key, ""))
        if not source:
            return None
        max_w, max_h = max(1, int(size[0])), max(1, int(size[1]))
        source_w, source_h = source.get_size()
        scale = min(max_w / max(1, source_w), max_h / max(1, source_h))
        width = max(1, int(source_w * scale))
        height = max(1, int(source_h * scale))
        return self.scale_cache.get_or_create(
            key,
            (width, height),
            lambda: pygame.transform.smoothscale(source, (width, height)),
        )

    def warm_scaled_icons(self, sizes: tuple[tuple[int, int], ...] = ((24, 24), (28, 28), (34, 34), (40, 40), (54, 54), (72, 72))) -> None:
        for key in tuple(self.item_images.keys()):
            for size in sizes:
                self.scaled_icon(key, size)
