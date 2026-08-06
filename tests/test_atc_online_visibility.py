from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
INDEX = (ROOT / "app/static/index.html").read_text(encoding="utf-8")


def test_live_atc_uses_separate_label_pane_and_visible_online_label():
    assert "map.createPane('atcLabels')" in APP_JS
    assert "map.getPane('atcLabels').style.pointerEvents = 'none'" in APP_JS
    assert 'class="atc-online-label-box"' in APP_JS
    assert "atc-online-pulse" in APP_JS
    assert "· ONLINE" in APP_JS
    assert ".atc-online-label-box" in STYLES
    assert ".atc-online-pulse" in STYLES
    assert "LIVE CENTER ATC" in INDEX
    assert "LIVE APP/DEP ATC" in INDEX


def test_active_coverage_has_halo_solid_exact_outline_and_stronger_fill():
    assert "function atcHaloStyle(item)" in APP_JS
    assert "weight: exact ? 8 : 5.5" in APP_JS
    assert "weight: exact ? 2.7 : 1.8" in APP_JS
    assert "fillOpacity: exact ? 0.09 : 0.045" in APP_JS
    assert "dashArray: exact ? null : '7 6'" in APP_JS
    assert "layers.push(halo)" in APP_JS


def test_published_reference_boundaries_are_dimmed_against_live_atc():
    assert "weight: 0.85, opacity: 0.42" in APP_JS
    assert "weight: 0.95, opacity: 0.44" in APP_JS
    assert "fillOpacity: 0.008" in APP_JS
