import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

import app.detection as detection_module
from app.airports import AirportResolver
from app.bases import recommend_base
from app.detection import DetectionEngine
from app.main import app
from app.vatsim import VatsimMonitor


def _square():
    return {
        "type": "Polygon",
        "coordinates": [[[-110, 35], [-100, 35], [-100, 45], [-110, 45], [-110, 35]]],
    }


def _coverage(callsign="DEN_CTR", frequency=127650000):
    return {
        "callsign": callsign,
        "facility": "CTR",
        "online_seconds": 900,
        "frequencies_hz": [frequency],
        "frequencies": [frequency / 1_000_000],
        "geometry": _square(),
        "bbox": [-110, 35, -100, 45],
        "transceivers": [{"frequency": frequency, "lat": 39.0, "lon": -104.0}],
        "match_quality": "facility",
        "sector_specific": False,
        "source": "TEST",
        "boundary_id": "KZDV",
    }


def _pilot(cid=15, logon_time="2026-08-04T20:00:00Z", arrival="EGLL"):
    return {
        "cid": cid,
        "logon_time": logon_time,
        "callsign": "UAL15",
        "latitude": 39.0,
        "longitude": -104.0,
        "altitude": 35000,
        "groundspeed": 460,
        "heading": 90,
        "transponder": "1234",
        "flight_plan": {
            "flight_rules": "I",
            "aircraft_short": "B789",
            "departure": "KDEN",
            "arrival": arrival,
        },
    }


def test_wall_clock_feed_outage_does_not_age_nordo_timer(monkeypatch):
    clock = {"value": 1000.0}
    monkeypatch.setattr(detection_module.time, "time", lambda: clock["value"])
    engine = DetectionEngine(AirportResolver())
    audio = {"UAL15": [{"frequency": 122800000}]}

    engine.evaluate([_pilot()], [], audio, [_coverage()])
    clock["value"] += 15
    display, _ = engine.evaluate([_pilot()], [], audio, [_coverage()])
    assert display[0]["frequency_mismatch_seconds"] == 15

    # Ten minutes pass without a qualifying observed snapshot.
    clock["value"] += 600
    gap, _ = engine.evaluate([_pilot()], [], audio, [])
    assert gap[0]["frequency_mismatch_seconds"] == 15
    assert gap[0]["auto_scramble_mismatch_seconds"] <= 15


def test_callsign_reuse_resets_timer_and_manual_designation(monkeypatch):
    clock = {"value": 2000.0}
    monkeypatch.setattr(detection_module.time, "time", lambda: clock["value"])
    engine = DetectionEngine(AirportResolver())
    audio = {"UAL15": [{"frequency": 122800000}]}
    first = _pilot(cid=15, logon_time="A")
    engine.evaluate([first], [], audio, [_coverage()])
    engine.memory["UAL15"].comms_observed_accumulated = 400
    engine.mark_manual_nordo("UAL15", session_key="15:A")

    second = _pilot(cid=99, logon_time="B")
    display, alerts = engine.evaluate([second], [], audio, [_coverage()])
    assert display[0]["frequency_mismatch_seconds"] == 0
    assert display[0]["manual_nordo"] is False
    assert not any(reason["code"] == "MANUAL_NORDO" for alert in alerts for reason in alert["reasons"])


def test_qra_recommendations_do_not_silently_cross_border():
    us = recommend_base(47.0, -111.0, target_region="UNITED STATES")
    ca = recommend_base(54.4, -110.3, target_region="CANADA")
    assert us is not None and str(us.get("country") or "UNITED STATES").upper() == "UNITED STATES"
    assert ca is not None and ca.get("country") == "CANADA"
    assert ca["icao"] == "CYOD"
    # All aircraft options at a base are evaluated, not only array position 0.
    assert ca["selected_aircraft"] in {"F18H", "F35"}


def test_new_alert_occurrence_resets_old_console_workflow():
    async def broadcast(_payload):
        return None

    async def scenario():
        monitor = VatsimMonitor(broadcast)
        alert = {
            "id": "same-id",
            "callsign": "UAL15",
            "title": "NORDO",
            "confidence": 96,
            "severity": "red",
            "lat": 39.0,
            "lon": -104.0,
            "recommended_base": None,
            "active_interceptors": [],
        }
        try:
            monitor._sync_operations([alert], [])
            await monitor.accept_operation("same-id", "console-a", "QRA A")
            monitor._sync_operations([], [])
            monitor._sync_operations([alert], [])
            operation = monitor.operations["same-id"]
            assert operation["occurrence"] == 2
            assert operation["accepted_count"] == 0
            assert operation["accepted_console_list"] == []
            assert next(p for p in operation["phases"] if p["id"] == "qra_accepted")["complete"] is False
        finally:
            await monitor.client.aclose()

    asyncio.run(scenario())


