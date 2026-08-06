from pathlib import Path

ROOT = Path(__file__).parents[1]
INDEX = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")
MAIN = (ROOT / "app" / "main.py").read_text(encoding="utf-8")


def test_atc_workspace_exposes_operator_vsoa_selection_and_target_dispatch():
    assert 'id="atc-operator-aircraft-input"' in INDEX
    assert 'id="atc-save-operator-aircraft"' in INDEX
    assert 'id="atc-vsoa-aircraft-options"' in INDEX
    assert "TARGET / CASE AIRCRAFT" in INDEX
    assert "MY VSOA AIRCRAFT" in INDEX
    assert "function liveVsoaAircraft" in JS
    assert "function operatorAircraftPilot" in JS
    assert "function atcVsoaRosterHtml" in JS
    assert "function atcOperatorDispatchHtml" in JS
    assert "function assignOperatorAircraftToTarget" in JS
    assert "data-atc-dispatch-operator" in JS
    assert "'/api/intercepts/manual/batch'" in JS
    assert "vng-adoc.operator-aircraft" in JS


def test_vsoa_operator_is_airborne_and_explicitly_remarked_before_dispatch():
    assert ".filter(pilot => pilot?.vsoa && !pilot?.on_ground)" in JS
    assert "if (!pilot || !pilot.vsoa || pilot.on_ground)" in JS
    assert "if (!interceptor?.vsoa || interceptor?.on_ground)" in JS
    assert "availableVsoa.length === 1" in JS
    assert "VSOA-tagged flights are detected from explicit flight-plan remarks" in JS


def test_atc_map_shows_operator_aircraft_and_pending_assignment_route():
    assert "atc-map-operator-label" in JS
    assert "MY VSOA AIRCRAFT" in JS
    assert "PENDING ASSIGNMENT" in JS
    assert ".atc-map-legend i.operator" in CSS
    assert ".atc-operator-dispatch" in CSS
    assert ".atc-vsoa-aircraft-card" in CSS


def test_v144_deployment_identity():
    assert 'data-build="1.4.8"' in INDEX
    assert "v1.4.8" in INDEX
    assert 'APP_VERSION = "1.4.8"' in MAIN
    assert 'UI_BUILD_ID = "v1.4.8-deep-audit-reliability"' in MAIN
