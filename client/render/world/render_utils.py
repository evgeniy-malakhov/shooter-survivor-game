from __future__ import annotations

import math

import pygame

from client.render import palette
from client.render.render_context import RenderContext
from shared.constants import ARMORS, MAP_HEIGHT, MAP_WIDTH, WEAPONS
from shared.items import ITEMS
from shared.models import PlayerState, RectState, Vec2
from shared.rarities import RARITY_KEYS, rarity_color, rarity_rank, rarity_spec
from shared.weapon_modules import WEAPON_MODULES


def world_to_screen(ctx: RenderContext, pos: Vec2) -> tuple[int, int]:
    return ctx.camera_controller.world_to_screen(pos, ctx.camera)


def world_rect_to_screen(ctx: RenderContext, rect: RectState) -> pygame.Rect:
    return ctx.camera_controller.world_rect_to_screen(rect, ctx.camera)


def world_size(ctx: RenderContext, value: float, minimum: int = 1) -> int:
    return ctx.camera_controller.world_size_to_screen(value, minimum)


def draw_text(
    ctx: RenderContext,
    text: str,
    x: int,
    y: int,
    color: tuple[int, int, int],
    font: pygame.font.Font | None = None,
) -> None:
    fonts = ctx.fonts
    selected = font or (fonts.normal if fonts else pygame.font.Font(None, 18))
    surface = ctx.text_cache.render(selected, text, color) if ctx.text_cache else selected.render(text, True, color)
    ctx.screen.blit(surface, (x, y))


def draw_text_fit(
    ctx: RenderContext,
    text: str,
    rect: pygame.Rect,
    color: tuple[int, int, int],
    font: pygame.font.Font | None = None,
    *,
    center: bool = False,
) -> None:
    if ctx.fonts:
        candidates = [font or ctx.fonts.normal, ctx.fonts.normal, ctx.fonts.small]
    else:
        fallback = pygame.font.Font(None, 18)
        candidates = [font or fallback, fallback]
    chosen = candidates[-1]
    for candidate in candidates:
        if candidate.size(text)[0] <= rect.w:
            chosen = candidate
            break
    surface = ctx.text_cache.render(chosen, text, color) if ctx.text_cache else chosen.render(text, True, color)
    target = surface.get_rect(center=rect.center) if center else surface.get_rect(topleft=rect.topleft)
    ctx.screen.blit(surface, target)


def draw_bar(ctx: RenderContext, rect: pygame.Rect, ratio: float, color: tuple[int, int, int]) -> None:
    ratio = max(0.0, min(1.0, ratio))
    pygame.draw.rect(ctx.screen, (33, 40, 58), rect, border_radius=4)
    pygame.draw.rect(ctx.screen, color, pygame.Rect(rect.x, rect.y, int(rect.w * ratio), rect.h), border_radius=4)
    pygame.draw.rect(ctx.screen, (100, 116, 150), rect, 1, border_radius=4)


def icon_color(key: str) -> tuple[int, int, int]:
    if key == "heart":
        return palette.RED
    if key == "shield" or key in ARMORS:
        return palette.CYAN
    if key in WEAPONS:
        return palette.YELLOW
    spec = ITEMS.get(key)
    if spec:
        return spec.color
    return palette.TEXT


