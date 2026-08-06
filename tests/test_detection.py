import time

from app.airports import AirportResolver
from app.atc_boundaries import AtcBoundaryStore
from app.bases import recommend_base
from app.config import settings
from app.detection import DetectionEngine
from app.geometry import (
    destination_point,
    haversine_nm,
    is_canada_region,
    is_monitored_region,
    is_us_region,
    point_in_geojson_geometry,
    point_in_polygon,
)


def test_distance_reasonable():
    assert 180 < haversine_nm(30.4941, -81.6879, 33.6407, -84.4277) < 300


def test_polygon_and_geojson():
    square = [[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]
    assert point_in_polygon(0, 0, square)
    assert not point_in_polygon(3, 3, square)
    geometry = {"type": "Polygon", "coordinates": [square]}
    assert point_in_geojson_geometry(0, 0, geometry)
    assert not point_in_geojson_geometry(3, 3, geometry)


def test_destination_projection():
    lat, lon = destination_point(30.0, -80.0, 90, 60)
    assert 29.8 < lat < 30.2
    assert lon > -79.0


def test_nearest_base_southeast():
    base = recommend_base(30.5, -82.0)
    assert base is not None
    assert base["icao"] in {"KJAX", "KOZR"}


def test_center_alias_matches_vatspy_boundary():
    store = AtcBoundaryStore()
    store.fir_features = [
        {
            "type": "Feature",
            "properties": {"id": "ZDV", "name": "Denver ARTCC"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-110, 35], [-100, 35], [-100, 45], [-110, 45], [-110, 35]]],
            },
        }
    ]
    controller = {"callsign": "DEN_CTR", "frequency": "127.650", "visual_range": 350}
    audio = {
        "DEN_CTR": [
            {"frequency": 127650000, "latDeg": 39.8, "lonDeg": -104.7}
        ]
    }
    coverage = store.build_coverage([controller], audio)
    assert len(coverage) == 1
    assert coverage[0]["boundary_id"] == "ZDV"
    assert coverage[0]["geometry"] is not None


def test_1200_and_2000_are_whitelisted_for_squawk_anomaly_scoring():
    assert {"1200", "2000"}.issubset(settings.whitelisted_squawk_set)
    engine = DetectionEngine(AirportResolver())
    pilots = [
        {
            "cid": 1,
            "callsign": "VFR1200",
            "latitude": 38.0,
            "longitude": -98.0,
            "altitude": 7500,
            "groundspeed": 130,
            "heading": 90,
            "transponder": "1200",
            "flight_plan": {"flight_rules": "V", "aircraft_short": "C172"},
        },
        {
            "cid": 2,
            "callsign": "IFR2000",
            "latitude": 39.0,
            "longitude": -97.0,
            "altitude": 18000,
            "groundspeed": 300,
            "heading": 90,
            "transponder": "2000",
            "flight_plan": {
                "flight_rules": "I",
                "aircraft_short": "B738",
                "assigned_transponder": "3456",
            },
        },
    ]
    display, alerts = engine.evaluate(pilots, [], {}, [])
    assert not alerts
    assert all(not item["reasons"] for item in display)


def test_generic_center_facility_plus_live_transceiver_is_high_confidence():
    engine = DetectionEngine(AirportResolver())
    pilot = {
        "cid": 3,
        "callsign": "NORDO1",
        "latitude": 39.0,
        "longitude": -104.0,
        "altitude": 30000,
        "groundspeed": 420,
        "heading": 90,
        "transponder": "3456",
        "flight_plan": {"flight_rules": "I", "aircraft_short": "A320"},
    }
    coverage = [{
        "callsign": "DEN_CTR",
        "facility": "CTR",
        "online_seconds": 900,
        "frequencies_hz": [127650000],
        "frequencies": [127.65],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-110, 35], [-100, 35], [-100, 45], [-110, 45], [-110, 35]]],
        },
        "bbox": [-110, 35, -100, 45],
        "transceivers": [{
            "id": 1, "frequency": 127650000, "lat": 39.8, "lon": -104.7,
            "height_msl_m": 1655, "height_agl_m": 20,
        }],
        "match_quality": "facility",
        "sector_specific": False,
        "source": "VATSpy facility boundary",
    }]
    audio = {"NORDO1": [{"frequency": 122800000}]}
    engine.evaluate([pilot], [], audio, coverage)
    engine.memory["NORDO1"].condition_started["nordo_1228"] = time.time() - 301
    display, alerts = engine.evaluate([pilot], [], audio, coverage)
    assert display[0]["center"] == "DEN_CTR"
    assert display[0]["coverage_confidence"] == "HIGH"
    assert display[0]["nordo_watch"] is not None
    assert not alerts

