from __future__ import annotations

import unittest

try:
    import discord  # noqa: F401
except ModuleNotFoundError:
    discord = None


@unittest.skipIf(discord is None, "discord.py is not installed in the local test runtime")
class DiscordUiTests(unittest.IsolatedAsyncioTestCase):
    async def test_dashboard_has_expected_buttons(self) -> None:
        from fleetbot.presentation import FleetDashboard

        async def handler(*_args: object) -> None:
            return None

        view = FleetDashboard(owner_id=123, handler=handler)
        labels = [item.label for item in view.children]
        self.assertEqual(
            labels,
            ["Airport", "Aircraft", "Type", "Wing", "Fleet Status"],
        )

    async def test_paginator_has_previous_page_and_next_controls(self) -> None:
        from fleetbot.presentation import EmbedPaginator, make_base_embed

        view = EmbedPaginator(
            [make_base_embed("One"), make_base_embed("Two")],
            owner_id=123,
        )
        labels = [item.label for item in view.children]
        self.assertEqual(labels, ["Previous", "Page 1/2", "Next"])
        self.assertTrue(view.previous_page.disabled)
        self.assertFalse(view.next_page.disabled)


if __name__ == "__main__":
    unittest.main()