def draw_item_icon(
    ctx: RenderContext,
    key: str,
    rect: pygame.Rect,
    *,
    aura: bool = True,
    shadow: bool = True,
) -> bool:
    icon = ctx.assets.scaled_icon(key, rect.size)
    if not icon:
        return False
    target = icon.get_rect(center=rect.center)
    color = icon_color(key)
    if aura:
        aura_rect = target.inflate(max(10, rect.w // 3), max(10, rect.h // 3))
        aura_surface = pygame.Surface(aura_rect.size, pygame.SRCALPHA)
        pygame.draw.ellipse(aura_surface, (*color, 26), aura_surface.get_rect())
        ctx.screen.blit(aura_surface, aura_rect)
    if shadow:
        shadow_icon = icon.copy()
        shadow_icon.fill((0, 0, 0, 120), special_flags=pygame.BLEND_RGBA_MULT)
        ctx.screen.blit(shadow_icon, target.move(2, 3))
    ctx.screen.blit(icon, target)
    return True


def draw_rarity_frame(ctx: RenderContext, rect: pygame.Rect, rarity: str, width: int = 2) -> None:
    color = rarity_color(rarity)
    rank = rarity_rank(rarity)
    pulse = (math.sin((ctx.now or 0.0) * 4.0) + 1.0) * 0.5
    glow_rect = rect.inflate(10 + rank * 5, 10 + rank * 5)
    glow = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
    for layer in range(2 + min(rank, 3)):
        layer_rect = glow.get_rect().inflate(-layer * 5, -layer * 5)
        alpha = max(10, int(42 + rank * 22 + pulse * 22) - layer * 17)
        pygame.draw.rect(glow, (*color, alpha), layer_rect, 2, border_radius=10)
    ctx.screen.blit(glow, glow_rect)
    pygame.draw.rect(ctx.screen, color, rect.inflate(2, 2), width + (1 if rank >= 2 else 0), border_radius=9)
    corner = 10 + rank * 2
    for sx, sy in ((rect.left, rect.top), (rect.right, rect.top), (rect.left, rect.bottom), (rect.right, rect.bottom)):
        x_dir = 1 if sx == rect.left else -1
        y_dir = 1 if sy == rect.top else -1
        pygame.draw.line(ctx.screen, color, (sx, sy), (sx + corner * x_dir, sy), 2)
        pygame.draw.line(ctx.screen, color, (sx, sy), (sx, sy + corner * y_dir), 2)


def draw_rarity_badge(ctx: RenderContext, rect: pygame.Rect, rarity: str, *, compact: bool = False) -> None:
    if rarity not in RARITY_KEYS:
        return
    size = 15 if compact else 18
    inset = 1 if compact else 5
    badge = pygame.Rect(rect.right - size - inset, rect.y + inset, size, size)
    color = rarity_color(rarity)
    glow_rect = badge.inflate(8, 8)
    glow = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
    pygame.draw.ellipse(glow, (*color, 44), glow.get_rect())
    ctx.screen.blit(glow, glow_rect)
    pygame.draw.rect(ctx.screen, (8, 12, 20), badge, border_radius=5)
    pygame.draw.rect(ctx.screen, color, badge, 1, border_radius=5)
    icon_rect = badge.inflate(-4, -4)
    if not draw_item_icon(ctx, rarity, icon_rect, aura=False, shadow=False):
        points = [
            (badge.centerx, badge.y + 3),
            (badge.right - 3, badge.centery),
            (badge.centerx, badge.bottom - 3),
            (badge.x + 3, badge.centery),
        ]
        pygame.draw.polygon(ctx.screen, color, points)


def draw_mini_durability(ctx: RenderContext, rect: pygame.Rect, durability: float) -> None:
    color = palette.GREEN if durability >= 55 else palette.YELLOW if durability >= 25 else palette.RED
    bar = pygame.Rect(rect.x + 8, rect.bottom - 7, rect.w - 16, 4)
    pygame.draw.rect(ctx.screen, (34, 38, 50), bar, border_radius=2)
    pygame.draw.rect(ctx.screen, color, pygame.Rect(bar.x, bar.y, int(bar.w * max(0, min(100, durability)) / 100), bar.h), border_radius=2)


def client_armor_max(player: PlayerState) -> int:
    best = max(1, ARMORS.get(player.armor_key, ARMORS["none"]).armor_points)
    for item in player.equipment.values():
        spec = ITEMS.get(item.key) if item else None
        if not item or not spec or not spec.armor_key or item.durability <= 0:
            continue
        armor = ARMORS.get(spec.armor_key, ARMORS["none"])
        rarity = rarity_spec(item.rarity)
        best = max(best, int(round(armor.armor_points * rarity.armor_points_multiplier)))
    return max(1, best)


def has_active_flashlight(player: PlayerState | None) -> bool:
    weapon = player.active_weapon() if player else None
    return bool(weapon and weapon.utility_on and weapon.modules.get("utility") == "flashlight_module")


def point_lit_by_flashlight(player: PlayerState, pos: Vec2) -> bool:
    if player.floor >= 0:
        return True
    if not has_active_flashlight(player):
        return False
    distance = player.pos.distance_to(pos)
    if distance < 100:
        return True
    module = WEAPON_MODULES.get("flashlight_module")
    if distance > (module.cone_range if module else 620):
        return False
    angle_to = player.pos.angle_to(pos)
    half_angle = math.radians((module.cone_degrees if module else 58) * 0.5)
    return abs((angle_to - player.angle + math.pi) % math.tau - math.pi) <= half_angle


def loot_icon_key(ctx: RenderContext, kind: str, payload: str) -> str:
    if kind == "ammo":
        ammo_key = f"{payload}_ammo"
        return ammo_key if ammo_key in ctx.assets.item_images else "ammo_pack"
    if kind == "medkit":
        return "medicine"
    if kind == "armor":
        armor_key = f"{payload}_torso"
        return armor_key if armor_key in ITEMS or armor_key in ctx.assets.item_images else payload
    return payload if kind in {"item", "weapon"} else ctx.assets.icon_mapping.get(kind, kind)


def map_dimensions(ctx: RenderContext) -> tuple[float, float]:
    snapshot = ctx.snapshot
    return (
        float(snapshot.map_width if snapshot and snapshot.map_width else MAP_WIDTH),
        float(snapshot.map_height if snapshot and snapshot.map_height else MAP_HEIGHT),
    )
