from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

try:
    import aiohttp  # noqa: F401
except ModuleNotFoundError:
    aiohttp = None


@unittest.skipIf(aiohttp is None, "aiohttp is not installed in the local test runtime")
class ApiCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_snapshot_is_returned_without_blocking_user_command(self) -> None:
        from fleetbot.api import PhpVmsClient
        from fleetbot.domain import FleetSnapshot

        client = PhpVmsClient("https://example.com", "test-key")
        stale = FleetSnapshot(
            aircraft=(),
            fetched_at=datetime.now(timezone.utc),
            source="stale",
            stale=True,
            last_error="temporary outage",
        )
        client._snapshot = stale
        client._load_airlines = AsyncMock(side_effect=AssertionError("network used"))
        client._get_all_pages = AsyncMock(side_effect=AssertionError("network used"))

        result = await client.get_fleet()

        self.assertIs(result, stale)
        client._load_airlines.assert_not_awaited()
        client._get_all_pages.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
