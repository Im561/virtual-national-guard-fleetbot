import asyncio
import time

from app.vatsim import VatsimMonitor


def pilot(callsign):
    return {
        "callsign": callsign,
        "center": "TEST_CTR",
        "frequencies": [122.8],
        "active_artcc_frequencies": [125.1],
        "frequency_mismatch_active": True,
        "nordo_watch": {"title": "POSSIBLE NORDO — INVESTIGATE", "confidence": 70, "duration_seconds": 500},
        "auto_scramble_flag": {"active": True, "controller": "TEST_CTR"},
        "alert_id": f"{callsign}:AUTO_SCRAMBLE_FREQ_MISMATCH",
        "requires_ack": True,
        "manual_nordo": False,
    }


def alert(callsign):
    return {
        "id": f"{callsign}:AUTO_SCRAMBLE_FREQ_MISMATCH",
        "callsign": callsign,
        "center": "TEST_CTR",
        "confidence": 95,
        "reasons": [{"code": "AUTO_SCRAMBLE_FREQ_MISMATCH"}],
        "requires_ack": True,
    }


def test_single_automatic_flag_is_not_delayed():
    monitor = VatsimMonitor(lambda payload: None)
    pilots = [pilot("ONE1")]
    alerts = [alert("ONE1")]
    monitor._apply_mass_alert_verification(pilots, alerts)
    assert len(alerts) == 1
    assert not pilots[0].get("mass_alert_verification_pending")


def test_simultaneous_auto_flags_stay_as_verifying_watches_not_alert_queue(monkeypatch):
    monitor = VatsimMonitor(lambda payload: None)
    monkeypatch.setattr("app.vatsim.settings.mass_alert_guard_verify_seconds", 45)
    monkeypatch.setattr("app.vatsim.settings.mass_alert_guard_min_snapshots", 3)
    pilots = [pilot("ONE1"), pilot("TWO2")]
    alerts = [alert("ONE1"), alert("TWO2")]
    monitor._apply_mass_alert_verification(pilots, alerts)
    assert alerts == []
    assert all(item["nordo_watch"]["title"] == "POSSIBLE NORDO — VERIFYING" for item in pilots)
    assert all(item["mass_alert_verification_pending"] for item in pilots)
    assert monitor.state.mass_alert_guard["active"] is True


def test_individual_track_promotes_after_fresh_stable_verification(monkeypatch):
    monitor = VatsimMonitor(lambda payload: None)
    monkeypatch.setattr("app.vatsim.settings.mass_alert_guard_verify_seconds", 0)
    monkeypatch.setattr("app.vatsim.settings.mass_alert_guard_min_snapshots", 3)
    pilots = [pilot("ONE1"), pilot("TWO2")]
    for sequence in range(3):
        monitor.state.feed_sequence = sequence
        alerts = [alert("ONE1"), alert("TWO2")]
        monitor._apply_mass_alert_verification(pilots, alerts)
    assert len(alerts) == 2
    assert all(item.get("mass_alert_independently_verified") for item in alerts)
    assert all(not item.get("mass_alert_verification_pending") for item in pilots)


def test_emergency_alert_bypasses_mass_guard():
    monitor = VatsimMonitor(lambda payload: None)
    pilots = [pilot("EMERG1"), pilot("TWO2")]
    emergency = alert("EMERG1")
    emergency["reasons"].append({"code": "SQUAWK_7700"})
    alerts = [emergency, alert("TWO2")]
    monitor._apply_mass_alert_verification(pilots, alerts)
    assert emergency in alerts


def test_atc_can_dismiss_pending_automatic_flag_with_audit_reason():
    broadcasts = []
    async def broadcast(payload):
        broadcasts.append(payload)
    async def scenario():
        monitor = VatsimMonitor(broadcast)
        try:
            p = pilot("ONE1")
            monitor.state.pilots = [p]
            found = await monitor.dismiss_alert(
                p["alert_id"], actor="MIA CENTER DESK", reason="Verified coordinated handoff"
            )
            assert found is True
            record = monitor.automatic_flag_dismissals[p["alert_id"]]
            assert record["reason"] == "Verified coordinated handoff"
            assert p["automatic_flag_dismissed"] is True
            assert broadcasts
        finally:
            await monitor.client.aclose()
    asyncio.run(scenario())


def test_atc_ui_exposes_automatic_flag_dismissal():
    from pathlib import Path
    root = Path(__file__).parents[1]
    js = (root / "app/static/app.js").read_text()
    assert "DISMISS AUTOMATIC FLAG" in js
    assert "data-dismiss-automatic-flag" in js
    assert "dismissAutomaticFlag" in js
    assert "A dismissal reason is required" in js
