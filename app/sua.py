from __future__ import annotations

import logging
import math
import re
import time
from typing import Any
from urllib.parse import urljoin

import httpx

from .config import settings
from .geometry import destination_point, geometry_bbox, initial_bearing_deg

log = logging.getLogger('vng-adoc.sua')

_US_BBOXES = (
    (-126.0, 23.0, -65.0, 50.5),
    (-180.0, 50.0, -129.0, 72.5),
    (170.0, 50.0, 180.0, 56.0),
    (-162.0, 17.0, -153.0, 24.0),
    (-69.0, 17.0, -63.0, 20.0),
    (143.0, 12.0, 147.0, 22.0),
    (-173.0, -15.5, -168.0, -10.0),
)


def _strip_z(value: Any) -> Any:
    if (
        isinstance(value, list)
        and len(value) >= 2
        and isinstance(value[0], (int, float))
        and isinstance(value[1], (int, float))
    ):
        return [float(value[0]), float(value[1])]
    if isinstance(value, list):
        return [_strip_z(item) for item in value]
    return value


def _bbox_intersects_us(bbox: list[float] | None) -> bool:
    if not bbox:
        return False
    min_lon, min_lat, max_lon, max_lat = bbox
    for west, south, east, north in _US_BBOXES:
        if max_lon >= west and min_lon <= east and max_lat >= south and min_lat <= north:
            return True
    return False


def _category(properties: dict[str, Any]) -> str | None:
    name = str(properties.get('NAME') or '').strip().upper()
    type_code = str(properties.get('TYPE_CODE') or '').strip().upper()
    class_code = str(properties.get('CLASS') or '').strip().upper()
    combined = ' '.join((name, type_code, class_code))
    if name.startswith('P-') or type_code in {'P', 'PROHIBITED'} or 'PROHIBITED' in combined:
        return 'PROHIBITED'
    if name.startswith('R-') or type_code in {'R', 'RESTRICTED'} or 'RESTRICTED' in combined:
        return 'RESTRICTED'
    return None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().upper().replace(',', '')
    if not text:
        return None
    filtered = ''.join(char for char in text if char.isdigit() or char in '.-')
    if filtered in {'', '-', '.', '-.'}:
        return None
    try:
        return float(filtered)
    except ValueError:
        return None


def parse_altitude_ft(value: Any, unit: Any, description: Any, code: Any, *, upper: bool) -> int:
    text = ' '.join(str(item or '').strip().upper() for item in (description, code, unit, value))
    if any(token in text for token in ('UNLTD', 'UNLIMITED')):
        return 999_999
    if any(token in text for token in ('SFC', 'SURFACE', 'GND')):
        return 0
    amount = _number(value)
    if amount is None:
        amount = _number(description)
    if amount is None:
        return 999_999 if upper else 0
    if 'FL' in text:
        return int(round(amount * 100 if amount < 1000 else amount))
    if 'M' in str(unit or '').upper() and 'FT' not in str(unit or '').upper():
        return int(round(amount * 3.28084))
    return int(round(amount))


def altitude_label(value: Any, description: Any, code: Any, fallback_ft: int) -> str:
    for candidate in (description, code):
        text = str(candidate or '').strip()
        if text:
            return text
    raw = str(value or '').strip()
    if raw:
        return raw
    if fallback_ft >= 999_999:
        return 'UNLTD'
    if fallback_ft == 0:
        return 'SFC'
    return f'{fallback_ft:,} FT'


def _parse_openair_altitude(value: str, *, upper: bool) -> int:
    text = str(value or '').strip().upper().replace(' ', '')
    if not text:
        return 999_999 if upper else 0
    if text in {'SFC', 'GND'}:
        return 0
    if 'UNL' in text:
        return 999_999
    match = re.search(r'FL(\d+)', text)
    if match:
        return int(match.group(1)) * 100
    match = re.search(r'(\d+(?:\.\d+)?)', text.replace(',', ''))
    if not match:
        return 999_999 if upper else 0
    return int(round(float(match.group(1))))


