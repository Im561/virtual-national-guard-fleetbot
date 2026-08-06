import time

from app.airports import AirportResolver
from app.atc_boundaries import AtcBoundaryStore
from app.detection import DetectionEngine


def square(min_lon=-110, min_lat=35, max_lon=-100, max_lat=45):
    return {
        "type": "Polygon",
        "coordinates": [[
            [min_lon, min_lat], [max_lon, min_lat], [max_lon, max_lat],
            [min_lon, max_lat], [min_lon, min_lat],
        ]],
    }


def pilot(callsign="NORDO1", lat=39.0, lon=-104.0, frequency=122800000):
    return {
        "cid": 100,
        "callsign": callsign,
        "latitude": lat,
        "longitude": lon,
        "altitude": 30000,
        "groundspeed": 430,
        "heading": 90,
        "transponder": "3456",
        "flight_plan": {"flight_rules": "I", "aircraft_short": "A320"},
    }, {callsign: [{"frequency": frequency}]}


def coverage(callsign, frequency, lat, lon, geometry=None, match_quality="sector", online_seconds=3600):
    return {
        "callsign": callsign,
        "facility": "CTR",
        "online_seconds": online_seconds,
        "frequencies_hz": [frequency],
        "frequencies": [frequency / 1_000_000],
        "geometry": geometry,
        "bbox": [-110, 35, -100, 45] if geometry else None,
        "transceivers": [{
            "id": 1,
            "frequency": frequency,
            "lat": lat,
            "lon": lon,
            "height_msl_m": 1500,
            "height_agl_m": 20,
        }],
        "match_quality": match_quality,
        "sector_specific": match_quality == "sector",
        "source": "test",
    }


def test_polygon_without_live_transceiver_never_creates_nordo():
    engine = DetectionEngine(AirportResolver())
    p, audio = pilot()
    broad = {
        "callsign": "DEN_CTR",
        "facility": "CTR",
        "frequencies_hz": [127650000],
        "frequencies": [127.65],
        "geometry": square(),
        "bbox": [-110, 35, -100, 45],
        "transceivers": [],
        "match_quality": "facility",
        "sector_specific": False,
        "source": "VATSpy facility boundary",
    }
    display, alerts = engine.evaluate([p], [], audio, [broad])
    assert display[0]["center"] is None
    assert display[0]["coverage_selection_reason"] == "NO_LIVE_TRANSCEIVER_COVERAGE"
    assert not alerts


def test_transceiver_beyond_radio_horizon_does_not_create_nordo():
    engine = DetectionEngine(AirportResolver())
    p, audio = pilot()
    far = coverage("DEN_CTR", 127650000, 35.1, -109.8, geometry=square())
    display, alerts = engine.evaluate([p], [], audio, [far])
    assert display[0]["center"] is None
    assert not alerts


def test_overlapping_controllers_start_communications_watch_when_none_match():
    engine = DetectionEngine(AirportResolver())
    p, audio = pilot()
    one = coverage("DEN_17_CTR", 127650000, 39.1, -104.1, geometry=square())
    two = coverage("DEN_18_CTR", 132750000, 39.12, -104.12, geometry=square())
    engine.evaluate([p], [], audio, [one, two])
    engine.memory["NORDO1"].condition_started["verified_frequency_mismatch"] = time.time() - 31
    display, alerts = engine.evaluate([p], [], audio, [one, two])
    assert display[0]["center"] == "DEN_17_CTR / DEN_18_CTR"
    assert display[0]["coverage_selection_reason"] == "MULTI_POSITION_MISMATCH"
    assert display[0]["ownership_status"] == "COVERAGE_SET_MISMATCH"
    assert display[0]["frequency_mismatch_active"] is True
    assert display[0]["nordo_watch"] is not None
    assert not alerts


def test_matching_any_overlapping_controller_frequency_suppresses_alert():
    engine = DetectionEngine(AirportResolver())
    p, audio = pilot(frequency=132750000)
    one = coverage("DEN_17_CTR", 127650000, 39.1, -104.1, geometry=square())
    two = coverage("DEN_18_CTR", 132750000, 39.12, -104.12, geometry=square())
    display, alerts = engine.evaluate([p], [], audio, [one, two])
    assert display[0]["center"] == "DEN_18_CTR"
    assert display[0]["coverage_selection_reason"] == "FREQUENCY_MATCH"
    assert not alerts


