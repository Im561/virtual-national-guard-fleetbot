import asyncio
from pathlib import Path

from app.vatsim import VatsimMonitor


def pilot(callsign: str, lat: float, lon: float, *, speed: int, heading: int, altitude: int, vsoa: bool = False):
    return {
        "callsign": callsign,
        "lat": lat,
        "lon": lon,
        "altitude": altitude,
        "groundspeed": speed,
        "heading": heading,
        "squawk": "1200",
        "on_ground": False,
        "aircraft": "F16" if vsoa else "B738",
        "aircraft_type": "F16" if vsoa else "B738",
        "aircraft_category": "fighter" if vsoa else "airliner",
        "display_class": "fighter" if vsoa else "standard",
        "active_intercept": False,
        "track_color": "green",
        "operational_status": None,
        "intercept_assignment": None,
        "active_interceptors": [],
        "severity": "green",
        "manual_nordo": False,
        "nordo_watch": None,
        "context": [],
        "vsoa": vsoa,
        "vsoa_label": "vUSAF" if vsoa else None,
    }


def test_batch_assignment_control_and_release_all_are_shared():
    broadcasts = []

    async def broadcast(payload):
        broadcasts.append(payload)

    async def scenario():
        monitor = VatsimMonitor(broadcast)
        try:
            one = pilot("VIPER11", 27.0, -81.0, speed=500, heading=90, altitude=28000, vsoa=True)
            two = pilot("EAGLE21", 26.7, -81.2, speed=470, heading=70, altitude=30000, vsoa=True)
            target = pilot("AAL123", 27.8, -80.1, speed=430, heading=100, altitude=33000)
            monitor.state.pilots = [one, two, target]
            monitor.state.alerts = []

            ok, assignments, errors, error = await monitor.assign_manual_intercepts(
                ["VIPER11", "EAGLE21"], "AAL123", "MIA INTERCEPT DESK"
            )
            assert ok is True
            assert error is None
            assert errors == {}
            assert {item["interceptor_callsign"] for item in assignments} == {"VIPER11", "EAGLE21"}
            assert all(item["target_callsign"] == "AAL123" for item in assignments)
            assert all(item["separation_nm"] > 0 for item in assignments)
            assert len(target["active_interceptors"]) == 2

            ok, control, error = await monitor.set_intercept_target_control(
                "AAL123",
                "MIA INTERCEPT DESK",
                response_status="NOT_RESPONDING",
                atc_status="COORDINATING",
                command_status="ATTEMPT_CONTACT",
                note="MIA_CTR 132.450 notified",
            )
            assert ok is True and error is None
            assert control["target_response_status"] == "NOT_RESPONDING"
            assert control["atc_coordination_status"] == "COORDINATING"
            assert control["command_status"] == "ATTEMPT_CONTACT"
            assert control["coordination_note"] == "MIA_CTR 132.450 notified"
            assert len(monitor.state.intercept_controls) == 1
            assert all(item["target_response_status"] == "NOT_RESPONDING" for item in monitor.state.manual_intercepts)
            assert all(item["command_status"] == "ATTEMPT_CONTACT" for item in monitor.state.manual_intercepts)

            found, removed = await monitor.clear_target_intercepts("AAL123", "MIA INTERCEPT DESK")
            assert found is True
            assert len(removed) == 2
            assert monitor.state.manual_intercepts == []
            assert one["manual_intercept"] is False
            assert two["manual_intercept"] is False
            assert broadcasts
        finally:
            await monitor.client.aclose()

    asyncio.run(scenario())


def test_batch_assignment_rejects_target_and_keeps_valid_live_interceptors():
    async def broadcast(_payload):
        return None

    async def scenario():
        monitor = VatsimMonitor(broadcast)
        try:
            fighter = pilot("VIPER11", 27.0, -81.0, speed=500, heading=90, altitude=28000, vsoa=True)
            target = pilot("AAL123", 27.8, -80.1, speed=430, heading=100, altitude=33000)
            monitor.state.pilots = [fighter, target]
            monitor.state.alerts = []

            ok, assignments, errors, error = await monitor.assign_manual_intercepts(
                ["VIPER11", "MISSING"], "AAL123", "TEST"
            )
            assert ok is True
            assert error is None
            assert errors == {"MISSING": "interceptor_not_found"}
            assert [item["interceptor_callsign"] for item in assignments] == ["VIPER11"]
        finally:
            await monitor.client.aclose()

    asyncio.run(scenario())


def test_multi_interceptor_tab_and_shared_controls_are_wired():
    root = Path(__file__).parents[1]
    index = (root / "app" / "static" / "index.html").read_text(encoding="utf-8")
    js = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
    css = (root / "app" / "static" / "styles.css").read_text(encoding="utf-8")
    main = (root / "app" / "main.py").read_text(encoding="utf-8")

    assert 'data-workspace-tab="intercept"' in index
    assert '>INTERCEPTS <span id="active-intercept-tab-count">' in index
    assert 'id="intercept-multi-candidates"' in index
    assert 'id="assign-selected-interceptors"' in index
    assert "SELECT VSOA" in index
    assert "ACTIVE INTERCEPT MISSIONS" in index
    assert "assignSelectedInterceptors" in js
    assert "rankedInterceptorCandidates" in js
    assert "targetControlButtonsHtml" in js
    assert "INTERCEPT_APPROVED" in js
    assert "ESCORT_SHADOW" in js
    assert "interceptorCalculationCardHtml" in js
    assert "/api/intercepts/manual/batch" in js
    assert "/api/intercepts/targets/${encodeURIComponent(targetCallsign)}/control" in js
    assert '@app.post("/api/intercepts/manual/batch")' in main
    assert '@app.post("/api/intercepts/targets/{target_callsign}/control")' in main
    assert '@app.delete("/api/intercepts/targets/{target_callsign}")' in main
    assert ".intercept-ops-layout" in css
    assert ".interceptor-calculation-card" in css
