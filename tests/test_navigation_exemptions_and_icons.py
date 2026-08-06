import math
import time
from pathlib import Path

from app.airports import AirportResolver
from app.detection import (
    DetectionEngine,
    aircraft_category,
    normalize_aircraft_type,
)


def exact_coverage():
    return [
        {
            "callsign": "DEN_17_CTR",
            "facility": "CTR",
            "online_seconds": 1800,
            "frequencies_hz": [127650000],
            "frequencies": [127.65],
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-106, 37], [-102, 37], [-102, 41], [-106, 41], [-106, 37]]],
            },
            "bbox": [-106, 37, -102, 41],
            "transceivers": [
                {
                    "id": 1,
                    "frequency": 127650000,
                    "lat": 39.0,
                    "lon": -104.0,
                    "height_msl_m": 1600,
                    "height_agl_m": 20,
                }
            ],
            "match_quality": "exact_sector",
            "sector_specific": True,
            "source": "test exact sector",
        }
    ]


def pilot(*, aircraft="B738/M", remarks="", squawk="3456"):
    return {
        "cid": 42,
        "callsign": "ORBIT1",
        "latitude": 39.0,
        "longitude": -104.0,
        "altitude": 30000,
        "groundspeed": 300,
        "heading": 90,
        "transponder": squawk,
        "flight_plan": {
            "flight_rules": "I",
            "aircraft_short": aircraft,
            "remarks": remarks,
        },
    }


def seed_orbit(engine: DetectionEngine, callsign="ORBIT1"):
    now = time.time()
    points = []
    # Roughly a 5 NM circle, 720 degrees of accumulated heading change over 620 seconds.
    for index in range(31):
        angle = math.radians(index * 24)
        lat = 39.0 + 0.083 * math.cos(angle)
        lon = -104.0 + 0.106 * math.sin(angle)
        points.append((now - 620 + index * (620 / 30), lat, lon, (index * 24) % 360))
    engine.memory[callsign].recent_positions = points
    engine.memory[callsign].condition_started["nordo_1228"] = now - 360
    engine.memory[callsign].condition_started["auto_scramble_frequency_mismatch"] = now - 360
    engine.memory[callsign].auto_scramble_controller = "DEN_17_CTR"


def test_type_parser_skips_wake_prefix_and_classifies_types():
    assert normalize_aircraft_type("H/B738/L-SDE2E3") == "B738"
    assert aircraft_category("H/B738/L-SDE2E3") == "airliner"
    assert normalize_aircraft_type("H160/M") == "H160"
    assert aircraft_category("H160/M") == "helicopter"
    assert aircraft_category("F35/M") == "fighter"


def test_ordinary_orbit_plus_nordo_mismatch_becomes_alert():
    engine = DetectionEngine(AirportResolver())
    item = pilot()
    engine.evaluate([item], [], {"ORBIT1": [{"frequency": 122800000}]}, exact_coverage())
    seed_orbit(engine)
    display, alerts = engine.evaluate(
        [item], [], {"ORBIT1": [{"frequency": 122800000}]}, exact_coverage()
    )
    assert display[0]["orbit_detected"] is True
    assert any(reason["code"] == "UNRESPONSIVE_ORBIT" for reason in display[0]["reasons"])
    assert alerts