def test_unambiguous_persistent_1228_is_observation_only_without_corroboration():
    engine = DetectionEngine(AirportResolver())
    p, audio = pilot()
    one = coverage("DEN_17_CTR", 127650000, 39.1, -104.1, geometry=square())
    engine.evaluate([p], [], audio, [one])
    engine.memory["NORDO1"].condition_started["nordo_1228"] = time.time() - 700
    display, alerts = engine.evaluate([p], [], audio, [one])
    assert display[0]["center"] == "DEN_17_CTR"
    assert display[0]["coverage_selection_reason"] == "UNAMBIGUOUS_TRANSCEIVER"
    assert not display[0]["reasons"]
    assert any(item["code"] == "NORDO_1228" for item in display[0]["observations"])
    assert not alerts


def test_persistent_1228_plus_independent_airspace_evidence_creates_alert():
    engine = DetectionEngine(AirportResolver())
    p, audio = pilot()
    one = coverage("DEN_17_CTR", 127650000, 39.1, -104.1, geometry=square())
    restricted = {
        "id": "RTEST",
        "designation": "R-TEST",
        "category": "RESTRICTED",
        "floor_ft": 0,
        "ceiling_ft": 50000,
        "floor_label": "SFC",
        "ceiling_label": "FL500",
        "bbox": [-105, 38, -103, 40],
        "geometry": square(-105, 38, -103, 40),
    }
    engine.evaluate([p], [], audio, [one], [restricted])
    engine.memory["NORDO1"].condition_started["nordo_1228"] = time.time() - 700
    display, alerts = engine.evaluate([p], [], audio, [one], [restricted])
    assert alerts
    assert {reason["category"] for reason in alerts[0]["reasons"]} == {"radio", "protected_airspace"}
    assert display[0]["intercept_candidate"] is True


def test_city_alias_preserves_center_subsector_identifier():
    store = AtcBoundaryStore()
    store.fir_features = [
        {"type": "Feature", "properties": {"id": "ZDV", "name": "Denver ARTCC"}, "geometry": square()},
        {"type": "Feature", "properties": {"id": "ZDV-17", "name": "Denver Sector 17"}, "geometry": square(-106, 38, -102, 42)},
    ]
    controller = {"callsign": "DEN_17_CTR", "frequency": "127.650", "visual_range": 350}
    audio = {"DEN_17_CTR": [{"id": 1, "frequency": 127650000, "latDeg": 39.8, "lonDeg": -104.7, "heightMslM": 1600}]}
    result = store.build_coverage([controller], audio)
    assert result[0]["boundary_id"] == "ZDV-17"
    assert result[0]["match_quality"] == "sector"
    assert result[0]["sector_specific"] is True


def test_tracon_longest_prefix_wins():
    store = AtcBoundaryStore()
    store.tracon_features = [
        {"type": "Feature", "properties": {"id": "SCT", "prefix": ["LAX"], "name": "SoCal Approach"}, "geometry": square(-119, 32, -116, 35)},
        {"type": "Feature", "properties": {"id": "SCT-U", "prefix": ["LAX_U"], "name": "SoCal North"}, "geometry": square(-119, 33, -117, 35)},
    ]
    controller = {"callsign": "LAX_U_APP", "frequency": "124.500", "visual_range": 100}
    audio = {"LAX_U_APP": [{"id": 1, "frequency": 124500000, "latDeg": 34.0, "lonDeg": -118.0, "heightMslM": 100}]}
    result = store.build_coverage([controller], audio)
    assert result[0]["boundary_id"] == "SCT-U"
    assert result[0]["match_quality"] == "tracon"


def test_all_configured_center_aliases_resolve_to_facility_boundaries():
    from app.atc_boundaries import CENTER_ALIASES

    store = AtcBoundaryStore()
    ids = sorted(set(CENTER_ALIASES.values()))
    store.fir_features = [
        {"type": "Feature", "properties": {"id": ident, "name": ident}, "geometry": square()}
        for ident in ids
    ]
    for alias, expected in CENTER_ALIASES.items():
        feature, quality, boundary_id = store._match_fir(f"{alias}_CTR")
        assert feature is not None, alias
        assert boundary_id == expected
        assert quality == "facility"


