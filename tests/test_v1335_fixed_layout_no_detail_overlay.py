from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
JS = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
CSS = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")


def test_legacy_selected_track_nordo_overlay_is_completely_removed():
    assert 'id="detail-content"' not in HTML
    assert 'id="selected-severity"' not in HTML
    assert 'data-panel-key="detail"' not in HTML
    assert "TRACK / INTERCEPT DATA" not in HTML
    assert "NORDO WORKFLOW" not in HTML
    assert "el('detail-content').addEventListener" not in JS


def test_fixed_rail_cannot_cover_map_and_dedicated_workspaces_remain():
    assert '.right-rail .alerts{flex:1 1 auto' in CSS
    assert '.right-rail .resizable-panel::after{display:none}' in CSS
    assert 'id="intercept-workspace"' in HTML
    assert 'id="atc-workspace"' in HTML
    assert 'id="intercept-map"' in HTML
    assert 'id="atc-map"' in HTML
