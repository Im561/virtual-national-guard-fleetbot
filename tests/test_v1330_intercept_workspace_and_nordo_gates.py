import asyncio
import time
from pathlib import Path

from app.airports import AirportResolver
from app.detection import DetectionEngine
from app.vatsim import VatsimMonitor


def polygon(min_lon, min_lat, max_lon, max_lat):
    return {
        "type": "Polygon",
        "coordinates": [[
            [min_lon, min_lat],
            [max_lon, min_lat],
            [max_lon, max_lat],
            [min_lon, max_lat],
            [min_lon, min_lat],
        ]],
    }


def coverage(
    callsign="TEST_CTR",
    frequency=127650000,
    *,
    lat=39.0,
    lon=-104.0,
    geometry=None,
    bbox=None,
    online_seconds=1200,
):
    return {
        "callsign": callsign,
        "facility": "CTR",
        "online_seconds": online_seconds,
        "frequencies_hz": [frequency],
        "frequencies": [frequency / 1_000_000],
        "geometry": geometry,
        "bbox": bbox,
        "transceivers": [{
            "id": 1,
            "frequency": frequency,
            "lat": lat,
            "lon": lon,
            "height_msl_m": 1500,
            "height_agl_m": 20,
        }],
        "match_quality": "sector",
        "sector_specific": True,
        "source": "test",
        "boundary_id": callsign.replace("_CTR", ""),
        "parent_boundary_id": callsign.replace("_CTR", ""),
        "parent_geometry": geometry,
    }


def vatsim_pilot(callsign, lat, lon, frequency, *, heading=90, speed=430, altitude=30000):
    return {
        "cid": 100,
        "callsign": callsign,
        "latitude": lat,
        "longitude": lon,
        "altitude": altitude,
        "groundspeed": speed,
        "heading": heading,
        "transponder": "3456",
        "flight_plan": {
            "flight_rules": "I",
            "aircraft_short": "A320",
            "departure": "KAAA",
            "arrival": "KBBB",
        },
    }, {callsign: [{"frequency": frequency}]}


def display_pilot(callsign, lat, lon, *, fighter=False, vsoa=False):
    return {
        "callsign": callsign,
        "lat": lat,
        "lon": lon,
        "altitude": 28000 if fighter else 33000,
        "groundspeed": 490 if fighter else 430,
        "heading": 90,
        "squawk": "1200",
        "on_ground": False,
        "aircraft": "F16" if fighter else "B738",
        "aircraft_type": "F16" if fighter else "B738",
        "aircraft_category": "fighter" if fighter else "airliner",
        "display_class": "fighter" if fighter else "standard",
        "active_intercept": False,
        "track_color": "green",
        "operational_status": None,
        "intercept_assignment": None,
        "active_interceptors": [],
        "severity": "green",
        "manual_nordo": False,
        "nordo_watch": None,
        "context": [],
        "vsoa": vsoa,
        "vsoa_label": "vUSAF" if vsoa else None,
    }


def test_active_artcc_frequency_is_explicitly_whitelisted():
    resolver = AirportResolver()
    resolver.nearby_advisory_matches = lambda *args, **kwargs: []
    engine = DetectionEngine(resolver)
    pilot, audio = vatsim_pilot("AAL101", 39.0, -104.0, 127650000)
    area = polygon(-108, 36, -100, 44)
    ctr = coverage(geometry=area, bbox=[-108, 36, -100, 44])

    display, alerts = engine.evaluate([pilot], [], audio, [ctr])

    assert not alerts
    track = display[0]
    assert track["active_artcc_high_confidence"] is True
    assert track["active_artcc_frequency_match"] is True
    assert track["active_artcc_frequencies"] == [127.65]
    assert track["frequency_mismatch_active"] is False
    assert track["nordo_gate_ready"] is False


