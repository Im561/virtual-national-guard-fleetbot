from pathlib import Path


def test_basemap_selector_and_modes_present():
    root = Path(__file__).resolve().parents[1]
    html = (root / "app/static/index.html").read_text(encoding="utf-8")
    js = (root / "app/static/app.js").read_text(encoding="utf-8")
    assert 'id="basemap-select"' in html
    for mode in ("dark-satellite", "satellite", "dark-gray", "topographic", "atc-scope"):
        assert mode in html
        assert mode in js
    assert "function setBasemap" in js
    assert "vng-adoc.basemap" in js


def test_atc_scope_grid_present_without_floating_hud():
    root = Path(__file__).resolve().parents[1]
    html = (root / "app/static/index.html").read_text(encoding="utf-8")
    js = (root / "app/static/app.js").read_text(encoding="utf-8")
    css = (root / "app/static/styles.css").read_text(encoding="utf-8")
    assert 'id="scope-hud"' not in html
    assert "function updateScopeGrid()" in js
    assert "scopeRangeNm" in js
    assert ".leaflet-tile.basemap-atc-scope" in css
    assert '.map-panel[data-basemap="atc-scope"]' in css


def test_compact_docked_map_menu_present():
    root = Path(__file__).resolve().parents[1]
    html = (root / "app/static/index.html").read_text(encoding="utf-8")
    js = (root / "app/static/app.js").read_text(encoding="utf-8")
    css = (root / "app/static/styles.css").read_text(encoding="utf-8")
    for name in ("layers", "regions", "tools"):
        assert f'data-map-menu="{name}"' in html
        assert f'data-map-menu-panel="{name}"' in html
    assert "function setMapMenuPanel" in js
    assert ".map-control-dock" in css
    assert "grid-template-rows:auto minmax(0,1fr)" in css
