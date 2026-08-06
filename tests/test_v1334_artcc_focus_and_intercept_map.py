from pathlib import Path
import re

ROOT = Path(__file__).parents[1]
INDEX = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")


def test_single_artcc_focus_controls_and_filtering_are_present():
    assert 'id="artcc-focus-select"' in INDEX
    assert 'id="clear-artcc-focus"' in INDEX
    assert 'id="artcc-focus-status"' in INDEX
    assert "function applyArtccFocus" in JS
    assert "function pilotArtccRole" in JS
    assert "function focusedPilotCallsigns" in JS
    assert "pointInGeoJsonGeometry(pilot.lat, pilot.lon" in JS
    assert "pointInGeoJsonGeometry(pilot.arrival_lat, pilot.arrival_lon" in JS
    assert "localStorage.setItem('vng-adoc.artcc-focus'" in JS
    assert ".artcc-focus-control" in CSS


def test_dedicated_intercept_map_tracks_status_routes_and_predicted_points():
    assert 'id="intercept-map"' in INDEX
    assert 'id="intercept-map-fit-all"' in INDEX
    assert 'id="intercept-map-auto-fit"' in INDEX
    assert "function renderInterceptTacticalMap" in JS
    assert "intercept_point_lat" in JS and "intercept_point_lon" in JS
    assert "ANTICIPATED INTERCEPT POINT" in JS
    assert "target_response_status" in JS
    assert ".intercept-map-track" in CSS
    assert ".intercept-map-point" in CSS


def test_intercept_auto_fit_button_changes_state_once_per_click():
    match = re.search(
        r"el\('intercept-map-auto-fit'\)\.addEventListener\('click', \(\) => \{(?P<body>.*?)\n\}\);",
        JS,
        re.S,
    )
    assert match, "AUTO FIT click handler is missing"
    assert match.group("body").count("state.interceptMapAutoFit = !state.interceptMapAutoFit") == 1
