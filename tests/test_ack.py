import asyncio
from pathlib import Path

from app.vatsim import VatsimMonitor


def test_server_acknowledgment_is_console_local_and_does_not_mutate_shared_state():
    broadcasts = []

    async def broadcaster(payload):
        broadcasts.append(payload)

    monitor = VatsimMonitor(broadcaster)
    monitor.state.alerts = [
        {"id": "abc123", "acknowledged": False, "requires_ack": True, "severity": "red"}
    ]
    monitor.state.pilots = [
        {"callsign": "TEST1", "alert_id": "abc123", "requires_ack": True}
    ]

    async def run():
        try:
            found = await monitor.acknowledge_alert("abc123")
            assert found is True
            assert monitor.state.alerts[0]["acknowledged"] is False
            assert monitor.state.alerts[0]["requires_ack"] is True
            assert monitor.state.pilots[0]["requires_ack"] is True
            assert not broadcasts
        finally:
            await monitor.client.aclose()

    asyncio.run(run())


def test_browser_acknowledgment_uses_local_storage_and_skips_shared_ack_post():
    js = Path('app/static/app.js').read_text(encoding='utf-8')
    assert "vng-adoc.local-acknowledged" in js
    assert "ALERT ACKNOWLEDGED ON THIS CONSOLE" in js
    ack_branch = js[js.index("if (action === 'ack')"):js.index("const controller = new AbortController()")]
    assert '/api/alerts/' not in ack_branch
    assert 'saveLocalAcknowledgments()' in ack_branch


def test_alert_id_stays_stable_when_primary_reason_changes():
    from app.airports import AirportResolver
    from app.detection import DetectionEngine

    engine = DetectionEngine(AirportResolver())
    assert engine._alert_id("TEST1", "SQUAWK_7700") == engine._alert_id("TEST1", "NORDO_1228")


def test_live_payload_excludes_heavy_reference_geometry():
    from app.vatsim import LiveState

    state = LiveState()
    state.atc_coverage = [{"callsign": "DEN_CTR", "geometry": {"type": "Polygon"}}]
    live = state.live_payload()
    full = state.full_payload()
    assert "atc_coverage" not in live
    assert "zones" not in live
    assert full["atc_coverage"]
    assert full["zones"]


def test_local_acknowledgment_and_shared_response_workflow_are_wired():
    js = Path('app/static/app.js').read_text(encoding='utf-8')
    assert "state.localAcknowledged.has(operation.id)" in js
    assert "ACCEPT INTERCEPT · MARK INBOUND" in js
    assert "INTERCEPT PHASE CHECKLIST" in js
    assert "Acknowledged on this console" in js
