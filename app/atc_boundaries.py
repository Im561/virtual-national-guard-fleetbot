from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from .config import settings
from .geometry import circular_mean, geometry_bbox, is_enabled_region

log = logging.getLogger("vng-adoc.atc")

# VATSIM center callsigns frequently use city identifiers while VATSpy uses
# FAA ARTCC/FIR identifiers. Both forms are accepted here.
CENTER_ALIASES: dict[str, str] = {
    # Current VATSpy uses ICAO FIR identifiers (KZxx) for CONUS ARTCCs.
    # Accept both the city-style controller prefixes and legacy Zxx forms.
    "ABQ": "KZAB", "ZAB": "KZAB", "KZAB": "KZAB",
    "ANC": "PAZA", "ZAN": "PAZA", "KZAN": "PAZA", "PAZA": "PAZA",
    "CHI": "KZAU", "ZAU": "KZAU", "KZAU": "KZAU",
    "BOS": "KZBW", "ZBW": "KZBW", "KZBW": "KZBW",
    "DC": "KZDC", "ZDC": "KZDC", "KZDC": "KZDC",
    "DEN": "KZDV", "ZDV": "KZDV", "KZDV": "KZDV",
    "FTW": "KZFW", "ZFW": "KZFW", "KZFW": "KZFW",
    "HNL": "PHZH", "ZHN": "PHZH", "PHZH": "PHZH",
    "HOU": "KZHU", "ZHU": "KZHU", "KZHU": "KZHU",
    "IND": "KZID", "ZID": "KZID", "KZID": "KZID",
    "JAX": "KZJX", "ZJX": "KZJX", "KZJX": "KZJX",
    "KC": "KZKC", "ZKC": "KZKC", "KZKC": "KZKC",
    "LAX": "KZLA", "ZLA": "KZLA", "KZLA": "KZLA",
    "SLC": "KZLC", "ZLC": "KZLC", "KZLC": "KZLC",
    "MIA": "KZMA", "ZMA": "KZMA", "KZMA": "KZMA",
    "MEM": "KZME", "ZME": "KZME", "KZME": "KZME",
    "MSP": "KZMP", "ZMP": "KZMP", "KZMP": "KZMP",
    "NY": "KZNY", "ZNY": "KZNY", "KZNY": "KZNY",
    "OAK": "KZOA", "ZOA": "KZOA", "KZOA": "KZOA",
    "CLE": "KZOB", "ZOB": "KZOB", "KZOB": "KZOB",
    "SEA": "KZSE", "ZSE": "KZSE", "KZSE": "KZSE",
    "ATL": "KZTL", "ZTL": "KZTL", "KZTL": "KZTL",
    "GUM": "PGZU", "ZUA": "PGZU", "PGZU": "PGZU",
    "SJU": "TJZS", "ZSU": "TJZS", "TJZS": "TJZS",
    # Canadian FIR identifiers and common city-style controller prefixes.
    "TOR": "CZYZ", "YYZ": "CZYZ", "CZYZ": "CZYZ",
    "MTL": "CZUL", "YUL": "CZUL", "CZUL": "CZUL",
    "VAN": "CZVR", "YVR": "CZVR", "CZVR": "CZVR",
    "EDM": "CZEG", "YEG": "CZEG", "CZEG": "CZEG",
    "WIN": "CZWG", "YWG": "CZWG", "CZWG": "CZWG",
    "MONCTON": "CZQM", "YQM": "CZQM", "CZQM": "CZQM",
    "GANDER": "CZQX", "YQX": "CZQX", "CZQX": "CZQX",
}

