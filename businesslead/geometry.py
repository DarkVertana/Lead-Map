"""Circles on the globe: the tiles a sweep is made of."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Tile:
    lat: float
    lng: float
    radius: float

def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def split_tile(tile: Tile) -> list[Tile]:
    """Four smaller circles covering the same ground, for a saturated tile."""
    return build_tiles(tile.lat, tile.lng, tile.radius, 2)


def build_tiles(lat: float, lng: float, radius_m: float, grid: int) -> list[Tile]:
    """Split a search circle into grid x grid sub-circles to beat the 60-result cap."""
    if grid <= 1:
        return [Tile(lat, lng, radius_m)]

    step = (2.0 * radius_m) / grid
    sub_radius = step * math.sqrt(2) / 2      # covers each tile's half-diagonal
    lat_per_m = 1.0 / 111_320.0
    lng_per_m = 1.0 / (111_320.0 * max(math.cos(math.radians(lat)), 0.01))

    tiles = []
    for row in range(grid):
        for col in range(grid):
            dy = (row + 0.5) * step - radius_m
            dx = (col + 0.5) * step - radius_m
            tiles.append(Tile(lat + dy * lat_per_m, lng + dx * lng_per_m, sub_radius))
    return tiles
