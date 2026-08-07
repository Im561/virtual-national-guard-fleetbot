from __future__ import annotations

import asyncio
import time
from collections import Counter, defaultdict
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from .domain import (
    Aircraft,
    FleetSnapshot,
    batches,
    clean,
    exact_or_partial,
    has_manage_guild,
    normalize,
    truncate,
)
from .presentation import (
    FleetDashboard,
    add_grouped_fields,
    aircraft_line,
    footer_for,
    make_base_embed,
    send_pages,
)


if TYPE_CHECKING:
    from .app import FleetBot


def user_cooldown_key(interaction: discord.Interaction) -> tuple[int | None, int]:
    return interaction.guild_id, interaction.user.id


def no_results_embed(title: str, message: str, snapshot: FleetSnapshot) -> discord.Embed:
    embed = make_base_embed(title, message)
    embed.set_footer(text=footer_for(snapshot))
    return embed


async def build_location_pages(bot: FleetBot, query: str) -> list[discord.Embed]:
    icao = normalize(query)
    if len(icao) not in {3, 4}:
        return [
            make_base_embed(
                "Invalid airport code",
                "Enter a valid 3- or 4-character airport code, such as `KLFI`.",
            )
        ]

    snapshot, airport_info = await asyncio.gather(
        bot.api.get_fleet(),
        bot.api.get_airport(icao),
    )
    matches = [item for item in snapshot.aircraft if item.airport_id == icao]
    airport_name = clean(airport_info.get("name")) if airport_info else ""
    description = (
        f"**{airport_name}**\n" if airport_name else ""
    ) + f"{len(matches)} airframe{'s' if len(matches) != 1 else ''} currently listed at `{icao}`."

    if not matches:
        return [
            no_results_embed(
                f"Airframes at {icao}",
                description
                + "\n\nThe fleet API currently has no aircraft assigned to this airport.",
                snapshot,
            )
        ]

    grouped: dict[str, list[Aircraft]] = defaultdict(list)
    for item in matches:
        label = item.wing_name
        if item.wing_code:
            label = f"{label} ({item.wing_code})"
        grouped[label].append(item)

    fields = [
        (
            wing,
            [
                aircraft_line(item)
                for item in sorted(
                    items,
                    key=lambda value: (value.display_type, value.display_tail),
                )
            ],
        )
        for wing, items in sorted(grouped.items(), key=lambda entry: entry[0].casefold())
    ]
    return add_grouped_fields(
        f"Airframes at {icao}",
        description,
        fields,
        footer_for(snapshot),
    )


async def build_airframe_pages(bot: FleetBot, query: str) -> list[discord.Embed]:
    snapshot = await bot.api.get_fleet()
    matches = exact_or_partial(
        snapshot.aircraft,
        query,
        ("registration", "tail_number", "name", "id"),
    )
    if not matches:
        return [
            no_results_embed(
                "Airframe search",
                f"No airframe matched `{truncate(query, 80)}`.",
                snapshot,
            )
        ]

    pages: list[discord.Embed] = []
    groups = batches(matches, 12)
    for page_number, group in enumerate(groups, start=1):
        embed = make_base_embed(
            f"Airframe search: {truncate(query, 80)}",
            f"Showing {len(matches)} matching result{'s' if len(matches) != 1 else ''}.",
        )
        for item in group:
            location_text = f"`{item.airport_id}`" if item.airport_id else "Unknown"
            wing = item.wing_name + (
                f" ({item.wing_code})" if item.wing_code else ""
            )
            value = (
                f"Type: **{item.display_type}**\n"
                f"Location: {location_text}\n"
                f"Wing: {wing}\n"
                f"Status: {'Active' if item.active else 'Inactive'}"
            )
            embed.add_field(
                name=truncate(item.display_tail, 256),
                value=truncate(value, 1024),
                inline=True,
            )
        if len(groups) > 1:
            embed.description += f"\nPage {page_number} of {len(groups)}."
        embed.set_footer(text=footer_for(snapshot))
        pages.append(embed)
    return pages


async def build_type_pages(bot: FleetBot, query: str) -> list[discord.Embed]:
    snapshot = await bot.api.get_fleet()
    matches = exact_or_partial(
        snapshot.aircraft,
        query,
        ("icao", "type_name", "name"),
    )
    if not matches:
        return [
            no_results_embed(
                "Aircraft type search",
                f"No aircraft type matched `{truncate(query, 80)}`.",
                snapshot,
            )
        ]

    grouped: dict[str, list[Aircraft]] = defaultdict(list)
    for item in matches:
        grouped[item.airport_id or "UNKNOWN"].append(item)
    fields = [
        (
            airport,
            [
                f"• `{item.display_tail}` — {item.wing_name}"
                + ("" if item.active else " · **Inactive**")
                for item in sorted(
                    items,
                    key=lambda value: (value.wing_name.casefold(), value.display_tail),
                )
            ],
        )
        for airport, items in sorted(grouped.items())
    ]
    return add_grouped_fields(
        f"Aircraft type: {truncate(query.upper(), 100)}",
        f"{len(matches)} matching airframe{'s' if len(matches) != 1 else ''}.",
        fields,
        footer_for(snapshot),
    )


