from pathlib import Path

ROOT=Path(__file__).parents[1]
HTML=(ROOT/"app/static/index.html").read_text()
JS=(ROOT/"app/static/app.js").read_text()
CSS=(ROOT/"app/static/styles.css").read_text()

def test_aircraft_hover_overlay_is_permanently_removed():
    assert 'id="toggle-hover-details"' not in HTML
    assert "hoverCardsEnabled" not in JS
    assert "scheduleAircraftHover" not in JS
    assert "marker.on('mouseover'" not in JS
    assert ".aircraft-hover-tooltip{display:none!important" in CSS

def test_click_opens_detailed_track_popup():
    assert "marker.on('click'" in JS
    assert "marker.bindPopup(aircraftPopup(current)" in JS
    assert "REPORTED RADIO(S)" in JS
    assert "ASSIGNED SQUAWK" in JS
