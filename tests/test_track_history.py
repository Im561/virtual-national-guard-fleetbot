import asyncio

from app.vatsim import VatsimMonitor


async def _broadcast(_payload):
    return None


def test_shared_track_history_records_movement():
    monitor = VatsimMonitor(_broadcast)
    try:
        monitor._record_track_history([
            {"callsign": "AAL123", "lat": 30.0, "lon": -80.0, "altitude": 30000}
        ])
        monitor._record_track_history([
            {"callsign": "AAL123", "lat": 30.02, "lon": -79.98, "altitude": 30200}
        ])
        history = monitor.get_track_history("aal123")
        assert len(history) == 2
        assert history[0]["lat"] == 30.0
        assert history[-1]["altitude"] == 30200
    finally:
        asyncio.run(monitor.client.aclose())