async def build_wing_pages(bot: FleetBot, query: str) -> list[discord.Embed]:
    snapshot = await bot.api.get_fleet()
    matches = exact_or_partial(
        snapshot.aircraft,
        query,
        ("wing_name", "wing_code"),
    )
    if not matches:
        return [
            no_results_embed(
                "Wing search",
                f"No wing matched `{truncate(query, 80)}`.",
                snapshot,
            )
        ]

    grouped: dict[str, list[Aircraft]] = defaultdict(list)
    for item in matches:
        grouped[item.airport_id or "UNKNOWN"].append(item)
    wing_names = sorted({item.wing_name for item in matches})
    title_name = wing_names[0] if len(wing_names) == 1 else truncate(query, 100)
    fields = [
        (
            airport,
            [
                aircraft_line(item)
                for item in sorted(
                    items,
                    key=lambda value: (value.display_type, value.display_tail),
                )
            ],
        )
        for airport, items in sorted(grouped.items())
    ]
    return add_grouped_fields(
        f"Wing fleet: {title_name}",
        f"{len(matches)} matching airframe{'s' if len(matches) != 1 else ''}.",
        fields,
        footer_for(snapshot),
    )


async def build_status_pages(bot: FleetBot) -> list[discord.Embed]:
    snapshot = await bot.api.get_fleet()
    total = len(snapshot.aircraft)
    active = sum(item.active for item in snapshot.aircraft)
    airport_counts = Counter(item.airport_id or "UNKNOWN" for item in snapshot.aircraft)
    type_counts = Counter(item.display_type for item in snapshot.aircraft)

    embed = make_base_embed(
        "Virtual National Guard Fleet Status",
        f"Current phpVMS fleet snapshot contains **{total}** airframes.",
    )
    embed.add_field(name="Data state", value=f"**{snapshot.state_label}**", inline=True)
    embed.add_field(name="Active", value=str(active), inline=True)
    embed.add_field(name="Inactive", value=str(total - active), inline=True)
    embed.add_field(name="Locations", value=str(len(airport_counts)), inline=True)
    embed.add_field(
        name="Largest locations",
        value="\n".join(
            f"• `{airport}` — **{count}**"
            for airport, count in airport_counts.most_common(10)
        ) or "No location data",
        inline=False,
    )
    embed.add_field(
        name="Largest aircraft groups",
        value="\n".join(
            f"• **{aircraft_type}** — {count}"
            for aircraft_type, count in type_counts.most_common(10)
        ) or "No type data",
        inline=False,
    )
    if snapshot.stale and snapshot.last_error:
        embed.add_field(
            name="Live API warning",
            value=truncate(snapshot.last_error, 1024),
            inline=False,
        )
    embed.set_footer(text=footer_for(snapshot))
    return [embed]


async def run_action(
    bot: FleetBot,
    interaction: discord.Interaction,
    action: str,
    query: str | None,
    ephemeral: bool,
) -> None:
    builders = {
        "location": build_location_pages,
        "airframe": build_airframe_pages,
        "type": build_type_pages,
        "wing": build_wing_pages,
    }
    if action == "status":
        pages = await build_status_pages(bot)
    else:
        builder = builders[action]
        pages = await builder(bot, query or "")
    await send_pages(interaction, pages, ephemeral=ephemeral)


