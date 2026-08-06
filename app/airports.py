from __future__ import annotations

import asyncio
import json
import math
import time
from pathlib import Path
from typing import Any

import httpx

from .config import settings
from .geometry import haversine_nm

# Reliable fallback coordinates for common airports and all configured VNG bases.
FALLBACK_AIRPORTS: dict[str, tuple[float, float, str]] = {
    "KATL": (33.6407, -84.4277, "Atlanta"), "KJFK": (40.6413, -73.7781, "New York JFK"),
    "KDEN": (39.8561, -104.6737, "Denver"), "KLAX": (33.9416, -118.4085, "Los Angeles"),
    "KORD": (41.9742, -87.9073, "Chicago O'Hare"), "KDFW": (32.8998, -97.0403, "Dallas/Fort Worth"),
    "KSEA": (47.4502, -122.3088, "Seattle"), "KMIA": (25.7959, -80.2870, "Miami"),
    "KBOS": (42.3656, -71.0096, "Boston"), "KIAH": (29.9902, -95.3368, "Houston"),
    "KPHX": (33.4342, -112.0116, "Phoenix"), "KCLT": (35.2144, -80.9473, "Charlotte"),
    "KSFO": (37.6213, -122.3790, "San Francisco"), "KLAS": (36.0840, -115.1537, "Las Vegas"),
    "KMCO": (28.4312, -81.3081, "Orlando"), "KMSP": (44.8848, -93.2223, "Minneapolis"),
    "KDTW": (42.2162, -83.3554, "Detroit"), "KEWR": (40.6895, -74.1745, "Newark"),
    "KPHL": (39.8744, -75.2424, "Philadelphia"), "KBWI": (39.1754, -76.6684, "Baltimore"),
    "KDCA": (38.8512, -77.0402, "Washington National"), "KIAD": (38.9531, -77.4565, "Washington Dulles"),
    "KJAX": (30.4941, -81.6879, "Jacksonville"), "KLSV": (36.2362, -115.0343, "Nellis"),
    "KBKF": (39.7017, -104.7517, "Buckley"), "KNBG": (29.8253, -90.0350, "NAS JRB New Orleans"),
    "KLFI": (37.0829, -76.3605, "Langley"), "KPDX": (45.5887, -122.5975, "Portland"),
    "PHNL": (21.3187, -157.9225, "Honolulu"), "KFAT": (36.7762, -119.7181, "Fresno"),
    "KOZR": (31.2757, -85.7134, "Cairns AAF"), "KSZL": (38.7303, -93.5482, "Whiteman"),
}

# Keep route/departure calculations available for configured operational bases
# even when the external airport API is temporarily unreachable.
try:
    for _base in json.loads((Path(__file__).parent / "data" / "bases.json").read_text(encoding="utf-8")):
        _icao = str(_base.get("icao") or "").upper()
        if _icao and _base.get("lat") is not None and _base.get("lon") is not None:
            FALLBACK_AIRPORTS.setdefault(
                _icao,
                (float(_base["lat"]), float(_base["lon"]), str(_base.get("name") or _icao)),
            )
except (OSError, ValueError, TypeError):
    pass