def test_vsoa_orbit_is_exempt_but_emergency_squawk_is_not():
    engine = DetectionEngine(AirportResolver())
    item = pilot(remarks="/VSOA/ TRAINING")
    engine.evaluate([item], [], {"ORBIT1": [{"frequency": 122800000}]}, exact_coverage())
    seed_orbit(engine)
    display, alerts = engine.evaluate(
        [item], [], {"ORBIT1": [{"frequency": 122800000}]}, exact_coverage()
    )
    assert display[0]["navigation_exempt"] is True
    assert display[0]["navigation_exemption_reason"] == "VSOA"
    assert any(obs["code"] == "MISSION_ORBIT_EXEMPT" for obs in display[0]["observations"])
    assert not any(reason["code"] == "UNRESPONSIVE_ORBIT" for reason in display[0]["reasons"])
    assert not alerts

    org_marker = pilot(remarks="OPR/vUSCG TRAINING")
    engine.evaluate([org_marker], [], {"ORBIT1": [{"frequency": 122800000}]}, exact_coverage())
    seed_orbit(engine)
    display, alerts = engine.evaluate(
        [org_marker], [], {"ORBIT1": [{"frequency": 122800000}]}, exact_coverage()
    )
    assert display[0]["vsoa"] is True
    assert display[0]["vsoa_label"] == "vUSCG"
    assert display[0]["navigation_exemption_reason"] == "VSOA"
    assert not any(reason["code"] == "UNRESPONSIVE_ORBIT" for reason in display[0]["reasons"])
    assert not alerts

    emergency = pilot(remarks="/VSOA/ TRAINING", squawk="7700")
    display, alerts = engine.evaluate(
        [emergency], [], {"ORBIT1": [{"frequency": 122800000}]}, exact_coverage()
    )
    assert any(reason["code"] == "SQUAWK_7700" for reason in display[0]["reasons"])
    assert alerts


def test_helicopter_orbit_is_exempt_but_frequency_monitoring_remains():
    engine = DetectionEngine(AirportResolver())
    item = pilot(aircraft="H160/M")
    engine.evaluate([item], [], {"ORBIT1": [{"frequency": 122800000}]}, exact_coverage())
    seed_orbit(engine)
    display, alerts = engine.evaluate(
        [item], [], {"ORBIT1": [{"frequency": 122800000}]}, exact_coverage()
    )
    assert display[0]["aircraft_category"] == "helicopter"
    assert display[0]["navigation_exemption_reason"] == "HELICOPTER"
    assert display[0]["nordo_watch"] is not None
    assert not any(reason["code"] == "UNRESPONSIVE_ORBIT" for reason in display[0]["reasons"])
    assert not alerts


def test_atc_scope_uses_radar_symbols_while_tactical_mode_keeps_category_shapes():
    root = Path(__file__).resolve().parents[1]
    js = (root / "app/static/app.js").read_text(encoding="utf-8")
    css = (root / "app/static/styles.css").read_text(encoding="utf-8")
    assert "scopeAircraftSvg(pilot)" not in js
    assert "scope-aircraft-shape" not in css
    assert '<span class="scope-primary"></span><span class="scope-beacon"></span><span class="scope-vector"></span>' in js
    assert "tacticalAircraftSvg(pilot)" in js
    assert "pilot?.aircraft_type" in js
    assert "pilot?.aircraft_category" in js


def test_departure_reversal_does_not_become_orbit_intercept():
    engine = DetectionEngine(AirportResolver())
    item = {
        "cid": 77,
        "callsign": "DEP180",
        "latitude": 39.90,
        "longitude": -104.70,
        "altitude": 15000,
        "groundspeed": 220,
        "heading": 270,
        "transponder": "3456",
        "flight_plan": {
            "flight_rules": "I",
            "aircraft_short": "B738/M",
            "departure": "KDEN",
            "arrival": "KORD",
            "remarks": "",
        },
    }
    engine.evaluate([item], [], {"DEP180": [{"frequency": 122800000}]}, exact_coverage())
    now = time.time()
    points = []
    for index in range(31):
        angle = math.radians(index * 24)
        points.append((now - 620 + index * (620 / 30), 39.90 + 0.04 * math.cos(angle), -104.70 + 0.05 * math.sin(angle), (index * 24) % 360))
    memory = engine.memory["DEP180"]
    memory.recent_positions = points
    memory.condition_started["nordo_1228"] = now - 360
    memory.condition_started["auto_scramble_frequency_mismatch"] = now - 360
    memory.auto_scramble_controller = "DEN_17_CTR"
    display, alerts = engine.evaluate([item], [], {"DEP180": [{"frequency": 122800000}]}, exact_coverage())
    assert display[0]["departure_turn_suppressed"] is True
    assert display[0]["orbit_detected"] is False
    assert not any(reason["code"] == "UNRESPONSIVE_ORBIT" for reason in display[0]["reasons"])
    assert not alerts
