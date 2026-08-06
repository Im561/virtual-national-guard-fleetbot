from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
JS = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
CSS = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
MAIN = (ROOT / "app/main.py").read_text(encoding="utf-8")


def test_resizable_saved_console_layout_exists():
    assert 'id="rail-resizer"' in HTML
    assert 'data-panel-key="metrics"' in HTML
    assert 'data-panel-key="alerts"' in HTML
    assert 'data-panel-key="detail"' not in HTML
    assert 'id="detail-content"' not in HTML
    assert "vng-adoc.rail-width" in JS
    assert "vng-adoc.panel-height." in JS
    assert "initializeResizableLayout" in JS
    assert ".right-rail .alerts{flex:1 1 auto" in CSS
    assert ".right-rail .resizable-panel::after{display:none}" in CSS


def test_shared_accept_and_phase_api_are_wired():
    assert '/api/operations/{alert_id}/accept' in MAIN
    assert '/api/operations/{alert_id}/phases/{phase_id}' in MAIN
    assert 'ACCEPT INTERCEPT · MARK INBOUND' in JS
    assert 'CONSOLES INBOUND' in JS
    assert 'INTERCEPT PHASE CHECKLIST' in JS
    assert 'id="metric-inbound"' in HTML


def test_low_zoom_icons_avoid_unnecessary_altitude_speed_replacements():
    assert "state.iconDensity === 'full' ? Math.round((pilot.altitude || 0) / 100) : ''" in JS
    assert "record.positionKey !== nextPositionKey" in JS
    assert "interceptKey === state.interceptRenderKey" in JS
    assert "backdrop-filter:none" in CSS