CENTER_NAMES: dict[str, str] = {
    "KZAB": "Albuquerque ARTCC", "KZAU": "Chicago ARTCC", "KZBW": "Boston ARTCC",
    "KZDC": "Washington ARTCC", "KZDV": "Denver ARTCC", "KZFW": "Fort Worth ARTCC",
    "KZHU": "Houston ARTCC", "KZID": "Indianapolis ARTCC", "KZJX": "Jacksonville ARTCC",
    "KZKC": "Kansas City ARTCC", "KZLA": "Los Angeles ARTCC", "KZLC": "Salt Lake City ARTCC",
    "KZMA": "Miami ARTCC", "KZME": "Memphis ARTCC", "KZMP": "Minneapolis ARTCC",
    "KZNY": "New York ARTCC", "KZOA": "Oakland ARTCC", "KZOB": "Cleveland ARTCC",
    "KZSE": "Seattle ARTCC", "KZTL": "Atlanta ARTCC", "PAZA": "Anchorage FIR",
    "PHZH": "Honolulu FIR", "PGZU": "Guam FIR", "TJZS": "San Juan FIR",
    "CZEG": "Edmonton FIR", "CZQM": "Moncton FIR", "CZQO": "Gander Oceanic FIR",
    "CZQX": "Gander Domestic FIR", "CZUL": "Montreal FIR", "CZVR": "Vancouver FIR",
    "CZWG": "Winnipeg FIR", "CZYZ": "Toronto FIR", "CZZV": "Northern Quebec FIR",
}



