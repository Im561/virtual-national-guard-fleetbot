import time

from app.airports import AirportResolver
from app.detection import DetectionEngine


def pilot(callsign="AAL101", frequency=122800000):
    return {
        "cid": 101,
        "callsign": callsign,
        "latitude": 26.5,
        "longitude": -80.2,
        "altitude": 32000,
        "groundspeed": 450,
        "heading": 180,
        "transponder": "4321",
        "flight_plan": {
            "flight_rules": "I",
            "aircraft_short": "B738",
            "departure": "KMCO",
            "arrival": "KMIA",
        },
    }, {callsign: [{"frequency": frequency}]}


def coverage(callsign="MIA_CTR", frequency=133200000, online_seconds=30):
    return {
        "callsign": callsign,
        "facility": "CTR",
        "online_seconds": online_seconds,
        "frequencies_hz": [frequency],
        "frequencies": [frequency / 1_000_000],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-83.0, 24.0], [-77.0, 24.0], [-77.0, 30.0],
                [-83.0, 30.0], [-83.0, 24.0],
            ]],
        },
        "bbox": [-83.0, 24.0, -77.0, 30.0],
        "transceivers": [{
            "id": 1,
            "frequency": frequency,
            "lat": 26.2,
            "lon": -80.1,
            "height_msl_m": 5,
            "height_agl_m": 5,
        }],
        "match_quality": "facility",
        "sector_specific": False,
        "source": "test",
    }


def test_newly_online_center_does_not_start_mass_1228_cases():
    engine = DetectionEngine(AirportResolver())
    pilots = []
    audio = {}
    for index in range(25):
        item, radios = pilot(f"TEST{index:02d}")
        item["longitude"] += index * 0.01
        pilots.append(item)
        audio.update(radios)

    display, alerts = engine.evaluate(pilots, [], audio, [coverage(online_seconds=30)])

    assert not alerts
    assert all(track["frequency_mismatch_active"] is False for track in display)
    assert all(track["nordo_watch"] is None for track in display)
    assert all(track["communications_watch_controller_stable"] is False for track in display)
    assert all(
        any(obs["code"] == "ATC_ACTIVATION_GRACE" for obs in track["observations"])
        for track in display
    )


def test_case_can_start_after_communications_settling_window():
    engine = DetectionEngine(AirportResolver())
    item, audio = pilot()
    display, _ = engine.evaluate([item], [], audio, [coverage(online_seconds=180)])

    assert display[0]["communications_watch_controller_stable"] is True
    assert display[0]["frequency_mismatch_active"] is True
    assert display[0]["nordo_watch"] is None

    memory = engine.memory["AAL101"]
    memory.comms_case_started = time.time() - 35
    memory.comms_last_mismatch = time.time()
    memory.comms_observed_accumulated = 35
    memory.comms_case_status = "MISMATCH"
    display, _ = engine.evaluate([item], [], audio, [coverage(online_seconds=215)])
    assert display[0]["nordo_watch"] is not None
    assert display[0]["nordo_watch"]["title"] == "POSSIBLE NORDO — OBSERVE"


def test_existing_case_survives_handoff_to_newly_opened_center_position():
    engine = DetectionEngine(AirportResolver())
    item, audio = pilot()
    engine.evaluate([item], [], audio, [coverage(callsign="JAX_CTR", online_seconds=900)])
    memory = engine.memory["AAL101"]
    memory.comms_case_started = time.time() - 240
    memory.comms_last_mismatch = time.time()
    memory.comms_observed_accumulated = 240
    memory.comms_case_status = "MISMATCH"
    memory.comms_last_scope = "FACILITY:KZJX"

    display, _ = engine.evaluate(
        [item], [], audio,
        [coverage(callsign="MIA_CTR", frequency=133200000, online_seconds=20)],
    )

    assert display[0]["frequency_mismatch_active"] is True
    assert display[0]["frequency_mismatch_current"] is True
    assert display[0]["frequency_mismatch_seconds"] >= 240


def test_low_confidence_1228_cannot_start_new_case():
    engine = DetectionEngine(AirportResolver())
    item, audio = pilot()
    low = coverage(online_seconds=900)
    low["geometry"] = None
    low["bbox"] = None
    low["match_quality"] = "none"
    low["sector_specific"] = False

    display, alerts = engine.evaluate([item], [], audio, [low])

    assert not alerts
    assert display[0]["coverage_confidence"] == "MEDIUM"
    assert display[0]["frequency_mismatch_active"] is False
    assert display[0]["nordo_watch"] is None
    assert any(obs["code"] == "1228_LOW_CONFIDENCE_COVERAGE" for obs in display[0]["observations"])
