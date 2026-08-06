import asyncio
from pathlib import Path

from app.vatsim import LiveState, VatsimMonitor


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


def test_live_payload_exposes_intercept_recalculation_timestamp():
    state = LiveState()
    state.intercept_recalculated_at = "2026-08-05T04:32:00+00:00"
    assert state.live_payload()["intercept_recalculated_at"] == state.intercept_recalculated_at


def test_force_recalculate_rebuilds_multiple_solutions_and_broadcasts():
    broadcasts = []

    async def broadcast(payload):
        broadcasts.append(payload)

    async def scenario():
        monitor = VatsimMonitor(broadcast)
        try:
            one = pilot("VIPER11", 27.0, -81.0, speed=500, heading=80, altitude=28000, vsoa=True)
            two = pilot("EAGLE21", 26.7, -81.2, speed=470, heading=65, altitude=30000, vsoa=True)
            target = pilot("AAL123", 27.8, -80.1, speed=430, heading=105, altitude=33000)
            monitor.state.pilots = [one, two, target]
            monitor.state.alerts = []

            ok, assignments, errors, error = await monitor.assign_manual_intercepts(
                ["VIPER11", "EAGLE21"], "AAL123", "TEST DESK"
            )
            assert ok is True and error is None and errors == {}
            assert len(assignments) == 2
            before = {
                item["interceptor_callsign"]: (item.get("intercept_point_lat"), item.get("intercept_point_lon"))
                for item in monitor.state.manual_intercepts
            }

            target["lat"] = 28.3
            target["lon"] = -79.5
            target["heading"] = 135
            summary = await monitor.recalculate_intercepts("TEST DESK")

            assert summary["actor"] == "TEST DESK"
            assert summary["manual_intercepts"] == 2
            assert summary["recalculated_at"] == monitor.state.intercept_recalculated_at
            assert monitor.state.revision > 0
            assert len(monitor.state.manual_intercepts) == 2
            assert len(target["active_interceptors"]) == 2
            after = {
                item["interceptor_callsign"]: (item.get("intercept_point_lat"), item.get("intercept_point_lon"))
                for item in monitor.state.manual_intercepts
            }
            assert after != before
            assert all(lat is not None and lon is not None for lat, lon in after.values())
            assert broadcasts[-1]["type"] == "live"
            assert broadcasts[-1]["intercept_recalculated_at"] == summary["recalculated_at"]
        finally:
            await monitor.client.aclose()

    asyncio.run(scenario())


def test_intercept_page_has_live_map_recalc_and_multi_interceptor_wiring():
    root = Path(__file__).parents[1]
    index = (root / "app" / "static" / "index.html").read_text(encoding="utf-8")
    js = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
    css = (root / "app" / "static" / "styles.css").read_text(encoding="utf-8")
    main = (root / "app" / "main.py").read_text(encoding="utf-8")

    for element_id in (
        "intercept-map",
        "intercept-map-status",
        "intercept-map-summary",
        "intercept-map-fit-all",
        "intercept-map-auto-fit",
        "intercepts-recalculate-now",
        "intercept-recalc-state",
        "intercept-recalc-detail",
    ):
        assert f'id="{element_id}"' in index
    assert "RECALCULATE NOW" in index
    assert "ANTICIPATED INTERCEPT POINT" in index

    for function_name in (
        "renderInterceptTacticalMap",
        "ensureInterceptMap",
        "updateInterceptRecalcStatus",
        "recalculateInterceptsNow",
    ):
        assert f"function {function_name}" in js or f"async function {function_name}" in js
    assert "/api/intercepts/recalculate" in js
    assert "intercept_point_lat" in js
    assert "intercept_point_lon" in js
    assert "interceptRecalcBusy" in js
    assert "multiInterceptorSelection" in js

    assert '@app.post("/api/intercepts/recalculate")' in main
    assert ".intercept-tactical-panel" in css
    assert "#intercept-map" in css
    assert ".intercept-map-track" in css
