from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .airports import AirportResolver
from .bases import recommend_base
from .config import settings
from .geometry import (
    bbox_contains,
    circular_mean,
    destination_point,
    haversine_nm,
    heading_delta,
    initial_bearing_deg,
    point_in_geojson_geometry,
    point_in_polygon,
    point_to_great_circle_segment_nm,
    is_france_region,
    is_us_region,
)
from .spatial_index import SpatialGridIndex, coverage_bbox
from .track_signature import intercept_pair_signature

ZONES = json.loads((Path(__file__).parent / "data" / "zones.json").read_text(encoding="utf-8"))

SEVERITY_RANK = {"green": 0, "yellow": 1, "orange": 2, "red": 3}


def operational_region(lat: float, lon: float) -> str:
    if is_france_region(lat, lon):
        return "FRANCE"
    if is_us_region(lat, lon):
        return "UNITED STATES"
    return "CANADA"
EMERGENCY_SQUAWKS = {"7500", "7600", "7700"}
INTERCEPT_SQUAWKS = {"7777"}
# Frequencies that can legitimately be monitored or used for advisory traffic,
# but never establish that an aircraft is in contact with its controlling ATC
# facility. Their presence must not clear or inhibit a wrong-frequency case.
NON_CONTROLLING_FREQUENCIES: tuple[tuple[int, str], ...] = (
    (121_500_000, "GUARD"),
    (122_800_000, "ADVISORY/UNICOM"),
)
NON_CONTROLLING_FREQUENCY_TOLERANCE_HZ = 5_000
RADIO_LIMITATION_TERMS = ("NORDO", "NO VOICE", "TEXT ONLY", "RECEIVE ONLY", "RX ONLY")

# Public VATSIM flight-plan data has no authoritative unit field. BLACKJACK is
# therefore treated as a likely USCG NCRAD flight only when the live aircraft is
# a helicopter, is operating near Washington, D.C., and uses the established
# unit callsign or explicitly declares BLACKJACK/USCG in remarks.
BLACKJACK_CALLSIGN_RE = re.compile(r"^(?:BLACKJACK|BLKJACK|BLKJAK|BLKJK|BJK)[-_ ]?\d{0,2}$", re.IGNORECASE)
BLACKJACK_REMARK_RE = re.compile(r"(?<![A-Z0-9])BLACK[\s._/-]*JACK(?![A-Z0-9])", re.IGNORECASE)
BLACKJACK_HOME = (38.8512, -77.0402)  # KDCA airport reference point, not a facility location
BLACKJACK_RECOGNITION_RADIUS_NM = 180.0

# Flight-plan remarks are free text and there is no authoritative organization
# field in the public VATSIM pilot feed. Keep this list explicit and
# conservative: recognized organization markers identify a likely VSOA flight,
# but never verify membership or authorization. Token boundaries prevent
# strings such as NOTVUSCGTEST from being treated as an affiliation marker.
VSOA_ORGANIZATION_MARKERS: tuple[tuple[str, str], ...] = (
    (
        "VSOA",
        r"(?:VSOA|VATSIM[\s._/-]*SPECIAL[\s._/-]*OPERATIONS(?:[\s._/-]*ASSOCIATION)?|VIRTUAL[\s._/-]*SPECIAL[\s._/-]*OPERATIONS[\s._/-]*ASSOCIATION)",
    ),
    ("vUSCG", r"V[\s._/-]*USCG"),
    ("vRCAF", r"V[\s._/-]*RCAF"),
    ("vUSAF", r"V[\s._/-]*USAF"),
    ("vUSN", r"V[\s._/-]*USN"),
    ("vUSMC", r"V[\s._/-]*USMC"),
    ("vANG", r"V[\s._/-]*ANG"),
    ("vDHS", r"V[\s._/-]*DHS"),
    ("vNG", r"V[\s._/-]*NG"),
    ("vNATO", r"V[\s._/-]*NATO"),
    ("vRAF", r"V[\s._/-]*RAF"),
    ("vRNLAF", r"V[\s._/-]*RNLAF"),
    ("vGAF", r"V[\s._/-]*GAF"),
    ("vIAF", r"V[\s._/-]*IAF"),
    ("vAGRS", r"V[\s._/-]*AGRS"),
    ("BVASO", r"BVASO"),
    ("FAAv", r"FAAV"),
    ("FABv", r"FABV"),
    ("vAirMed", r"V[\s._/-]*AIRMED"),
)
VSOA_MARKER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (
        label,
        re.compile(rf"(?<![A-Z0-9])(?:{expression})(?![A-Z0-9])", re.IGNORECASE),
    )
    for label, expression in VSOA_ORGANIZATION_MARKERS
)
VSOA_REMARK_RE = re.compile(
    r"(?<![A-Z0-9])(?:"
    + "|".join(f"(?:{expression})" for _, expression in VSOA_ORGANIZATION_MARKERS)
    + r")(?![A-Z0-9])",
    re.IGNORECASE,
)


def detect_vsoa_marker(remarks: str) -> str | None:
    """Return the first explicit VSOA/organization marker found in remarks."""
    for label, pattern in VSOA_MARKER_PATTERNS:
        if pattern.search(remarks or ""):
            return label
    return None


def detect_blackjack_unit(
    callsign: str,
    remarks: str,
    aircraft_type: str,
    lat: float,
    lon: float,
) -> bool:
    """Conservatively identify a likely USCG NCRAD BLACKJACK helicopter.

    This is a visualization/workflow hint for VATSIM only. It does not verify
    real-world identity, authorization, or membership.
    """
    if not HELICOPTER_RE.match(str(aircraft_type or "")):
        return False
    if haversine_nm(lat, lon, BLACKJACK_HOME[0], BLACKJACK_HOME[1]) > BLACKJACK_RECOGNITION_RADIUS_NM:
        return False
    normalized = re.sub(r"[^A-Z0-9]", "", str(callsign or "").upper())
    callsign_match = bool(BLACKJACK_CALLSIGN_RE.match(normalized))
    remarks_value = str(remarks or "")
    remarks_match = bool(
        BLACKJACK_REMARK_RE.search(remarks_value)
        and re.search(r"(?<![A-Z0-9])(?:V[\s._/-]*USCG|USCG)(?![A-Z0-9])", remarks_value, re.IGNORECASE)
    )
    return callsign_match or remarks_match


MISSION_EXEMPTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("VSOA", VSOA_REMARK_RE),
    ("SAR", re.compile(r"(?<![A-Z0-9])SAR(?![A-Z0-9])", re.IGNORECASE)),
    ("SEARCH AND RESCUE", re.compile(r"(?<![A-Z0-9])SEARCH(?:\s+AND\s+|\s*&\s*)RESCUE(?![A-Z0-9])", re.IGNORECASE)),
    ("LAW ENFORCEMENT", re.compile(r"(?<![A-Z0-9])LAW\s+ENFORCEMENT(?![A-Z0-9])", re.IGNORECASE)),
    ("PATROL", re.compile(r"(?<![A-Z0-9])PATROL(?![A-Z0-9])", re.IGNORECASE)),
    ("ORBIT", re.compile(r"(?<![A-Z0-9])ORBIT(?![A-Z0-9])", re.IGNORECASE)),
    ("TRAINING", re.compile(r"(?<![A-Z0-9])TRAINING(?![A-Z0-9])", re.IGNORECASE)),
    ("FORMATION", re.compile(r"(?<![A-Z0-9])FORMATION(?![A-Z0-9])", re.IGNORECASE)),
)

HELICOPTER_RE = re.compile(
    r"^(?:H\d{1,3}|UH|HH|CH|AH|MH|SH|OH|EC|AS|AW|S76|S92|B06|B47|R22|R44|R66|MD5|BK1|KA32|MI8|MI17|MI24|MI26|MI28|HUEY)",
    re.IGNORECASE,
)
FIGHTER_RE = re.compile(
    r"^(?:F14|F15|F16|F18|FA18|F22|F35|F4|F5|F104|F111|F117|A10|AV8|EF2K|EUFI|M2K|MIR2|RAFA|JAS3|GR4|TOR|MIG|SU2|SU3|FA50|TA50|T38)",
    re.IGNORECASE,
)
BOMBER_RE = re.compile(r"^(?:B1|B2|B52|TU95|TU160|VULC|LANC)", re.IGNORECASE)
MILITARY_RE = re.compile(r"^(?:C5|C17|C130|C30J|A400|AN12|AN22|AN26|AN72|AN124|AN225|IL76|KC10|KC46|K35R|KC135|E3|E8|P3|P8|C2|C27J|C295|CN35|VC25|B703)", re.IGNORECASE)
TURBOPROP_RE = re.compile(r"^(?:AT4|AT7|DH8|DHC|SF34|E120|F50|B190|C208|PC12|TBM|BE20|B350|C90|P46T|JS31|JS32|JS41|L410|AN24)", re.IGNORECASE)
BUSINESS_RE = re.compile(r"^(?:C25|C5[0-9X]|C6[0-9A-Z]|C7[0-9A-Z]|GLF|GLEX|G280|CL3|CL6|LJ|E50P|E55P|HDJT|SF50|PC24|F2TH|FA7X|FA8X|H25|PRM1)", re.IGNORECASE)
AIRLINER_RE = re.compile(r"^(?:A3|A2[2-9]|A4|B7|BCS|E1[7-9]|E2[0-9]|CRJ|MD8|MD9|DC8|DC9|DC10|L101|F70|F100|C919|SU95|IL6|IL8|TU1|TU2|Y11|ARJ)", re.IGNORECASE)


def normalize_aircraft_type(raw: str) -> str:
    """Extract an ICAO-like type code while skipping wake/equipment prefixes."""
    value = str(raw or "").upper().strip()
    if re.search(r"F[/\s-]*A[/\s-]*18", value):
        return "F18"
    tokens = re.findall(r"[A-Z0-9]+", value)
    for token in tokens:
        if token in {"H", "J", "L", "M", "S"} or token.isdigit():
            continue
        if re.fullmatch(r"[A-Z][A-Z0-9]{1,4}", token):
            return token
    return "ACFT"


def aircraft_category(type_code: str, active_intercept: bool = False) -> str:
    code = normalize_aircraft_type(type_code)
    if active_intercept or FIGHTER_RE.match(code):
        return "fighter"
    if HELICOPTER_RE.match(code):
        return "helicopter"
    if BOMBER_RE.match(code):
        return "bomber"
    if MILITARY_RE.match(code):
        return "military"
    if TURBOPROP_RE.match(code):
        return "turboprop"
    if BUSINESS_RE.match(code):
        return "business"
    if AIRLINER_RE.match(code):
        return "airliner"
    return "general"


def mission_exemption_reason(remarks: str, helicopter: bool) -> str | None:
    if helicopter:
        return "HELICOPTER"
    for label, pattern in MISSION_EXEMPTION_PATTERNS:
        if pattern.search(remarks or ""):
            return label
    return None


@dataclass
class TrackMemory:
    last_seen: float
    last_heading: float
    last_altitude: int
    last_maneuver: float
    first_seen: float | None = None
    condition_started: dict[str, float] = field(default_factory=dict)
    min_destination_distance: float | None = None
    last_controller_match: float | None = None
    auto_scramble_controller: str | None = None
    # Persistent communications case state. These fields intentionally follow
    # the aircraft callsign across sector splits and handoffs instead of tying
    # the timer to one controller callsign or boundary identifier.
    comms_case_started: float | None = None
    comms_last_mismatch: float | None = None
    comms_gap_started: float | None = None
    comms_match_streak: int = 0
    comms_case_status: str = "INACTIVE"
    comms_last_scope: str | None = None
    comms_scope_changes: int = 0
    comms_last_reset_reason: str | None = None
    comms_cooldown_until: float = 0.0
    comms_cooldown_reason: str | None = None
    frequency_change_grace_until: float = 0.0
    last_reported_frequencies: tuple[int, ...] | None = None
    auto_scramble_accumulated: float = 0.0
    comms_observed_accumulated: float = 0.0
    session_key: str | None = None
    last_arrival: str | None = None
    last_lat: float | None = None
    last_lon: float | None = None
    recent_positions: list[tuple[float, float, float, float]] = field(default_factory=list)


