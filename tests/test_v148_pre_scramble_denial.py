import asyncio
import time

from app.airports import AirportResolver
from app.detection import DetectionEngine
from app.vatsim import VatsimMonitor


def square(min_lon=-110, min_lat=35, max_lon=-100, max_lat=45):
    return {
        "type": "Polygon",
        "coordinates": [[
            [min_lon, min_lat], [max_lon, min_lat], [max_lon, max_lat],
            [min_lon, max_lat], [min_lon, min_lat],
        ]],
    }


def pilot(callsign="NORDO1", frequency=122_800_000):
    return {
        "cid": 100,
        "callsign": callsign,
        "latitude": 39.0,
        "longitude": -104.0,
        "altitude": 30_000,
        "groundspeed": 430,
        "heading": 90,
        "transponder": "3456",
        "logon_time": "2026-08-06T14:00:00Z",
        "flight_plan": {"flight_rules": "I", "aircraft_short": "A320"},
    }, {callsign: [{"frequency": frequency}]}


def coverage():
    return {
        "callsign": "DEN_17_CTR",
        "facility": "CTR",
        "online_seconds": 900,
        "frequencies_hz": [127_650_000],
        "frequencies": [127.65],
        "geometry": square(),
        "bbox": [-110, 35, -100, 45],
        "transceivers": [{
            "id": 1,
            "frequency": 127_650_000,
            "lat": 39.1,
            "lon": -104.1,
            "height_msl_m": 1500,
            "height_agl_m": 20,
        }],
        "match_quality": "sector",
        "sector_specific": True,
        "source": "test",
        "coverage_confidence": "HIGH",
        "coverage_confidence_basis": "EXACT_SECTOR_AND_TRANSCEIVER",
    }


def test_detector_publishes_final_thirty_second_pre_scramble_warning() -> None:
    engine = DetectionEngine(AirportResolver())
    track, audio = pilot()
    live_coverage = coverage()
    engine.evaluate([track], [], audio, [live_coverage])
    now = time.time()
    memory = engine.memory["NORDO1"]
    memory.condition_started["verified_frequency_mismatch"] = now - 800
    memory.condition_started["auto_scramble_frequency_mismatch"] = now - 451

    display, alerts = engine.evaluate([track], [], audio, [live_coverage])

    warning = display[0]["pre_scramble_warning"]
    assert not alerts
    assert warning is not None
    assert warning["active"] is True
    assert 0 < warning["remaining_seconds"] <= 30
    assert warning["case_id"] == display[0]["pre_scramble_case_id"]
    assert warning["alert_id"] == display[0]["alert_id"] or display[0]["alert_id"] is None
    assert warning["controller"] == "DEN_17_CTR"


def test_auto_flag_replaces_pre_scramble_warning_at_threshold() -> None:
    engine = DetectionEngine(AirportResolver())
    track, audio = pilot()
    live_coverage = coverage()
    engine.evaluate([track], [], audio, [live_coverage])
    now = time.time()
    memory = engine.memory["NORDO1"]
    memory.condition_started["verified_frequency_mismatch"] = now - 800
    memory.condition_started["auto_scramble_frequency_mismatch"] = now - 481

    display, alerts = engine.evaluate([track], [], audio, [live_coverage])

    assert alerts
    assert display[0]["auto_scramble_flag"] is not None
    assert display[0]["pre_scramble_warning"] is None


def test_shared_pre_scramble_denial_suppresses_only_communications_auto_alert() -> None:
    async def scenario() -> None:
        broadcasts: list[dict] = []

        async def broadcaster(payload: dict) -> None:
            broadcasts.append(payload)

        monitor = VatsimMonitor(broadcaster)
        try:
            alert_id = "abc123"
            case_id = "case-current"
            monitor.state.pilots = [{
                "callsign": "NORDO1",
                "center": "DEN_17_CTR",
                "frequency_mismatch_active": True,
                "pre_scramble_case_id": case_id,
                "pre_scramble_warning": {
                    "active": True,
                    "case_id": case_id,
                    "alert_id": alert_id,
                    "controller": "DEN_17_CTR",
                    "remaining_seconds": 12,
                },
                "alert_id": alert_id,
                "requires_ack": True,
            }]
            monitor.state.alerts = [{
                "id": alert_id,
                "callsign": "NORDO1",
                "reasons": [{"code": "AUTO_SCRAMBLE_FREQ_MISMATCH"}],
                "requires_ack": True,
            }]

            ok, record, error = await monitor.deny_pre_scramble(
                "NORDO1",
                case_id,
                actor="TEST CONSOLE",
            )

            assert ok is True and error is None
            assert record and record["case_id"] == case_id
            assert monitor.state.alerts == []
            assert monitor.state.pilots[0]["pre_scramble_denied"] is True
            assert monitor.state.pilots[0]["requires_ack"] is False
            assert broadcasts and broadcasts[-1]["pre_scramble_denials"][0]["case_id"] == case_id

            emergency = {
                "id": alert_id,
                "callsign": "NORDO1",
                "reasons": [
                    {"code": "AUTO_SCRAMBLE_FREQ_MISMATCH"},
                    {"code": "SQUAWK_7700"},
                ],
                "requires_ack": True,
            }
            alerts = [emergency]
            monitor._apply_pre_scramble_denials(monitor.state.pilots, alerts)
            assert alerts == [emergency]
        finally:
            await monitor.client.aclose()

    asyncio.run(scenario())


def test_pre_scramble_denial_rejects_stale_case_identity() -> None:
    async def scenario() -> None:
        async def broadcaster(_: dict) -> None:
            return None

        monitor = VatsimMonitor(broadcaster)
        try:
            monitor.state.pilots = [{
                "callsign": "NORDO1",
                "frequency_mismatch_active": True,
                "pre_scramble_case_id": "current-case",
                "pre_scramble_warning": {"active": True, "case_id": "current-case", "alert_id": "abc123"},
            }]
            ok, record, error = await monitor.deny_pre_scramble("NORDO1", "old-case")
            assert ok is False
            assert record is None
            assert error == "stale_case"
        finally:
            await monitor.client.aclose()

    asyncio.run(scenario())


def test_pre_scramble_compact_ui_and_endpoint_are_wired() -> None:
    index = open("app/static/index.html", encoding="utf-8").read()
    js = open("app/static/app.js", encoding="utf-8").read()
    main = open("app/main.py", encoding="utf-8").read()
    assert 'id="pre-scramble-strip"' in index
    assert 'id="deny-pre-scramble"' in index
    assert "function renderPreScrambleWarning" in js
    assert "/api/pre-scramble/${encodeURIComponent(callsign)}/deny" in js
    assert '@app.post("/api/pre-scramble/{callsign}/deny")' in main
