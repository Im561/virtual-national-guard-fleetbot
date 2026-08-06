from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
INDEX = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
STYLES = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")
LOGO = ROOT / "app" / "static" / "assets" / "vatsim-special-operations-logo.png"


def test_aircraft_type_classifier_and_silhouettes_are_present():
    assert "function aircraftCategory(pilot)" in APP_JS
    for category in ("fighter", "helicopter", "bomber", "military", "turboprop", "business", "airliner", "general"):
        assert f"{category}:" in APP_JS
    assert "tacticalAircraftSvg(pilot)" in APP_JS
    assert "aircraftCategory(pilot)" in APP_JS


def test_fighter_and_helicopter_designators_are_recognized():
    assert "F22" in APP_JS and "F35" in APP_JS and "F16" in APP_JS
    assert "UH" in APP_JS and "HH" in APP_JS and "H160" not in APP_JS  # H-prefix regex covers H160
    assert "H\\d{1,3}" in APP_JS


def test_exact_user_logo_is_bundled_in_upper_left_brand_block():
    assert LOGO.exists()
    assert LOGO.stat().st_size > 50_000
    assert "/static/assets/vatsim-special-operations-logo.png?v=1.4.9" in INDEX
    brand_start = INDEX.index('<div class="brand-block">')
    logo_index = INDEX.index('class="header-logo"', brand_start)
    title_index = INDEX.index('AIR DEFENSE OPERATIONS CENTER', brand_start)
    assert brand_start < logo_index < title_index
    assert "header-logo-wrap" not in INDEX
    assert ".brand-block .header-logo" in STYLES


def test_scope_datablock_includes_aircraft_type():
    assert "const typeCode = aircraftTypeCode(pilot);" in APP_JS
    assert "${altitude} ${speed} ${escapeHtml(typeCode)}" in APP_JS
