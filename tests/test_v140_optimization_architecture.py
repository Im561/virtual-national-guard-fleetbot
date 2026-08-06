import asyncio
from pathlib import Path

from app.live_delta import build_live_delta, compact_live_payload
from app.persistence import OperationalStateStore
from app.spatial_index import SpatialGridIndex
from app.vatsim import VatsimMonitor


ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
INDEX = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
MAIN = (ROOT / "app/main.py").read_text(encoding="utf-8")


def test_live_delta_upserts_and_removes_keyed_collections():
    previous = {
        "type": "live",
        "revision": 10,
        "feed_sequence": 4,
        "pilots": [{"callsign": "AAL1", "lat": 1}, {"callsign": "DAL2", "lat": 2}],
        "alerts": [{"id": "alert-a", "callsign": "AAL1"}],
        "operations": [],
        "manual_intercepts": [],
        "intercept_controls": [],
        "controllers": [],
        "stats": {"monitored_aircraft": 2},
    }
    current = {
        **previous,
        "revision": 11,
        "feed_sequence": 5,
        "pilots": [{"callsign": "AAL1", "lat": 1.5}, {"callsign": "UAL3", "lat": 3}],
        "alerts": [],
        "stats": {"monitored_aircraft": 2},
    }
    delta = build_live_delta(previous, current)
    assert delta is not None
    assert delta["base_revision"] == 10 and delta["revision"] == 11
    assert {item["callsign"] for item in delta["collections"]["pilots"]["upsert"]} == {"AAL1", "UAL3"}
    assert delta["collections"]["pilots"]["remove"] == ["DAL2"]
    assert delta["collections"]["alerts"]["remove"] == ["ALERT-A"]


def test_websocket_payload_removes_selection_only_pilot_detail():
    payload = {
        "type": "live",
        "revision": 1,
        "pilots": [{
            "callsign": "AAL1",
            "lat": 27.0,
            "lon": -80.0,
            "context": ["large context"],
            "controller_candidates": [{"callsign": "ZMA_CTR"}],
            "center_frequencies": [132.45],
        }],
    }
    compact = compact_live_payload(payload)
    assert compact["payload_mode"] == "compact"
    assert compact["pilots"][0]["callsign"] == "AAL1"
    assert "context" not in compact["pilots"][0]
    assert "controller_candidates" not in compact["pilots"][0]
    assert payload["pilots"][0]["context"] == ["large context"]


def test_spatial_grid_returns_bbox_candidate_without_global_scan():
    index = SpatialGridIndex(5.0)
    inside = {"callsign": "ZMA_CTR"}
    far = {"callsign": "ZSE_CTR"}
    index.add(inside, (-90.0, 20.0, -75.0, 35.0))
    index.add(far, (-130.0, 40.0, -115.0, 50.0))
    result = index.query(27.0, -80.0)
    assert inside in result
    assert far not in result


def test_operational_state_sqlite_round_trip(tmp_path):
    store = OperationalStateStore(str(tmp_path / "state.sqlite3"))
    snapshot = {
        "operations": [{"id": "case-1", "status": "ACTIVE"}],
        "manual_intercepts": [{"interceptor_callsign": "VIPER11", "target_callsign": "AAL1"}],
    }
    store.save(snapshot, "2026-08-05T00:00:00+00:00")
    assert store.load() == snapshot


def test_unchanged_manual_intercept_skips_recalculation_but_force_recalc_runs():
    broadcasts = []

    async def broadcast(payload):
        broadcasts.append(payload)

    async def scenario():
        monitor = VatsimMonitor(broadcast)
        try:
            interceptor = {
                "callsign": "VIPER11", "lat": 27.0, "lon": -81.0, "altitude": 28000,
                "groundspeed": 500, "heading": 90, "squawk": "1200", "on_ground": False,
                "vsoa": True, "context": [], "active_interceptors": [], "aircraft_category": "fighter",
                "severity": "green", "track_color": "green",
            }
            target = {
                "callsign": "AAL1", "lat": 27.8, "lon": -80.1, "altitude": 33000,
                "groundspeed": 430, "heading": 100, "squawk": "1200", "on_ground": False,
                "vsoa": False, "context": [], "active_interceptors": [], "aircraft_category": "airliner",
                "severity": "green", "track_color": "green",
            }
            monitor.state.pilots = [interceptor, target]
            monitor.state.alerts = []
            calls = 0
            original = monitor.engine._track_intercept_solution

            def counted(one, two):
                nonlocal calls
                calls += 1
                return original(one, two)

            monitor.engine._track_intercept_solution = counted
            ok, *_ = await monitor.assign_manual_intercepts(["VIPER11"], "AAL1", "TEST")
            assert ok is True and calls == 1
            monitor._rebuild_current_intercepts()
            assert calls == 1
            await monitor.recalculate_intercepts("TEST")
            assert calls == 2
        finally:
            if monitor.persistence_task and not monitor.persistence_task.done():
                monitor.persistence_task.cancel()
            await monitor.client.aclose()

    asyncio.run(scenario())


def test_frontend_uses_delta_modules_and_active_workspace_rendering():
    assert '/static/modules/delta-client.js?v=1.4.8' in INDEX
    assert '/static/modules/artcc-cache.js?v=1.4.8' in INDEX
    assert '/static/modules/render-scheduler.js?v=1.4.8' in INDEX
    assert "data?.type === 'delta'" in JS
    assert "VngRenderScheduler?.mark('map', 'intercept', 'atc')" in JS
    assert "if (state.workspaceTab === 'map')" in JS
    assert "fetchTrackDetail(callsign)" in JS
    assert '@app.get("/api/tracks/{callsign}")' in MAIN
    assert "build_live_delta" in MAIN and "compact_live_payload" in MAIN


def test_connection_manager_sends_delta_after_full_snapshot():
    from app.main import ConnectionManager

    class FakeSocket:
        def __init__(self):
            self.messages = []

        async def send_text(self, value):
            self.messages.append(value)

    async def scenario():
        manager = ConnectionManager()
        socket = FakeSocket()
        manager.connections.add(socket)
        base_pilots = [{"callsign": f"TST{i:03d}", "lat": 25 + i / 1000, "lon": -80.0} for i in range(100)]
        first = {
            "type": "live", "revision": 1, "feed_sequence": 1, "pilots": base_pilots,
            "alerts": [], "operations": [], "manual_intercepts": [], "intercept_controls": [],
            "controllers": [], "stats": {"monitored_aircraft": 100},
        }
        second = {
            **first, "revision": 2, "feed_sequence": 2,
            "pilots": [{**item, "lat": item["lat"] + 0.01} if item["callsign"] == "TST050" else item for item in base_pilots],
        }
        await manager.broadcast(first)
        await manager.broadcast(second)
        import json
        messages = [json.loads(value) for value in socket.messages]
        assert messages[0]["type"] == "live"
        assert messages[1]["type"] == "delta"
        assert messages[1]["base_revision"] == 1 and messages[1]["revision"] == 2
        assert [item["callsign"] for item in messages[1]["collections"]["pilots"]["upsert"]] == ["TST050"]

    asyncio.run(scenario())
