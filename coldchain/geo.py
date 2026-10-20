"""Geospatial helpers."""
from __future__ import annotations

import math
from typing import Sequence

LatLon = tuple[float, float]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def segment_lengths(points: Sequence[LatLon]) -> list[float]:
    return [haversine_km(*points[i], *points[i + 1]) for i in range(len(points) - 1)]


def route_length_km(points: Sequence[LatLon]) -> float:
    return sum(segment_lengths(points))


def route_position(points: Sequence[LatLon], frac: float) -> tuple[float, float, int]:
    """Interpolate a position along a polyline.

    Returns (lat, lon, index_of_next_waypoint).
    """
    frac = min(max(frac, 0.0), 1.0)
    segs = segment_lengths(points)
    target = frac * sum(segs)
    acc = 0.0
    for i, d in enumerate(segs):
        if acc + d >= target:
            t = (target - acc) / d if d else 0.0
            lat = points[i][0] + t * (points[i + 1][0] - points[i][0])
            lon = points[i][1] + t * (points[i + 1][1] - points[i][1])
            return lat, lon, i + 1
        acc += d
    return points[-1][0], points[-1][1], len(points) - 1