class AtcBoundaryStore:
    """Loads and matches the public VATSpy and SimAware boundary datasets.

    The returned geometry is for display and geographic validation. Alert
    coverage is computed separately from the live VATSIM transceiver locations,
    because a whole ARTCC/TRACON polygon does not prove that every sector within
    that facility is currently owned by one online controller.
    """

    def __init__(self) -> None:
        self.fir_features: list[dict[str, Any]] = []
        self.tracon_features: list[dict[str, Any]] = []
        self.last_refresh = 0.0
        self.status = "NOT LOADED"
        self.sources: dict[str, str] = {}
        self.position_first_seen: dict[str, float] = {}

    async def refresh(self, client: httpx.AsyncClient, force: bool = False) -> None:
        now = time.time()
        if (
            not force
            and self.fir_features
            and now - self.last_refresh < settings.atc_boundary_refresh_seconds
        ):
            return

        failures: list[str] = []
        try:
            response = await client.get(settings.vatspy_boundaries_url, follow_redirects=True)
            response.raise_for_status()
            payload = response.json()
            self.fir_features = list(payload.get("features") or [])
            self.sources["fir"] = settings.vatspy_boundaries_url
        except Exception as exc:
            failures.append(f"VATSpy: {type(exc).__name__}")
            log.warning("Unable to refresh VATSpy boundaries: %s", exc)

        try:
            response = await client.get(settings.tracon_boundaries_url, follow_redirects=True)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                self.tracon_features = list(payload.get("features") or [])
            elif isinstance(payload, list):
                self.tracon_features = payload
            self.sources["tracon"] = settings.tracon_boundaries_url
        except Exception as exc:
            failures.append(f"TRACON: {type(exc).__name__}")
            log.warning("Unable to refresh SimAware TRACON boundaries: %s", exc)

        if self.fir_features or self.tracon_features:
            self.last_refresh = now
        self.status = "ONLINE" if not failures else "PARTIAL — " + ", ".join(failures)
        if not self.fir_features and not self.tracon_features:
            self.status = "TRANSCEIVER FALLBACK"

    @staticmethod
    def _controller_center(transceivers: list[dict[str, Any]]) -> tuple[float, float] | None:
        coords = [
            (float(item["latDeg"]), float(item["lonDeg"]))
            for item in transceivers
            if item.get("latDeg") is not None and item.get("lonDeg") is not None
        ]
        return circular_mean(coords)

    @staticmethod
    def _controller_frequencies(
        controller: dict[str, Any], transceivers: list[dict[str, Any]]
    ) -> list[int]:
        values = {
            int(item.get("frequency") or 0)
            for item in transceivers
            if item.get("frequency")
        }
        raw = str(controller.get("frequency") or "").strip()
        try:
            if raw:
                values.add(round(float(raw) * 1_000_000))
        except ValueError:
            pass
        return sorted(value for value in values if value > 0)

    @staticmethod
    def _normalise_transceivers(transceivers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for item in transceivers:
            if item.get("latDeg") is None or item.get("lonDeg") is None:
                continue
            result.append(
                {
                    "id": item.get("id"),
                    "frequency": int(item.get("frequency") or 0),
                    "lat": float(item["latDeg"]),
                    "lon": float(item["lonDeg"]),
                    "height_msl_m": float(item.get("heightMslM") or 0),
                    "height_agl_m": float(item.get("heightAglM") or 0),
                }
            )
        return result

    @staticmethod
    def _geometry_polygons(geometry: dict[str, Any] | None) -> list[Any]:
        if not geometry:
            return []
        geometry_type = str(geometry.get("type") or "")
        coordinates = geometry.get("coordinates") or []
        if geometry_type == "Polygon":
            return [coordinates]
        if geometry_type == "MultiPolygon":
            return list(coordinates)
        return []

    @classmethod
    def _fir_index(cls, features: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        # The VATSpy dataset can contain more than one feature for a single FIR
        # (for example separate mainland/oceanic pieces). Merge those pieces so
        # the displayed and point-in-polygon boundary is complete.
        result: dict[str, dict[str, Any]] = {}
        for feature in features:
            props = feature.get("properties") or {}
            boundary_id = str(props.get("id") or "").upper()
            if not boundary_id:
                continue
            polygons = cls._geometry_polygons(feature.get("geometry"))
            if boundary_id not in result:
                result[boundary_id] = {
                    "type": "Feature",
                    "properties": dict(props),
                    "geometry": {
                        "type": "MultiPolygon",
                        "coordinates": list(polygons),
                    } if polygons else feature.get("geometry"),
                }
                continue
            existing = result[boundary_id]
            merged = cls._geometry_polygons(existing.get("geometry")) + polygons
            existing["geometry"] = {"type": "MultiPolygon", "coordinates": merged}
        return result

    def center_boundaries(self) -> list[dict[str, Any]]:
        """Return all parent U.S. and Canadian FIR/ARTCC outlines.

        These are static reference outlines, independent of whether a controller
        is online. Subsector features are excluded here; an online split sector
        can still overlay its exact geometry through ``build_coverage``.
        """
        result: list[dict[str, Any]] = []
        for boundary_id, feature in self._fir_index(self.fir_features).items():
            props = feature.get("properties") or {}
            division = str(props.get("division") or "").upper()
            parent = "-" not in boundary_id
            supported = bool(
                parent
                and (
                    division in {"VATUSA", "VATCAN"}
                    or boundary_id == "TJZS"
                )
            )
            if not supported or not feature.get("geometry"):
                continue
            country = "CANADA" if division == "VATCAN" else "UNITED STATES"
            result.append(
                {
                    "id": boundary_id,
                    "name": CENTER_NAMES.get(boundary_id, boundary_id),
                    "country": country,
                    "division": division,
                    "label_lat": props.get("label_lat"),
                    "label_lon": props.get("label_lon"),
                    "oceanic": str(props.get("oceanic") or "0") == "1",
                    "geometry": feature.get("geometry"),
                    "source": "VATSpy Data Project",
                }
            )
        return sorted(result, key=lambda item: (item["country"], item["id"]))

    def _match_fir(self, callsign: str) -> tuple[dict[str, Any] | None, str, str | None]:
        base = callsign.rsplit("_CTR", 1)[0]
        tokens = [token for token in base.split("_") if token]
        if not tokens:
            return None, "none", None

        index = self._fir_index(self.fir_features)
        first = tokens[0].upper()
        mapped_first = CENTER_ALIASES.get(first, first)

        # Try the most specific sector identifier first. A callsign such as
        # DEN_17_CTR can therefore match KZDV-17 when that subsector exists.
        candidate_groups: list[tuple[str, str]] = []
        mapped_tokens = [mapped_first, *[token.upper() for token in tokens[1:]]]
        raw_tokens = [token.upper() for token in tokens]
        legacy_tokens = [
            mapped_first[1:] if mapped_first.startswith("KZ") else mapped_first,
            *[token.upper() for token in tokens[1:]],
        ]
        for values in (mapped_tokens, legacy_tokens, raw_tokens):
            for length in range(len(values), 0, -1):
                candidate = "-".join(values[:length])
                quality = "sector" if length > 1 else "facility"
                candidate_groups.append((candidate, quality))

        seen: set[str] = set()
        for candidate, quality in candidate_groups:
            if candidate in seen:
                continue
            seen.add(candidate)
            feature = index.get(candidate)
            if feature:
                if quality == "facility" and len(tokens) > 1:
                    quality = "facility_fallback"
                return feature, quality, candidate
        return None, "none", None

    @staticmethod
    def _feature_prefixes(feature: dict[str, Any]) -> set[str]:
        props = feature.get("properties") or {}
        raw_prefixes = props.get("prefix") or []
        if isinstance(raw_prefixes, str):
            raw_prefixes = [raw_prefixes]
        return {str(value).upper() for value in raw_prefixes if str(value).strip()}

    def _match_tracon(self, callsign: str, suffix: str) -> tuple[dict[str, Any] | None, str | None]:
        base = callsign.rsplit(f"_{suffix}", 1)[0]
        tokens = [token for token in base.split("_") if token]
        prefixes = ["_".join(tokens[:length]).upper() for length in range(len(tokens), 0, -1)]

        # SimAware requires each prefix/suffix pair to be unique. We still rank
        # longest-prefix matches so LAX_U_APP cannot accidentally select LAX_APP.
        best: tuple[int, dict[str, Any], str] | None = None
        for feature in self.tracon_features:
            props = feature.get("properties") or {}
            feature_suffix = str(props.get("suffix") or "APP").upper()
            if feature_suffix != suffix:
                continue
            accepted = self._feature_prefixes(feature)
            for prefix in prefixes:
                if prefix not in accepted:
                    continue
                score = len(prefix.split("_"))
                if best is None or score > best[0]:
                    best = (score, feature, prefix)
                break
        if best:
            return best[1], best[2]
        return None, None

    def _controller_online_since(self, controller: dict[str, Any], callsign: str, now: float) -> float:
        raw = str(controller.get("logon_time") or "").strip()
        if raw:
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                timestamp = parsed.timestamp()
                if 0 < timestamp <= now + 60:
                    self.position_first_seen[callsign] = timestamp
                    return timestamp
            except ValueError:
                pass
        return self.position_first_seen.setdefault(callsign, now)

    def build_coverage(
        self,
        controllers: list[dict[str, Any]],
        audio: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        coverage: list[dict[str, Any]] = []
        matched = 0
        fallback = 0
        now = time.time()
        active_positions: set[str] = set()
        fir_index = self._fir_index(self.fir_features)

        for controller in controllers:
            callsign = str(controller.get("callsign") or "").upper()
            suffix = callsign.rsplit("_", 1)[-1] if "_" in callsign else ""
            if suffix not in {"CTR", "APP", "DEP", "TWR", "GND", "DEL"}:
                continue
            active_positions.add(callsign)
            online_since = self._controller_online_since(controller, callsign, now)
            online_seconds = max(0, int(now - online_since))

            raw_transceivers = audio.get(callsign, [])
            transceivers = self._normalise_transceivers(raw_transceivers)
            center = self._controller_center(raw_transceivers)

            feature: dict[str, Any] | None
            match_quality: str
            matched_id: str | None
            if suffix == "CTR":
                feature, match_quality, matched_id = self._match_fir(callsign)
            elif suffix in {"APP", "DEP"}:
                feature, matched_id = self._match_tracon(callsign, suffix)
                base_prefix = callsign.rsplit(f"_{suffix}", 1)[0]
                match_quality = (
                    "tracon"
                    if feature and matched_id == base_prefix
                    else "tracon_fallback"
                    if feature
                    else "none"
                )
            else:
                # Tower, Ground and Delivery are small airport-local positions.
                # Their live AFV transceiver location is a stronger geographic
                # reference than a broad Center/TRACON polygon.
                feature = None
                matched_id = callsign.rsplit(f"_{suffix}", 1)[0]
                match_quality = "airport_transceiver"

            geometry = feature.get("geometry") if feature else None
            properties = feature.get("properties") if feature else {}
            bbox = geometry_bbox(geometry)
            boundary_id = str((properties or {}).get("id") or matched_id or "").upper()
            parent_boundary_id = boundary_id.split("-", 1)[0] if suffix == "CTR" and boundary_id else None
            parent_feature = fir_index.get(parent_boundary_id or "") if parent_boundary_id else None
            parent_geometry = parent_feature.get("geometry") if parent_feature else geometry if suffix == "CTR" else None

            is_us_boundary = boundary_id.startswith(("KZ", "Z")) or boundary_id in {
                "PAZA", "PHZH", "PGZU", "TJZS", "SCT", "N90", "A80", "D10", "F11", "NCT", "PCT"
            }
            is_canada_boundary = boundary_id.startswith("CZ")
            is_france_boundary = boundary_id.startswith("LF")
            is_supported_boundary = (
                is_us_boundary
                or (settings.monitor_canada and is_canada_boundary)
                or (settings.monitor_france and is_france_boundary)
            )
            if center and not is_enabled_region(
                center[0], center[1], settings.monitor_canada, settings.monitor_france
            ) and not is_supported_boundary:
                continue
            if not center and not is_supported_boundary:
                continue

            visual_range = int(controller.get("visual_range") or 0)
            if suffix == "CTR":
                default_radius = settings.center_coverage_radius_nm
            elif suffix in {"APP", "DEP"}:
                default_radius = settings.approach_coverage_radius_nm
            elif suffix == "TWR":
                default_radius = settings.tower_alert_max_range_nm
            else:
                default_radius = settings.ground_alert_max_range_nm
            radius = float(visual_range or default_radius)
            if suffix == "CTR":
                radius = min(settings.center_coverage_radius_nm, max(100.0, radius))
            elif suffix in {"APP", "DEP"}:
                radius = min(140.0, max(25.0, radius))
            elif suffix == "TWR":
                radius = min(30.0, max(8.0, radius))
            else:
                radius = min(10.0, max(3.0, radius))

            frequencies = self._controller_frequencies(controller, raw_transceivers)
            if geometry:
                matched += 1
            else:
                fallback += 1

            coverage.append(
                {
                    "callsign": callsign,
                    "facility": suffix,
                    "online_since": online_since,
                    "online_seconds": online_seconds,
                    "logon_time": controller.get("logon_time"),
                    "frequency": controller.get("frequency"),
                    "frequencies_hz": frequencies,
                    "frequencies": [round(value / 1_000_000, 3) for value in frequencies],
                    "lat": center[0] if center else None,
                    "lon": center[1] if center else None,
                    "radius_nm": radius,
                    "transceivers": transceivers,
                    "geometry": geometry,
                    "bbox": bbox,
                    "boundary_id": boundary_id or None,
                    "parent_boundary_id": parent_boundary_id,
                    "parent_geometry": parent_geometry,
                    "parent_bbox": geometry_bbox(parent_geometry),
                    "name": (properties or {}).get("name") or boundary_id or callsign,
                    "match_quality": match_quality,
                    "sector_specific": match_quality in {"sector", "tracon", "airport_transceiver"},
                    "alert_basis": "LIVE_TRANSCEIVERS",
                    "source": (
                        "VATSpy sector boundary"
                        if suffix == "CTR" and geometry and match_quality == "sector"
                        else "VATSpy facility boundary"
                        if suffix == "CTR" and geometry
                        else "SimAware TRACON boundary"
                        if geometry
                        else "VATSIM airport transceiver"
                        if suffix in {"TWR", "GND", "DEL"}
                        else "VATSIM transceiver fallback"
                    ),
                }
            )

        for callsign in list(self.position_first_seen):
            if callsign not in active_positions:
                self.position_first_seen.pop(callsign, None)

        if coverage:
            self.status = f"{len(coverage)} ONLINE POSITIONS · {matched} POLYGON · {fallback} TRANSCEIVER FALLBACK"
        return coverage
