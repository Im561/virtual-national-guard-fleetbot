from pathlib import Path

from app.airports import AirportResolver
from app.detection import DetectionEngine


def test_aircraft_payload_contains_flight_plan_endpoint_coordinates():
    engine = DetectionEngine(AirportResolver())
    pilot = {
        "cid": 991,
        "callsign": "AAL123",
        "latitude": 37.0,
        "longitude": -90.0,
        "altitude": 36000,
        "groundspeed": 450,
        "heading": 75,
        "transponder": "1200",
        "flight_plan": {
            "flight_rules": "I",
            "aircraft_short": "B738",
            "departure": "KATL",
            "arrival": "KJFK",
            "route": "KATL DCT SPA J14 RIC DCT KJFK",
        },
    }
    display, _ = engine.evaluate([pilot], [], {}, [], [])
    track = display[0]
    assert track["flight_rules"] == "I"
    assert track["departure_lat"] == 33.6407
    assert track["departure_lon"] == -84.4277
    assert track["arrival_lat"] == 40.6413
    assert track["arrival_lon"] == -73.7781
    assert "SPA" in track["route"]


def test_click_route_preview_is_present_without_hover_overlay():
    root = Path(__file__).resolve().parents[1]
    js = (root / "app/static/app.js").read_text(encoding="utf-8")
    css = (root / "app/static/styles.css").read_text(encoding="utf-8")
    html = (root / "app/static/index.html").read_text(encoding="utf-8")
    for token in (
        "function updateAircraftTrackHistory(pilot)",
        "function renderFlightPlanPreview(callsign)",
        "function fetchTrackHistory(callsign, force = false)",
        "normalizedTrackHistory(callsign)",
        "aircraftTrackHistory",
        "serverTrackHistory",
        "flightPlanPreviewLayerGroup",
    ):
        assert token in js
    assert 'id="toggle-hover-details"' not in html
    assert "function aircraftHoverTooltip" not in js
    assert ".aircraft-hover-tooltip{display:none!important" in css


def test_click_popup_and_shared_history_endpoint_are_used():
    root = Path(__file__).resolve().parents[1]
    js = (root / "app/static/app.js").read_text(encoding="utf-8")
    main = (root / "app/main.py").read_text(encoding="utf-8")
    assert "function aircraftPopup(pilot)" in js
    assert "marker.on('click'" in js
    assert "/api/tracks/${encodeURIComponent(callsign)}/history" in js
    assert '@app.get("/api/tracks/{callsign}/history")' in main


def test_observed_trail_draws_after_filed_endpoint_reference():
    root = Path(__file__).resolve().parents[1]
    js = (root / "app/static/app.js").read_text(encoding="utf-8")
    filed = js.index("if (hasDeparture && hasArrival)")
    observed = js.index("Draw observed history after the filed endpoint reference")
    assert observed > filed
    assert "weight: 2.8" in js
