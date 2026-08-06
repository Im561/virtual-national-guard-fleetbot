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


def test_manual_recalculation_updates_every_assigned_interceptor_and_broadcasts():
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
                ["VIPER11", "EAGLE21"], "AAL123", "TEST DESK"
            )
            assert ok is True and errors == {} and error is None
            first = {item["interceptor_callsign"]: item for item in assignments}
            first_separation = {key: value["separation_nm"] for key, value in first.items()}
            assert all(item.get("calculated_at") for item in assignments)

            # Move all three live tracks and change motion data, then force an
            # immediate recalculation from the current in-memory VATSIM state.
            one.update(lat=27.35, lon=-80.72, heading=105, groundspeed=515, altitude=29500)
            two.update(lat=27.05, lon=-80.95, heading=85, groundspeed=485, altitude=31000)
            target.update(lat=28.05, lon=-79.82, heading=115, groundspeed=445, altitude=34000)
            broadcasts.clear()
            before_revision = monitor.state.revision

            recalculated = await monitor.recalculate_intercepts("TEST DESK")
            second = {item["interceptor_callsign"]: item for item in recalculated}

            assert set(second) == {"VIPER11", "EAGLE21"}
            assert monitor.state.revision == before_revision + 1
            assert broadcasts and broadcasts[-1]["manual_intercepts"]
            assert all(second[key]["separation_nm"] != first_separation[key] for key in second)
            assert second["VIPER11"]["interceptor"]["heading"] == 105
            assert second["VIPER11"]["interceptor"]["groundspeed"] == 515
            assert second["EAGLE21"]["interceptor"]["altitude"] == 31000
            assert all(item["target"]["heading"] == 115 for item in second.values())
            assert all(item["target"]["groundspeed"] == 445 for item in second.values())
            assert all(item.get("calculated_at") for item in second.values())
        finally:
            await monitor.client.aclose()

    asyncio.run(scenario())


def test_intercept_workspace_exposes_live_recalc_multi_select_and_draft_safety():
    root = Path(__file__).parents[1]
    index = (root / "app" / "static" / "index.html").read_text(encoding="utf-8")
    js = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
    css = (root / "app" / "static" / "styles.css").read_text(encoding="utf-8")
    main = (root / "app" / "main.py").read_text(encoding="utf-8")
    vatsim = (root / "app" / "vatsim.py").read_text(encoding="utf-8")

    assert 'id="intercepts-recalculate-now"' in index
    assert 'id="intercept-recalc-state"' in index
    assert 'id="intercept-recalc-detail"' in index
    assert 'id="intercept-selected-list"' in index
    assert 'id="assign-selected-interceptors"' in index and "disabled" in index
    assert "updateInterceptRecalcStatus" in js
    assert "recalculateInterceptsNow" in js
    assert "'/api/intercepts/recalculate'" in js
    assert "state.interceptNoteDrafts" in js
    assert "item.pilot.vsoa && !item.assignedTarget" in js
    assert "ASSIGN ${callsigns.length} SELECTED" in js
    assert "TARGET H/S/A" in js and "LAST RECALC" in js
    assert '@app.post("/api/intercepts/recalculate")' in main
    assert "async def recalculate_intercepts" in vatsim
    assert '"calculated_at": now_iso' in vatsim
    assert ".intercept-recalc-status" in css
    assert ".intercept-selected-list" in css
    assert ".interceptor-live-calcs" in css
    assert ".intercept-note-control input.dirty" in css
