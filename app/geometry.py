from __future__ import annotations

import math
from typing import Any, Iterable

EARTH_RADIUS_NM = 3440.065


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_NM * math.asin(min(1.0, math.sqrt(a)))


def initial_bearing_rad(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlon)
    return math.atan2(y, x)




def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return (math.degrees(initial_bearing_rad(lat1, lon1, lat2, lon2)) + 360.0) % 360.0


def destination_point(lat: float, lon: float, bearing_deg: float, distance_nm: float) -> tuple[float, float]:
    """Project a point along a great-circle track."""
    angular = distance_nm / EARTH_RADIUS_NM
    bearing = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular)
        + math.cos(lat1) * math.sin(angular) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular) * math.cos(lat1),
        math.cos(angular) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), ((math.degrees(lon2) + 540) % 360) - 180


def point_to_great_circle_segment_nm(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> float:
    plat, plon = point
    slat, slon = start
    elat, elon = end
    segment = haversine_nm(slat, slon, elat, elon)
    if segment < 1.0:
        return haversine_nm(plat, plon, slat, slon)

    delta13 = haversine_nm(slat, slon, plat, plon) / EARTH_RADIUS_NM
    theta13 = initial_bearing_rad(slat, slon, plat, plon)
    theta12 = initial_bearing_rad(slat, slon, elat, elon)
    xt = math.asin(max(-1.0, min(1.0, math.sin(delta13) * math.sin(theta13 - theta12))))

    cos_xt = max(1e-12, math.cos(xt))
    ratio = max(-1.0, min(1.0, math.cos(delta13) / cos_xt))
    at = math.acos(ratio) * EARTH_RADIUS_NM
    if math.cos(theta13 - theta12) < 0:
        at = -at

    if 0 <= at <= segment:
        return abs(xt) * EARTH_RADIUS_NM
    return min(
        haversine_nm(plat, plon, slat, slon),
        haversine_nm(plat, plon, elat, elon),
    )


def point_in_polygon(lat: float, lon: float, coordinates: list[list[float]]) -> bool:
    if len(coordinates) < 3:
        return False
    inside = False
    j = len(coordinates) - 1
    for i, point in enumerate(coordinates):
        if len(point) < 2 or len(coordinates[j]) < 2:
            j = i
            continue
        x_i, y_i = float(point[0]), float(point[1])
        x_j, y_j = float(coordinates[j][0]), float(coordinates[j][1])
        intersects = ((y_i > lat) != (y_j > lat)) and (
            lon < (x_j - x_i) * (lat - y_i) / ((y_j - y_i) or 1e-12) + x_i
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def point_in_geojson_geometry(lat: float, lon: float, geometry: dict[str, Any] | None) -> bool:
    """Return whether a point lies in a GeoJSON Polygon or MultiPolygon.

    Holes are honored when present. Unsupported geometry types return False.
    """
    if not geometry:
        return False
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates") or []

    if geometry_type == "Polygon":
        polygons = [coordinates]
    elif geometry_type == "MultiPolygon":
        polygons = coordinates
    else:
        return False

    for polygon in polygons:
        if not polygon or not point_in_polygon(lat, lon, polygon[0]):
            continue
        if any(point_in_polygon(lat, lon, hole) for hole in polygon[1:]):
            continue
        return True
    return False


def geometry_bbox(geometry: dict[str, Any] | None) -> list[float] | None:
    """Return [min_lon, min_lat, max_lon, max_lat] for Polygon/MultiPolygon."""
    if not geometry:
        return None
    points: list[tuple[float, float]] = []

    def walk(value: Any) -> None:
        if (
            isinstance(value, list)
            and len(value) >= 2
            and isinstance(value[0], (int, float))
            and isinstance(value[1], (int, float))
        ):
            points.append((float(value[0]), float(value[1])))
            return
        if isinstance(value, list):
            for item in value:
                walk(item)

    walk(geometry.get("coordinates") or [])
    if not points:
        return None
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    return [min(lons), min(lats), max(lons), max(lats)]


def bbox_contains(bbox: list[float] | None, lat: float, lon: float) -> bool:
    return bool(bbox and bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3])


def circular_mean(points: Iterable[tuple[float, float]]) -> tuple[float, float] | None:
    items = list(points)
    if not items:
        return None
    x = y = z = 0.0
    for lat, lon in items:
        lat_r, lon_r = math.radians(lat), math.radians(lon)
        x += math.cos(lat_r) * math.cos(lon_r)
        y += math.cos(lat_r) * math.sin(lon_r)
        z += math.sin(lat_r)
    total = len(items)
    x, y, z = x / total, y / total, z / total
    lon = math.atan2(y, x)
    hyp = math.sqrt(x * x + y * y)
    lat = math.atan2(z, hyp)
    return math.degrees(lat), math.degrees(lon)


def heading_delta(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def is_us_region(lat: float, lon: float) -> bool:
    """Return True for the 50 states, DC, and major U.S. territories.

    Bounding boxes are intentionally broad so coastal traffic is not dropped.
    """
    conus = 23.0 <= lat <= 50.5 and -126.0 <= lon <= -65.0
    alaska = 50.0 <= lat <= 72.5 and -180.0 <= lon <= -129.0
    western_aleutians = 50.0 <= lat <= 55.5 and 170.0 <= lon <= 180.0
    hawaii = 17.5 <= lat <= 23.5 and -161.5 <= lon <= -153.0
    puerto_rico_usvi = 17.0 <= lat <= 19.5 and -68.5 <= lon <= -63.5
    guam_cnmi = 12.0 <= lat <= 21.5 and 143.0 <= lon <= 146.5
    american_samoa = -15.0 <= lat <= -10.0 and -172.5 <= lon <= -168.0
    return conus or alaska or western_aleutians or hawaii or puerto_rico_usvi or guam_cnmi or american_samoa


def is_canada_region(lat: float, lon: float) -> bool:
    """Return True for Canadian domestic airspace using broad geographic bounds.

    The bounds intentionally include coastal and northern FIR traffic so tracks
    near the border are not dropped from the monitoring display.
    """
    mainland_and_arctic = 41.0 <= lat <= 84.5 and -141.5 <= lon <= -52.0
    newfoundland_labrador = 46.0 <= lat <= 61.5 and -67.5 <= lon <= -52.0
    return mainland_and_arctic or newfoundland_labrador


def is_france_region(lat: float, lon: float) -> bool:
    """Return True for metropolitan France and Corsica using a conservative outline."""
    mainland_outline = [
        [-5.6, 48.7], [-4.8, 47.7], [-2.2, 46.0], [-1.8, 43.2],
        [0.8, 42.3], [3.2, 42.3], [7.6, 43.5], [7.7, 48.8],
        [6.2, 49.8], [4.2, 50.3], [2.4, 51.1], [-1.8, 49.8],
    ]
    corsica_outline = [[8.4, 41.2], [9.7, 41.2], [9.7, 43.2], [8.4, 43.2]]
    return point_in_polygon(lat, lon, mainland_outline) or point_in_polygon(lat, lon, corsica_outline)


def is_monitored_region(lat: float, lon: float) -> bool:
    """Return True for the United States, Canada, or metropolitan France."""
    return is_us_region(lat, lon) or is_canada_region(lat, lon) or is_france_region(lat, lon)


def is_enabled_region(
    lat: float,
    lon: float,
    monitor_canada: bool = False,
    monitor_france: bool = False,
) -> bool:
    """Return True for an enabled operational monitoring region."""
    return (
        is_us_region(lat, lon)
        or (monitor_canada and is_canada_region(lat, lon))
        or (monitor_france and is_france_region(lat, lon))
    )
