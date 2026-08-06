from pathlib import Path

from app.airports import AirportResolver
from app.detection import DetectionEngine


def _pilot(callsign="UAL15"):
    return {
        "cid": 15,
        "callsign": callsign,
        "latitude": 39.0,
        "longitude": -104.0,
        "altitude": 35000,
        "groundspeed": 460,
        "heading": 90,
        "transponder": "1234",
        "flight_plan": {
            "flight_rules": "I",
            "aircraft_short": "B789",
            "departure": "KDEN",
            "arrival": "EGLL",
        },
    }


def test_manual_nordo_creates_immediate_shared_red_alert():
    engine = DetectionEngine(AirportResolver())
    record = engine.mark_manual_nordo("ual15")
    display, alerts = engine.evaluate([_pilot()], [], {}, [], [])

    assert record["callsign"] == "UAL15"
    assert len(alerts) == 1
    assert alerts[0]["callsign"] == "UAL15"
    assert alerts[0]["severity"] == "red"
    assert alerts[0]["requires_ack"] is True
    assert alerts[0]["recommended_base"] is not None
    assert display[0]["manual_nordo"] is True
    assert display[0]["nordo_watch"]["title"] == "MANUAL NORDO"
    assert any(reason["code"] == "MANUAL_NORDO" for reason in display[0]["reasons"])


def test_clearing_manual_nordo_removes_manual_alert():
    engine = DetectionEngine(AirportResolver())
    engine.mark_manual_nordo("UAL15")
    assert engine.clear_manual_nordo("UAL15") is True
    display, alerts = engine.evaluate([_pilot()], [], {}, [], [])
    assert alerts == []
    assert display[0]["manual_nordo"] is False


def test_manual_nordo_ui_and_api_are_wired():
    js = Path("app/static/app.js").read_text(encoding="utf-8")
    main = Path("app/main.py").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert "MARK AIRCRAFT NORDO" in js
    assert "CLEAR MANUAL NORDO" in js
    assert "data-atc-action" in js
    assert "mark-nordo" in js
    assert '/api/tracks/{callsign}/manual-nordo' in main
    assert '.manual-nordo-control' in css
