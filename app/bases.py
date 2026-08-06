from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .geometry import destination_point, haversine_nm, initial_bearing_deg, is_canada_region, is_france_region, is_us_region

DATA_PATH = Path(__file__).parent / 'data' / 'bases.json'


def load_bases() -> list[dict[str, Any]]:
    return json.loads(DATA_PATH.read_text(encoding='utf-8'))


BASES = load_bases()

AIRCRAFT_SPEED_KT = {
    'F22': 850,
    'F15': 780,
    'F16': 720,
    'F35': 750,
    'F18H': 780,
    'RAFALE': 800,
    'M2K': 760,
}


def _format_lat_lon(lat: float, lon: float) -> str:
    ns = 'N' if lat >= 0 else 'S'
    ew = 'E' if lon >= 0 else 'W'
    return f"{abs(lat):.2f}°{ns}, {abs(lon):.2f}°{ew}"


def compute_intercept_solution(
    base: dict[str, Any],
    target_lat: float,
    target_lon: float,
    target_heading: float | None,
    target_speed_kt: float | None,
    target_altitude_ft: int | None,
    launch_delay_minutes: float = 4.0,
    horizon_minutes: float = 120.0,
    step_minutes: float = 0.5,
    aircraft_code: str | None = None,
) -> dict[str, Any]:
    aircraft_code = aircraft_code or (base.get('aircraft') or ['F16'])[0]
    interceptor_speed = float(AIRCRAFT_SPEED_KT.get(aircraft_code, 700))
    base_lat = float(base['lat'])
    base_lon = float(base['lon'])

    direct_distance = haversine_nm(base_lat, base_lon, target_lat, target_lon)
    best_time = None
    intercept_point = (target_lat, target_lon)
    target_heading = float(target_heading or 0)
    target_speed_kt = float(target_speed_kt or 0)

    if target_speed_kt > 80:
        t = launch_delay_minutes
        while t <= horizon_minutes:
            target_travel_nm = target_speed_kt * (t / 60.0)
            projected_lat, projected_lon = destination_point(
                target_lat, target_lon, target_heading, target_travel_nm
            )
            interceptor_range_nm = interceptor_speed * max(0.0, (t - launch_delay_minutes) / 60.0)
            distance_to_intercept = haversine_nm(base_lat, base_lon, projected_lat, projected_lon)
            if distance_to_intercept <= interceptor_range_nm:
                best_time = t
                intercept_point = (projected_lat, projected_lon)
                direct_distance = distance_to_intercept
                break
            t += step_minutes

    if best_time is None:
        flight_minutes = (direct_distance / interceptor_speed) * 60.0
        best_time = launch_delay_minutes + flight_minutes

    intercept_course = initial_bearing_deg(base_lat, base_lon, intercept_point[0], intercept_point[1])
    return {
        'selected_aircraft': aircraft_code,
        'launch_delay_minutes': round(launch_delay_minutes, 1),
        'intercept_total_minutes': round(best_time, 1),
        'intercept_flight_minutes': round(max(0.0, best_time - launch_delay_minutes), 1),
        'intercept_course_deg': int(round(intercept_course)) % 360,
        'intercept_distance_nm': round(direct_distance, 1),
        'intercept_altitude_ft': int(target_altitude_ft or 0),
        'intercept_point_lat': round(intercept_point[0], 4),
        'intercept_point_lon': round(intercept_point[1], 4),
        'intercept_point_label': _format_lat_lon(intercept_point[0], intercept_point[1]),
    }


def recommend_base(
    lat: float,
    lon: float,
    target_heading: float | None = None,
    target_speed_kt: float | None = None,
    target_altitude_ft: int | None = None,
    target_region: str | None = None,
    allow_cross_border: bool | None = None,
) -> dict[str, Any] | None:
    """Return the fastest eligible QRA base/aircraft combination.

    By default U.S. targets are ranked against U.S. bases and Canadian targets
    against RCAF bases. This avoids a nearby cross-border base silently
    displacing the appropriate national response network.
    """
    if allow_cross_border is None:
        # Late import avoids coupling this small calculation module to settings
        # during data-file tooling and unit tests.
        from .config import settings
        allow_cross_border = settings.allow_cross_border_qra_recommendations

    normalized_region = str(target_region or '').upper()
    if normalized_region in {'CANADA', 'FRANCE', 'UNITED STATES'}:
        desired_country = normalized_region
    elif is_france_region(lat, lon):
        desired_country = 'FRANCE'
    elif is_canada_region(lat, lon) and not is_us_region(lat, lon):
        desired_country = 'CANADA'
    else:
        desired_country = 'UNITED STATES'
    candidates: list[dict[str, Any]] = []
    for base in BASES:
        if not base.get('scramble_enabled', False):
            continue
        base_country = str(base.get('country') or 'UNITED STATES').upper()
        if not allow_cross_border and base_country != desired_country:
            continue
        distance = haversine_nm(lat, lon, float(base['lat']), float(base['lon']))
        for aircraft in (base.get('aircraft') or ['F16']):
            speed = AIRCRAFT_SPEED_KT.get(aircraft, 700)
            flight_minutes = (distance / speed) * 60
            total_minutes = 4 + flight_minutes
            intercept = compute_intercept_solution(
                base,
                lat,
                lon,
                target_heading,
                target_speed_kt,
                target_altitude_ft,
                aircraft_code=aircraft,
            )
            candidates.append(
                {
                    **base,
                    'selected_aircraft': aircraft,
                    'distance_nm': round(distance, 1),
                    'estimated_response_minutes': round(total_minutes, 1),
                    **intercept,
                }
            )
    return min(candidates, key=lambda item: item['intercept_total_minutes']) if candidates else None