def test_split_center_full_facility_fallback_starts_watch_but_keeps_scramble_guard():
    store = AtcBoundaryStore()
    store.fir_features = [
        {"type": "Feature", "properties": {"id": "ZDV", "name": "Denver ARTCC"}, "geometry": square()},
    ]
    controller = {"callsign": "DEN_17_CTR", "frequency": "127.650", "visual_range": 350}
    tx = {"DEN_17_CTR": [{"id": 1, "frequency": 127650000, "latDeg": 39.1, "lonDeg": -104.1, "heightMslM": 1500}]}
    built = store.build_coverage([controller], tx)
    built[0]["online_seconds"] = 900
    assert built[0]["match_quality"] == "facility_fallback"
    assert built[0]["geometry"] is not None

    engine = DetectionEngine(AirportResolver())
    p, audio = pilot()
    engine.evaluate([p], [], audio, built)
    engine.memory["NORDO1"].condition_started["verified_frequency_mismatch"] = time.time() - 31
    display, alerts = engine.evaluate([p], [], audio, built)
    assert display[0]["center"] == "DEN_17_CTR"
    assert display[0]["coverage_selection_reason"] == "SPLIT_POSITION_FALLBACK"
    assert display[0]["coverage_confidence_basis"] == "SPLIT_CENTER_FACILITY_AND_TRANSCEIVER"
    assert display[0]["frequency_mismatch_active"] is True
    assert display[0]["nordo_watch"] is not None
    assert not alerts


def test_split_tracon_generic_fallback_is_identified():
    store = AtcBoundaryStore()
    store.tracon_features = [
        {"type": "Feature", "properties": {"id": "SCT", "prefix": ["LAX"], "name": "SoCal Approach"}, "geometry": square(-119, 32, -116, 35)},
    ]
    controller = {"callsign": "LAX_U_APP", "frequency": "124.500", "visual_range": 100}
    tx = {"LAX_U_APP": [{"id": 1, "frequency": 124500000, "latDeg": 34.0, "lonDeg": -118.0, "heightMslM": 100}]}
    built = store.build_coverage([controller], tx)
    assert built[0]["match_quality"] == "tracon_fallback"
    assert built[0]["sector_specific"] is False


def test_1228_outside_confirmed_coverage_is_never_alerted():
    engine = DetectionEngine(AirportResolver())
    p, audio = pilot()
    display, alerts = engine.evaluate([p], [], audio, [])
    assert not alerts
    assert display[0]["severity"] == "green"
    assert any(item["code"] == "1228_OUTSIDE_COVERAGE" for item in display[0]["observations"])


def test_1228_with_another_nonmatching_frequency_remains_nordo_candidate():
    engine = DetectionEngine(AirportResolver())
    p, _ = pilot()
    audio = {"NORDO1": [{"frequency": 122800000}, {"frequency": 128650000}]}
    one = coverage("DEN_17_CTR", 127650000, 39.1, -104.1, geometry=square())
    display, alerts = engine.evaluate([p], [], audio, [one])
    assert not alerts
    assert not display[0]["reasons"]
    assert display[0]["nordo_candidate_active"] is True
    assert not any(item["code"] == "1228_WITH_OTHER_RADIO" for item in display[0]["observations"])


def test_wrong_frequency_enters_watch_rail_after_thirty_seconds_even_without_1228():
    engine = DetectionEngine(AirportResolver())
    p, _ = pilot(frequency=128650000)
    audio = {"NORDO1": [{"frequency": 128650000}]}
    one = coverage("DEN_17_CTR", 127650000, 39.1, -104.1, geometry=square(), online_seconds=900)
    engine.evaluate([p], [], audio, [one])
    engine.memory["NORDO1"].condition_started["verified_frequency_mismatch"] = time.time() - 31
    display, alerts = engine.evaluate([p], [], audio, [one])
    assert not alerts
    assert display[0]["frequency_mismatch_active"] is True
    assert display[0]["frequency_mismatch_seconds"] >= 30
    assert display[0]["nordo_candidate_active"] is False
    assert display[0]["nordo_watch"]["title"] == "ATC FREQUENCY MISMATCH — OBSERVE"


def test_vfr_1228_is_monitoring_only():
    engine = DetectionEngine(AirportResolver())
    p, audio = pilot()
    p["flight_plan"]["flight_rules"] = "V"
    one = coverage("DEN_17_CTR", 127650000, 39.1, -104.1, geometry=square())
    display, alerts = engine.evaluate([p], [], audio, [one])
    assert not alerts
    assert any(item["code"] == "1228_VFR" for item in display[0]["observations"])


