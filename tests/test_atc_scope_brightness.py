from pathlib import Path


def test_atc_scope_dims_tiles_not_operational_layers():
    root = Path(__file__).resolve().parents[1]
    css = (root / "app/static/styles.css").read_text(encoding="utf-8")
    assert '.leaflet-tile.basemap-atc-scope' in css
    assert '.map-panel[data-basemap]::after{display:none!important;content:none!important}' in css
    assert '.map-panel[data-basemap="atc-scope"]::after{display:none!important' in css
    assert '.leaflet-overlay-pane' in css
    assert '.leaflet-marker-pane' in css
    assert 'opacity:1!important;filter:none!important' in css
