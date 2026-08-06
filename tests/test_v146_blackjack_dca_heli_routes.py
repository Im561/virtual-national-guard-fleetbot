from pathlib import Path

from app.detection import detect_blackjack_unit

ROOT = Path(__file__).parents[1]
INDEX = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
JS = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
CSS = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
MAIN = (ROOT / "app/main.py").read_text(encoding="utf-8")


def test_blackjack_detection_is_helicopter_location_and_identity_constrained():
    assert detect_blackjack_unit("BLACKJACK1", "VUSCG NCRAD", "MH65", 38.85, -77.04)
    assert detect_blackjack_unit("BJK2", "", "AS65", 38.85, -77.04)
    assert detect_blackjack_unit("BLKJK3", "", "MH65", 38.85, -77.04)
    assert detect_blackjack_unit("CG6501", "VUSCG BLACK JACK NCR", "MH65", 38.85, -77.04)
    assert not detect_blackjack_unit("BLACKJACK1", "VUSCG", "B738", 38.85, -77.04)
    assert not detect_blackjack_unit("BLACKJACK1", "VUSCG", "MH65", 34.00, -118.00)
    assert not detect_blackjack_unit("N12345", "HELICOPTER", "MH65", 38.85, -77.04)


def test_dca_heli_route_controls_and_current_chart_link_exist():
    assert 'id="toggle-dca-heli-routes"' in INDEX
    assert 'id="open-dca-heli-chart"' in INDEX
    assert '07-09-2026/PDFs/Balt-Wash_Heli.pdf' in INDEX
    assert 'DCA HELICOPTER ROUTE REFERENCE' in INDEX
    assert 'CLOSED ROUTE SEGMENT' in INDEX


def test_dca_reference_overlay_and_blackjack_ui_are_wired():
    assert "const DCA_HELI_ROUTES" in JS
    assert "WASHINGTON ROUTE 1" in JS
    assert "WASHINGTON ROUTE 5" in JS
    assert "BROAD CREEK TRANSITION" in JS
    assert "ROUTE 4 · CLOSED SEGMENT" in JS
    assert "function renderDcaHeliRoutes" in JS
    assert "function toggleDcaHeliRoutes" in JS
    assert "vng-adoc.dca-heli-routes" in JS
    assert "if (pilot?.blackjack) return 'BLACKJACK'" in JS
    assert "SPECIAL UNIT" in JS and "MISSION ROLE" in JS
    assert ".dca-heli-map-label" in CSS
    assert ".scope-tag.vsoa.blackjack" in CSS
    assert 'UI_BUILD_ID = "v1.4.8-deep-audit-reliability"' in MAIN
    assert '"blackjack_recognition": True' in MAIN
    assert '"dca_heli_route_reference": True' in MAIN