def test_auto_scramble_flag_waits_until_atc_has_been_online_five_minutes():
    engine = DetectionEngine(AirportResolver())
    p, audio = pilot(frequency=122800000)
    recent = coverage(
        "DEN_17_CTR", 127650000, 39.1, -104.1,
        geometry=square(), online_seconds=299,
    )
    engine.evaluate([p], [], audio, [recent])
    engine.memory["NORDO1"].condition_started["verified_frequency_mismatch"] = time.time() - 45
    engine.memory["NORDO1"].condition_started["auto_scramble_frequency_mismatch"] = time.time() - 900
    display, alerts = engine.evaluate([p], [], audio, [recent])
    assert not alerts
    assert display[0]["auto_scramble_flag"] is None
    assert display[0]["frequency_mismatch_seconds"] >= 44
    assert display[0]["auto_scramble_mismatch_seconds"] == 0
    assert display[0]["nordo_watch"] is not None
    assert any(item["code"] == "ATC_RECENTLY_ONLINE" for item in display[0]["observations"])


def test_auto_scramble_flag_after_eight_continuous_minutes_of_verified_mismatch():
    engine = DetectionEngine(AirportResolver())
    p, audio = pilot(frequency=122800000)
    stable = coverage(
        "DEN_17_CTR", 127650000, 39.1, -104.1,
        geometry=square(), online_seconds=900,
    )
    engine.evaluate([p], [], audio, [stable])
    engine.memory["NORDO1"].condition_started["verified_frequency_mismatch"] = time.time() - 800
    engine.memory["NORDO1"].condition_started["auto_scramble_frequency_mismatch"] = time.time() - 481
    display, alerts = engine.evaluate([p], [], audio, [stable])
    assert alerts
    assert alerts[0]["severity"] == "red"
    assert alerts[0]["requires_ack"] is True
    assert any(reason["code"] == "AUTO_SCRAMBLE_FREQ_MISMATCH" for reason in alerts[0]["reasons"])
    assert display[0]["auto_scramble_flag"]["active"] is True
    assert display[0]["frequency_mismatch_seconds"] >= 480


def test_matching_any_valid_atc_frequency_resets_auto_scramble_timer():
    engine = DetectionEngine(AirportResolver())
    p, audio = pilot(frequency=127650000)
    stable = coverage(
        "DEN_17_CTR", 127650000, 39.1, -104.1,
        geometry=square(), online_seconds=900,
    )
    engine.evaluate([p], [], audio, [stable])
    engine.memory["NORDO1"].condition_started["auto_scramble_frequency_mismatch"] = time.time() - 900
    display, alerts = engine.evaluate([p], [], audio, [stable])
    assert not alerts
    assert display[0]["atc_frequency_match"] is True
    assert display[0]["frequency_mismatch_seconds"] == 0
    assert display[0]["auto_scramble_flag"] is None


def test_switching_controller_preserves_mismatch_timer_and_auto_flag():
    engine = DetectionEngine(AirportResolver())
    p, audio = pilot(frequency=122800000)
    den = coverage("DEN_17_CTR", 127650000, 39.1, -104.1, geometry=square(), online_seconds=900)
    engine.evaluate([p], [], audio, [den])
    engine.memory["NORDO1"].condition_started["verified_frequency_mismatch"] = time.time() - 700
    engine.memory["NORDO1"].condition_started["auto_scramble_frequency_mismatch"] = time.time() - 700
    kc = coverage("KC_12_CTR", 128600000, 39.1, -104.1, geometry=square(), online_seconds=900)
    display, alerts = engine.evaluate([p], [], audio, [kc])
    assert alerts
    assert display[0]["frequency_mismatch_seconds"] >= 699
    assert display[0]["frequency_mismatch_scope_changes"] >= 1
    assert display[0]["auto_scramble_flag"] is not None