class DetectionEngine:
    def __init__(self, airports: AirportResolver) -> None:
        self.airports = airports
        self.memory: dict[str, TrackMemory] = {}
        self.acknowledged: set[str] = set()
        self.dismissed: set[str] = set()
        self.manual_nordo: dict[str, dict[str, Any]] = {}
        self.temporary_exemptions: dict[str, dict[str, Any]] = {}
        self.pre_scramble_denials: dict[str, dict[str, Any]] = {}
        self._automatic_intercept_cache: dict[tuple[str, str], tuple[tuple[Any, ...], dict[str, Any]]] = {}

    def acknowledge(self, alert_id: str) -> None:
        self.acknowledged.add(alert_id)

    def dismiss(self, alert_id: str) -> None:
        self.dismissed.add(alert_id)

    def mark_manual_nordo(self, callsign: str, session_key: str | None = None) -> dict[str, Any]:
        callsign = str(callsign or "").upper().strip()
        record = self.manual_nordo.get(callsign)
        if record is None:
            now = time.time()
            record = {
                "callsign": callsign,
                "marked_at_epoch": now,
                "marked_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                "source": "OPERATOR",
                "session_key": session_key,
            }
            self.manual_nordo[callsign] = record
        self.dismissed.discard(self._alert_id(callsign))
        return record

    def clear_manual_nordo(self, callsign: str) -> bool:
        callsign = str(callsign or "").upper().strip()
        return self.manual_nordo.pop(callsign, None) is not None

    def active_temporary_exemption(self, callsign: str, now: float | None = None) -> dict[str, Any] | None:
        now = time.time() if now is None else float(now)
        callsign = str(callsign or "").upper().strip()
        active: list[dict[str, Any]] = []
        for exemption_id, record in list(self.temporary_exemptions.items()):
            expires = float(record.get("expires_at_epoch") or 0.0)
            if expires <= now:
                self.temporary_exemptions.pop(exemption_id, None)
                continue
            if str(record.get("callsign") or "").upper() == callsign:
                active.append(record)
        if not active:
            return None
        return max(active, key=lambda item: float(item.get("expires_at_epoch") or 0.0))

    @staticmethod
    def _alert_id(callsign: str, code: str = "ACTIVE") -> str:
        # Keep one stable alert identity per active track. Reason ordering can
        # change between snapshots; tying the ID to the primary reason caused
        # an acknowledged popup to reopen as a different ID. The ID is released
        # when all reasons clear, so a later occurrence can alarm again.
        return hashlib.sha1(callsign.encode()).hexdigest()[:12]

    def _duration(self, memory: TrackMemory, key: str, active: bool, now: float) -> float:
        if active:
            started = memory.condition_started.setdefault(key, now)
            return now - started
        memory.condition_started.pop(key, None)
        return 0.0

    @staticmethod
    def _reset_communications_case(memory: TrackMemory, reason: str) -> None:
        memory.comms_case_started = None
        memory.comms_last_mismatch = None
        memory.comms_gap_started = None
        memory.comms_match_streak = 0
        memory.comms_case_status = "INACTIVE"
        memory.comms_last_scope = None
        memory.auto_scramble_accumulated = 0.0
        memory.comms_observed_accumulated = 0.0
        memory.auto_scramble_controller = None
        memory.comms_last_reset_reason = reason
        memory.condition_started.pop("verified_frequency_mismatch", None)
        memory.condition_started.pop("auto_scramble_frequency_mismatch", None)
        memory.condition_started.pop("nordo_1228", None)

    @staticmethod
    def _record_position(
        memory: TrackMemory, now: float, lat: float, lon: float, heading: float
    ) -> None:
        history = memory.recent_positions
        if not history or now - history[-1][0] >= 8:
            history.append((now, lat, lon, heading % 360.0))
        cutoff = now - max(1200, settings.orbit_detection_window_seconds + 120)
        if history and history[0][0] < cutoff:
            memory.recent_positions = [item for item in history if item[0] >= cutoff]

    @staticmethod
    def _orbit_metrics(memory: TrackMemory, now: float) -> dict[str, float | int | bool]:
        cutoff = now - settings.orbit_detection_window_seconds
        points = [item for item in memory.recent_positions if item[0] >= cutoff]
        if len(points) < settings.orbit_detection_min_points:
            return {
                "detected": False,
                "points": len(points),
                "turn_degrees": 0.0,
                "net_turn_degrees": 0.0,
                "direction_consistency": 0.0,
                "span_seconds": 0.0,
                "displacement_nm": 0.0,
                "radius_nm": 0.0,
            }

        span = points[-1][0] - points[0][0]
        signed_turns = [
            (points[index][3] - points[index - 1][3] + 540.0) % 360.0 - 180.0
            for index in range(1, len(points))
        ]
        turn_degrees = sum(abs(value) for value in signed_turns)
        net_turn_degrees = sum(signed_turns)
        positive_turn = sum(value for value in signed_turns if value > 0)
        negative_turn = abs(sum(value for value in signed_turns if value < 0))
        direction_consistency = (
            max(positive_turn, negative_turn) / turn_degrees if turn_degrees > 0 else 0.0
        )
        displacement = haversine_nm(points[0][1], points[0][2], points[-1][1], points[-1][2])
        center_lat = sum(item[1] for item in points) / len(points)
        center_lon = sum(item[2] for item in points) / len(points)
        radius = max(haversine_nm(center_lat, center_lon, item[1], item[2]) for item in points)
        detected = bool(
            span >= settings.orbit_detection_min_duration_seconds
            and turn_degrees >= settings.orbit_detection_turn_degrees
            and abs(net_turn_degrees) >= settings.orbit_detection_min_net_turn_degrees
            and direction_consistency >= settings.orbit_turn_direction_consistency
            and displacement <= settings.orbit_detection_max_displacement_nm
            and radius <= settings.orbit_detection_max_radius_nm
        )
        return {
            "detected": detected,
            "points": len(points),
            "turn_degrees": round(turn_degrees, 1),
            "net_turn_degrees": round(net_turn_degrees, 1),
            "direction_consistency": round(direction_consistency, 3),
            "span_seconds": round(span, 1),
            "displacement_nm": round(displacement, 1),
            "radius_nm": round(radius, 1),
        }

    @staticmethod
    def _zone_contains(zone: dict[str, Any], lat: float, lon: float, altitude: int) -> bool:
        if not (zone["floor_ft"] <= altitude <= zone["ceiling_ft"]):
            return False
        if zone["type"] == "circle":
            center_lat, center_lon = zone["center"]
            return haversine_nm(lat, lon, center_lat, center_lon) <= zone["radius_nm"]
        if zone["type"] == "polygon":
            return point_in_polygon(lat, lon, zone["coordinates"])
        return False

    def _zone_hits(self, lat: float, lon: float, altitude: int) -> list[dict[str, Any]]:
        return [zone for zone in ZONES if self._zone_contains(zone, lat, lon, altitude)]

    @staticmethod
    def _sua_hits(
        lat: float,
        lon: float,
        altitude: int,
        areas: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = []
        for area in areas:
            if not (int(area.get("floor_ft") or 0) <= altitude <= int(area.get("ceiling_ft") or 999_999)):
                continue
            bbox = area.get("bbox")
            if bbox and not bbox_contains(bbox, lat, lon):
                continue
            if point_in_geojson_geometry(lat, lon, area.get("geometry")):
                hits.append(area)
        return hits

    @staticmethod
    def _controller_online_seconds(controller: dict[str, Any], now: float) -> int:
        raw = str(controller.get("logon_time") or "").strip()
        if not raw:
            return 0
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0, int(now - parsed.timestamp()))
        except ValueError:
            return 0

    @staticmethod
    def _build_centers(
        controllers: list[dict[str, Any]], audio: dict[str, list[dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        """Build live transceiver fallbacks when reference polygons are unavailable."""
        centers: list[dict[str, Any]] = []
        now = time.time()
        controller_map = {str(c.get("callsign", "")).upper(): c for c in controllers}
        for callsign, raw_transceivers in audio.items():
            suffix = callsign.rsplit("_", 1)[-1] if "_" in callsign else ""
            if suffix not in {"CTR", "APP", "DEP", "TWR", "GND", "DEL"}:
                continue
            transceivers = []
            coords = []
            for item in raw_transceivers:
                if item.get("latDeg") is None or item.get("lonDeg") is None:
                    continue
                lat = float(item["latDeg"])
                lon = float(item["lonDeg"])
                coords.append((lat, lon))
                transceivers.append(
                    {
                        "id": item.get("id"),
                        "frequency": int(item.get("frequency") or 0),
                        "lat": lat,
                        "lon": lon,
                        "height_msl_m": float(item.get("heightMslM") or 0),
                        "height_agl_m": float(item.get("heightAglM") or 0),
                    }
                )
            center = circular_mean(coords)
            if not center:
                continue
            controller = controller_map.get(callsign, {})
            frequencies = sorted(
                {int(item.get("frequency", 0)) for item in transceivers if item.get("frequency")}
            )
            centers.append(
                {
                    "callsign": callsign,
                    "online_seconds": DetectionEngine._controller_online_seconds(controller, now),
                    "logon_time": controller.get("logon_time"),
                    "lat": center[0],
                    "lon": center[1],
                    "frequencies_hz": frequencies,
                    "frequencies": [round(value / 1_000_000, 3) for value in frequencies],
                    "frequency": controller.get("frequency"),
                    "geometry": None,
                    "bbox": None,
                    "radius_nm": (
                        settings.center_coverage_radius_nm
                        if suffix == "CTR"
                        else settings.approach_coverage_radius_nm
                        if suffix in {"APP", "DEP"}
                        else settings.tower_alert_max_range_nm
                        if suffix == "TWR"
                        else settings.ground_alert_max_range_nm
                    ),
                    "facility": suffix,
                    "transceivers": transceivers,
                    "match_quality": "none",
                    "sector_specific": False,
                    "alert_basis": "LIVE_TRANSCEIVERS",
                    "source": "VATSIM transceiver fallback",
                }
            )
        return centers

    @staticmethod
    def _radio_horizon_nm(
        altitude_ft: int,
        receiver_height_msl_m: float,
        facility: str,
    ) -> float:
        """Conservative VHF line-of-sight estimate for an AFV transceiver."""
        aircraft_ft = max(0.0, float(altitude_ft))
        receiver_ft = max(0.0, float(receiver_height_msl_m) * 3.28084)
        horizon = 1.23 * ((aircraft_ft ** 0.5) + (receiver_ft ** 0.5))
        cap = (
            settings.center_alert_max_range_nm
            if facility == "CTR"
            else settings.approach_alert_max_range_nm
            if facility in {"APP", "DEP"}
            else settings.tower_alert_max_range_nm
            if facility == "TWR"
            else settings.ground_alert_max_range_nm
        )
        floor = 25.0 if facility in {"CTR", "APP", "DEP"} else 8.0 if facility == "TWR" else 3.0
        return max(floor, min(float(cap), horizon + 8.0))

    @staticmethod
    def _ground_track_state(
        altitude: int,
        groundspeed: int,
        departure_distance_nm: float | None,
        destination_distance_nm: float | None,
    ) -> tuple[bool, str | None, float | None]:
        distances = [
            value
            for value in (departure_distance_nm, destination_distance_nm)
            if value is not None
        ]
        nearest = min(distances) if distances else None
        on_ground = bool(
            nearest is not None
            and nearest <= settings.ground_airport_radius_nm
            and groundspeed <= settings.ground_track_max_speed_kt
            and altitude <= settings.ground_track_max_msl_ft
        )
        if not on_ground:
            return False, None, nearest
        return True, ("STATIONARY" if groundspeed <= 3 else "TAXI"), nearest

    @classmethod
    def _coverage_candidates(
        cls,
        lat: float,
        lon: float,
        altitude: int,
        coverage: list[dict[str, Any]],
        *,
        on_ground: bool = False,
        allow_split_fallback: bool = False,
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for item in coverage:
            facility = str(item.get("facility") or "").upper()
            if facility not in {"CTR", "APP", "DEP", "TWR", "GND", "DEL"}:
                continue
            if facility in {"APP", "DEP"} and altitude > 24000:
                continue
            if facility in {"GND", "DEL"} and not on_ground:
                continue
            if (
                item.get("match_quality") in {"facility_fallback", "tracon_fallback"}
                and not settings.atc_split_fallback_alerts
                and not allow_split_fallback
            ):
                # A split position that only matched the full facility polygon
                # is displayed, but is not trusted for automated radio alerts.
                continue

            # A polygon is a geographic guard only. It never establishes alert
            # coverage by itself because one online position may own only a
            # subset of an ARTCC/TRACON.
            geometry = item.get("geometry")
            bbox = item.get("bbox")
            if geometry:
                if bbox and not bbox_contains(bbox, lat, lon):
                    continue
                if not point_in_geojson_geometry(lat, lon, geometry):
                    continue

            best: dict[str, Any] | None = None
            for transceiver in item.get("transceivers") or []:
                tx_lat = transceiver.get("lat")
                tx_lon = transceiver.get("lon")
                if tx_lat is None or tx_lon is None:
                    continue
                receiver_height_msl_m = float(transceiver.get("height_msl_m") or 0)
                estimated_agl_ft = max(0.0, float(altitude) - receiver_height_msl_m * 3.28084)
                if facility == "TWR" and not on_ground and estimated_agl_ft > settings.tower_max_agl_ft:
                    continue
                reach = cls._radio_horizon_nm(
                    altitude,
                    receiver_height_msl_m,
                    facility,
                )
                distance = haversine_nm(lat, lon, float(tx_lat), float(tx_lon))
                if distance > reach:
                    continue
                ratio = distance / max(reach, 1.0)
                if best is None or ratio < best["range_ratio"]:
                    best = {
                        "distance_nm": distance,
                        "coverage_radius_nm": reach,
                        "range_ratio": ratio,
                        "transceiver_frequency": int(transceiver.get("frequency") or 0),
                        "estimated_agl_ft": estimated_agl_ft,
                    }

            # Do not turn a polygon-only match into a radio alert. This is the
            # key false-positive protection for split Center and APP positions.
            if best is None:
                if settings.atc_polygon_only_alerts and item.get("lat") is not None and item.get("lon") is not None:
                    distance = haversine_nm(lat, lon, float(item["lat"]), float(item["lon"]))
                    radius = float(item.get("radius_nm") or 0)
                    if radius > 0 and distance <= radius:
                        best = {
                            "distance_nm": distance,
                            "coverage_radius_nm": radius,
                            "range_ratio": distance / radius,
                            "transceiver_frequency": 0,
                        }
                if best is None:
                    continue

            # Deterministic facility hierarchy. Frequency matches still win
            # across all candidates, which handles normal handoffs and top-down
            # coverage without forcing a false mismatch.
            if on_ground:
                priority = {
                    "GND": 0,
                    "DEL": 1,
                    "TWR": 2,
                    "APP": 3,
                    "DEP": 3,
                    "CTR": 4,
                }.get(facility, 9)
            elif altitude <= 18000:
                priority = {
                    "TWR": 0,
                    "APP": 1,
                    "DEP": 1,
                    "CTR": 2,
                    "GND": 9,
                    "DEL": 9,
                }.get(facility, 9)
            else:
                priority = 0 if facility == "CTR" else 1

            candidates.append(
                {
                    **item,
                    **best,
                    "priority": priority,
                    # A generic Center position such as DEN_CTR can own the
                    # full ARTCC. When it matches the exact facility polygon and
                    # the aircraft is also inside conservative live AFV
                    # transceiver reach, that is sufficient high-confidence
                    # coverage. Split positions that only fall back to the whole
                    # facility remain display-only above and never reach here.
                    "coverage_confidence": (
                        "HIGH"
                        if best["range_ratio"] <= 0.8
                        and (
                            item.get("sector_specific")
                            or (
                                facility == "CTR"
                                and item.get("match_quality") in {"facility", "facility_fallback"}
                                and bool(item.get("geometry"))
                            )
                        )
                        else "MEDIUM"
                    ),
                    "coverage_confidence_basis": (
                        "EXACT_SECTOR_AND_TRANSCEIVER"
                        if item.get("sector_specific")
                        else "SPLIT_CENTER_FACILITY_AND_TRANSCEIVER"
                        if facility == "CTR"
                        and item.get("match_quality") == "facility_fallback"
                        and bool(item.get("geometry"))
                        else "GENERIC_CENTER_FACILITY_AND_TRANSCEIVER"
                        if facility == "CTR"
                        and item.get("match_quality") == "facility"
                        and bool(item.get("geometry"))
                        else "TRANSCEIVER_ONLY"
                    ),
                }
            )

        candidates.sort(key=lambda value: (value["priority"], value["range_ratio"]))
        return candidates

    @staticmethod
    def _non_controlling_frequency_label(frequency_hz: int) -> str | None:
        for reference_hz, label in NON_CONTROLLING_FREQUENCIES:
            if abs(int(frequency_hz) - reference_hz) <= NON_CONTROLLING_FREQUENCY_TOLERANCE_HZ:
                return label
        return None

    @classmethod
    def _frequency_matches(cls, pilot_frequencies: list[int], controller: dict[str, Any]) -> bool:
        # Guard and advisory/UNICOM frequencies are monitoring destinations, not
        # proof of controller contact. Ignore them even if a malformed coverage
        # record happens to advertise one of those frequencies. A separate, real
        # ATC-frequency match still clears the case normally.
        usable_pilot_frequencies = [
            frequency
            for frequency in pilot_frequencies
            if cls._non_controlling_frequency_label(frequency) is None
        ]
        usable_controller_frequencies = [
            frequency
            for frequency in (controller.get("frequencies_hz") or [])
            if cls._non_controlling_frequency_label(frequency) is None
        ]
        return any(
            abs(pilot_frequency - controller_frequency) <= settings.frequency_match_tolerance_hz
            for pilot_frequency in usable_pilot_frequencies
            for controller_frequency in usable_controller_frequencies
        )

    @classmethod
    def _select_controller(
        cls,
        candidates: list[dict[str, Any]],
        pilot_frequencies: list[int],
    ) -> tuple[dict[str, Any] | None, bool, str]:
        if not candidates:
            return None, False, "NO_LIVE_TRANSCEIVER_COVERAGE"

        # Any exact frequency match in any valid overlapping live position wins.
        # This prevents a nearer APP/DEP candidate from falsely overriding a
        # legitimate Center frequency (or vice versa) near facility boundaries.
        matching = [item for item in candidates if cls._frequency_matches(pilot_frequencies, item)]
        if matching:
            return min(matching, key=lambda value: (value["priority"], value["range_ratio"])), True, "FREQUENCY_MATCH"

        best_priority = candidates[0]["priority"]
        primary = [item for item in candidates if item["priority"] == best_priority]
        best = primary[0]
        if settings.atc_require_unambiguous_controller and len(primary) > 1:
            second = primary[1]
            separation = second["range_ratio"] - best["range_ratio"]
            different_position = second.get("callsign") != best.get("callsign")
            different_frequencies = set(second.get("frequencies_hz") or []) != set(best.get("frequencies_hz") or [])
            if different_position and different_frequencies and separation < settings.atc_overlap_margin:
                return None, False, "AMBIGUOUS_OVERLAP"

        return best, False, "UNAMBIGUOUS_TRANSCEIVER"

    @staticmethod
    def _early_unicom_handoff_exemption(
        *,
        lat: float,
        lon: float,
        heading: float,
        groundspeed: float,
        has_1228: bool,
        on_ground: bool,
        communications_controller: dict[str, Any] | None,
        coverage: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Identify a plausible early Center-to-UNICOM release.

        VATSIM controllers commonly send an aircraft to 122.800 before the
        exact ARTCC boundary when the downstream Center is offline. This
        exemption is intentionally conservative: the aircraft must currently
        be inside the active Center's parent ARTCC, be moving toward an exit
        within the configured lookahead, and the projected point must not be
        inside any other online Center's parent ARTCC.
        """
        if (
            not has_1228
            or on_ground
            or groundspeed < settings.nordo_min_groundspeed_kt
            or not communications_controller
            or communications_controller.get("facility") != "CTR"
        ):
            return None
        current_parent = str(
            communications_controller.get("parent_boundary_id")
            or communications_controller.get("boundary_id")
            or ""
        ).strip()
        current_geometry = communications_controller.get("parent_geometry")
        callsign = str(communications_controller.get("callsign") or "").upper()
        # An unsplit position such as DEN_CTR normally already uses the parent
        # ARTCC outline. Split positions (DEN_17_CTR) still require the explicit
        # parent geometry so an internal sector edge cannot look like a handoff.
        if not current_geometry and callsign.endswith("_CTR") and callsign.count("_") == 1:
            current_geometry = communications_controller.get("geometry")
        if not current_parent or not current_geometry:
            return None
        if not point_in_geojson_geometry(lat, lon, current_geometry):
            return None
        lookahead_nm = min(
            settings.early_unicom_handoff_max_lookahead_nm,
            max(0.0, groundspeed) * settings.early_unicom_handoff_lookahead_minutes / 60.0,
        )
        if lookahead_nm < 10.0:
            return None
        projected_lat, projected_lon = destination_point(lat, lon, heading, lookahead_nm)
        if point_in_geojson_geometry(projected_lat, projected_lon, current_geometry):
            return None

        downstream_online: list[str] = []
        for item in coverage:
            if item.get("facility") != "CTR":
                continue
            geometry = item.get("parent_geometry") or item.get("geometry")
            if not geometry or not point_in_geojson_geometry(projected_lat, projected_lon, geometry):
                continue
            parent_id = str(item.get("parent_boundary_id") or item.get("boundary_id") or "").split("-", 1)[0]
            if parent_id and parent_id != current_parent:
                downstream_online.append(str(item.get("callsign") or parent_id))
        if downstream_online:
            return None
        return {
            "current_controller": communications_controller.get("callsign"),
            "current_artcc": current_parent or communications_controller.get("boundary_id"),
            "lookahead_minutes": settings.early_unicom_handoff_lookahead_minutes,
            "lookahead_nm": round(lookahead_nm, 1),
            "projected_lat": round(projected_lat, 5),
            "projected_lon": round(projected_lon, 5),
            "downstream_center_online": False,
        }

    @classmethod
    def _online_center_handoff_exemption(
        cls,
        *,
        lat: float,
        lon: float,
        heading: float,
        groundspeed: float,
        pilot_frequencies: list[int],
        on_ground: bool,
        communications_controller: dict[str, Any] | None,
        coverage: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Allow an early handoff to a staffed neighboring Center.

        A pilot may be switched to the next Center before crossing the published
        ARTCC boundary.  The exemption is deliberately narrow: the aircraft must
        still be inside the current Center's parent ARTCC, be flying toward an
        exit within 80 NM, and one reported ATC-capable radio must exactly match
        the online downstream Center whose parent ARTCC contains the projected
        track.  Internal split-sector edges and unrelated frequencies never
        qualify.
        """
        if (
            on_ground
            or groundspeed < settings.nordo_min_groundspeed_kt
            or not pilot_frequencies
            or not communications_controller
            or communications_controller.get("facility") != "CTR"
        ):
            return None

        current_parent = str(
            communications_controller.get("parent_boundary_id")
            or communications_controller.get("boundary_id")
            or ""
        ).split("-", 1)[0].strip().upper()
        current_geometry = communications_controller.get("parent_geometry")
        callsign = str(communications_controller.get("callsign") or "").upper()
        if not current_geometry and callsign.endswith("_CTR") and callsign.count("_") == 1:
            current_geometry = communications_controller.get("geometry")
        if not current_parent or not current_geometry:
            return None
        if not point_in_geojson_geometry(lat, lon, current_geometry):
            return None

        downstream: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
        seen: set[tuple[str, str]] = set()
        for item in coverage:
            if str(item.get("facility") or "").upper() != "CTR":
                continue
            parent_id = str(
                item.get("parent_boundary_id") or item.get("boundary_id") or ""
            ).split("-", 1)[0].strip().upper()
            geometry = item.get("parent_geometry") or item.get("geometry")
            item_callsign = str(item.get("callsign") or parent_id).upper()
            key = (parent_id, item_callsign)
            if (
                not parent_id
                or parent_id == current_parent
                or not geometry
                or key in seen
                or not cls._frequency_matches(pilot_frequencies, item)
            ):
                continue
            seen.add(key)
            downstream.append((item, parent_id, geometry))
        if not downstream:
            return None

        max_distance = max(0.0, float(settings.online_center_handoff_max_distance_nm))
        step = max(0.5, float(settings.online_center_handoff_probe_step_nm))
        if max_distance < step:
            return None

        first_outside_nm: float | None = None
        distance = step
        while distance <= max_distance + 1e-9:
            projected_lat, projected_lon = destination_point(lat, lon, heading, distance)
            if point_in_geojson_geometry(projected_lat, projected_lon, current_geometry):
                distance += step
                continue
            if first_outside_nm is None:
                first_outside_nm = distance
            for item, parent_id, geometry in downstream:
                if not point_in_geojson_geometry(projected_lat, projected_lon, geometry):
                    continue
                matched = sorted({
                    round(int(pilot_frequency) / 1_000_000, 3)
                    for pilot_frequency in pilot_frequencies
                    for controller_frequency in (item.get("frequencies_hz") or [])
                    if cls._non_controlling_frequency_label(int(pilot_frequency)) is None
                    and abs(int(pilot_frequency) - int(controller_frequency)) <= settings.frequency_match_tolerance_hz
                })
                return {
                    "current_controller": communications_controller.get("callsign"),
                    "current_artcc": current_parent,
                    "downstream_controller": item.get("callsign") or parent_id,
                    "downstream_artcc": parent_id,
                    "matched_frequencies": matched,
                    "boundary_distance_nm": round(first_outside_nm or distance, 1),
                    "downstream_entry_distance_nm": round(distance, 1),
                    "max_distance_nm": round(max_distance, 1),
                    "projected_lat": round(projected_lat, 5),
                    "projected_lon": round(projected_lon, 5),
                    "downstream_center_online": True,
                }
            distance += step
        return None

    @staticmethod
    def _track_intercept_solution(fighter: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
        fighter_reported_speed = max(0.0, float(fighter.get("groundspeed") or 0))
        target_speed = max(0.0, float(target.get("groundspeed") or 0))
        target_heading = float(target.get("heading") or 0) % 360
        fighter_heading = float(fighter.get("heading") or 0) % 360
        fighter_lat, fighter_lon = float(fighter["lat"]), float(fighter["lon"])
        target_lat, target_lon = float(target["lat"]), float(target["lon"])
        separation = haversine_nm(fighter_lat, fighter_lon, target_lat, target_lon)
        direct_bearing = initial_bearing_deg(fighter_lat, fighter_lon, target_lat, target_lon)
        intercept_point = (target_lat, target_lon)
        eta_minutes: float | None = None

        # ETA uses the interceptor's current reported groundspeed. Ground or
        # nearly stationary tracks do not receive a fictitious intercept time.
        solver_speed = fighter_reported_speed if not fighter.get("on_ground") and fighter_reported_speed >= 80.0 else 0.0
        if solver_speed > 0:
            t = 0.25
            while t <= 75.0:
                projected = destination_point(target_lat, target_lon, target_heading, target_speed * t / 60.0)
                if haversine_nm(fighter_lat, fighter_lon, projected[0], projected[1]) <= solver_speed * t / 60.0:
                    eta_minutes = t
                    intercept_point = projected
                    break
                t += 0.25

        course = initial_bearing_deg(fighter_lat, fighter_lon, intercept_point[0], intercept_point[1])
        one_min_target = destination_point(target_lat, target_lon, target_heading, target_speed / 60.0)
        one_min_fighter = destination_point(fighter_lat, fighter_lon, fighter_heading, fighter_reported_speed / 60.0)
        next_separation = haversine_nm(one_min_fighter[0], one_min_fighter[1], one_min_target[0], one_min_target[1])
        signed_closure_rate = (separation - next_separation) * 60.0
        relative_bearing = ((direct_bearing - fighter_heading + 540.0) % 360.0) - 180.0
        altitude_delta = int(target.get("altitude") or 0) - int(fighter.get("altitude") or 0)
        trend = "CLOSING" if signed_closure_rate > 10 else "OPENING" if signed_closure_rate < -10 else "STEADY"
        return {
            "target_callsign": target["callsign"],
            "separation_nm": round(separation, 1),
            "closure_rate_kt": round(max(0.0, signed_closure_rate)),
            "signed_closure_rate_kt": round(signed_closure_rate),
            "closure_status": trend,
            "estimated_intercept_minutes": round(eta_minutes, 1) if eta_minutes is not None else None,
            "estimated_intercept_seconds": int(round(eta_minutes * 60)) if eta_minutes is not None else None,
            "recommended_course_deg": int(round(course)) % 360,
            "bearing_to_target_deg": int(round(direct_bearing)) % 360,
            "relative_bearing_deg": round(relative_bearing, 1),
            "intercept_point_lat": round(intercept_point[0], 4),
            "intercept_point_lon": round(intercept_point[1], 4),
            "turn_required_deg": round(heading_delta(fighter_heading, course), 1),
            "interceptor_heading_deg": int(round(fighter_heading)) % 360,
            "interceptor_speed_kt": int(round(fighter_reported_speed)),
            "interceptor_altitude_ft": int(fighter.get("altitude") or 0),
            "target_heading_deg": int(round(target_heading)) % 360,
            "target_speed_kt": int(round(target_speed)),
            "target_altitude_ft": int(target.get("altitude") or 0),
            "altitude_delta_ft": altitude_delta,
        }

    def _associate_interceptors(
        self, display_pilots: list[dict[str, Any]], alerts: list[dict[str, Any]]
    ) -> None:
        target_by_call = {item["callsign"]: item for item in display_pilots}
        alert_by_call = {item["callsign"]: item for item in alerts}
        targets = [target_by_call[call] for call in alert_by_call if call in target_by_call]
        if not targets:
            return
        for fighter in (item for item in display_pilots if item.get("active_intercept")):
            ranked: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
            for target in targets:
                if target["callsign"] == fighter["callsign"]:
                    continue
                pair_key = (str(fighter.get("callsign") or ""), str(target.get("callsign") or ""))
                signature = intercept_pair_signature(fighter, target)
                cached = self._automatic_intercept_cache.get(pair_key)
                if cached and cached[0] == signature:
                    solution = dict(cached[1])
                else:
                    solution = self._track_intercept_solution(fighter, target)
                    self._automatic_intercept_cache[pair_key] = (signature, dict(solution))
                eta = solution["estimated_intercept_minutes"]
                if solution["separation_nm"] > 650 or solution["turn_required_deg"] > 145:
                    continue
                rank = (eta if eta is not None else 999.0) + solution["turn_required_deg"] / 30.0
                ranked.append((rank, target, solution))
            if not ranked:
                continue
            _, target, solution = min(ranked, key=lambda item: item[0])
            fighter["intercept_assignment"] = solution
            target["active_interceptors"].append({"callsign": fighter["callsign"], **solution})
            alert = alert_by_call.get(target["callsign"])
            if alert is not None:
                alert.setdefault("active_interceptors", []).append({"callsign": fighter["callsign"], **solution})

    def evaluate(
        self,
        pilots: list[dict[str, Any]],
        controllers: list[dict[str, Any]],
        audio: dict[str, list[dict[str, Any]]],
        atc_coverage: list[dict[str, Any]] | None = None,
        sua_areas: list[dict[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        now = time.time()
        coverage = list(atc_coverage or [])
        if not any(item.get("facility") == "CTR" for item in coverage):
            existing = {str(item.get("callsign") or "").upper() for item in coverage}
            coverage.extend(
                item
                for item in self._build_centers(controllers, audio)
                if str(item.get("callsign") or "").upper() not in existing
            )

        coverage_index = SpatialGridIndex(settings.spatial_grid_degrees)
        for coverage_item in coverage:
            coverage_index.add(coverage_item, coverage_bbox(coverage_item, settings.center_alert_max_range_nm))

        alerts: list[dict[str, Any]] = []
        display_pilots: list[dict[str, Any]] = []
        active_alert_ids: set[str] = set()
        seen: set[str] = set()

        for pilot in pilots:
            callsign = str(pilot.get("callsign") or "UNKNOWN").upper()
            seen.add(callsign)
            altitude = int(pilot.get("altitude") or 0)
            groundspeed = int(pilot.get("groundspeed") or 0)
            heading = float(pilot.get("heading") or 0)
            lat, lon = float(pilot["latitude"]), float(pilot["longitude"])
            session_key = f"{pilot.get('cid') or 'NO-CID'}:{pilot.get('logon_time') or 'NO-LOGON'}"
            memory = self.memory.get(callsign)
            session_changed = bool(memory and memory.session_key and memory.session_key != session_key)
            teleported = bool(
                memory
                and memory.last_lat is not None
                and memory.last_lon is not None
                and haversine_nm(memory.last_lat, memory.last_lon, lat, lon) > 300
            )
            if not memory or session_changed or teleported:
                memory = TrackMemory(
                    now,
                    heading,
                    altitude,
                    now,
                    first_seen=now,
                    session_key=session_key,
                    last_lat=lat,
                    last_lon=lon,
                )
                self.memory[callsign] = memory
                # A new network session or implausible position jump must never
                # inherit a prior pilot's NORDO designation or timer history.
                if session_changed or teleported:
                    self.manual_nordo.pop(callsign, None)
                    # A new network session using the same callsign is a new
                    # alert occurrence and must not inherit a prior operator's
                    # acknowledgment or dismissal.
                    track_alert_id = self._alert_id(callsign)
                    self.acknowledged.discard(track_alert_id)
                    self.dismissed.discard(track_alert_id)
                tick_seconds = 0.0
            else:
                if memory.first_seen is None:
                    memory.first_seen = now
                memory.session_key = session_key
                # Timers are based on observed snapshots, never wall-clock outage
                # time. A stale feed or sleeping host therefore cannot auto-escalate.
                tick_seconds = max(
                    0.0,
                    min(float(settings.max_observed_feed_tick_seconds), now - memory.last_seen),
                )
            if heading_delta(heading, memory.last_heading) >= 7 or abs(altitude - memory.last_altitude) >= 1200:
                memory.last_maneuver = now
            memory.last_heading = heading
            memory.last_altitude = altitude
            memory.last_seen = now
            memory.last_lat = lat
            memory.last_lon = lon
            self._record_position(memory, now, lat, lon, heading)

            flight_plan = pilot.get("flight_plan") or {}
            dep = str(flight_plan.get("departure") or "").upper()
            arr = str(flight_plan.get("arrival") or "").upper()
            aircraft = str(
                flight_plan.get("aircraft_short") or flight_plan.get("aircraft") or "—"
            )
            flight_rules = str(flight_plan.get("flight_rules") or "").upper()
            remarks = str(flight_plan.get("remarks") or "").upper()
            if memory.last_arrival is not None and memory.last_arrival != arr:
                memory.min_destination_distance = None
            memory.last_arrival = arr
            declared_radio_limitation = any(term in remarks for term in RADIO_LIMITATION_TERMS)
            vsoa_marker = detect_vsoa_marker(remarks)
            aircraft_type = normalize_aircraft_type(aircraft)
            preliminary_category = aircraft_category(aircraft_type)
            helicopter_flight = preliminary_category == "helicopter"
            blackjack_unit = detect_blackjack_unit(callsign, remarks, aircraft_type, lat, lon)
            if blackjack_unit:
                vsoa_marker = "vUSCG · BLACKJACK"
            vsoa_flight = bool(vsoa_marker or blackjack_unit)
            navigation_exemption = mission_exemption_reason(remarks, helicopter_flight)
            pilot_freqs = sorted(
                {int(item.get("frequency", 0)) for item in audio.get(callsign, []) if item.get("frequency")}
            )
            reported_frequency_signature = tuple(pilot_freqs)
            if (
                memory.comms_case_started is None
                and memory.last_reported_frequencies is not None
                and memory.last_reported_frequencies
                and reported_frequency_signature
                and memory.last_reported_frequencies != reported_frequency_signature
                and all(self._non_controlling_frequency_label(value) is None for value in reported_frequency_signature)
            ):
                memory.frequency_change_grace_until = max(
                    memory.frequency_change_grace_until,
                    now + max(0, settings.communications_frequency_change_grace_seconds),
                )
            memory.last_reported_frequencies = reported_frequency_signature
            temporary_exemption = self.active_temporary_exemption(callsign, now)
            temporary_exemption_active = bool(temporary_exemption)
            dep_info = self.airports.get(dep)
            arr_info = self.airports.get(arr)
            departure_distance = haversine_nm(lat, lon, dep_info[0], dep_info[1]) if dep_info else None
            destination_distance = haversine_nm(lat, lon, arr_info[0], arr_info[1]) if arr_info else None
            track_age_seconds = max(0.0, now - float(memory.first_seen or now))
            departure_turn_suppressed = bool(
                departure_distance is not None
                and departure_distance <= settings.orbit_departure_suppression_nm
                and track_age_seconds <= settings.orbit_departure_suppression_seconds
                and altitude <= settings.orbit_departure_suppression_max_altitude_ft
            )
            near_terminal_distance = bool(
                (departure_distance is not None and departure_distance <= settings.nordo_terminal_exclusion_nm)
                or (destination_distance is not None and destination_distance <= settings.nordo_terminal_exclusion_nm)
            )
            # Do not suppress a high-altitude en-route NORDO candidate merely
            # because its filed departure or destination is within 55 NM. The
            # terminal exemption is limited to aircraft that are both low and
            # slow enough for legitimate CTAF/UNICOM use to be plausible.
            near_terminal_airport = bool(
                near_terminal_distance
                and altitude <= settings.nordo_terminal_exclusion_max_altitude_ft
                and groundspeed <= settings.nordo_terminal_exclusion_max_groundspeed_kt
            )
            on_ground, ground_status, nearest_airport_distance = self._ground_track_state(
                altitude,
                groundspeed,
                departure_distance,
                destination_distance,
            )

            controller_candidates: list[dict[str, Any]] = []
            communications_candidates: list[dict[str, Any]] = []
            nearby_controller = None
            frequency_matches_controller = False
            coverage_selection_reason = "NOT_EVALUATED"
            # Strict candidates continue to determine the most likely exact owner.
            # A second, communications-only candidate set admits parent-facility
            # fallbacks for split Center/TRACON positions. If a pilot matches none
            # of the frequencies in that full valid set, exact sector ownership is
            # unnecessary to establish that the pilot is on the wrong frequency.
            if on_ground or altitude >= 500 or groundspeed > 20:
                nearby_coverage = coverage_index.query(lat, lon)
                controller_candidates = self._coverage_candidates(
                    lat,
                    lon,
                    altitude,
                    nearby_coverage,
                    on_ground=on_ground,
                )
                communications_candidates = self._coverage_candidates(
                    lat,
                    lon,
                    altitude,
                    nearby_coverage,
                    on_ground=on_ground,
                    allow_split_fallback=True,
                )
                nearby_controller, frequency_matches_controller, coverage_selection_reason = self._select_controller(
                    controller_candidates, pilot_freqs
                )

            matching_communications_candidates = [
                item
                for item in communications_candidates
                if self._frequency_matches(pilot_freqs, item)
            ]
            frequency_matches_any_controller = bool(matching_communications_candidates)
            communications_frequency_mismatch = bool(
                communications_candidates
                and pilot_freqs
                and not frequency_matches_any_controller
            )
            primary_communications_candidates: list[dict[str, Any]] = []
            if communications_candidates:
                best_priority = communications_candidates[0]["priority"]
                primary_communications_candidates = [
                    item
                    for item in communications_candidates
                    if item["priority"] == best_priority
                ]
            communications_controller = nearby_controller or (
                primary_communications_candidates[0]
                if primary_communications_candidates
                else None
            )
            communications_callsigns = sorted(
                {
                    str(item.get("callsign") or "")
                    for item in primary_communications_candidates
                    if item.get("callsign")
                }
            )
            communications_controller_label = (
                nearby_controller["callsign"]
                if nearby_controller
                else " / ".join(communications_callsigns[:3])
                if communications_callsigns
                else None
            )
            common_boundaries = {
                str(item.get("boundary_id") or "")
                for item in primary_communications_candidates
                if item.get("boundary_id")
            }
            communications_scope_key = (
                f"FACILITY:{next(iter(common_boundaries))}"
                if len(common_boundaries) == 1
                else "POSITIONS:" + "|".join(communications_callsigns)
                if communications_callsigns
                else None
            )
            communications_selection_reason = coverage_selection_reason
            if not nearby_controller and communications_controller:
                communications_selection_reason = (
                    "MULTI_POSITION_MISMATCH"
                    if len(primary_communications_candidates) > 1
                    else "SPLIT_POSITION_FALLBACK"
                    if communications_controller.get("match_quality")
                    in {"facility_fallback", "tracon_fallback"}
                    else "COMMUNICATIONS_COVERAGE"
                )
            ownership_status = (
                "VERIFIED_FREQUENCY_MATCH"
                if frequency_matches_any_controller
                else "COVERAGE_SET_MISMATCH"
                if communications_frequency_mismatch
                else "EXPECTED_OWNER"
                if nearby_controller
                else "AMBIGUOUS_HANDOFF"
                if coverage_selection_reason == "AMBIGUOUS_OVERLAP"
                else "NO_LIVE_COVERAGE"
            )

            reasons: list[dict[str, Any]] = []
            observations: list[dict[str, Any]] = []
            score = 0
            severity = "green"
            critical_trigger = False

            def evidence_category(code: str) -> str:
                if code.startswith("SQUAWK_"):
                    return "emergency"
                if code.startswith(("ZONE_", "FAA_PROHIBITED", "FAA_RESTRICTED")):
                    return "protected_airspace"
                if code.startswith(("NORDO_", "NO_RADIO", "MANUAL_NORDO")):
                    return "radio"
                if code.startswith(("ROUTE_", "DEST_", "MISSED_")):
                    return "navigation"
                if code.startswith("ASSIGNED_"):
                    return "identity"
                return "behavior"

            def add(
                code: str,
                label: str,
                points: int,
                level: str,
                detail: str,
                *,
                critical: bool = False,
            ) -> None:
                nonlocal score, severity, critical_trigger
                score += points
                critical_trigger = critical_trigger or critical
                if SEVERITY_RANK[level] > SEVERITY_RANK[severity]:
                    severity = level
                reasons.append({
                    "code": code,
                    "label": label,
                    "points": points,
                    "detail": detail,
                    "category": evidence_category(code),
                    "critical": critical,
                })

            def observe(code: str, label: str, detail: str) -> None:
                observations.append({"code": code, "label": label, "detail": detail})

            manual_nordo = self.manual_nordo.get(callsign)
            if manual_nordo and manual_nordo.get("session_key") not in {None, session_key}:
                self.manual_nordo.pop(callsign, None)
                manual_nordo = None
            manual_nordo_seconds = (
                max(0, int(now - float(manual_nordo.get("marked_at_epoch") or now)))
                if manual_nordo
                else 0
            )

            squawk = str(pilot.get("transponder") or "").zfill(4)
            if manual_nordo:
                marked_label = str(manual_nordo.get("marked_at") or "").replace("+00:00", "Z")
                add(
                    "MANUAL_NORDO",
                    "Operator-designated NORDO",
                    100,
                    "red",
                    f"Aircraft manually marked NORDO at {marked_label}; shared designation remains active until cleared",
                    critical=True,
                )
            if squawk == "7500":
                add("SQUAWK_7500", "Unlawful interference squawk", 100, "red", "Transponder 7500", critical=True)
            elif squawk == "7600":
                add("SQUAWK_7600", "Radio failure squawk", 70, "red", "Transponder 7600", critical=True)
            elif squawk == "7700":
                add("SQUAWK_7700", "General emergency squawk", 100, "red", "Transponder 7700", critical=True)

            zone_hits = self._zone_hits(lat, lon, altitude)
            for zone in zone_hits:
                points = 100 if zone["severity"] == "red" else 45
                add(
                    f"ZONE_{zone['id']}",
                    "Monitored airspace penetration",
                    points,
                    zone["severity"],
                    zone["name"],
                    critical=zone["severity"] == "red",
                )

            regulatory_hits = self._sua_hits(lat, lon, altitude, list(sua_areas or []))
            local_ids = {str(zone.get("id") or "").replace("-", "").upper() for zone in zone_hits}
            for area in regulatory_hits:
                designation = str(area.get("designation") or "UNKNOWN")
                if designation.replace("-", "").upper() in local_ids:
                    continue
                floor_label = area.get("floor_label") or f"{area.get('floor_ft', 0):,} FT"
                ceiling_label = area.get("ceiling_label") or f"{area.get('ceiling_ft', 0):,} FT"
                if area.get("category") == "PROHIBITED":
                    add(
                        f"FAA_PROHIBITED_{area.get('id')}",
                        "Prohibited airspace penetration",
                        100,
                        "red",
                        f"{designation} · {floor_label}–{ceiling_label}",
                        critical=True,
                    )
                else:
                    # The public geometry describes the regulatory area, but it
                    # does not prove current activation of a joint-use area.
                    add(
                        f"FAA_RESTRICTED_{area.get('id')}",
                        "Restricted airspace penetration",
                        45,
                        "orange",
                        f"{designation} · activation unverified · {floor_label}–{ceiling_label}",
                    )

            # Predict a short straight-line track so operators receive an advisory
            # before an aircraft crosses a configured monitored-zone boundary.
            if not zone_hits and groundspeed >= 150 and altitude >= settings.min_airborne_altitude_ft:
                lookahead_nm = groundspeed * settings.monitored_zone_lookahead_minutes / 60
                projected_lat, projected_lon = destination_point(lat, lon, heading, lookahead_nm)
                projected_hits = self._zone_hits(projected_lat, projected_lon, altitude)
                if projected_hits:
                    zone = projected_hits[0]
                    observe(
                        f"ZONE_APPROACH_{zone['id']}",
                        "Approaching monitored airspace",
                        f"Projected entry into {zone['name']} within approximately {settings.monitored_zone_lookahead_minutes} minutes",
                    )
                projected_sua = self._sua_hits(
                    projected_lat, projected_lon, altitude, list(sua_areas or [])
                )
                if projected_sua and not regulatory_hits:
                    area = projected_sua[0]
                    designation = str(area.get("designation") or "UNKNOWN")
                    if area.get("category") == "PROHIBITED":
                        observe(
                            f"FAA_PROHIBITED_APPROACH_{area.get('id')}",
                            "Approaching prohibited airspace",
                            f"Projected entry into {designation} within approximately {settings.monitored_zone_lookahead_minutes} minutes",
                        )
                    else:
                        observe(
                            f"FAA_RESTRICTED_APPROACH_{area.get('id')}",
                            "Approaching restricted airspace",
                            f"Projected entry into {designation}; activation unverified",
                        )

            has_1228 = any(abs(freq - 122_800_000) <= 5_000 for freq in pilot_freqs)

            # Explicit communications whitelist gates. The public VATSIM feed
            # cannot prove voice contact, so automatic NORDO logic is only allowed
            # to proceed after ruling out all visible legitimate assignments:
            #   1) any active ARTCC frequency covering the aircraft,
            #   2) a matching CTAF/UNICOM/ATF within 50 NM, and
            #   3) an early release to 122.800 before entering an unstaffed FIR.
            active_artcc_candidates = [
                item
                for item in communications_candidates
                if item.get("facility") == "CTR"
                and item.get("coverage_confidence") == "HIGH"
                and item.get("frequencies_hz")
            ]
            active_artcc_frequency_matches = [
                item for item in active_artcc_candidates if self._frequency_matches(pilot_freqs, item)
            ]
            active_artcc_frequency_whitelisted = bool(active_artcc_frequency_matches)
            active_artcc_high_confidence = bool(active_artcc_candidates)

            # Nearby CTAF/UNICOM use is only treated as plausible for
            # terminal-profile traffic. A blanket 50-NM exemption would hide
            # high-altitude 122.800 mismatches whenever an en-route aircraft
            # passes near one of the many airports sharing that frequency.
            advisory_profile_plausible = bool(
                on_ground
                or (
                    altitude <= settings.advisory_frequency_whitelist_max_altitude_ft
                    and groundspeed <= settings.advisory_frequency_whitelist_max_groundspeed_kt
                )
            )
            advisory_frequency_matches = (
                self.airports.nearby_advisory_matches(
                    lat,
                    lon,
                    pilot_freqs,
                    settings.advisory_frequency_whitelist_radius_nm,
                    settings.frequency_match_tolerance_hz,
                )
                if advisory_profile_plausible
                else []
            )
            advisory_frequency_whitelisted = bool(advisory_frequency_matches)

            early_unicom_handoff_detail = self._early_unicom_handoff_exemption(
                lat=lat,
                lon=lon,
                heading=heading,
                groundspeed=groundspeed,
                has_1228=has_1228,
                on_ground=on_ground,
                communications_controller=communications_controller,
                coverage=coverage,
            )
            early_unicom_handoff = bool(early_unicom_handoff_detail)
            online_center_handoff_detail = (
                self._online_center_handoff_exemption(
                    lat=lat,
                    lon=lon,
                    heading=heading,
                    groundspeed=groundspeed,
                    pilot_frequencies=pilot_freqs,
                    on_ground=on_ground,
                    communications_controller=communications_controller,
                    coverage=coverage,
                )
                if communications_frequency_mismatch
                else None
            )
            online_center_handoff = bool(online_center_handoff_detail)
            if online_center_handoff or early_unicom_handoff:
                memory.comms_cooldown_until = max(
                    memory.comms_cooldown_until,
                    now + max(0, settings.communications_handoff_cooldown_seconds),
                )
                memory.comms_cooldown_reason = (
                    "ONLINE_CENTER_HANDOFF" if online_center_handoff else "EARLY_UNICOM_HANDOFF"
                )
            frequency_change_grace_active = bool(memory.comms_case_started is None and now < memory.frequency_change_grace_until)
            communications_cooldown_active = bool(now < memory.comms_cooldown_until)

            communications_exemption_active = bool(
                advisory_frequency_whitelisted
                or early_unicom_handoff
                or online_center_handoff
                or temporary_exemption_active
                or frequency_change_grace_active
                or communications_cooldown_active
            )
            effective_communications_frequency_mismatch = bool(
                communications_frequency_mismatch and not communications_exemption_active
            )
            if temporary_exemption_active:
                ownership_status = "TEMPORARY_OPERATOR_EXEMPTION"
            elif frequency_change_grace_active:
                ownership_status = "FREQUENCY_CHANGE_GRACE"
            elif communications_cooldown_active:
                ownership_status = "POST_HANDOFF_COOLDOWN"
            elif advisory_frequency_whitelisted:
                ownership_status = "ADVISORY_FREQUENCY_WHITELIST"
            elif online_center_handoff:
                ownership_status = "ONLINE_CENTER_HANDOFF"
            elif early_unicom_handoff:
                ownership_status = "EARLY_UNICOM_HANDOFF"

            monitor_only_frequencies = [
                {
                    "frequency": round(freq / 1_000_000, 3),
                    "role": self._non_controlling_frequency_label(freq),
                }
                for freq in pilot_freqs
                if self._non_controlling_frequency_label(freq) is not None
            ]
            atc_capable_reported_frequencies = [
                round(freq / 1_000_000, 3)
                for freq in pilot_freqs
                if self._non_controlling_frequency_label(freq) is None
            ]
            coverage_is_high = bool(
                communications_controller
                and (
                    not settings.nordo_require_high_confidence_coverage
                    or any(
                        item.get("coverage_confidence") == "HIGH"
                        for item in primary_communications_candidates
                    )
                )
            )
            if communications_controller and frequency_matches_any_controller and coverage_is_high:
                memory.last_controller_match = now

            controller_online_seconds = (
                min(
                    int(item.get("online_seconds") or 0)
                    for item in primary_communications_candidates
                )
                if primary_communications_candidates
                else 0
            )
            communications_controller_online_seconds = (
                max(
                    int(item.get("online_seconds") or 0)
                    for item in primary_communications_candidates
                )
                if primary_communications_candidates
                else 0
            )
            communications_controller_is_stable = bool(
                primary_communications_candidates
                and any(
                    int(item.get("online_seconds") or 0)
                    >= settings.communications_atc_min_online_seconds
                    for item in primary_communications_candidates
                )
            )
            controller_is_stable = bool(
                primary_communications_candidates
                and all(
                    int(item.get("online_seconds") or 0)
                    >= settings.auto_scramble_atc_min_online_seconds
                    for item in primary_communications_candidates
                )
            )
            communications_stabilization_remaining_seconds = max(
                0,
                settings.communications_atc_min_online_seconds
                - communications_controller_online_seconds,
            )
            auto_scramble_coverage_is_high = bool(
                primary_communications_candidates
                and (
                    not settings.auto_scramble_require_high_confidence_coverage
                    or all(
                        item.get("coverage_confidence") == "HIGH"
                        for item in primary_communications_candidates
                    )
                )
            )

            # Current-snapshot mismatch qualification. A newly staffed
            # controller is not allowed to create a new case until its live
            # coverage has remained online for the communications settling
            # window. This is the alert-storm guard for a Center login. An
            # already-running case may continue through a normal handoff to a
            # newly opened split position.
            mismatch_signal_now = bool(
                communications_controller
                and any(item.get("frequencies_hz") for item in communications_candidates)
                and effective_communications_frequency_mismatch
                and coverage_is_high
                and not declared_radio_limitation
                and not near_terminal_airport
                and altitude >= settings.frequency_mismatch_observe_min_altitude_ft
                and groundspeed >= settings.frequency_mismatch_observe_min_groundspeed_kt
                and (
                    not settings.frequency_mismatch_observe_require_ifr
                    or flight_rules == "I"
                )
                and (
                    not settings.auto_scramble_require_reported_radio
                    or bool(pilot_freqs)
                )
            )
            mismatch_now = bool(
                mismatch_signal_now
                and (
                    communications_controller_is_stable
                    or memory.comms_case_started is not None
                )
            )
            matched_now = bool(
                bool(pilot_freqs)
                and (
                    (
                        communications_controller
                        and frequency_matches_any_controller
                    )
                    or communications_exemption_active
                )
            )
            coverage_now = bool(
                communications_controller
                and any(item.get("frequencies_hz") for item in communications_candidates)
            )
            case_started_now = False
            prior_comms_status = memory.comms_case_status
            observed_mismatch_tick = tick_seconds if prior_comms_status == "MISMATCH" else 0.0

            # Compatibility with earlier in-memory timer keys and tests. On a
            # rolling deployment this also preserves an already-running timer
            # if the process object survives code reload under a local runner.
            legacy_starts = [
                memory.condition_started.get("verified_frequency_mismatch"),
                memory.condition_started.get("nordo_1228") if has_1228 else None,
            ]
            legacy_starts = [value for value in legacy_starts if value is not None]
            if mismatch_now and legacy_starts:
                legacy_started = min(float(value) for value in legacy_starts)
                if memory.comms_case_started is None or legacy_started < memory.comms_case_started:
                    memory.comms_case_started = legacy_started
                memory.comms_observed_accumulated = max(
                    memory.comms_observed_accumulated,
                    min(now - legacy_started, float(settings.max_observed_feed_tick_seconds) * 40),
                )
                memory.comms_last_mismatch = now
                memory.comms_case_status = "MISMATCH"
            legacy_auto = memory.condition_started.get("auto_scramble_frequency_mismatch")
            if (
                mismatch_now
                and legacy_auto is not None
                and controller_is_stable
                and auto_scramble_coverage_is_high
            ):
                memory.auto_scramble_accumulated = max(
                    memory.auto_scramble_accumulated,
                    now - float(legacy_auto),
                )

            if on_ground:
                if memory.comms_case_started is not None:
                    self._reset_communications_case(memory, "AIRCRAFT_ON_GROUND")
            elif temporary_exemption_active:
                if memory.comms_case_started is not None:
                    self._reset_communications_case(memory, "TEMPORARY_OPERATOR_EXEMPTION")
            elif advisory_frequency_whitelisted:
                if memory.comms_case_started is not None:
                    self._reset_communications_case(memory, "AIRPORT_ADVISORY_FREQUENCY_VERIFIED")
            elif online_center_handoff:
                if memory.comms_case_started is not None:
                    self._reset_communications_case(memory, "ONLINE_CENTER_HANDOFF")
            elif early_unicom_handoff:
                if memory.comms_case_started is not None:
                    self._reset_communications_case(memory, "EARLY_UNICOM_HANDOFF")
            elif communications_cooldown_active:
                if memory.comms_case_started is not None:
                    self._reset_communications_case(memory, "POST_HANDOFF_COOLDOWN")
            elif frequency_change_grace_active and memory.comms_case_started is None:
                pass
            elif mismatch_now:
                if memory.comms_case_started is None:
                    memory.comms_case_started = now
                    memory.auto_scramble_accumulated = 0.0
                    memory.comms_observed_accumulated = 0.0
                    memory.comms_scope_changes = 0
                    case_started_now = True
                elif prior_comms_status == "MISMATCH":
                    memory.comms_observed_accumulated += observed_mismatch_tick
                if (
                    communications_scope_key
                    and memory.comms_last_scope
                    and communications_scope_key != memory.comms_last_scope
                ):
                    memory.comms_scope_changes += 1
                if communications_scope_key:
                    memory.comms_last_scope = communications_scope_key
                memory.comms_last_mismatch = now
                memory.comms_gap_started = None
                memory.comms_match_streak = 0
                memory.comms_case_status = "MISMATCH"
                memory.comms_last_reset_reason = None
            elif matched_now and memory.comms_case_started is not None:
                # One transient matching snapshot can be caused by a handoff,
                # client reconnect, or monitored secondary radio. Require two
                # consecutive feed updates before clearing the case.
                memory.comms_match_streak += 1
                memory.comms_gap_started = None
                if memory.comms_match_streak >= max(1, settings.communications_clear_match_snapshots):
                    self._reset_communications_case(
                        memory,
                        f"{max(1, settings.communications_clear_match_snapshots)}_CONSECUTIVE_FREQUENCY_MATCHES",
                    )
                else:
                    memory.comms_case_status = "VERIFYING_FREQUENCY_MATCH"
            elif memory.comms_case_started is not None:
                # Preserve the case through brief sector gaps, split changes, or
                # missing transceiver snapshots. A gap longer than 60 seconds
                # closes the case rather than silently carrying it indefinitely.
                if memory.comms_gap_started is None:
                    memory.comms_gap_started = now
                memory.comms_match_streak = 0
                gap_seconds = now - memory.comms_gap_started
                if gap_seconds > settings.communications_case_gap_seconds:
                    self._reset_communications_case(memory, "LEFT_STAFFED_COVERAGE_OVER_60_SECONDS")
                else:
                    memory.comms_case_status = (
                        "RADIO_DATA_GAP" if coverage_now else "BRIEF_COVERAGE_GAP"
                    )

            frequency_mismatch_active = memory.comms_case_started is not None
            frequency_mismatch_current = bool(mismatch_now)
            # Test/rolling-upgrade compatibility: older in-memory cases tracked
            # only a wall-clock start. Seed once only when the immediately prior
            # snapshot was a mismatch; never seed after a real stale-feed gap.
            if (
                frequency_mismatch_active
                and memory.comms_observed_accumulated <= 0
                and memory.comms_last_mismatch is not None
                and now - memory.comms_last_mismatch <= 5
                and memory.comms_case_started is not None
            ):
                memory.comms_observed_accumulated = max(0.0, now - memory.comms_case_started)
            frequency_mismatch_duration = (
                max(0.0, memory.comms_observed_accumulated)
                if memory.comms_case_started is not None
                else 0.0
            )

            nordo_active = bool(
                frequency_mismatch_active
                and has_1228
                and active_artcc_high_confidence
                and not communications_exemption_active
                and not active_artcc_frequency_whitelisted
                and not declared_radio_limitation
                and not near_terminal_airport
                and altitude >= settings.nordo_min_altitude_ft
                and groundspeed >= settings.nordo_min_groundspeed_kt
                and (not settings.nordo_require_ifr or flight_rules == "I")
            )
            # Use the persistent communications case clock so a Denver split or
            # normal Center handoff cannot erase an already developing NORDO.
            nordo_duration = frequency_mismatch_duration if nordo_active else 0.0
            nordo_evidence: dict[str, Any] | None = None
            nordo_watch: dict[str, Any] | None = None
            recently_matched_controller = bool(
                memory.last_controller_match is not None
                and now - memory.last_controller_match <= settings.nordo_previous_match_window_seconds
            )
            investigate_threshold = (
                settings.nordo_investigate_after_switch_seconds
                if recently_matched_controller
                else settings.nordo_investigate_seconds
            )
            if nordo_duration >= investigate_threshold:
                nordo_watch = {
                    "id": f"NORDO-{callsign}",
                    "level": "orange",
                    "title": "POSSIBLE NORDO — INVESTIGATE",
                    "duration_seconds": int(nordo_duration),
                    "controller": communications_controller_label,
                    "confidence": 78 if recently_matched_controller else 70,
                    "detail": (
                        f"122.800 reported with no radio matching {communications_controller_label} for "
                        f"{int(nordo_duration // 60)}m"
                        + (" after previously matching the controller frequency" if recently_matched_controller else "")
                    ),
                }
                nordo_evidence = {
                    "code": "NORDO_1228",
                    "label": "Persistent possible NORDO",
                    "points": 28,
                    "level": "orange",
                    "detail": nordo_watch["detail"],
                }
            elif nordo_duration >= settings.nordo_advisory_seconds:
                nordo_watch = {
                    "id": f"NORDO-{callsign}",
                    "level": "yellow",
                    "title": "NORDO WATCH",
                    "duration_seconds": int(nordo_duration),
                    "controller": communications_controller_label,
                    "confidence": 52,
                    "detail": (
                        f"122.800 reported with no radio matching {communications_controller_label} for "
                        f"{int(nordo_duration // 60)}m; monitoring for persistence"
                    ),
                }
                nordo_evidence = {
                    "code": "NORDO_1228",
                    "label": "Persistent frequency mismatch",
                    "points": 12,
                    "level": "yellow",
                    "detail": nordo_watch["detail"],
                }
            elif online_center_handoff:
                detail = online_center_handoff_detail or {}
                matched = " / ".join(f"{value:.3f}" for value in (detail.get("matched_frequencies") or [])) or "reported frequency"
                observe(
                    "ONLINE_CENTER_HANDOFF",
                    "Early handoff to staffed downstream Center verified",
                    (
                        f"No alert: {matched} matches {detail.get('downstream_controller', 'the downstream Center')} "
                        f"and the projected track enters {detail.get('downstream_artcc', 'the neighboring ARTCC')} "
                        f"within {detail.get('downstream_entry_distance_nm', '—')} NM "
                        f"(boundary crossing approximately {detail.get('boundary_distance_nm', '—')} NM ahead)"
                    ),
                )
            elif has_1228:
                if advisory_frequency_whitelisted:
                    nearest_advisory = advisory_frequency_matches[0]
                    observe(
                        "ADVISORY_FREQUENCY_WHITELIST",
                        "Nearby CTAF / UNICOM frequency verified",
                        (
                            f"No alert: {nearest_advisory['frequency']:.3f} is published as "
                            f"{nearest_advisory['type']} for {nearest_advisory['airport']} "
                            f"{nearest_advisory['distance_nm']:.1f} NM away"
                        ),
                    )
                elif early_unicom_handoff:
                    detail = early_unicom_handoff_detail or {}
                    observe(
                        "EARLY_UNICOM_HANDOFF",
                        "Likely early handoff to 122.800",
                        (
                            f"No alert: projected to leave the active ARTCC in approximately "
                            f"{detail.get('lookahead_minutes', '—')} minutes / {detail.get('lookahead_nm', '—')} NM, "
                            "with no staffed downstream ARTCC detected"
                        ),
                    )
                elif not communications_controller:
                    observe(
                        "1228_OUTSIDE_COVERAGE",
                        "122.800 outside confirmed ATC alert coverage",
                        "No alert: a live controller/transceiver coverage set could not be established",
                    )
                elif not coverage_is_high:
                    observe(
                        "1228_LOW_CONFIDENCE_COVERAGE",
                        "122.800 without high-confidence live coverage",
                        "No alert: the active coverage set is not sufficiently precise for communications-mismatch monitoring",
                    )
                elif not active_artcc_high_confidence:
                    observe(
                        "1228_NO_EXACT_ARTCC",
                        "122.800 without exact active ARTCC coverage",
                        "No NORDO alert: high-confidence live ARTCC boundary and transceiver coverage is required",
                    )
                elif mismatch_signal_now and not communications_controller_is_stable:
                    observe(
                        "ATC_ACTIVATION_GRACE",
                        "ATC recently online — communications grace period",
                        (
                            f"{communications_controller_label} has just become active; new NORDO/watch cases are held "
                            f"for another {int(communications_stabilization_remaining_seconds // 60)}m "
                            f"{int(communications_stabilization_remaining_seconds % 60):02d}s so pilots can establish contact"
                        ),
                    )
                elif near_terminal_airport:
                    observe(
                        "1228_TERMINAL_AREA",
                        "122.800 near departure or destination",
                        "No alert: terminal-area UNICOM/CTAF use is plausible",
                    )
                elif declared_radio_limitation:
                    observe(
                        "1228_DECLARED_LIMITATION",
                        "Declared radio limitation",
                        "No alert: flight-plan remarks identify a voice/radio limitation",
                    )
                elif altitude < settings.nordo_min_altitude_ft or groundspeed < settings.nordo_min_groundspeed_kt:
                    observe(
                        "1228_LOW_ALTITUDE",
                        "122.800 below en-route alert criteria",
                        "No alert: aircraft is below the configured en-route altitude/speed threshold",
                    )
                elif settings.nordo_require_ifr and flight_rules != "I":
                    observe(
                        "1228_VFR",
                        "VFR aircraft monitoring 122.800",
                        "No alert: VFR/UNICOM use alone is not intercept evidence",
                    )

            strict_auto_case = bool(
                frequency_mismatch_active
                and altitude >= settings.auto_scramble_min_altitude_ft
                and groundspeed >= settings.auto_scramble_min_groundspeed_kt
                and (not settings.auto_scramble_require_ifr or flight_rules == "I")
                and not declared_radio_limitation
                and not near_terminal_airport
                and not communications_exemption_active
                and (not has_1228 or active_artcc_high_confidence)
            )
            auto_scramble_eligible = bool(
                mismatch_now
                and strict_auto_case
                and controller_is_stable
                and auto_scramble_coverage_is_high
            )
            if auto_scramble_eligible and not case_started_now:
                memory.auto_scramble_accumulated += observed_mismatch_tick
            auto_scramble_mismatch_duration = max(0.0, memory.auto_scramble_accumulated)
            observe_remaining_seconds = max(
                0,
                settings.frequency_mismatch_observe_seconds
                - int(frequency_mismatch_duration),
            )
            mismatch_remaining_seconds = max(
                0,
                settings.auto_scramble_frequency_mismatch_seconds
                - int(auto_scramble_mismatch_duration),
            )
            stabilization_remaining_seconds = max(
                0,
                settings.auto_scramble_atc_min_online_seconds - controller_online_seconds,
            )

            if (
                mismatch_signal_now
                and not communications_controller_is_stable
                and memory.comms_case_started is None
                and not has_1228
            ):
                observe(
                    "ATC_ACTIVATION_GRACE",
                    "ATC recently online — communications grace period",
                    (
                        f"{communications_controller_label} has just become active; new wrong-frequency cases are held "
                        f"for another {int(communications_stabilization_remaining_seconds // 60)}m "
                        f"{int(communications_stabilization_remaining_seconds % 60):02d}s"
                    ),
                )

            pre_scramble_case_id: str | None = None
            if frequency_mismatch_active and memory.comms_case_started is not None:
                pre_scramble_case_id = hashlib.sha1(
                    (
                        f"{callsign}|{session_key}|"
                        f"{int(memory.comms_case_started * 1000)}"
                    ).encode()
                ).hexdigest()[:16]
            pre_scramble_denial = (
                self.pre_scramble_denials.get(pre_scramble_case_id)
                if pre_scramble_case_id
                else None
            )

            auto_scramble_flag: dict[str, Any] | None = None
            if (
                frequency_mismatch_active
                and strict_auto_case
                and pre_scramble_denial is None
                and auto_scramble_mismatch_duration >= settings.auto_scramble_frequency_mismatch_seconds
            ):
                auto_scramble_flag = {
                    "active": True,
                    "controller": communications_controller_label,
                    "controller_online_seconds": controller_online_seconds,
                    "mismatch_seconds": int(frequency_mismatch_duration),
                    "eligible_mismatch_seconds": int(auto_scramble_mismatch_duration),
                    "title": "AUTO SCRAMBLE FLAG",
                    "detail": (
                        f"No reported pilot radio matches {communications_controller_label} after "
                        f"{int(auto_scramble_mismatch_duration // 60)}m of eligible mismatch time; "
                        f"total verified mismatch {int(frequency_mismatch_duration // 60)}m "
                        f"{int(frequency_mismatch_duration % 60):02d}s and ATC online "
                        f"{int(controller_online_seconds // 60)}m"
                    ),
                }
                add(
                    "AUTO_SCRAMBLE_FREQ_MISMATCH",
                    "Automatic scramble flag — persistent ATC frequency mismatch",
                    80,
                    "red",
                    auto_scramble_flag["detail"],
                    critical=True,
                )
            elif (
                frequency_mismatch_active
                and strict_auto_case
                and pre_scramble_denial is not None
                and auto_scramble_mismatch_duration >= settings.auto_scramble_frequency_mismatch_seconds
            ):
                observe(
                    "PRE_SCRAMBLE_DENIED",
                    "Automatic scramble escalation denied by operator",
                    (
                        f"Shared operator denial by {pre_scramble_denial.get('denied_by', 'console')} "
                        f"remains active for this communications case; monitoring continues"
                    ),
                )
            elif frequency_mismatch_active and frequency_mismatch_current and not controller_is_stable:
                observe(
                    "ATC_RECENTLY_ONLINE",
                    "Verified frequency mismatch — ATC stabilization pending",
                    (
                        f"Wrong-frequency timer {int(frequency_mismatch_duration // 60)}m "
                        f"{int(frequency_mismatch_duration % 60):02d}s; automatic-flag timer begins "
                        f"after another {int(stabilization_remaining_seconds // 60)}m "
                        f"{int(stabilization_remaining_seconds % 60):02d}s of continuous "
                        f"{communications_controller_label} uptime"
                    ),
                )
            elif frequency_mismatch_active:
                observe(
                    "ATC_FREQ_MISMATCH_TIMER",
                    "Verified ATC frequency mismatch timer",
                    (
                        f"Wrong-frequency timer {int(frequency_mismatch_duration // 60)}m "
                        f"{int(frequency_mismatch_duration % 60):02d}s; eligible automatic-flag timer "
                        f"{int(auto_scramble_mismatch_duration // 60)}m "
                        f"{int(auto_scramble_mismatch_duration % 60):02d}s; flag in "
                        f"{int(mismatch_remaining_seconds // 60)}m "
                        f"{int(mismatch_remaining_seconds % 60):02d}s if unchanged"
                    ),
                )

            pre_scramble_warning: dict[str, Any] | None = None
            if (
                pre_scramble_case_id
                and pre_scramble_denial is None
                and auto_scramble_flag is None
                and auto_scramble_eligible
                and 0 < mismatch_remaining_seconds <= max(1, settings.pre_scramble_warning_seconds)
            ):
                pre_scramble_warning = {
                    "active": True,
                    "alert_id": self._alert_id(callsign),
                    "case_id": pre_scramble_case_id,
                    "callsign": callsign,
                    "controller": communications_controller_label,
                    "remaining_seconds": int(mismatch_remaining_seconds),
                    "warning_seconds": max(1, int(settings.pre_scramble_warning_seconds)),
                    "threshold_seconds": int(settings.auto_scramble_frequency_mismatch_seconds),
                    "deadline_epoch": now + float(mismatch_remaining_seconds),
                    "title": "AUTOMATIC SCRAMBLE ALERT PENDING",
                    "detail": (
                        f"Persistent verified ATC frequency mismatch is within "
                        f"{int(mismatch_remaining_seconds)} seconds of automatic escalation"
                    ),
                }

            # Put a developing mismatch in the watch rail after two stable feed
            # snapshots. This is an observe flag only and does not create an
            # intercept recommendation or sound the scramble alarm.
            if (
                frequency_mismatch_active
                and frequency_mismatch_duration >= settings.frequency_mismatch_observe_seconds
                and nordo_watch is None
            ):
                possible_nordo = has_1228
                nordo_watch = {
                    "id": f"COMMS-{callsign}",
                    "kind": "FREQUENCY_MISMATCH_OBSERVE",
                    "level": "yellow",
                    "title": (
                        "POSSIBLE NORDO — OBSERVE"
                        if possible_nordo
                        else "ATC FREQUENCY MISMATCH — OBSERVE"
                    ),
                    "duration_seconds": int(frequency_mismatch_duration),
                    "controller": communications_controller_label,
                    "confidence": 40 if possible_nordo else 32,
                    "detail": (
                        f"No reported radio matches {communications_controller_label} for "
                        f"{int(frequency_mismatch_duration // 60)}m "
                        f"{int(frequency_mismatch_duration % 60):02d}s"
                        + ("; pilot is reporting 122.800" if possible_nordo else "")
                    ),
                }

            if manual_nordo:
                nordo_watch = {
                    "id": f"MANUAL-NORDO-{callsign}",
                    "kind": "MANUAL_NORDO",
                    "level": "red",
                    "title": "MANUAL NORDO",
                    "duration_seconds": manual_nordo_seconds,
                    "controller": communications_controller_label or "OPERATOR CONFIRMED",
                    "confidence": 99,
                    "detail": "Operator manually designated this aircraft NORDO; automatic frequency and ownership gates are bypassed until cleared",
                }

            missing_radio_active = bool(
                settings.enable_missing_radio_alert
                and nearby_controller
                and coverage_selection_reason == "UNAMBIGUOUS_TRANSCEIVER"
                and flight_rules == "I"
                and altitude >= 10000
                and not pilot_freqs
                and not declared_radio_limitation
            )
            missing_radio_duration = self._duration(
                memory, "missing_radio", missing_radio_active, now
            )
            if missing_radio_duration >= settings.missing_radio_seconds:
                observe(
                    "NO_RADIO_DATA",
                    "No reported pilot radio data",
                    f"No transceiver reported under {nearby_controller['callsign']} for {int(missing_radio_duration // 60)}m; not alerting without corroboration",
                )

            assigned_squawk = str(flight_plan.get("assigned_transponder") or "").strip().zfill(4)
            mismatch_active = bool(
                flight_rules == "I"
                and altitude >= settings.min_airborne_altitude_ft
                and len(assigned_squawk) == 4
                and assigned_squawk.isdigit()
                and assigned_squawk != "0000"
                and squawk.isdigit()
                and squawk != assigned_squawk
                and squawk not in settings.whitelisted_squawk_set
                and squawk not in EMERGENCY_SQUAWKS
                and squawk not in INTERCEPT_SQUAWKS
            )
            mismatch_duration = self._duration(
                memory, "assigned_squawk_mismatch", mismatch_active, now
            )
            if mismatch_duration >= settings.assigned_squawk_mismatch_seconds:
                observe(
                    "ASSIGNED_SQUAWK_MISMATCH",
                    "Assigned squawk mismatch",
                    f"Current {squawk}; flight-plan assignment {assigned_squawk}; not intercept evidence by itself",
                )

            route_deviation = None
            if dep_info and arr_info and flight_rules == "I" and altitude >= 10000:
                dep_distance = departure_distance if departure_distance is not None else haversine_nm(lat, lon, dep_info[0], dep_info[1])
                destination_distance = destination_distance if destination_distance is not None else haversine_nm(lat, lon, arr_info[0], arr_info[1])
                if dep_distance > 100 and destination_distance > 100:
                    route_deviation = point_to_great_circle_segment_nm(
                        (lat, lon), (dep_info[0], dep_info[1]), (arr_info[0], arr_info[1])
                    )
                    active = route_deviation >= settings.route_deviation_nm
                    duration = self._duration(memory, "route_corridor", active, now)
                    if duration >= settings.route_deviation_seconds:
                        if navigation_exemption:
                            observe(
                                "MISSION_ROUTE_EXEMPT",
                                "Mission route deviation suppressed",
                                f"{navigation_exemption} exemption; {route_deviation:.0f} NM from the straight endpoint corridor",
                            )
                        elif settings.enable_route_deviation_alerts and not settings.navigation_anomalies_observation_only:
                            add(
                                "ROUTE_CORRIDOR",
                                "Broad route-corridor deviation",
                                30,
                                "orange",
                                f"{route_deviation:.0f} NM from departure-arrival corridor",
                            )
                        else:
                            observe(
                                "ROUTE_CORRIDOR",
                                "Broad route-corridor deviation",
                                f"{route_deviation:.0f} NM from straight departure-arrival corridor; observation only because it is not the filed airway route",
                            )

                if destination_distance <= settings.destination_arm_distance_nm:
                    if memory.min_destination_distance is None:
                        memory.min_destination_distance = destination_distance
                    else:
                        memory.min_destination_distance = min(
                            memory.min_destination_distance, destination_distance
                        )
                destination_overshoot_active = bool(
                    memory.min_destination_distance is not None
                    and destination_distance
                    > memory.min_destination_distance + settings.destination_overshoot_nm
                    and altitude > 8000
                    and groundspeed > 150
                )
                if destination_overshoot_active:
                    if navigation_exemption:
                        observe(
                            "MISSION_OVERSHOOT_EXEMPT",
                            "Mission destination overshoot suppressed",
                            f"{navigation_exemption} exemption; now {destination_distance:.0f} NM from {arr}",
                        )
                    elif settings.navigation_anomalies_observation_only:
                        observe(
                            "DEST_OVERSHOOT",
                            "Destination overshoot",
                            f"Now {destination_distance:.0f} NM from {arr}; closest approach {memory.min_destination_distance:.0f} NM; observation only because diversion, holding, missed approach, or amended clearance cannot be distinguished",
                        )
                    else:
                        add(
                            "DEST_OVERSHOOT",
                            "Destination overshoot",
                            45,
                            "orange",
                            f"Now {destination_distance:.0f} NM from {arr}; closest approach {memory.min_destination_distance:.0f} NM",
                        )
                elif destination_distance <= 100 and altitude >= 24000 and not navigation_exemption:
                    observe(
                        "MISSED_DESCENT",
                        "Expected descent not apparent",
                        f"{destination_distance:.0f} NM from {arr} at FL{altitude // 100:03d}; monitoring only",
                    )

            if departure_turn_suppressed:
                # Discard normal SID/vector/procedure-turn history so a 180°
                # departure reversal cannot mature into an orbit/intercept case.
                memory.recent_positions = memory.recent_positions[-1:]
            orbit_metrics = self._orbit_metrics(memory, now)
            orbit_detected = bool(
                orbit_metrics["detected"]
                and not departure_turn_suppressed
                and not on_ground
                and altitude >= settings.orbit_detection_min_altitude_ft
                and groundspeed >= settings.orbit_detection_min_groundspeed_kt
            )
            orbit_corroborated_by_nordo = bool(
                auto_scramble_mismatch_duration >= settings.orbit_nordo_corroboration_seconds
                or nordo_duration >= settings.nordo_advisory_seconds
            )
            if orbit_detected:
                orbit_detail = (
                    f"Approximately {orbit_metrics['turn_degrees']:.0f}° total / "
                    f"{abs(float(orbit_metrics.get('net_turn_degrees') or 0)):.0f}° same-direction turn over "
                    f"{int(float(orbit_metrics['span_seconds']) // 60)}m; remained within "
                    f"{orbit_metrics['radius_nm']:.0f} NM"
                )
                if navigation_exemption:
                    observe(
                        "MISSION_ORBIT_EXEMPT",
                        "Mission orbit/loitering suppressed",
                        f"{navigation_exemption} exemption; {orbit_detail}",
                    )
                elif orbit_corroborated_by_nordo:
                    add(
                        "UNRESPONSIVE_ORBIT",
                        "Repeated orbit with communications mismatch",
                        65,
                        "red",
                        orbit_detail + "; persistent ATC-frequency mismatch is also present",
                        critical=True,
                    )
                else:
                    observe(
                        "REPEATED_ORBIT",
                        "Repeated orbit / no route progress",
                        orbit_detail + "; no communications mismatch corroboration",
                    )

            stable_seconds = now - memory.last_maneuver
            if stable_seconds >= 3600 and altitude >= 18000:
                if navigation_exemption:
                    observe(
                        "MISSION_STABLE_EXEMPT",
                        "Mission loitering observation suppressed",
                        f"{navigation_exemption} exemption; stable track for {int(stable_seconds // 60)}m",
                    )
                else:
                    observe(
                        "STABLE_TRACK",
                        "Extended unchanged track",
                        f"No major heading/altitude change for {int(stable_seconds // 60)}m; monitoring only",
                    )

            # A 122.800 mismatch is a corroborating signal, not a standalone
            # intercept alert. Promote it only when a separate evidence category
            # is already present (for example navigation or protected airspace).
            existing_categories = {item["category"] for item in reasons}
            if nordo_evidence:
                if existing_categories:
                    add(
                        nordo_evidence["code"],
                        nordo_evidence["label"],
                        nordo_evidence["points"],
                        nordo_evidence["level"],
                        nordo_evidence["detail"],
                    )
                else:
                    observe(
                        nordo_evidence["code"],
                        nordo_evidence["label"],
                        nordo_evidence["detail"] + "; no independent intercept indicator present",
                    )

            # Squawk 7777 is reserved by this virtual operation for an aircraft
            # actively responding to an intercept. It is rendered as an
            # operational track and does not generate a second anomaly alert.
            fighter_track = squawk in INTERCEPT_SQUAWKS
            final_aircraft_category = aircraft_category(aircraft_type, fighter_track)
            if fighter_track and not manual_nordo:
                for item in reasons:
                    observe(item["code"], item["label"], item["detail"])
                reasons = []
                score = 0
                severity = "green"
                critical_trigger = False

            evidence_categories = {item["category"] for item in reasons}
            candidate_basis = bool(
                reasons
                and (
                    critical_trigger
                    or (
                        len(evidence_categories) >= settings.alert_min_independent_categories
                        and score >= 45
                    )
                )
            )

            if critical_trigger:
                confidence = 99 if any(item["points"] >= 100 for item in reasons) else 95
            elif candidate_basis:
                confidence = min(
                    94,
                    int(round(35 + score * 0.60 + max(0, len(evidence_categories) - 1) * 12)),
                )
            else:
                confidence = min(59, int(round(20 + score * 0.40))) if reasons else 0

            intercept_candidate = bool(
                candidate_basis
                and (critical_trigger or confidence >= settings.alert_queue_min_confidence)
            )

            if intercept_candidate and confidence >= settings.scramble_alarm_confidence:
                severity = "red"
            elif intercept_candidate:
                severity = "orange"
            else:
                # Keep weak or single-source observations off the alert map and
                # out of the Active Alert Queue. They remain visible in track detail.
                for item in reasons:
                    observe(
                        item["code"],
                        item["label"],
                        item["detail"] + "; insufficient independent evidence for an intercept alert",
                    )
                reasons = []
                score = 0
                confidence = 0
                severity = "green"

            recommendation = recommend_base(
                lat,
                lon,
                target_heading=heading,
                target_speed_kt=groundspeed,
                target_altitude_ft=altitude,
                target_region=operational_region(lat, lon),
            ) if intercept_candidate else None
            primary_code = reasons[0]["code"] if reasons else "NORMAL"
            alert_id = self._alert_id(callsign, primary_code)

            context = []
            if squawk in settings.whitelisted_squawk_set:
                context.append(f"Squawk {squawk} is whitelisted for squawk-anomaly scoring")
            if declared_radio_limitation:
                context.append("Flight-plan remarks declare a radio/voice limitation")
            if manual_nordo:
                context.append("Operator manually designated this aircraft NORDO; automatic detection gates are bypassed until the designation is cleared")
            if fighter_track:
                context.append("Squawk 7777 indicates an active interceptor track and is shown in yellow")
            if blackjack_unit:
                context.append(
                    "Likely USCG NCRAD BLACKJACK helicopter based on callsign/remarks, helicopter type, and proximity to KDCA; VATSIM identity is not independently verified"
                )
            elif vsoa_flight:
                context.append(
                    f"Flight-plan remarks contain the recognized VSOA marker {vsoa_marker}"
                )
            if navigation_exemption:
                context.append(
                    f"{navigation_exemption} mission exemption suppresses orbit, loitering, route-deviation, and destination-overshoot scoring only"
                )
            if advisory_frequency_whitelisted and advisory_frequency_matches:
                advisory = advisory_frequency_matches[0]
                context.append(
                    f"Reported {advisory['frequency']:.3f} matches {advisory['type']} at {advisory['airport']} {advisory['distance_nm']:.1f} NM away; automatic NORDO suppressed"
                )
            if online_center_handoff:
                detail = online_center_handoff_detail or {}
                context.append(
                    f"Reported radio matches online {detail.get('downstream_controller', 'downstream Center')} and the aircraft is projected to enter {detail.get('downstream_artcc', 'the neighboring ARTCC')} within {detail.get('downstream_entry_distance_nm', '—')} NM; frequency-mismatch alert suppressed"
                )
            if early_unicom_handoff:
                context.append(
                    "122.800 is consistent with an early handoff before an unstaffed downstream ARTCC; automatic NORDO suppressed"
                )
            if active_artcc_frequency_whitelisted:
                context.append(
                    "At least one reported aircraft radio matches an active high-confidence ARTCC frequency"
                )
            if communications_selection_reason == "MULTI_POSITION_MISMATCH":
                context.append(
                    "Multiple live ATC positions overlap, but none of their published frequencies matches the aircraft; communications timer remains active"
                )
            elif communications_controller:
                context.append(
                    f"ATC communications coverage confirmed by live {communications_controller['facility']} transceiver: "
                    f"{communications_controller['distance_nm']:.0f} NM of {communications_controller['coverage_radius_nm']:.0f} NM estimated reach"
                )
                context.append(
                    f"{communications_controller_label} continuously online for at least approximately {controller_online_seconds // 60} minutes"
                )

            display = {
                "callsign": callsign,
                "cid": pilot.get("cid"),
                "logon_time": pilot.get("logon_time"),
                "lat": lat,
                "lon": lon,
                "altitude": altitude,
                "groundspeed": groundspeed,
                "heading": heading,
                "squawk": squawk,
                "on_ground": on_ground,
                "ground_status": ground_status,
                "nearest_airport_distance_nm": round(nearest_airport_distance, 1) if nearest_airport_distance is not None else None,
                "display_class": "fighter" if fighter_track else "standard",
                "active_intercept": fighter_track,
                "track_color": "red" if manual_nordo else ("yellow" if fighter_track else severity),
                "operational_status": "ACTIVE INTERCEPT" if fighter_track else None,
                "intercept_assignment": None,
                "active_interceptors": [],
                "vsoa": vsoa_flight,
                "vsoa_label": vsoa_marker,
                "blackjack": blackjack_unit,
                "special_unit": "USCG NCRAD BLACKJACK" if blackjack_unit else None,
                "special_mission": "ROTARY WING AIR INTERCEPT" if blackjack_unit else None,
                "home_station": "KDCA" if blackjack_unit else None,
                "nordo_watch": nordo_watch,
                "manual_nordo": bool(manual_nordo),
                "manual_nordo_marked_at": manual_nordo.get("marked_at") if manual_nordo else None,
                "manual_nordo_seconds": manual_nordo_seconds,
                "region": operational_region(lat, lon),
                "assigned_squawk": assigned_squawk if assigned_squawk != "0000" else None,
                "aircraft": aircraft,
                "aircraft_type": aircraft_type,
                "aircraft_category": final_aircraft_category,
                "is_helicopter": helicopter_flight,
                "navigation_exempt": bool(navigation_exemption),
                "navigation_exemption_reason": navigation_exemption,
                "orbit_detected": orbit_detected,
                "orbit_metrics": orbit_metrics,
                "departure_turn_suppressed": departure_turn_suppressed,
                "track_age_seconds": round(track_age_seconds, 1),
                "flight_rules": flight_rules,
                "departure": dep,
                "arrival": arr,
                "departure_lat": round(dep_info[0], 5) if dep_info else None,
                "departure_lon": round(dep_info[1], 5) if dep_info else None,
                "arrival_lat": round(arr_info[0], 5) if arr_info else None,
                "arrival_lon": round(arr_info[1], 5) if arr_info else None,
                "route": flight_plan.get("route") or "",
                "remarks": flight_plan.get("remarks") or "",
                "frequencies": [round(value / 1_000_000, 3) for value in pilot_freqs],
                "monitor_only_frequencies": monitor_only_frequencies,
                "atc_capable_reported_frequencies": atc_capable_reported_frequencies,
                "center": communications_controller_label,
                "controller_facility": communications_controller.get("facility") if communications_controller else None,
                "controller_online_seconds": controller_online_seconds if communications_controller else None,
                "atc_frequency_match": frequency_matches_any_controller,
                "active_artcc_frequency_match": active_artcc_frequency_whitelisted,
                "active_artcc_high_confidence": active_artcc_high_confidence,
                "active_artcc_callsigns": sorted({
                    str(item.get("callsign") or "")
                    for item in active_artcc_candidates
                    if item.get("callsign")
                }),
                "active_artcc_frequencies": sorted({
                    frequency
                    for item in active_artcc_candidates
                    for frequency in (item.get("frequencies") or [])
                }),
                "advisory_frequency_whitelisted": advisory_frequency_whitelisted,
                "advisory_frequency_matches": advisory_frequency_matches[:6],
                "early_unicom_handoff": early_unicom_handoff,
                "early_unicom_handoff_detail": early_unicom_handoff_detail,
                "online_center_handoff": online_center_handoff,
                "online_center_handoff_detail": online_center_handoff_detail,
                "temporary_exemption_active": temporary_exemption_active,
                "temporary_exemption_detail": dict(temporary_exemption) if temporary_exemption else None,
                "frequency_change_grace_active": frequency_change_grace_active,
                "frequency_change_grace_remaining_seconds": max(0, int(memory.frequency_change_grace_until - now)),
                "communications_cooldown_active": communications_cooldown_active,
                "communications_cooldown_reason": memory.comms_cooldown_reason,
                "communications_cooldown_remaining_seconds": max(0, int(memory.comms_cooldown_until - now)),
                "communications_clear_match_snapshots": max(1, settings.communications_clear_match_snapshots),
                "nordo_gate_ready": bool(
                    active_artcc_high_confidence
                    and communications_controller_is_stable
                    and has_1228
                    and not communications_exemption_active
                    and not active_artcc_frequency_whitelisted
                    and not declared_radio_limitation
                ),
                "frequency_mismatch_active": frequency_mismatch_active,
                "frequency_mismatch_current": frequency_mismatch_current,
                "frequency_mismatch_case_status": memory.comms_case_status,
                "frequency_mismatch_seconds": int(frequency_mismatch_duration),
                "frequency_mismatch_scope_changes": memory.comms_scope_changes,
                "frequency_mismatch_last_reset_reason": memory.comms_last_reset_reason,
                "frequency_mismatch_observe_threshold_seconds": settings.frequency_mismatch_observe_seconds,
                "frequency_mismatch_observe_remaining_seconds": observe_remaining_seconds,
                "frequency_mismatch_threshold_seconds": settings.auto_scramble_frequency_mismatch_seconds,
                "frequency_mismatch_remaining_seconds": mismatch_remaining_seconds,
                "auto_scramble_mismatch_seconds": int(auto_scramble_mismatch_duration),
                "auto_scramble_eligible": auto_scramble_eligible,
                "communications_watch_controller_stable": communications_controller_is_stable,
                "communications_watch_stabilization_remaining_seconds": communications_stabilization_remaining_seconds,
                "frequency_mismatch_controller_stable": controller_is_stable,
                "frequency_mismatch_stabilization_remaining_seconds": stabilization_remaining_seconds,
                "auto_scramble_flag": auto_scramble_flag,
                "pre_scramble_case_id": pre_scramble_case_id,
                "pre_scramble_warning": pre_scramble_warning,
                "pre_scramble_denied": bool(pre_scramble_denial),
                "pre_scramble_denial": dict(pre_scramble_denial) if pre_scramble_denial else None,
                "center_frequencies": sorted({
                    frequency
                    for item in primary_communications_candidates
                    for frequency in (item.get("frequencies") or [])
                }),
                "center_boundary_source": (communications_controller or {}).get("source"),
                "coverage_confidence": (communications_controller or {}).get("coverage_confidence"),
                "coverage_confidence_basis": (communications_controller or {}).get("coverage_confidence_basis"),
                "coverage_selection_reason": communications_selection_reason,
                "nordo_candidate_active": nordo_active,
                "nordo_candidate_seconds": int(nordo_duration),
                "near_terminal_exemption": near_terminal_airport,
                "ownership_status": ownership_status,
                "coverage_distance_nm": round(communications_controller["distance_nm"], 1) if communications_controller else None,
                "coverage_radius_nm": round(communications_controller["coverage_radius_nm"], 1) if communications_controller else None,
                "controller_candidates": [
                    {
                        "callsign": item.get("callsign"),
                        "facility": item.get("facility"),
                        "frequencies": item.get("frequencies") or [],
                        "distance_nm": round(item.get("distance_nm") or 0, 1),
                        "coverage_radius_nm": round(item.get("coverage_radius_nm") or 0, 1),
                        "match_quality": item.get("match_quality"),
                        "coverage_confidence": item.get("coverage_confidence"),
                        "coverage_confidence_basis": item.get("coverage_confidence_basis"),
                    }
                    for item in communications_candidates[:4]
                ],
                "route_deviation_nm": round(route_deviation, 1) if route_deviation is not None else None,
                "departure_distance_nm": round(departure_distance, 1) if departure_distance is not None else None,
                "destination_distance_nm": round(destination_distance, 1) if destination_distance is not None else None,
                "severity": severity,
                "score": score,
                "confidence": confidence if reasons else 0,
                "requires_ack": bool(
                    reasons
                    and confidence >= settings.scramble_alarm_confidence
                    and alert_id not in self.acknowledged
                ),
                "reasons": reasons,
                "observations": observations,
                "intercept_candidate": intercept_candidate,
                "evidence_categories": sorted(evidence_categories),
                "context": context,
                "recommended_base": recommendation,
                "alert_id": alert_id if reasons else None,
            }
            display_pilots.append(display)

            if reasons:
                active_alert_ids.add(alert_id)

            if reasons and alert_id not in self.dismissed:
                alerts.append(
                    {
                        "id": alert_id,
                        "callsign": callsign,
                        "severity": severity,
                        "score": score,
                        "confidence": confidence,
                        "title": reasons[0]["label"],
                        "reasons": reasons,
                        "observations": observations,
                        "nordo_watch": nordo_watch,
                        "manual_nordo": bool(manual_nordo),
                        "manual_nordo_marked_at": manual_nordo.get("marked_at") if manual_nordo else None,
                        "manual_nordo_seconds": manual_nordo_seconds,
                        "evidence_categories": sorted(evidence_categories),
                        "context": context,
                        "aircraft": aircraft,
                        "altitude": altitude,
                        "groundspeed": groundspeed,
                        "heading": heading,
                        "lat": lat,
                        "lon": lon,
                        "center": display["center"],
                        "frequencies": display["frequencies"],
                        "departure": dep,
                        "arrival": arr,
                        "recommended_base": recommendation,
                        "acknowledged": alert_id in self.acknowledged,
                        "requires_ack": bool(
                            confidence >= settings.scramble_alarm_confidence
                            and alert_id not in self.acknowledged
                        ),
                    }
                )

        for callsign in list(self.memory):
            memory = self.memory[callsign]
            if callsign not in seen and now - memory.last_seen > 60 and memory.comms_case_started is not None:
                self._reset_communications_case(memory, "TRACK_DISCONNECTED_OVER_60_SECONDS")
            if callsign not in seen and now - memory.last_seen > 600:
                self.memory.pop(callsign, None)

        # An acknowledgment applies to the current occurrence. Once the
        # condition clears, the same alert may alarm again on a later occurrence.
        self.acknowledged.intersection_update(active_alert_ids)
        self.dismissed.intersection_update(active_alert_ids)

        live_pair_callsigns = {str(item.get("callsign") or "") for item in display_pilots}
        self._automatic_intercept_cache = {
            key: value for key, value in self._automatic_intercept_cache.items()
            if key[0] in live_pair_callsigns and key[1] in live_pair_callsigns
        }
        self._associate_interceptors(display_pilots, alerts)
        alerts.sort(
            key=lambda alert: (SEVERITY_RANK[alert["severity"]], alert["score"]),
            reverse=True,
        )
        return display_pilots, alerts