def register_commands(bot: FleetBot) -> None:
    async def dashboard_handler(
        interaction: discord.Interaction,
        action: str,
        query: str | None,
        ephemeral: bool,
    ) -> None:
        await run_action(bot, interaction, action, query, ephemeral)

    @bot.tree.command(name="fleet", description="Open the interactive fleet dashboard.")
    @app_commands.checks.cooldown(2, 10.0, key=user_cooldown_key)
    async def fleet_dashboard(interaction: discord.Interaction) -> None:
        embed = make_base_embed(
            "Virtual National Guard Fleet Operations",
            "Choose a button below. Search buttons open a short form, and long results include Previous and Next controls.",
        )
        embed.add_field(
            name="Search",
            value="Airport · Aircraft · Type · Wing",
            inline=False,
        )
        embed.add_field(
            name="Overview",
            value="Fleet Status shows totals, locations, aircraft groups, and data health.",
            inline=False,
        )
        await interaction.response.send_message(
            embed=embed,
            view=FleetDashboard(interaction.user.id, dashboard_handler),
            ephemeral=True,
        )

    @bot.tree.command(name="location", description="Show all airframes currently at an airport.")
    @app_commands.describe(airport="ICAO airport code, for example KLFI")
    @app_commands.checks.cooldown(2, 10.0, key=user_cooldown_key)
    async def location(interaction: discord.Interaction, airport: str) -> None:
        await interaction.response.defer(thinking=True)
        await run_action(bot, interaction, "location", airport, False)

    @bot.tree.command(name="airframe", description="Find an airframe by registration or tail number.")
    @app_commands.describe(query="Registration, tail number, or aircraft name")
    @app_commands.checks.cooldown(2, 10.0, key=user_cooldown_key)
    async def airframe(interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer(thinking=True)
        await run_action(bot, interaction, "airframe", query, False)

    @bot.tree.command(name="type", description="Show where a type of aircraft is currently located.")
    @app_commands.describe(aircraft="Aircraft ICAO/type, for example F22 or F16")
    @app_commands.checks.cooldown(2, 10.0, key=user_cooldown_key)
    async def aircraft_type(interaction: discord.Interaction, aircraft: str) -> None:
        await interaction.response.defer(thinking=True)
        await run_action(bot, interaction, "type", aircraft, False)

    @bot.tree.command(name="wing", description="Show all aircraft assigned to a wing.")
    @app_commands.describe(wing="Wing name or phpVMS airline code")
    @app_commands.checks.cooldown(2, 10.0, key=user_cooldown_key)
    async def wing(interaction: discord.Interaction, wing: str) -> None:
        await interaction.response.defer(thinking=True)
        await run_action(bot, interaction, "wing", wing, False)

    @bot.tree.command(name="fleetstatus", description="Show a summary of the current fleet.")
    @app_commands.checks.cooldown(2, 10.0, key=user_cooldown_key)
    async def fleetstatus(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        await run_action(bot, interaction, "status", None, False)

    @bot.tree.command(name="refresh", description="Force the bot to reload phpVMS fleet data.")
    @app_commands.checks.cooldown(1, 30.0, key=user_cooldown_key)
    async def refresh(interaction: discord.Interaction) -> None:
        if not has_manage_guild(interaction.permissions):
            await interaction.response.send_message(
                "You need the **Manage Server** permission to use this command.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        snapshot = await bot.api.get_fleet(force=True)
        await interaction.followup.send(
            f"Fleet refresh finished with **{len(snapshot.aircraft)}** aircraft. Data state: **{snapshot.state_label}**.",
            ephemeral=True,
        )

    @bot.tree.command(name="apistatus", description="Check phpVMS connectivity and fleet health.")
    @app_commands.checks.cooldown(1, 30.0, key=user_cooldown_key)
    async def apistatus(interaction: discord.Interaction) -> None:
        if not has_manage_guild(interaction.permissions):
            await interaction.response.send_message(
                "You need the **Manage Server** permission to use this command.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        started = time.perf_counter()
        snapshot = await bot.api.get_fleet(force=True)
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        message = (
            f"Fleet data state: **{snapshot.state_label}**\n"
            f"Aircraft loaded: **{len(snapshot.aircraft)}**\n"
            f"Refresh and parsing time: **{elapsed_ms} ms**"
        )
        if snapshot.stale and snapshot.last_error:
            message += f"\nLive API warning: {truncate(snapshot.last_error, 300)}"
        await interaction.followup.send(message, ephemeral=True)

    @bot.tree.command(name="fleethelp", description="Show the fleet bot command guide.")
    async def fleethelp(interaction: discord.Interaction) -> None:
        embed = make_base_embed(
            "Virtual National Guard Fleet Bot",
            "Use `/fleet` for the button dashboard or use a command directly.",
        )
        for name, value in (
            ("/fleet", "Interactive buttons for airport, aircraft, type, wing, and fleet status."),
            ("/location", "`/location airport:KLFI` — airframes at an airport."),
            ("/airframe", "`/airframe query:04-4071` — find a tail or registration."),
            ("/type", "`/type aircraft:F22` — locations of an aircraft type."),
            ("/wing", "`/wing wing:192nd` — aircraft assigned to a wing."),
            ("/fleetstatus", "Fleet totals, locations, and aircraft groups."),
            ("Staff tools", "`/refresh` and `/apistatus` require Manage Server."),
        ):
            embed.add_field(name=name, value=value, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