def test_generic_den_center_facility_match_is_high_confidence_with_live_transceiver():
    engine = DetectionEngine(AirportResolver())
    p, audio = pilot(frequency=122800000)
    generic = coverage(
        "DEN_CTR", 127650000, 39.1, -104.1,
        geometry=square(), match_quality="facility", online_seconds=900,
    )
    generic["sector_specific"] = False
    engine.evaluate([p], [], audio, [generic])
    memory = engine.memory["NORDO1"]
    memory.condition_started["nordo_1228"] = time.time() - 301
    memory.condition_started["verified_frequency_mismatch"] = time.time() - 700
    memory.condition_started["auto_scramble_frequency_mismatch"] = time.time() - 481
    display, alerts = engine.evaluate([p], [], audio, [generic])
    assert display[0]["center"] == "DEN_CTR"
    assert display[0]["coverage_confidence"] == "HIGH"
    assert display[0]["coverage_confidence_basis"] == "GENERIC_CENTER_FACILITY_AND_TRANSCEIVER"
    assert display[0]["nordo_watch"] is not None
    assert display[0]["auto_scramble_flag"] is not None
    assert alerts


def test_1228_plus_guard_still_starts_nordo_when_no_radio_matches_atc():
    engine = DetectionEngine(AirportResolver())
    p, _ = pilot(frequency=122800000)
    audio = {"NORDO1": [{"frequency": 122800000}, {"frequency": 121500000}]}
    one = coverage("DEN_17_CTR", 127650000, 39.1, -104.1, geometry=square(), online_seconds=900)
    engine.evaluate([p], [], audio, [one])
    engine.memory["NORDO1"].condition_started["nordo_1228"] = time.time() - 301
    display, alerts = engine.evaluate([p], [], audio, [one])
    assert display[0]["nordo_watch"] is not None
    assert display[0]["nordo_candidate_active"] is True
    assert not any(item["code"] == "1228_WITH_OTHER_RADIO" for item in display[0]["observations"])
    assert not alerts  # watch remains observation-only without independent evidence


def test_high_altitude_near_destination_is_not_terminal_exempt():
    engine = DetectionEngine(AirportResolver())
    # Seed an airport near the aircraft to reproduce an arrival near Denver.
    engine.airports.cache["KDEN"] = (39.8617, -104.6731)
    p, audio = pilot(lat=39.9, lon=-104.7, frequency=122800000)
    p["flight_plan"]["arrival"] = "KDEN"
    p["altitude"] = 30000
    one = coverage("DEN_CTR", 127650000, 39.8, -104.7, geometry=square(), match_quality="facility", online_seconds=900)
    one["sector_specific"] = False
    display, _ = engine.evaluate([p], [], audio, [one])
    assert display[0]["near_terminal_exemption"] is False
    assert display[0]["nordo_candidate_active"] is True


def test_1228_coverage_set_timer_uses_all_live_candidate_frequencies():
    engine = DetectionEngine(AirportResolver())
    p, audio = pilot(frequency=122800000)
    one = coverage("DEN_17_CTR", 127650000, 39.1, -104.1, geometry=square(), online_seconds=900)
    two = coverage("DEN_18_CTR", 132750000, 39.12, -104.12, geometry=square(), online_seconds=900)
    display, _ = engine.evaluate([p], [], audio, [one, two])
    assert display[0]["frequency_mismatch_active"] is True
    assert set(display[0]["center_frequencies"]) == {127.65, 132.75}

    matching_audio = {"NORDO1": [{"frequency": 132750000}]}
    display, alerts = engine.evaluate([p], [], matching_audio, [one, two])
    assert display[0]["atc_frequency_match"] is True
    assert display[0]["frequency_mismatch_active"] is True
    assert display[0]["frequency_mismatch_case_status"] == "VERIFYING_FREQUENCY_MATCH"
    display, alerts = engine.evaluate([p], [], matching_audio, [one, two])
    assert display[0]["frequency_mismatch_active"] is False
    assert not alerts


def test_multi_position_auto_flag_waits_for_every_possible_owner_to_stabilize():
    engine = DetectionEngine(AirportResolver())
    p, audio = pilot(frequency=122800000)
    stable = coverage("DEN_17_CTR", 127650000, 39.1, -104.1, geometry=square(), online_seconds=900)
    recent = coverage("DEN_18_CTR", 132750000, 39.12, -104.12, geometry=square(), online_seconds=120)
    engine.evaluate([p], [], audio, [stable, recent])
    memory = engine.memory["NORDO1"]
    memory.condition_started["verified_frequency_mismatch"] = time.time() - 900
    memory.condition_started["auto_scramble_frequency_mismatch"] = time.time() - 900
    display, alerts = engine.evaluate([p], [], audio, [stable, recent])
    assert display[0]["frequency_mismatch_active"] is True
    assert display[0]["auto_scramble_eligible"] is False
    assert display[0]["auto_scramble_mismatch_seconds"] == 0
    assert not alerts