class AirportResolver:
    def __init__(self) -> None:
        self.cache = dict(FALLBACK_AIRPORTS)
        self.last_request = 0.0
        self.lock = asyncio.Lock()
        self._advisory_grid: dict[tuple[int, int], list[dict[str, Any]]] = {}
        self._load_advisory_frequencies()

    def _load_advisory_frequencies(self) -> None:
        """Load the compact local CTAF/UNICOM airport-frequency index.

        The detector uses a one-degree spatial grid so a 50 NM lookup checks
        only nearby cells instead of scanning thousands of airports for every
        VATSIM pilot on every feed update.
        """
        path = Path(__file__).parent / "data" / "advisory_frequencies.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        for item in payload.get("airports") or []:
            try:
                lat = float(item["la"])
                lon = float(item["lo"])
                frequencies = [
                    {
                        "frequency_hz": round(float(freq["m"]) * 1_000_000),
                        "frequency": round(float(freq["m"]), 3),
                        "type": str(freq.get("t") or "CTAF").upper(),
                    }
                    for freq in (item.get("f") or [])
                    if freq.get("m") is not None
                ]
            except (KeyError, TypeError, ValueError):
                continue
            if not frequencies:
                continue
            record = {
                "ident": str(item.get("i") or "").upper(),
                "name": str(item.get("n") or item.get("i") or "AIRPORT"),
                "country": str(item.get("c") or "").upper(),
                "lat": lat,
                "lon": lon,
                "frequencies": frequencies,
            }
            self._advisory_grid.setdefault((math.floor(lat), math.floor(lon)), []).append(record)

    def nearby_advisory_matches(
        self,
        lat: float,
        lon: float,
        pilot_frequencies_hz: list[int],
        radius_nm: float,
        tolerance_hz: int,
    ) -> list[dict[str, Any]]:
        if not pilot_frequencies_hz or radius_nm <= 0 or not self._advisory_grid:
            return []
        # One degree of latitude is approximately 60 NM. Add one cell for
        # longitude distortion and boundary overlap.
        cell_radius = max(1, int(math.ceil(radius_nm / 60.0)) + 1)
        lat_cell = math.floor(lat)
        lon_cell = math.floor(lon)
        matches: list[dict[str, Any]] = []
        seen: set[tuple[str, int]] = set()
        for dlat in range(-cell_radius, cell_radius + 1):
            for dlon in range(-cell_radius, cell_radius + 1):
                for airport in self._advisory_grid.get((lat_cell + dlat, lon_cell + dlon), []):
                    distance = haversine_nm(lat, lon, airport["lat"], airport["lon"])
                    if distance > radius_nm:
                        continue
                    for frequency in airport["frequencies"]:
                        frequency_hz = int(frequency["frequency_hz"])
                        if not any(
                            abs(int(pilot_frequency) - frequency_hz) <= tolerance_hz
                            for pilot_frequency in pilot_frequencies_hz
                        ):
                            continue
                        key = (airport["ident"], frequency_hz)
                        if key in seen:
                            continue
                        seen.add(key)
                        matches.append({
                            "airport": airport["ident"],
                            "name": airport["name"],
                            "country": airport["country"],
                            "frequency": frequency["frequency"],
                            "frequency_hz": frequency_hz,
                            "type": frequency["type"],
                            "distance_nm": round(distance, 1),
                        })
        matches.sort(key=lambda item: (item["distance_nm"], item["airport"], item["frequency_hz"]))
        return matches

    async def ensure(self, codes: set[str], client: httpx.AsyncClient) -> None:
        missing = sorted(code for code in codes if code and code not in self.cache and len(code) == 4)
        if not missing:
            return
        async with self.lock:
            missing = sorted(code for code in missing if code not in self.cache)
            if not missing:
                return
            # Respect AviationWeather's request-frequency guidance. One batched request per minute.
            if time.monotonic() - self.last_request < 60:
                return
            self.last_request = time.monotonic()
            try:
                response = await client.get(
                    settings.aviation_weather_airport_url,
                    params={"ids": ",".join(missing[:400]), "format": "json"},
                    headers={"User-Agent": settings.user_agent},
                    timeout=20,
                )
                if response.status_code == 204:
                    return
                response.raise_for_status()
                payload = response.json()
                records = payload if isinstance(payload, list) else payload.get("data", [])
                for item in records:
                    if not isinstance(item, dict):
                        continue
                    code = str(item.get("icaoId") or item.get("icao") or item.get("id") or item.get("ident") or "").upper()
                    lat = item.get("lat") if item.get("lat") is not None else item.get("latitude")
                    lon = item.get("lon") if item.get("lon") is not None else item.get("longitude")
                    name = str(item.get("name") or item.get("site") or code)
                    if code and lat is not None and lon is not None:
                        self.cache[code] = (float(lat), float(lon), name)
            except Exception:
                # Live tracking continues; rules needing unknown airport coordinates are simply skipped.
                return

    def get(self, code: str | None) -> tuple[float, float, str] | None:
        return self.cache.get((code or "").upper())
