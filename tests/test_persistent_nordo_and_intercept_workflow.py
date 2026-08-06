import asyncio
import time

from app.airports import AirportResolver
from app.detection import DetectionEngine
from app.vatsim import VatsimMonitor


def square():
    return {
        "type": "Polygon",
        "coordinates": [[[-110, 35], [-100, 35], [-100, 45], [-110, 45], [-110, 35]]],
    }


def coverage(callsign: str, frequency: int):
    return {
        "callsign": callsign,
        "facility": "CTR",
        "online_seconds": 900,
        "frequencies_hz": [frequency],
        "frequencies": [frequency / 1_000_000],
        "geometry": square(),
        "bbox": [-110, 35, -100, 45],
        "transceivers": [{"frequency": frequency, "lat": 39.0, "lon": -104.0}],
        "match_quality": "exact",
        "sector_specific": True,
        "source": "TEST",
    }


def pilot():
    return {
        "cid": 1,
        "callsign": "UAL15",
        "latitude": 39.0,
        "longitude": -104.0,
        "altitude": 35000,
        "groundspeed": 450,
        "heading": 90,
        "transponder": "3456",
        "flight_plan": {"flight_rules": "I", "aircraft_short": "B789"},
    }


def test_wrong_frequency_case_survives_sector_change_and_brief_coverage_gap():
    engine = DetectionEngine(AirportResolver())
    item = pilot()
    audio = {"UAL15": [{"frequency": 122800000}]}
    den17 = coverage("DEN_17_CTR", 127650000)
    den18 = coverage("DEN_18_CTR", 132750000)

    engine.evaluate([item], [], audio, [den17])
    memory = engine.memory["UAL15"]
    memory.comms_case_started = time.time() - 500
    memory.auto_scramble_accumulated = 300
    memory.comms_last_scope = "FACILITY:ZDV-17"

    gap_display, _ = engine.evaluate([item], [], audio, [])
    assert gap_display[0]["frequency_mismatch_active"] is True
    assert gap_display[0]["frequency_mismatch_case_status"] == "BRIEF_COVERAGE_GAP"
    assert gap_display[0]["frequency_mismatch_seconds"] >= 499
    assert gap_display[0]["auto_scramble_mismatch_seconds"] == 300

    handoff_display, _ = engine.evaluate([item], [], audio, [den18])
    assert handoff_display[0]["frequency_mismatch_active"] is True
    assert handoff_display[0]["frequency_mismatch_seconds"] >= 499
    assert handoff_display[0]["frequency_mismatch_scope_changes"] >= 1


def test_correct_frequency_requires_two_snapshots_to_clear_persistent_case():
    engine = DetectionEngine(AirportResolver())
    item = pilot()
    controller = coverage("DEN_CTR", 127650000)
    engine.evaluate([item], [], {"UAL15": [{"frequency": 122800000}]}, [controller])
    engine.memory["UAL15"].comms_case_started = time.time() - 180

    first, _ = engine.evaluate([item], [], {"UAL15": [{"frequency": 127650000}]}, [controller])
    assert first[0]["frequency_mismatch_active"] is True
    assert first[0]["frequency_mismatch_case_status"] == "VERIFYING_FREQUENCY_MATCH"

    second, _ = engine.evaluate([item], [], {"UAL15": [{"frequency": 127650000}]}, [controller])
    assert second[0]["frequency_mismatch_active"] is False
    assert second[0]["frequency_mismatch_seconds"] == 0


def test_shared_intercept_acceptance_and_phase_checklist():
    broadcasts = []

    async def broadcast(payload):
        broadcasts.append(payload)

    async def scenario():
        monitor = VatsimMonitor(broadcast)
        try:
            monitor._sync_operations(
                [{
                    "id": "alert-1",
                    "callsign": "UAL15",
                    "title": "Automatic scramble flag",
                    "confidence": 96,
                    "severity": "red",
                    "lat": 39.0,
                    "lon": -104.0,
                    "recommended_base": None,
                    "active_interceptors": [],
                }],
                [],
            )
            ok, operation = await monitor.accept_operation("alert-1", "console-a", "DEN QRA 1")
            assert ok is True
            assert operation["accepted_count"] == 1
            assert operation["accepted_console_list"][0]["status"] == "INBOUND"
            assert next(p for p in operation["phases"] if p["id"] == "qra_accepted")["complete"] is True

            ok, operation = await monitor.accept_operation("alert-1", "console-b", "DEN QRA 2")
            assert ok is True
            assert operation["accepted_count"] == 2

            ok, operation = await monitor.set_operation_phase(
                "alert-1", "fighters_airborne", True, "DEN QRA 1"
            )
            assert ok is True
            phase = next(p for p in operation["phases"] if p["id"] == "fighters_airborne")
            assert phase["complete"] is True
            assert phase["completed_by"] == "DEN QRA 1"

            ok, operation = await monitor.release_operation("alert-1", "console-b")
            assert ok is True
            assert operation["accepted_count"] == 1
            assert broadcasts
        finally:
            await monitor.client.aclose()

    asyncio.run(scenario())