def test_current_vatspy_kz_identifier_matches_denver_center():
    store = AtcBoundaryStore()
    store.fir_features = [
        {
            "type": "Feature",
            "properties": {"id": "KZDV", "name": "Denver ARTCC", "division": "VATUSA"},
            "geometry": square(),
        }
    ]
    controller = {"callsign": "DEN_CTR", "frequency": "127.650", "visual_range": 350}
    tx = {"DEN_CTR": [{"id": 1, "frequency": 127650000, "latDeg": 39.8, "lonDeg": -104.7, "heightMslM": 1600}]}
    built = store.build_coverage([controller], tx)
    assert built[0]["boundary_id"] == "KZDV"
    assert built[0]["geometry"] is not None
    assert built[0]["match_quality"] == "facility"


def test_all_center_boundaries_exclude_subsectors_and_merge_multipart_firs():
    store = AtcBoundaryStore()
    store.fir_features = [
        {"type": "Feature", "properties": {"id": "KZDV", "division": "VATUSA"}, "geometry": square(-110, 35, -100, 45)},
        {"type": "Feature", "properties": {"id": "KZDV-17", "division": "VATUSA"}, "geometry": square(-106, 38, -102, 42)},
        {"type": "Feature", "properties": {"id": "CZQM", "division": "VATCAN"}, "geometry": square(-68, 42, -60, 48)},
        {"type": "Feature", "properties": {"id": "CZQM", "division": "VATCAN"}, "geometry": square(-64, 48, -55, 55)},
        {"type": "Feature", "properties": {"id": "EGTT", "division": "VATUK"}, "geometry": square()},
    ]
    boundaries = store.center_boundaries()
    assert {item["id"] for item in boundaries} == {"KZDV", "CZQM"}
    moncton = next(item for item in boundaries if item["id"] == "CZQM")
    assert moncton["geometry"]["type"] == "MultiPolygon"
    assert len(moncton["geometry"]["coordinates"]) == 2


def test_guard_only_never_counts_as_atc_contact_or_clears_mismatch():
    engine = DetectionEngine(AirportResolver())
    p, _ = pilot(frequency=121500000)
    audio = {"NORDO1": [{"frequency": 121500000}]}
    one = coverage("DEN_CTR", 127650000, 39.0, -104.0, geometry=square(), match_quality="facility")
    one["sector_specific"] = False
    display, _ = engine.evaluate([p], [], audio, [one])
    track = display[0]
    assert track["atc_frequency_match"] is False
    assert track["frequency_mismatch_active"] is True
    assert track["monitor_only_frequencies"] == [{"frequency": 121.5, "role": "GUARD"}]
    assert track["atc_capable_reported_frequencies"] == []


def test_guard_plus_correct_center_frequency_still_allows_real_atc_match():
    engine = DetectionEngine(AirportResolver())
    p, _ = pilot(frequency=121500000)
    audio = {"NORDO1": [{"frequency": 121500000}, {"frequency": 127650000}]}
    one = coverage("DEN_CTR", 127650000, 39.0, -104.0, geometry=square(), match_quality="facility")
    one["sector_specific"] = False
    display, _ = engine.evaluate([p], [], audio, [one])
    track = display[0]
    assert track["atc_frequency_match"] is True
    assert track["frequency_mismatch_active"] is False
    assert track["monitor_only_frequencies"] == [{"frequency": 121.5, "role": "GUARD"}]
    assert track["atc_capable_reported_frequencies"] == [127.65]


def test_advisory_and_guard_together_are_both_monitor_only():
    engine = DetectionEngine(AirportResolver())
    p, _ = pilot(frequency=122800000)
    audio = {"NORDO1": [{"frequency": 122800000}, {"frequency": 121500000}]}
    one = coverage("DEN_CTR", 127650000, 39.0, -104.0, geometry=square(), match_quality="facility")
    one["sector_specific"] = False
    display, _ = engine.evaluate([p], [], audio, [one])
    track = display[0]
    assert track["atc_frequency_match"] is False
    assert track["frequency_mismatch_active"] is True
    assert {item["role"] for item in track["monitor_only_frequencies"]} == {"GUARD", "ADVISORY/UNICOM"}
    assert track["atc_capable_reported_frequencies"] == []
