from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable


class SpatialGridIndex:
    """Small dependency-free geographic candidate index.

    It is deliberately conservative: an item may be returned from extra cells,
    but an item whose bounding box contains a query point is never omitted.
    Exact polygon and radio-range checks remain authoritative in detection.py.
    """

    def __init__(self, cell_degrees: float = 5.0) -> None:
        self.cell_degrees = max(0.5, float(cell_degrees))
        self._cells: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        self._fallback: list[dict[str, Any]] = []

    def _cell(self, lat: float, lon: float) -> tuple[int, int]:
        return (
            math.floor((float(lat) + 90.0) / self.cell_degrees),
            math.floor((float(lon) + 180.0) / self.cell_degrees),
        )

    def add(self, item: dict[str, Any], bbox: Iterable[float] | None) -> None:
        values = list(bbox or [])
        if len(values) != 4 or not all(math.isfinite(float(value)) for value in values):
            self._fallback.append(item)
            return
        min_lon, min_lat, max_lon, max_lat = map(float, values)
        min_lat, max_lat = sorted((max(-90.0, min_lat), min(90.0, max_lat)))
        min_lon, max_lon = sorted((max(-180.0, min_lon), min(180.0, max_lon)))
        first = self._cell(min_lat, min_lon)
        last = self._cell(max_lat, max_lon)
        for lat_cell in range(first[0], last[0] + 1):
            for lon_cell in range(first[1], last[1] + 1):
                self._cells[(lat_cell, lon_cell)].append(item)

    def query(self, lat: float, lon: float) -> list[dict[str, Any]]:
        candidates = list(self._cells.get(self._cell(lat, lon), ()))
        if self._fallback:
            candidates.extend(self._fallback)
        if len(candidates) <= 1:
            return candidates
        seen: set[int] = set()
        unique: list[dict[str, Any]] = []
        for item in candidates:
            identity = id(item)
            if identity in seen:
                continue
            seen.add(identity)
            unique.append(item)
        return unique


def coverage_bbox(item: dict[str, Any], default_radius_nm: float = 250.0) -> tuple[float, float, float, float] | None:
    bbox = item.get("bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        return tuple(float(value) for value in bbox)

    points: list[tuple[float, float]] = []
    for transceiver in item.get("transceivers") or []:
        if transceiver.get("lat") is not None and transceiver.get("lon") is not None:
            points.append((float(transceiver["lat"]), float(transceiver["lon"])))
    if item.get("lat") is not None and item.get("lon") is not None:
        points.append((float(item["lat"]), float(item["lon"])))
    if not points:
        return None

    radius_nm = max(float(item.get("radius_nm") or 0.0), float(default_radius_nm))
    lat_pad = radius_nm / 60.0
    center_lat = sum(point[0] for point in points) / len(points)
    lon_scale = max(0.2, math.cos(math.radians(center_lat)))
    lon_pad = radius_nm / (60.0 * lon_scale)
    return (
        min(point[1] for point in points) - lon_pad,
        min(point[0] for point in points) - lat_pad,
        max(point[1] for point in points) + lon_pad,
        max(point[0] for point in points) + lat_pad,
    )