def test_cross_site_mutations_are_blocked_before_shared_actions():
    client = TestClient(app)
    response = client.post(
        "/api/alerts/not-real/ack",
        headers={"Origin": "https://malicious.example", "Host": "adoc.example"},
    )
    assert response.status_code == 403
    assert response.json()["error"] == "cross_origin_mutation_blocked"


def test_deep_audit_ui_reliability_controls_are_wired():
    index = Path("app/static/index.html").read_text(encoding="utf-8")
    js = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert 'id="feed-stale-banner"' in index
    assert 'id="toggle-map-legend"' in index
    assert "http_fallback_seconds" in Path("app/main.py").read_text(encoding="utf-8")
    assert "scheduleHttpFallback" in js
    assert "new automatic alarms paused" in js
    assert "history.length > 30" in js
    assert "record.latestPilot" in js
    assert "updateFeedAgeOnly" not in js
    assert ".feed-stale-banner" in css


def test_health_reports_initializing_or_stale_state_without_failing_railway_probe():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"initializing", "ok", "stale", "degraded"}
    assert "automatic_alerts_paused" in payload
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_browser_fetches_have_timeouts_and_single_sua_scheduler():
    js = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "fetchWithTimeout" in js
    assert "state.liveLoading" in js
    assert "scheduleSuaRefresh" in js
    assert "setInterval(loadSua" not in js
    assert "MAP ENGINE UNAVAILABLE" in js
    assert "DETECTOR DIAGNOSTICS" in js
    assert "ATC COVERAGE CANDIDATES" in js


def test_callsign_reuse_does_not_inherit_dismissal(monkeypatch):
    clock = {"value": 3000.0}
    monkeypatch.setattr(detection_module.time, "time", lambda: clock["value"])
    engine = DetectionEngine(AirportResolver())
    audio = {"UAL15": [{"frequency": 122800000}]}
    engine.evaluate([_pilot(cid=15, logon_time="A")], [], audio, [_coverage()])
    alert_id = engine._alert_id("UAL15")
    engine.dismiss(alert_id)
    assert alert_id in engine.dismissed

    second = _pilot(cid=99, logon_time="B")
    second["transponder"] = "7700"
    _, alerts = engine.evaluate([second], [], audio, [_coverage()])
    assert alert_id not in engine.dismissed
    assert any(alert["callsign"] == "UAL15" for alert in alerts)


def test_stale_inbound_console_presence_expires_and_heartbeat_does_not_rewind_stage():
    async def broadcast(_payload):
        return None

    async def scenario():
        monitor = VatsimMonitor(broadcast)
        alert = {
            "id": "presence-id", "callsign": "UAL15", "title": "NORDO",
            "confidence": 96, "severity": "red", "lat": 39.0, "lon": -104.0,
            "recommended_base": None, "active_interceptors": [],
        }
        try:
            monitor._sync_operations([alert], [])
            await monitor.accept_operation("presence-id", "console-a", "QRA A")
            await monitor.set_operation_phase("presence-id", "fighters_airborne", True, "QRA A")
            operation = monitor.operations["presence-id"]
            assert operation["status"] == "FIGHTERS AIRBORNE"
            # A presence heartbeat must not rewind the operational stage.
            await monitor.accept_operation("presence-id", "console-a", "QRA A")
            assert operation["status"] == "FIGHTERS AIRBORNE"
            operation["accepted_consoles"]["console-a"]["updated_at"] = "2000-01-01T00:00:00+00:00"
            monitor._sync_operations([alert], [])
            assert operation["accepted_count"] == 0
            assert any("presence expired" in event["label"] for event in operation["events"])
        finally:
            await monitor.client.aclose()

    asyncio.run(scenario())


def test_console_presence_heartbeat_is_wired_to_bootstrap():
    js = Path("app/static/app.js").read_text(encoding="utf-8")
    main = Path("app/main.py").read_text(encoding="utf-8")
    assert "heartbeatAcceptedOperations" in js
    assert "console_presence_heartbeat_seconds" in main


def test_monitor_only_frequency_labels_are_visible_in_operator_ui():
    js = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "formatPilotRadios" in js
    assert "NOT ATC CONTACT" in js
    assert "122.800 suppression requires a verified nearby advisory frequency or likely early handoff" in js
    assert "REPORTED ATC-CAPABLE RADIO(S)" in js


def test_detector_diagnostics_distinguish_watch_and_auto_flag_stabilization():
    js = (Path(__file__).parents[1] / "app" / "static" / "app.js").read_text(encoding="utf-8")
    assert "WATCH ACTIVATION" in js
    assert "AUTO-FLAG STABILIZATION" in js
    assert "communications_watch_stabilization_remaining_seconds" in js
