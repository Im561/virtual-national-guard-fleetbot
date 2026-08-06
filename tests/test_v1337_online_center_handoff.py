from app.airports import AirportResolver
from app.detection import DetectionEngine


def polygon(min_lon, min_lat, max_lon, max_lat):
    return {
        "type": "Polygon",
        "coordinates": [[[
            min_lon, min_lat
        ], [
            max_lon, min_lat
        ], [
            max_lon, max_lat
        ], [
            min_lon, max_lat
        ], [
            min_lon, min_lat
        ]]],
    }


def center(callsign, frequency, geometry, *, tx_lat, tx_lon, parent=None):
    boundary = callsign.replace("_CTR", "")
    return {
        "callsign": callsign,
        "facility": "CTR",
        "online_seconds": 1800,
        "frequencies_hz": [frequency],
        "frequencies": [frequency / 1_000_000],
        "geometry": geometry,
        "bbox": [
            min(point[0] for point in geometry["coordinates"][0]),
            min(point[1] for point in geometry["coordinates"][0]),
            max(point[0] for point in geometry["coordinates"][0]),
            max(point[1] for point in geometry["coordinates"][0]),
        ],
        "transceivers": [{
            "id": callsign,
            "frequency": frequency,
            "lat": tx_lat,
            "lon": tx_lon,
            "height_msl_m": 1500,
            "height_agl_m": 20,
        }],
        "match_quality": "sector",
        "sector_specific": True,
        "source": "test",
        "boundary_id": boundary,
        "parent_boundary_id": parent or boundary.split("-", 1)[0],
        "parent_geometry": geometry,
    }


def pilot(frequency, *, heading=90):
    callsign = "DAL2289"
    return {
        "cid": 100,
        "callsign": callsign,
        "latitude": 39.0,
        "longitude": -103.95,
        "altitude": 34000,
        "groundspeed": 450,
        "heading": heading,
        "transponder": "3456",
        "flight_plan": {
            "flight_rules": "I",
            "aircraft_short": "A320",
            "departure": "KDEN",
            "arrival": "KSLC",
        },
    }, {callsign: [{"frequency": frequency}]}


def setup_engine():
    resolver = AirportResolver()
    resolver.nearby_advisory_matches = lambda *args, **kwargs: []
    return DetectionEngine(resolver)


def test_online_downstream_center_frequency_is_whitelisted_within_80_nm_outbound():
    engine = setup_engine()
    current = center(
        "DEN_17_CTR", 127650000, polygon(-105.0, 38.0, -103.7, 40.0),
        tx_lat=39.0, tx_lon=-104.0, parent="KZDV",
    )
    downstream = center(
        "SLC_44_CTR", 125575000, polygon(-103.7, 38.0, -101.5, 40.0),
        tx_lat=39.0, tx_lon=-102.5, parent="KZLC",
    )
    item, audio = pilot(125575000, heading=90)

    display, alerts = engine.evaluate([item], [], audio, [current, downstream])

    assert not alerts
    track = display[0]
    assert track["online_center_handoff"] is True
    assert track["online_center_handoff_detail"]["downstream_controller"] == "SLC_44_CTR"
    assert track["online_center_handoff_detail"]["downstream_artcc"] == "KZLC"
    assert track["online_center_handoff_detail"]["downstream_entry_distance_nm"] <= 80.0
    assert track["online_center_handoff_detail"]["matched_frequencies"] == [125.575]
    assert track["frequency_mismatch_active"] is False
    assert track["frequency_mismatch_current"] is False
    assert any(value["code"] == "ONLINE_CENTER_HANDOFF" for value in track["observations"])


def test_handoff_whitelist_resets_an_existing_frequency_mismatch_case():
    engine = setup_engine()
    current = center(
        "DEN_17_CTR", 127650000, polygon(-105.0, 38.0, -103.7, 40.0),
        tx_lat=39.0, tx_lon=-104.0, parent="KZDV",
    )
    downstream = center(
        "SLC_44_CTR", 125575000, polygon(-103.7, 38.0, -101.5, 40.0),
        tx_lat=39.0, tx_lon=-102.5, parent="KZLC",
    )
    item, wrong_audio = pilot(124850000, heading=90)
    first, _ = engine.evaluate([item], [], wrong_audio, [current, downstream])
    assert first[0]["frequency_mismatch_active"] is True

    _, handoff_audio = pilot(125575000, heading=90)
    display, alerts = engine.evaluate([item], [], handoff_audio, [current, downstream])

    assert not alerts
    track = display[0]
    assert track["online_center_handoff"] is True
    assert track["frequency_mismatch_active"] is False
    assert track["frequency_mismatch_last_reset_reason"] == "ONLINE_CENTER_HANDOFF"


def test_matching_downstream_frequency_is_not_whitelisted_when_aircraft_is_moving_away():
    engine = setup_engine()
    current = center(
        "DEN_17_CTR", 127650000, polygon(-105.0, 38.0, -103.7, 40.0),
        tx_lat=39.0, tx_lon=-104.0, parent="KZDV",
    )
    downstream = center(
        "SLC_44_CTR", 125575000, polygon(-103.7, 38.0, -101.5, 40.0),
        tx_lat=39.0, tx_lon=-102.5, parent="KZLC",
    )
    item, audio = pilot(125575000, heading=270)

    display, _ = engine.evaluate([item], [], audio, [current, downstream])

    track = display[0]
    assert track["online_center_handoff"] is False
    assert track["frequency_mismatch_active"] is True
    assert track["frequency_mismatch_current"] is True


def test_random_frequency_or_offline_downstream_center_is_not_whitelisted():
    engine = setup_engine()
    current = center(
        "DEN_17_CTR", 127650000, polygon(-105.0, 38.0, -103.7, 40.0),
        tx_lat=39.0, tx_lon=-104.0, parent="KZDV",
    )
    item, audio = pilot(124850000, heading=90)

    display, _ = engine.evaluate([item], [], audio, [current])

    track = display[0]
    assert track["online_center_handoff"] is False
    assert track["frequency_mismatch_active"] is True


def test_internal_split_sector_handoff_does_not_use_artcc_border_whitelist():
    engine = setup_engine()
    parent_geometry = polygon(-105.0, 38.0, -101.5, 40.0)
    current = center(
        "DEN_17_CTR", 127650000, polygon(-105.0, 38.0, -103.7, 40.0),
        tx_lat=39.0, tx_lon=-104.0, parent="KZDV",
    )
    current["parent_geometry"] = parent_geometry
    next_sector = center(
        "DEN_18_CTR", 132125000, polygon(-103.7, 38.0, -101.5, 40.0),
        tx_lat=39.0, tx_lon=-102.5, parent="KZDV",
    )
    next_sector["parent_geometry"] = parent_geometry
    item, audio = pilot(132125000, heading=90)

    display, _ = engine.evaluate([item], [], audio, [current, next_sector])

    track = display[0]
    assert track["online_center_handoff"] is False
    assert track["frequency_mismatch_active"] is True
