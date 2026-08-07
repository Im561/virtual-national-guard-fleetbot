from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

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

    async def test_dashboard_command_sends_buttons_immediately(self) -> None:
        from fleetbot.commands import register_commands

        class FakeTree:
            def __init__(self) -> None:
                self.commands: dict[str, object] = {}

            def command(self, *, name: str, description: str):
                del description

                def decorator(callback: object) -> object:
                    self.commands[name] = callback
                    return callback

                return decorator

        class FakeResponse:
            def __init__(self) -> None:
                self.done = False
                self.messages: list[dict[str, object]] = []

            def is_done(self) -> bool:
                return self.done

            async def send_message(self, **kwargs: object) -> None:
                self.done = True
                self.messages.append(kwargs)

        tree = FakeTree()
        bot = SimpleNamespace(tree=tree, api=object())
        register_commands(bot)
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=123),
            response=FakeResponse(),
        )

        await tree.commands["fleet"](interaction)

        self.assertTrue(interaction.response.done)
        self.assertEqual(len(interaction.response.messages), 1)
        view = interaction.response.messages[0]["view"]
        self.assertEqual(
            [item.label for item in view.children],
            ["Airport", "Aircraft", "Type", "Wing", "Fleet Status"],
        )

    async def test_location_still_renders_when_airport_details_fail(self) -> None:
        from fleetbot.commands import build_location_pages
        from fleetbot.domain import Aircraft, FleetSnapshot

        aircraft = Aircraft(
            id="1",
            registration="04-4071",
            tail_number="",
            name="Raptor 1",
            icao="F22",
            type_name="F-22A Raptor",
            airport_id="KLFI",
            active=True,
            wing_id="1",
            wing_name="192nd Fighter Wing",
            wing_code="VNG",
            updated_at="",
        )

        class FakeApi:
            async def get_fleet(self):
                return FleetSnapshot(
                    aircraft=(aircraft,),
                    fetched_at=datetime.now(timezone.utc),
                )

            async def get_airport(self, _icao: str):
                raise RuntimeError("optional endpoint unavailable")

        pages = await build_location_pages(
            SimpleNamespace(api=FakeApi()),
            "KLFI",
        )

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].title, "Airframes at KLFI")
        self.assertIn("1 airframe", pages[0].description)

    async def test_slow_action_returns_a_safe_api_error(self) -> None:
        from fleetbot.commands import run_action
        from fleetbot.domain import PhpVmsApiError

        class SlowApi:
            async def get_fleet(self):
                import asyncio

                await asyncio.sleep(1)

        interaction = SimpleNamespace()
        with mock.patch("fleetbot.commands.COMMAND_TIMEOUT_SECONDS", 0.01):
            with self.assertRaisesRegex(PhpVmsApiError, "too long"):
                await run_action(
                    SimpleNamespace(api=SlowApi()),
                    interaction,
                    "status",
                    None,
                    False,
                )


if __name__ == "__main__":
    unittest.main()
