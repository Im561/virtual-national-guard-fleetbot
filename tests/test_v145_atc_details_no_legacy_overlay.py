from pathlib import Path

ROOT = Path(__file__).parents[1]
HTML = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
JS = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
CSS = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
MAIN = (ROOT / "app/main.py").read_text(encoding="utf-8")


def test_legacy_selected_track_and_hover_overlays_are_permanently_removed():
    assert 'id="toggle-hover-details"' not in HTML
    assert "function renderDetail" not in JS
    assert "function aircraftHoverTooltip" not in JS
    assert "scheduleAircraftHover" not in JS
    assert "marker.on('mouseover'" not in JS
    assert "#selected-track-overlay" in CSS
    assert ".aircraft-hover-tooltip{display:none!important" in CSS


def test_atc_uses_polished_native_aircraft_selectors():
    assert 'id="atc-operator-aircraft-select"' in HTML
    assert 'id="atc-track-select"' in HTML
    assert "function renderAtcAircraftSelectors" in JS
    assert ".atc-selection-toolbar" in CSS
    assert "ACTIVE CASES" in JS and "ALL LIVE AIRCRAFT" in JS


def test_atc_and_click_popup_restore_radio_and_squawk_details():
    for label in ["REPORTED RADIO(S)", "EXPECTED FREQUENCY", "CURRENT SQUAWK", "ASSIGNED SQUAWK", "SQUAWK COMPARISON"]:
        assert label in JS
    assert "assigned_squawk" in JS
    assert "formatPilotRadios(pilot)" in JS
    assert "active_artcc_frequencies || pilot.center_frequencies" in JS
    assert ".atc-aircraft-detail-grid" in CSS
    assert ".aircraft-click-card" in CSS


def test_v145_identity():
    assert 'data-build="1.4.8"' in HTML
    assert 'APP_VERSION = "1.4.8"' in MAIN
    assert 'UI_BUILD_ID = "v1.4.8-deep-audit-reliability"' in MAIN
