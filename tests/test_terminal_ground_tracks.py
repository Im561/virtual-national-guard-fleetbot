import time

from app.airports import AirportResolver
from app.atc_boundaries import AtcBoundaryStore
from app.detection import DetectionEngine


def terminal_coverage(callsign: str, facility: str, frequency: int, radius: float):
    return {
        "callsign": callsign,
        "facility": facility,
        "online_seconds": 3600,
        "frequencies_hz": [frequency],
        "frequencies": [frequency / 1_000_000],
        "geometry": None,
        "bbox": None,
        "lat": 40.6413,
        "lon": -73.7781,
        "radius_nm": radius,
        "transceivers": [{
            "id": 1,
            "frequency": frequency,
            "lat": 40.6413,
            "lon": -73.7781,
            "height_msl_m": 4,
            "height_agl_m": 3,
        }],
        "match_quality": "airport_transceiver",
        "sector_specific": True,
        "source": "test",
    }


def test_boundary_store_includes_tower_ground_and_delivery_positions():
    store = AtcBoundaryStore()
    controllers = [
        {"callsign": "JFK_TWR", "frequency": "119.100", "visual_range": 15},
        {"callsign": "JFK_GND", "frequency": "121.900", "visual_range": 5},
        {"callsign": "JFK_DEL", "frequency": "135.050", "visual_range": 5},
    ]
    audio = {
        item["callsign"]: [{
            "id": index,
            "frequency": round(float(item["frequency"]) * 1_000_000),
            "latDeg": 40.6413,
            "lonDeg": -73.7781,
            "heightMslM": 4,
            "heightAglM": 3,
        }]
        for index, item in enumerate(controllers, 1)
    }
    result = store.build_coverage(controllers, audio)
    assert {item["facility"] for item in result} == {"TWR", "GND", "DEL"}
    assert all(item["match_quality"] == "airport_transceiver" for item in result)
    assert all(item["sector_specific"] is True for item in result)


def test_ground_track_is_small_track_candidate_and_matches_ground_frequency():
    engine = DetectionEngine(AirportResolver())
    pilot = {
        "cid": 100,
        "callsign": "TAXI1",
        "latitude": 40.6413,
        "longitude": -73.7781,
        "altitude": 13,
        "groundspeed": 12,
        "heading": 220,
        "transponder": "3456",
        "flight_plan": {
            "flight_rules": "I",
            "aircraft_short": "A320",
            "departure": "KJFK",
            "arrival": "KBOS",
        },
    }
    audio = {"TAXI1": [{"frequency": 121900000}]}
    coverage = [
        terminal_coverage("JFK_GND", "GND", 121900000, 6),
        terminal_coverage("JFK_TWR", "TWR", 119100000, 18),
    ]
    display, alerts = engine.evaluate([pilot], [], audio, coverage)
    track = display[0]
    assert track["on_ground"] is True
    assert track["ground_status"] == "TAXI"
    assert track["center"] == "JFK_GND"
    assert track["controller_facility"] == "GND"
    assert track["ownership_status"] == "VERIFIED_FREQUENCY_MATCH"
    assert not alerts


def test_low_airborne_track_can_match_tower_without_becoming_ground_track():
    engine = DetectionEngine(AirportResolver())
    pilot = {
        "cid": 101,
        "callsign": "TOWER1",
        "latitude": 40.68,
        "longitude": -73.76,
        "altitude": 1800,
        "groundspeed": 145,
        "heading": 310,
        "transponder": "3456",
        "flight_plan": {
            "flight_rules": "I",
            "aircraft_short": "B738",
            "departure": "KJFK",
            "arrival": "KBOS",
        },
    }
    audio = {"TOWER1": [{"frequency": 119100000}]}
    coverage = [terminal_coverage("JFK_TWR", "TWR", 119100000, 18)]
    display, alerts = engine.evaluate([pilot], [], audio, coverage)
    track = display[0]
    assert track["on_ground"] is False
    assert track["center"] == "JFK_TWR"
    assert track["controller_facility"] == "TWR"
    assert track["atc_frequency_match"] is True
    assert not alerts


def test_ground_track_cannot_create_auto_scramble_flag():
    engine = DetectionEngine(AirportResolver())
    pilot = {
        "cid": 102,
        "callsign": "PARKED1",
        "latitude": 40.6413,
        "longitude": -73.7781,
        "altitude": 13,
        "groundspeed": 0,
        "heading": 0,
        "transponder": "3456",
        "flight_plan": {
            "flight_rules": "I",
            "aircraft_short": "A320",
            "departure": "KJFK",
            "arrival": "KBOS",
        },
    }
    audio = {"PARKED1": [{"frequency": 122800000}]}
    coverage = [terminal_coverage("JFK_GND", "GND", 121900000, 6)]
    engine.evaluate([pilot], [], audio, coverage)
    engine.memory["PARKED1"].condition_started["auto_scramble_frequency_mismatch"] = time.time() - 1000
    display, alerts = engine.evaluate([pilot], [], audio, coverage)
    assert display[0]["on_ground"] is True
    assert display[0]["auto_scramble_flag"] is None
    assert not alerts


def test_ui_contains_compact_ground_symbols_and_clear_owner_states():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    app_js = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
    styles = (root / "app" / "static" / "styles.css").read_text(encoding="utf-8")
    assert "groundScopeIcon" in app_js
    assert "groundTacticalIcon" in app_js
    assert "AMBIGUOUS HANDOFF" in app_js
    assert "NO LIVE COVERAGE" in app_js
    assert "NO VERIFIED OWNER" not in app_js
    assert ".ground-scope-track" in styles
    assert ".ground-tactical-track" in styles
