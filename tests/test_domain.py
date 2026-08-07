from __future__ import annotations

import unittest
from datetime import datetime, timezone

from fleetbot.domain import (
    Aircraft,
    FleetSnapshot,
    PageCursor,
    chunks_by_length,
    exact_or_partial,
    has_manage_guild,
    normalize,
)


def aircraft(registration: str, *, name: str = "Raptor") -> Aircraft:
    return Aircraft(
        id=registration,
        registration=registration,
        tail_number=registration,
        name=name,
        icao="F22",
        type_name="F-22A Raptor",
        airport_id="KLFI",
        active=True,
        wing_id="192",
        wing_name="192nd Fighter Wing",
        wing_code="VNG",
        updated_at="",
    )


class DomainTests(unittest.TestCase):
    def test_normalize_removes_search_punctuation(self) -> None:
        self.assertEqual(normalize(" 04-4071 "), "044071")

    def test_exact_results_win_over_partial_results(self) -> None:
        fleet = [aircraft("04-4071"), aircraft("04-40710")]
        matches = exact_or_partial(fleet, "04-4071", ("registration",))
        self.assertEqual([item.registration for item in matches], ["04-4071"])

    def test_chunks_stay_within_requested_limit(self) -> None:
        chunks = chunks_by_length(["aaaa", "bbbb", "cccc"], max_length=9)
        self.assertEqual(chunks, ["aaaa\nbbbb", "cccc"])

    def test_page_cursor_never_moves_out_of_bounds(self) -> None:
        cursor = PageCursor(total=3)
        cursor.previous()
        self.assertEqual(cursor.index, 0)
        cursor.next()
        cursor.next()
        cursor.next()
        self.assertEqual(cursor.index, 2)
        self.assertEqual(cursor.label, "Page 3/3")

    def test_snapshot_labels_live_cached_and_stale(self) -> None:
        snapshot = FleetSnapshot((aircraft("04-4071"),), datetime.now(timezone.utc))
        self.assertEqual(snapshot.state_label, "LIVE DATA")
        self.assertEqual(snapshot.as_cached().state_label, "CACHED DATA")
        self.assertEqual(snapshot.as_stale("offline").state_label, "STALE DATA")

    def test_manage_server_permission_is_required(self) -> None:
        allowed = type("Permissions", (), {"manage_guild": True})()
        denied = type("Permissions", (), {"manage_guild": False})()
        self.assertTrue(has_manage_guild(allowed))
        self.assertFalse(has_manage_guild(denied))
        self.assertFalse(has_manage_guild(None))


if __name__ == "__main__":
    unittest.main()