def test_complete_us_coverage_boxes():
    assert is_us_region(40.7, -74.0)      # contiguous states
    assert is_us_region(61.2, -149.9)     # Alaska
    assert is_us_region(21.3, -157.8)     # Hawaii
    assert is_us_region(13.5, 144.8)      # Guam
    assert is_us_region(-14.3, -170.7)    # American Samoa
    assert is_us_region(52.0, 179.0)      # western Aleutians


def test_faa_prohibited_airspace_creates_mandatory_ack_alert():
    engine = DetectionEngine(AirportResolver())
    pilot = {
        "cid": 10,
        "callsign": "TESTP1",
        "latitude": 38.0,
        "longitude": -98.0,
        "altitude": 10000,
        "groundspeed": 250,
        "heading": 90,
        "transponder": "1200",
        "flight_plan": {"flight_rules": "V", "aircraft_short": "C172"},
    }
    area = {
        "id": "PTEST",
        "designation": "P-TEST",
        "category": "PROHIBITED",
        "floor_ft": 0,
        "ceiling_ft": 18000,
        "floor_label": "SFC",
        "ceiling_label": "18,000 FT",
        "bbox": [-99, 37, -97, 39],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-99, 37], [-97, 37], [-97, 39], [-99, 39], [-99, 37]]],
        },
    }
    display, alerts = engine.evaluate([pilot], [], {}, [], [area])
    assert display[0]["confidence"] >= 90
    assert display[0]["requires_ack"] is True
    assert alerts[0]["requires_ack"] is True
    assert any(reason["code"].startswith("FAA_PROHIBITED") for reason in alerts[0]["reasons"])

    engine.acknowledge(alerts[0]["id"])
    _, acknowledged_alerts = engine.evaluate([pilot], [], {}, [], [area])
    assert acknowledged_alerts[0]["acknowledged"] is True
    assert acknowledged_alerts[0]["requires_ack"] is False


def test_restricted_airspace_alone_does_not_claim_90_percent_confidence():
    engine = DetectionEngine(AirportResolver())
    pilot = {
        "cid": 11,
        "callsign": "TESTR1",
        "latitude": 38.0,
        "longitude": -98.0,
        "altitude": 10000,
        "groundspeed": 250,
        "heading": 90,
        "transponder": "1200",
        "flight_plan": {"flight_rules": "V", "aircraft_short": "C172"},
    }
    area = {
        "id": "RTEST",
        "designation": "R-TEST",
        "category": "RESTRICTED",
        "floor_ft": 0,
        "ceiling_ft": 18000,
        "floor_label": "SFC",
        "ceiling_label": "18,000 FT",
        "bbox": [-99, 37, -97, 39],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-99, 37], [-97, 37], [-97, 39], [-99, 39], [-99, 37]]],
        },
    }
    display, alerts = engine.evaluate([pilot], [], {}, [], [area])
    assert display[0]["confidence"] == 0
    assert display[0]["requires_ack"] is False
    assert display[0]["severity"] == "green"
    assert any(item["code"].startswith("FAA_RESTRICTED") for item in display[0]["observations"])
    assert not alerts



