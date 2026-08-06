import asyncio
import time
from pathlib import Path

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


def pilot(callsign="TEST142", frequency=122800000):
    return {
        "cid": 142,
        "callsign": callsign,
        "latitude": 39.0,
        "longitude": -104.0,
        "altitude": 32000,
        "groundspeed": 440,
        "heading": 90,
        "transponder": "4321",
        "flight_plan": {"flight_rules": "I", "aircraft_short": "B738"},
    }, {callsign: [{"frequency": frequency}]}


def coverage():
    return {
        "callsign": "DEN_CTR",
        "facility": "CTR",
        "online_seconds": 1800,
        "frequencies_hz": [127650000],
        "frequencies": [127.65],
        "geometry": square(),
        "bbox": [-110, 35, -100, 45],
        "transceivers": [{
            "id": 1,
            "frequency": 127650000,
            "lat": 39.1,
            "lon": -104.1,
            "height_msl_m": 1500,
            "height_agl_m": 20,
        }],
        "match_quality": "sector",
        "sector_specific": True,
        "source": "test",
    }


def test_temporary_exemption_suppresses_communications_case_and_is_exposed():
    engine = DetectionEngine(AirportResolver())
    p, audio = pilot()
    engine.temporary_exemptions["ex-1"] = {
        "id": "ex-1",
        "callsign": "TEST142",
        "reason": "Coordinated handoff",
        "expires_at_epoch": time.time() + 900,
    }
    display, alerts = engine.evaluate([p], [], audio, [coverage()])
    assert not alerts
    track = display[0]
    assert track["temporary_exemption_active"] is True
    assert track["temporary_exemption_detail"]["reason"] == "Coordinated handoff"
    assert track["frequency_mismatch_active"] is False
    assert track["nordo_gate_ready"] is False


def test_frequency_change_grace_only_suppresses_a_new_case():
    engine = DetectionEngine(AirportResolver())
    p, correct_audio = pilot(frequency=127650000)
    engine.evaluate([p], [], correct_audio, [coverage()])
    _, changed_audio = pilot(frequency=128000000)
    display, _ = engine.evaluate([p], [], changed_audio, [coverage()])
    assert display[0]["frequency_change_grace_active"] is True
    assert display[0]["frequency_mismatch_active"] is False

    engine.memory["TEST142"].frequency_change_grace_until = time.time() - 1
    display, _ = engine.evaluate([p], [], changed_audio, [coverage()])
    assert display[0]["frequency_change_grace_active"] is False
    assert display[0]["frequency_mismatch_active"] is True


def test_monitor_creates_and_removes_shared_expiring_exemption():
    broadcasts = []

    async def broadcast(payload):
        broadcasts.append(payload)

    async def scenario():
        monitor = VatsimMonitor(broadcast)
        try:
            monitor.state.pilots = [{"callsign": "TEST142"}]
            ok, record, error = await monitor.create_temporary_exemption(
                "TEST142", 15, "ATC coordinated", "TEST DESK"
            )
            assert ok is True and error is None
            assert record["duration_minutes"] == 15
            assert monitor.state.temporary_exemptions[0]["callsign"] == "TEST142"
            assert monitor.engine.temporary_exemptions[record["id"]]["reason"] == "ATC coordinated"
            removed, _ = await monitor.remove_temporary_exemption(record["id"], "TEST DESK")
            assert removed is True
            assert monitor.state.temporary_exemptions == []
            assert broadcasts
        finally:
            await monitor.client.aclose()

    asyncio.run(scenario())


def test_v142_atc_evidence_timeline_handoff_and_layout_are_wired():
    root = Path(__file__).parents[1]
    js = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
    css = (root / "app" / "static" / "styles.css").read_text(encoding="utf-8")
    main = (root / "app" / "main.py").read_text(encoding="utf-8")
    vatsim = (root / "app" / "vatsim.py").read_text(encoding="utf-8")
    delta_js = (root / "app" / "static" / "modules" / "delta-client.js").read_text(encoding="utf-8")
    delta_py = (root / "app" / "live_delta.py").read_text(encoding="utf-8")

    for function_name in (
        "atcEvidencePanelHtml",
        "atcTimelinePanelHtml",
        "atcHandoffPanelHtml",
        "atcExemptionPanelHtml",
        "createTemporaryExemption",
        "removeTemporaryExemption",
    ):
        assert f"function {function_name}" in js or f"async function {function_name}" in js
    assert 'L.polyline([selectedPosition, handoffPoint]' in js
    assert '@app.post("/api/exemptions")' in main
    assert '@app.delete("/api/exemptions/{exemption_id}")' in main
    assert "async def create_temporary_exemption" in vatsim
    assert ".atc-evidence-panel" in css
    assert ".atc-timeline-panel" in css
    assert ".atc-exemption-form" in css
    assert "white-space:normal" in css
    assert "grid-template-columns:minmax(0,1fr)" in css


def test_temporary_exemptions_are_applied_by_browser_deltas():
    root = Path(__file__).parents[1]
    delta_js = (root / "app" / "static" / "modules" / "delta-client.js").read_text(encoding="utf-8")
    delta_py = (root / "app" / "live_delta.py").read_text(encoding="utf-8")
    assert "temporary_exemptions" in delta_js
    assert '"temporary_exemptions"' in delta_py