def _parse_coord(value: str) -> tuple[float, float] | None:
    match = re.search(
        r'(\d{1,2}):(\d{2}):(\d{2}(?:\.\d+)?)\s*([NS])\s+' 
        r'(\d{1,3}):(\d{2}):(\d{2}(?:\.\d+)?)\s*([EW])',
        value.strip(),
        re.I,
    )
    if not match:
        return None
    lat = int(match.group(1)) + int(match.group(2)) / 60 + float(match.group(3)) / 3600
    lon = int(match.group(5)) + int(match.group(6)) / 60 + float(match.group(7)) / 3600
    if match.group(4).upper() == 'S':
        lat = -lat
    if match.group(8).upper() == 'W':
        lon = -lon
    return lat, lon


def _circle_polygon(center: tuple[float, float], radius_nm: float, steps: int = 72) -> list[list[float]]:
    points: list[list[float]] = []
    for index in range(steps + 1):
        lat, lon = destination_point(center[0], center[1], index * 360 / steps, radius_nm)
        points.append([lon, lat])
    return points


def _arc_points(
    center: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
    clockwise: bool,
) -> list[list[float]]:
    radius = math.dist((0, 0), (0, 0))
    # Radius is measured on the sphere; using destination_point keeps the arc geodesic enough for display.
    from .geometry import haversine_nm
    radius = haversine_nm(center[0], center[1], start[0], start[1])
    start_bearing = initial_bearing_deg(center[0], center[1], start[0], start[1])
    end_bearing = initial_bearing_deg(center[0], center[1], end[0], end[1])
    if clockwise:
        sweep = (end_bearing - start_bearing) % 360
        direction = 1
    else:
        sweep = (start_bearing - end_bearing) % 360
        direction = -1
    steps = max(2, int(math.ceil(sweep / 4.0)))
    points: list[list[float]] = []
    for index in range(steps + 1):
        bearing = start_bearing + direction * sweep * (index / steps)
        lat, lon = destination_point(center[0], center[1], bearing, radius)
        points.append([lon, lat])
    return points


def parse_canadian_openair(text: str, source_url: str) -> list[dict[str, Any]]:
    """Parse restricted CYR areas from the current Canadian OpenAir export.

    The export is derived from the NAV CANADA Designated Airspace Handbook and is
    explicitly simulation-only. OpenAir arcs are densified to short line segments.
    """
    records = re.split(r'\n\s*\n', text.replace('\r\n', '\n'))
    areas: list[dict[str, Any]] = []
    for record_index, record in enumerate(records, start=1):
        lines = [line.strip() for line in record.splitlines() if line.strip() and not line.lstrip().startswith('*')]
        if not lines:
            continue
        airspace_class = next((line[3:].strip().upper() for line in lines if line.startswith('AC ')), '')
        name = next((line[3:].strip() for line in lines if line.startswith('AN ')), '')
        if airspace_class != 'R' and not name.upper().startswith('CYR'):
            continue
        lower_label = next((line[3:].strip() for line in lines if line.startswith('AL ')), 'SFC')
        upper_label = next((line[3:].strip() for line in lines if line.startswith('AH ')), 'UNLTD')
        center: tuple[float, float] | None = None
        clockwise = True
        points: list[list[float]] = []
        circle: list[list[float]] | None = None
        for line in lines:
            if line.startswith('V X='):
                center = _parse_coord(line.split('=', 1)[1])
            elif line.startswith('V D='):
                clockwise = line.split('=', 1)[1].strip() != '-'
            elif line.startswith('DP '):
                coord = _parse_coord(line[3:])
                if coord:
                    points.append([coord[1], coord[0]])
            elif line.startswith('DB ') and center:
                pair = line[3:].split(',', 1)
                if len(pair) == 2:
                    start = _parse_coord(pair[0])
                    end = _parse_coord(pair[1])
                    if start and end:
                        arc = _arc_points(center, start, end, clockwise)
                        if points and arc and points[-1] == arc[0]:
                            arc = arc[1:]
                        points.extend(arc)
            elif line.startswith('DC ') and center:
                radius = _number(line[3:])
                if radius is not None:
                    circle = _circle_polygon(center, radius)
        ring = circle or points
        if len(ring) < 3:
            continue
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        geometry = {'type': 'Polygon', 'coordinates': [ring]}
        bbox = geometry_bbox(geometry)
        designation_match = re.search(r'\bCYR\s*\d+[A-Z]?\b', name.upper())
        designation = designation_match.group(0).replace(' ', '') if designation_match else name
        lower_ft = _parse_openair_altitude(lower_label, upper=False)
        upper_ft = _parse_openair_altitude(upper_label, upper=True)
        if upper_ft < lower_ft:
            lower_ft, upper_ft = upper_ft, lower_ft
        areas.append(
            {
                'id': f'CA-{designation}-{record_index}',
                'designation': designation,
                'category': 'RESTRICTED',
                'class': 'CYR',
                'floor_ft': lower_ft,
                'ceiling_ft': upper_ft,
                'floor_label': lower_label,
                'ceiling_label': upper_label,
                'state': None,
                'city': name,
                'country': 'CANADA',
                'controlling_agency': None,
                'communications': None,
                'sector': None,
                'times_of_use': 'Refer to current NAV CANADA DAH / NOTAM',
                'remarks': 'OpenAir geometry derived from the current NAV CANADA Designated Airspace Handbook',
                'geometry': geometry,
                'bbox': bbox,
                'source': f'Canadian Airspace OpenAir (DAH-derived) · {source_url}',
            }
        )
    return areas


