import time
from pathlib import Path

import pytest

from app.airports import AirportResolver
from app.detection import DetectionEngine


def exact_den_coverage():
    return [
        {
            "callsign": "DEN_17_CTR",
            "facility": "CTR",
            "online_seconds": 900,
            "frequencies_hz": [127650000],
            "frequencies": [127.65],
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-106, 37], [-102, 37], [-102, 41], [-106, 41], [-106, 37]]],
            },
            "bbox": [-106, 37, -102, 41],
            "transceivers": [
                {
                    "id": 1,
                    "frequency": 127650000,
                    "lat": 39.1,
                    "lon": -104.1,
                    "height_msl_m": 1655,
                    "height_agl_m": 20,
                }
            ],
            "match_quality": "exact_sector",
            "sector_specific": True,
            "source": "VATSpy exact subsector",
        }
    ]


def pilot(remarks=""):
    return {
        "cid": 3,
        "callsign": "NORDO1",
        "latitude": 39.0,
        "longitude": -104.0,
        "altitude": 30000,
        "groundspeed": 420,
        "heading": 90,
        "transponder": "3456",
        "flight_plan": {
            "flight_rules": "I",
            "aircraft_short": "A320",
            "departure": "KDEN",
            "arrival": "KLAX",
            "remarks": remarks,
        },
    }


def test_five_minute_exact_coverage_mismatch_escalates_to_investigate_without_intercept_alert():
    engine = DetectionEngine(AirportResolver())
    item = pilot()
    engine.evaluate([item], [], {"NORDO1": [{"frequency": 122800000}]}, exact_den_coverage())
    engine.memory["NORDO1"].condition_started["nordo_1228"] = time.time() - 360
    display, alerts = engine.evaluate(
        [item], [], {"NORDO1": [{"frequency": 122800000}]}, exact_den_coverage()
    )
    assert not alerts
    assert display[0]["severity"] == "green"
    assert display[0]["nordo_watch"]["level"] == "orange"
    assert display[0]["nordo_watch"]["title"] == "POSSIBLE NORDO — INVESTIGATE"


def test_prior_controller_match_escalates_watch_after_twelve_minutes_without_scramble():
    engine = DetectionEngine(AirportResolver())
    item = pilot()
    engine.evaluate([item], [], {"NORDO1": [{"frequency": 127650000}]}, exact_den_coverage())
    assert engine.memory["NORDO1"].last_controller_match is not None
    engine.evaluate([item], [], {"NORDO1": [{"frequency": 122800000}]}, exact_den_coverage())
    engine.memory["NORDO1"].condition_started["nordo_1228"] = time.time() - 780
    display, alerts = engine.evaluate(
        [item], [], {"NORDO1": [{"frequency": 122800000}]}, exact_den_coverage()
    )
    assert not alerts
    assert display[0]["nordo_watch"]["level"] == "orange"
    assert "previously matching" in display[0]["nordo_watch"]["detail"]
    assert display[0]["recommended_base"] is None


def test_1228_outside_confirmed_coverage_never_creates_watch():
    engine = DetectionEngine(AirportResolver())
    item = pilot()
    engine.evaluate([item], [], {"NORDO1": [{"frequency": 122800000}]}, [])
    engine.memory["NORDO1"].condition_started["nordo_1228"] = time.time() - 3600
    display, alerts = engine.evaluate([item], [], {"NORDO1": [{"frequency": 122800000}]}, [])
    assert not alerts
    assert display[0]["nordo_watch"] is None
    assert any(o["code"] == "1228_OUTSIDE_COVERAGE" for o in display[0]["observations"])


def test_exact_vsoa_marker_highlights_track_without_alerting():
    engine = DetectionEngine(AirportResolver())
    item = pilot("/VSOA/ TRAINING FLIGHT")
    display, alerts = engine.evaluate([item], [], {}, [])
    assert display[0]["vsoa"] is True
    assert display[0]["vsoa_label"] == "VSOA"
    assert not alerts


@pytest.mark.parametrize(
    ("remarks", "expected_label"),
    [
        ("OPR/vUSCG WWW.VUSCG.COM", "vUSCG"),
        ("MEMBER vRCAF / NORAD TRAINING", "vRCAF"),
        ("V-USAF SPECIAL OPERATIONS", "vUSAF"),
        ("VDHS BORDER PATROL", "vDHS"),
        ("VAIRMED SAR TRAINING", "vAirMed"),
        ("VATSIM SPECIAL OPERATIONS ASSOCIATION MEMBER", "VSOA"),
    ],
)
def test_recognized_vsoa_organization_markers_highlight_track(remarks, expected_label):
    engine = DetectionEngine(AirportResolver())
    display, alerts = engine.evaluate([pilot(remarks)], [], {}, [])
    assert display[0]["vsoa"] is True
    assert display[0]["vsoa_label"] == expected_label
    assert display[0]["navigation_exemption_reason"] == "VSOA"
    assert not alerts


@pytest.mark.parametrize(
    "remarks",
    [
        "NOTAVSOATEST",
        "NOTVUSCGTEST",
        "VFR VATSIM CLIENT",
        "RCAF ROUTE REFERENCE",
        "USCG AUXILIARY REFERENCE",
    ],
)
def test_incidental_text_does_not_trigger_vsoa_marker(remarks):
    engine = DetectionEngine(AirportResolver())
    display, _ = engine.evaluate([pilot(remarks)], [], {}, [])
    assert display[0]["vsoa"] is False


def test_route_deviation_is_observation_only_by_default():
    engine = DetectionEngine(AirportResolver())
    item = {
        "cid": 7,
        "callsign": "OFFROUTE1",
        "latitude": 45.0,
        "longitude": -100.0,
        "altitude": 35000,
        "groundspeed": 450,
        "heading": 90,
        "transponder": "3456",
        "flight_plan": {
            "flight_rules": "I",
            "aircraft_short": "B738",
            "departure": "KJFK",
            "arrival": "KLAX",
        },
    }
    engine.evaluate([item], [], {}, [])
    engine.memory["OFFROUTE1"].condition_started["route_corridor"] = time.time() - 700
    display, alerts = engine.evaluate([item], [], {}, [])
    assert not alerts
    assert any(o["code"] == "ROUTE_CORRIDOR" for o in display[0]["observations"])


def test_volume_toolbar_and_watch_ui_exist():
    root = Path(__file__).resolve().parents[1]
    html = (root / "app/static/index.html").read_text(encoding="utf-8")
    js = (root / "app/static/app.js").read_text(encoding="utf-8")
    css = (root / "app/static/styles.css").read_text(encoding="utf-8")
    assert 'id="alert-volume"' in html
    assert 'id="toggle-map-controls"' in html
    assert 'id="nordo-watch-list"' in html
    assert 'id="metric-mismatch"' in html
    assert 'COMMS / NORDO WATCH' in html
    assert "vng-adoc.alert-volume" in js
    assert "vng-adoc.map-controls-expanded" in js
    assert "vng-adoc.local-acknowledged" in js
    assert "WRONG-FREQ TIMER" in js
    assert "AUTO-FLAG ELIGIBLE TIMER" in js
    assert ".vsoa-detail" in css
    assert "vsoaMarkerLabel" in js
    assert "VSOA MARKER" in js
    assert "does not verify membership or authorization" in js
    assert ".nordo-watch-card" in css