def test_canada_is_monitored_region():
    assert is_canada_region(43.68, -79.63)  # Toronto
    assert is_canada_region(49.19, -123.18)  # Vancouver
    assert is_canada_region(63.75, -68.55)  # Iqaluit
    assert is_monitored_region(43.68, -79.63)


def test_7777_is_fighter_display_only():
    engine = DetectionEngine(AirportResolver())
    pilot = {
        "cid": 7777,
        "callsign": "VIPER11",
        "latitude": 45.0,
        "longitude": -75.0,
        "altitude": 24000,
        "groundspeed": 430,
        "heading": 270,
        "transponder": "7777",
        "flight_plan": {"flight_rules": "I", "aircraft_short": "F22"},
    }
    display, alerts = engine.evaluate([pilot], [], {}, [])
    assert display[0]["display_class"] == "fighter"
    assert display[0]["region"] in {"UNITED STATES", "CANADA"}
    assert not display[0]["reasons"]
    assert not alerts


def test_recommend_base_returns_intercept_solution():
    base = recommend_base(38.9, -77.0, target_heading=270, target_speed_kt=420, target_altitude_ft=35000)
    assert base is not None
    assert 'intercept_course_deg' in base
    assert 0 <= base['intercept_course_deg'] <= 359
    assert base['intercept_total_minutes'] >= base['launch_delay_minutes']
    assert base['intercept_point_label']


def test_squawk_7777_is_shown_as_active_intercept_track():
    engine = DetectionEngine(AirportResolver())
    pilot = {
        'cid': 77,
        'callsign': 'REDEYE11',
        'latitude': 38.0,
        'longitude': -97.0,
        'altitude': 25000,
        'groundspeed': 420,
        'heading': 90,
        'transponder': '7777',
        'flight_plan': {'flight_rules': 'I', 'aircraft_short': 'F22'},
    }
    display, alerts = engine.evaluate([pilot], [], {}, [])
    assert display[0]['active_intercept'] is True
    assert display[0]['track_color'] == 'yellow'
    assert not alerts


def test_7777_is_active_interceptor_yellow_without_alert():
    engine = DetectionEngine(AirportResolver())
    pilot = {
        'cid': 7777,
        'callsign': 'REDEYE11',
        'latitude': 39.0,
        'longitude': -104.0,
        'altitude': 28000,
        'groundspeed': 480,
        'heading': 90,
        'transponder': '7777',
        'flight_plan': {
            'flight_rules': 'I',
            'aircraft_short': 'F22',
            'assigned_transponder': '3456',
        },
    }
    display, alerts = engine.evaluate([pilot], [], {}, [], [])
    assert not alerts
    assert display[0]['active_intercept'] is True
    assert display[0]['track_color'] == 'yellow'
    assert display[0]['alert_id'] is None


def test_7777_interceptor_associates_with_active_alert():
    engine = DetectionEngine(AirportResolver())
    target = {
        'cid': 1,
        'callsign': 'TARGET1',
        'latitude': 39.0,
        'longitude': -103.0,
        'altitude': 30000,
        'groundspeed': 420,
        'heading': 90,
        'transponder': '7700',
        'flight_plan': {'flight_rules': 'I', 'aircraft_short': 'B738'},
    }
    fighter = {
        'cid': 2,
        'callsign': 'REDEYE11',
        'latitude': 39.0,
        'longitude': -104.0,
        'altitude': 29000,
        'groundspeed': 520,
        'heading': 90,
        'transponder': '7777',
        'flight_plan': {'flight_rules': 'I', 'aircraft_short': 'F22'},
    }
    display, alerts = engine.evaluate([target, fighter], [], {}, [], [])
    fighter_display = next(item for item in display if item['callsign'] == 'REDEYE11')
    target_display = next(item for item in display if item['callsign'] == 'TARGET1')
    assert fighter_display['intercept_assignment']['target_callsign'] == 'TARGET1'
    assert target_display['active_interceptors'][0]['callsign'] == 'REDEYE11'
    assert alerts[0]['active_interceptors'][0]['callsign'] == 'REDEYE11'
