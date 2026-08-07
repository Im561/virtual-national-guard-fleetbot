from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fleetbot.domain import Aircraft, FleetSnapshot
from fleetbot.persistence import load_snapshot, save_snapshot


class PersistenceTests(unittest.TestCase):
    def test_snapshot_round_trip_loads_as_stale_disk_cache(self) -> None:
        item = Aircraft(
            id="1",
            registration="04-4071",
            tail_number="04-4071",
            name="Raptor",
            icao="F22",
            type_name="F-22A",
            airport_id="KLFI",
            active=True,
            wing_id="192",
            wing_name="192nd Fighter Wing",
            wing_code="VNG",
            updated_at="2026-08-06T00:00:00Z",
        )
        snapshot = FleetSnapshot((item,), datetime.now(timezone.utc))

        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "fleet-cache.json")
            save_snapshot(path, snapshot)
            loaded = load_snapshot(path)

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.aircraft, snapshot.aircraft)
        self.assertTrue(loaded.stale)
        self.assertEqual(loaded.source, "disk")

    def test_missing_cache_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "missing.json")
            self.assertIsNone(load_snapshot(path))


if __name__ == "__main__":
    unittest.main()