def test_matching_ctaf_within_50_nm_blocks_nordo_timer():
    resolver = AirportResolver()
    engine = DetectionEngine(resolver)
    # 01FL is in the bundled advisory-frequency index with CTAF 122.800.
    pilot, audio = vatsim_pilot("AAL202", 28.7819, -81.1592, 122800000, speed=190, altitude=8000)
    area = polygon(-84, 26, -79, 31)
    ctr = coverage(
        callsign="JAX_CTR",
        frequency=127250000,
        lat=28.8,
        lon=-81.2,
        geometry=area,
        bbox=[-84, 26, -79, 31],
    )

    engine.evaluate([pilot], [], audio, [ctr])
    engine.memory["AAL202"].condition_started["nordo_1228"] = time.time() - 900
    display, alerts = engine.evaluate([pilot], [], audio, [ctr])

    assert not alerts
    track = display[0]
    assert track["advisory_frequency_whitelisted"] is True
    assert any(item["airport"] == "01FL" for item in track["advisory_frequency_matches"])
    assert track["frequency_mismatch_active"] is False
    assert track["nordo_watch"] is None
    assert any(item["code"] == "ADVISORY_FREQUENCY_WHITELIST" for item in track["observations"])


def test_early_1228_handoff_into_unstaffed_boundary_is_suppressed():
    resolver = AirportResolver()
    resolver.nearby_advisory_matches = lambda *args, **kwargs: []
    engine = DetectionEngine(resolver)
    # The aircraft is near the eastern edge of the active Center and projected
    # outside it within the configured lookahead. No downstream Center is live.
    pilot, audio = vatsim_pilot(
        "AAL303",
        39.0,
        -103.85,
        122800000,
        heading=90,
        speed=480,
    )
    area = polygon(-105.0, 38.0, -103.7, 40.0)
    ctr = coverage(
        callsign="DEN_CTR",
        frequency=127650000,
        lat=39.0,
        lon=-104.0,
        geometry=area,
        bbox=[-105.0, 38.0, -103.7, 40.0],
    )

    engine.evaluate([pilot], [], audio, [ctr])
    engine.memory["AAL303"].condition_started["nordo_1228"] = time.time() - 900
    display, alerts = engine.evaluate([pilot], [], audio, [ctr])

    assert not alerts
    track = display[0]
    assert track["early_unicom_handoff"] is True
    assert track["early_unicom_handoff_detail"]["lookahead_minutes"] <= 12
    assert track["frequency_mismatch_active"] is False
    assert track["nordo_watch"] is None
    early_observation = next(item for item in track["observations"] if item["code"] == "EARLY_UNICOM_HANDOFF")
    assert "12 minutes" in early_observation["detail"]
    assert "90.0 NM" in early_observation["detail"]


def test_manual_intercept_response_status_is_shared_and_persistent():
    broadcasts = []

    async def broadcast(payload):
        broadcasts.append(payload)

    async def scenario():
        monitor = VatsimMonitor(broadcast)
        try:
            fighter = display_pilot("VIPER11", 27.0, -81.0, fighter=True, vsoa=True)
            target = display_pilot("AAL123", 27.8, -80.1)
            monitor.state.pilots = [fighter, target]
            monitor.state.alerts = []

            ok, _, error = await monitor.assign_manual_intercept("VIPER11", "AAL123", "MIA QRA")
            assert ok is True and error is None
            ok, assignment, error = await monitor.set_manual_intercept_response(
                "VIPER11", "NOT_RESPONDING", "MIA QRA"
            )
            assert ok is True and error is None
            assert assignment["target_response_status"] == "NOT_RESPONDING"
            assert monitor.manual_intercepts["VIPER11"]["target_response_updated_by"] == "MIA QRA"
            assert monitor.state.manual_intercepts[0]["target_response_status"] == "NOT_RESPONDING"
            assert broadcasts
        finally:
            await monitor.client.aclose()

    asyncio.run(scenario())


