from pathlib import Path


def test_single_artcc_focus_is_present_and_drives_the_dashboard():
    root = Path(__file__).parents[1]
    index = (root / "app" / "static" / "index.html").read_text(encoding="utf-8")
    js = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
    css = (root / "app" / "static" / "styles.css").read_text(encoding="utf-8")
    main = (root / "app" / "main.py").read_text(encoding="utf-8")

    assert 'id="artcc-focus-select"' in index
    assert 'id="clear-artcc-focus"' in index
    assert 'id="artcc-focus-status"' in index
    assert "ALL ARTCCS / FIRS" in index

    for name in (
        "pointInGeoJsonGeometry",
        "pilotBaseRelevantToArtcc",
        "collectFocusedArtccCallsigns",
        "buildFocusedDashboardData",
        "populateArtccFocusSelector",
        "setArtccFocus",
        "fitMapToFocusedArtcc",
    ):
        assert f"function {name}" in js

    assert "state.rawData = incomingData" in js
    assert "const data = buildFocusedDashboardData(incomingData)" in js
    assert "pointInGeoJsonGeometry(pilot.arrival_lat, pilot.arrival_lon" in js
    assert "lengthSquared <= Number.EPSILON" in js
    assert "manual_intercepts: manualIntercepts" in js
    assert "renderCenterBoundaries(state.centerBoundaryData" in js
    assert "renderAtcCoverage(state.atcCoverageData" in js
    assert ".artcc-focus-status.active" in css
    assert 'APP_VERSION = "1.4.8"' in main


def test_artcc_focus_retains_intercept_relationships_and_recalculates_counts():
    js = (Path(__file__).parents[1] / "app" / "static" / "app.js").read_text(encoding="utf-8")
    assert "links.push([assignment.interceptor_callsign, assignment.target_callsign])" in js
    assert "links.push([pilot.callsign, pilot.intercept_assignment.target_callsign])" in js
    assert "links.push([interceptor.callsign, pilot.callsign])" in js
    assert "red_alerts: alerts.filter" in js
    assert "nordo_watches: pilots.filter" in js
    assert "frequency_mismatches: pilots.filter" in js
    assert "centers_online: controllers.filter" in js