class SpecialUseAirspaceStore:
    def __init__(self) -> None:
        self.faa_areas: list[dict[str, Any]] = []
        self.canada_areas: list[dict[str, Any]] = []
        self.areas: list[dict[str, Any]] = []
        self.last_refresh = 0.0
        self.status = 'NOT LOADED'
        self.error: str | None = None
        self.canada_source_url: str | None = None

    async def _refresh_faa(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        query_url = settings.sua_feature_url.rstrip('/') + '/query'
        offset = 0
        page_size = 2000
        features: list[dict[str, Any]] = []
        while True:
            response = await client.get(
                query_url,
                params={
                    'where': '1=1',
                    'outFields': 'OBJECTID,NAME,TYPE_CODE,CLASS,UPPER_DESC,UPPER_VAL,UPPER_UOM,UPPER_CODE,LOWER_DESC,LOWER_VAL,LOWER_UOM,LOWER_CODE,CITY,STATE,COUNTRY,CONT_AGENT,COMM_NAME,SECTOR,TIMESOFUSE,REMARKS',
                    'returnGeometry': 'true',
                    'outSR': '4326',
                    'resultOffset': offset,
                    'resultRecordCount': page_size,
                    'f': 'geojson',
                },
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get('error'):
                raise RuntimeError(str(payload['error']))
            page = list(payload.get('features') or [])
            features.extend(page)
            if len(page) < page_size:
                break
            offset += len(page)
            if offset > 20_000:
                raise RuntimeError('FAA SUA pagination exceeded safety limit')

        normalized: list[dict[str, Any]] = []
        for feature in features:
            properties = feature.get('properties') or {}
            category = _category(properties)
            if not category:
                continue
            raw_geometry = feature.get('geometry')
            if not raw_geometry:
                continue
            geometry = {'type': raw_geometry.get('type'), 'coordinates': _strip_z(raw_geometry.get('coordinates') or [])}
            bbox = geometry_bbox(geometry)
            if not _bbox_intersects_us(bbox):
                continue
            lower_ft = parse_altitude_ft(properties.get('LOWER_VAL'), properties.get('LOWER_UOM'), properties.get('LOWER_DESC'), properties.get('LOWER_CODE'), upper=False)
            upper_ft = parse_altitude_ft(properties.get('UPPER_VAL'), properties.get('UPPER_UOM'), properties.get('UPPER_DESC'), properties.get('UPPER_CODE'), upper=True)
            if upper_ft < lower_ft:
                lower_ft, upper_ft = upper_ft, lower_ft
            normalized.append(
                {
                    'id': str(properties.get('OBJECTID') or len(normalized) + 1),
                    'designation': str(properties.get('NAME') or 'UNKNOWN').strip(),
                    'category': category,
                    'class': str(properties.get('CLASS') or '').strip() or None,
                    'floor_ft': lower_ft,
                    'ceiling_ft': upper_ft,
                    'floor_label': altitude_label(properties.get('LOWER_VAL'), properties.get('LOWER_DESC'), properties.get('LOWER_CODE'), lower_ft),
                    'ceiling_label': altitude_label(properties.get('UPPER_VAL'), properties.get('UPPER_DESC'), properties.get('UPPER_CODE'), upper_ft),
                    'state': str(properties.get('STATE') or '').strip() or None,
                    'city': str(properties.get('CITY') or '').strip() or None,
                    'country': 'UNITED STATES',
                    'controlling_agency': str(properties.get('CONT_AGENT') or '').strip() or None,
                    'communications': str(properties.get('COMM_NAME') or '').strip() or None,
                    'sector': str(properties.get('SECTOR') or '').strip() or None,
                    'times_of_use': str(properties.get('TIMESOFUSE') or '').strip() or None,
                    'remarks': str(properties.get('REMARKS') or '').strip() or None,
                    'geometry': geometry,
                    'bbox': bbox,
                    'source': 'FAA Special Use Airspace Feature Service',
                }
            )
        return normalized

    async def _refresh_canada(self, client: httpx.AsyncClient) -> tuple[list[dict[str, Any]], str]:
        index_url = settings.canada_airspace_index_url
        response = await client.get(index_url)
        response.raise_for_status()
        candidates = re.findall(r'href=["\']([^"\']*CanAirspace(\d+)all\.txt)["\']', response.text, re.I)
        if not candidates:
            raise RuntimeError('Current Canadian OpenAir link not found')
        path, _version = max(candidates, key=lambda item: int(item[1]))
        source_url = urljoin(index_url, path)
        data_response = await client.get(source_url)
        data_response.raise_for_status()
        areas = parse_canadian_openair(data_response.text, source_url)
        if not areas:
            raise RuntimeError('Canadian restricted-airspace parser returned no CYR areas')
        return areas, source_url

    async def refresh(self, client: httpx.AsyncClient, force: bool = False) -> None:
        now = time.time()
        if not force and self.areas and now - self.last_refresh < settings.sua_refresh_seconds:
            return
        errors: list[str] = []
        try:
            self.faa_areas = await self._refresh_faa(client)
        except Exception as exc:
            errors.append(f'FAA: {type(exc).__name__}')
            log.warning('FAA SUA refresh failed: %s', exc)
        if settings.monitor_canada:
            try:
                self.canada_areas, self.canada_source_url = await self._refresh_canada(client)
            except Exception as exc:
                errors.append(f'Canada: {type(exc).__name__}')
                log.warning('Canadian SUA refresh failed: %s', exc)
        else:
            self.canada_areas = []
            self.canada_source_url = None

        combined = self.faa_areas + self.canada_areas
        deduplicated: dict[tuple[Any, ...], dict[str, Any]] = {}
        for area in combined:
            key = (area['designation'].upper(), area['category'], area['floor_ft'], area['ceiling_ft'], str(area['geometry']))
            deduplicated[key] = area
        if deduplicated:
            self.areas = sorted(deduplicated.values(), key=lambda item: (item.get('country') or '', item['category'], item['designation'], item['floor_ft']))
            self.last_refresh = now
        self.error = '; '.join(errors) if errors else None
        self.status = f'SUA READY · US {len(self.faa_areas)} · CA {len(self.canada_areas)}'
        if errors and not self.areas:
            self.status = 'SUA UNAVAILABLE'