def test_focused_intercept_tab_vsoa_recommendations_and_status_controls_are_wired():
    root = Path(__file__).parents[1]
    index = (root / "app" / "static" / "index.html").read_text(encoding="utf-8")
    js = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
    css = (root / "app" / "static" / "styles.css").read_text(encoding="utf-8")
    main = (root / "app" / "main.py").read_text(encoding="utf-8")

    assert 'data-workspace-tab="intercept"' in index
    assert 'id="intercept-workspace"' in index
    assert 'id="vsoa-interceptor-recommendations"' in index
    assert "RECOMMENDED ACTIVE VSOA INTERCEPTORS" in index
    assert "renderActiveInterceptWorkspace" in js
    assert "renderVsoaInterceptorRecommendations" in js
    assert "NOT_RESPONDING" in js
    assert "COMMS_RESTORED" in js
    assert "/api/intercepts/manual/${encodeURIComponent(interceptorCallsign)}/response" in js
    assert "/api/intercepts/manual/{interceptor_callsign}/response" in main
    assert ".intercept-focus-grid" in css
    assert ".workspace-tabs" in css
    assert ".vsoa-recommendation" in css


def test_high_altitude_enroute_track_is_not_hidden_by_nearby_shared_ctaf():
    resolver = AirportResolver()
    engine = DetectionEngine(resolver)
    pilot, audio = vatsim_pilot("AAL204", 28.7819, -81.1592, 122800000, speed=430, altitude=30000)
    area = polygon(-84, 26, -79, 31)
    ctr = coverage(
        callsign="JAX_CTR",
        frequency=127250000,
        lat=28.8,
        lon=-81.2,
        geometry=area,
        bbox=[-84, 26, -79, 31],
    )

    display, _ = engine.evaluate([pilot], [], audio, [ctr])

    assert display[0]["advisory_frequency_whitelisted"] is False
    assert display[0]["frequency_mismatch_active"] is True


def test_split_artcc_automatic_alerts_form_one_persistent_audible_incident():
    async def broadcast(_payload):
        return None

    async def scenario():
        monitor = VatsimMonitor(broadcast)
        try:
            def alert(alert_id, callsign, center):
                return {
                    "id": alert_id,
                    "callsign": callsign,
                    "center": center,
                    "confidence": 99,
                    "score": 99,
                    "requires_ack": True,
                    "reasons": [{"code": "AUTO_SCRAMBLE_FREQ_MISMATCH"}],
                }

            alerts = [
                alert("A1", "AAL1", "MIA_CTR"),
                alert("A2", "AAL2", "MIA_17_CTR"),
                alert("A3", "AAL3", "MIA_32_CTR / MIA_17_CTR"),
            ]
            monitor._group_scramble_incidents(alerts)
            assert sum(not item["alarm_suppressed"] for item in alerts) == 1
            assert {item["alarm_group_key"] for item in alerts} == {"MIA_CTR"}
            primary_id = next(item["id"] for item in alerts if item["alarm_primary"])

            # If the original primary leaves while the incident remains active,
            # the remaining tracks stay grouped and do not sound again.
            remaining = [item for item in alerts if item["id"] != primary_id]
            monitor._group_scramble_incidents(remaining)
            assert all(item["alarm_suppressed"] for item in remaining)
            assert all(item["requires_ack"] is False for item in remaining)
        finally:
            await monitor.client.aclose()

    asyncio.run(scenario())


def test_atc_quick_workspace_and_grouped_alarm_diagnostics_are_wired():
    root = Path(__file__).parents[1]
    index = (root / "app" / "static" / "index.html").read_text(encoding="utf-8")
    js = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
    css = (root / "app" / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'data-workspace-tab="atc"' in index
    assert 'id="atc-workspace"' in index
    assert 'id="atc-console-label"' in index
    assert 'id="atc-selected-track"' in index
    assert "renderAtcWorkspace" in js
    assert "SET AS INTERCEPT TARGET" in js
    assert "CONFIRM NOT RESPONDING / NORDO" in js
    assert "!alert.alarm_suppressed" in js
    assert "GROUPED TRACK · NO ADDITIONAL ALARM" in js
    assert ".atc-quick-content" in css
