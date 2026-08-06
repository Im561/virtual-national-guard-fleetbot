import asyncio
from pathlib import Path

from app.vatsim import VatsimMonitor


def display_pilot(callsign: str, lat: float, lon: float, *, speed: int, heading: int, altitude: int, squawk: str = "1200"):
    return {
        "callsign": callsign,
        "lat": lat,
        "lon": lon,
        "altitude": altitude,
        "groundspeed": speed,
        "heading": heading,
        "squawk": squawk,
        "on_ground": False,
        "aircraft": "F16" if callsign.startswith("VIPER") else "B738",
        "aircraft_type": "F16" if callsign.startswith("VIPER") else "B738",
        "aircraft_category": "fighter" if callsign.startswith("VIPER") else "airliner",
        "display_class": "fighter" if squawk == "7777" else "standard",
        "active_intercept": squawk == "7777",
        "track_color": "yellow" if squawk == "7777" else "green",
        "operational_status": "ACTIVE INTERCEPT" if squawk == "7777" else None,
        "intercept_assignment": None,
        "active_interceptors": [],
        "severity": "green",
        "manual_nordo": False,
        "nordo_watch": None,
        "context": [],
        "vsoa": callsign.startswith("VIPER"),
    }


def test_manual_intercept_assignment_updates_live_geometry_and_can_be_cleared():
    broadcasts = []

    async def broadcast(payload):
        broadcasts.append(payload)

    async def scenario():
        monitor = VatsimMonitor(broadcast)
        try:
            fighter = display_pilot("VIPER11", 27.0, -81.0, speed=480, heading=120, altitude=28000)
            target = display_pilot("AAL123", 27.8, -80.1, speed=430, heading=90, altitude=33000)
            monitor.state.pilots = [fighter, target]
            monitor.state.alerts = []

            ok, assignment, error = await monitor.assign_manual_intercept("viper11", "aal123", "MIA QRA")
            assert ok is True
            assert error is None
            assert assignment["assignment_source"] == "manual"
            assert assignment["interceptor_callsign"] == "VIPER11"
            assert assignment["target_callsign"] == "AAL123"
            assert assignment["interceptor_heading_deg"] == 120
            assert assignment["target_heading_deg"] == 90
            assert assignment["interceptor_speed_kt"] == 480
            assert assignment["target_speed_kt"] == 430
            assert assignment["altitude_delta_ft"] == 5000
            assert assignment["separation_nm"] > 0
            assert "signed_closure_rate_kt" in assignment
            assert fighter["manual_intercept"] is True
            assert fighter["active_intercept"] is True
            assert fighter["intercept_assignment"]["target_callsign"] == "AAL123"
            assert target["active_interceptors"][0]["callsign"] == "VIPER11"
            original_separation = assignment["separation_nm"]

            target["lat"] = 27.4
            target["lon"] = -80.5
            monitor._apply_manual_intercepts(monitor.state.pilots, monitor.state.alerts)
            updated = monitor.state.manual_intercepts[0]
            assert updated["separation_nm"] < original_separation

            cleared, record = await monitor.clear_manual_intercept("VIPER11", "MIA QRA")
            assert cleared is True
            assert record["target_callsign"] == "AAL123"
            assert monitor.state.manual_intercepts == []
            assert fighter["manual_intercept"] is False
            assert fighter["active_intercept"] is False
            assert broadcasts
        finally:
            await monitor.client.aclose()

    asyncio.run(scenario())


def test_manual_assignment_overrides_only_selected_interceptor_auto_pairing():
    async def broadcast(_payload):
        return None

    async def scenario():
        monitor = VatsimMonitor(broadcast)
        try:
            fighter = display_pilot("VIPER11", 30.0, -84.0, speed=500, heading=90, altitude=30000, squawk="7777")
            auto_target = display_pilot("DAL100", 30.2, -83.5, speed=420, heading=90, altitude=32000)
            manual_target = display_pilot("JBU200", 31.0, -82.0, speed=440, heading=45, altitude=34000)
            alert = {"id": "a1", "callsign": "DAL100", "active_interceptors": []}
            monitor.state.pilots = [fighter, auto_target, manual_target]
            monitor.state.alerts = [alert]
            monitor.engine._associate_interceptors(monitor.state.pilots, monitor.state.alerts)
            assert fighter["intercept_assignment"]["target_callsign"] == "DAL100"

            ok, assignment, _ = await monitor.assign_manual_intercept("VIPER11", "JBU200", "TEST")
            assert ok is True
            assert assignment["target_callsign"] == "JBU200"
            assert fighter["intercept_assignment"]["target_callsign"] == "JBU200"
            assert auto_target["active_interceptors"] == []
            assert manual_target["active_interceptors"][0]["callsign"] == "VIPER11"
            assert alert["active_interceptors"] == []
        finally:
            await monitor.client.aclose()

    asyncio.run(scenario())


def test_manual_assignment_validates_live_tracks_and_distinct_callsigns():
    async def broadcast(_payload):
        return None

    async def scenario():
        monitor = VatsimMonitor(broadcast)
        try:
            monitor.state.pilots = [display_pilot("VIPER11", 30, -84, speed=500, heading=90, altitude=30000)]
            ok, _, error = await monitor.assign_manual_intercept("VIPER11", "VIPER11", "TEST")
            assert ok is False and error == "same_track"
            ok, _, error = await monitor.assign_manual_intercept("MISSING", "VIPER11", "TEST")
            assert ok is False and error == "interceptor_not_found"
            ok, _, error = await monitor.assign_manual_intercept("VIPER11", "MISSING", "TEST")
            assert ok is False and error == "target_not_found"
        finally:
            await monitor.client.aclose()

    asyncio.run(scenario())


def test_manual_intercept_ui_and_api_are_wired():
    root = Path(__file__).parents[1]
    main = (root / "app" / "main.py").read_text(encoding="utf-8")
    index = (root / "app" / "static" / "index.html").read_text(encoding="utf-8")
    js = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
    css = (root / "app" / "static" / "styles.css").read_text(encoding="utf-8")

    assert '@app.post("/api/intercepts/manual")' in main
    assert '@app.delete("/api/intercepts/manual/{interceptor_callsign}")' in main
    assert 'id="open-intercept-console"' in index
    assert 'id="intercept-target-input"' in index
    assert 'id="intercept-interceptor-input"' in index
    assert 'id="manual-intercept-list"' in index
    assert "assignManualIntercept" in js
    assert "signed_closure_rate_kt" in js
    assert "/api/intercepts/manual" in js
    assert ".intercept-console-modal" in css
    assert ".manual-intercept-card" in css
