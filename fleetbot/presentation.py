from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

import discord

from .domain import Aircraft, FleetSnapshot, PageCursor, chunks_by_length, truncate


SearchHandler = Callable[
    [discord.Interaction, str, str | None, bool],
    Awaitable[None],
]


def make_base_embed(title: str, description: str | None = None) -> discord.Embed:
    return discord.Embed(
        title=title,
        description=description,
        colour=discord.Colour.from_rgb(34, 67, 128),
        timestamp=datetime.now(timezone.utc),
    )


def aircraft_line(item: Aircraft) -> str:
    status = "" if item.active else " · **Inactive**"
    return f"• **{item.display_type}** — `{item.display_tail}`{status}"


def format_timestamp(timestamp: datetime) -> str:
    return discord.utils.format_dt(timestamp, style="R")


def footer_for(snapshot: FleetSnapshot) -> str:
    return (
        f"{snapshot.state_label} · Fleet data from {format_timestamp(snapshot.fetched_at)}"
        " · Source: Virtual National Guard phpVMS"
    )


def add_grouped_fields(
    title: str,
    description: str,
    grouped_lines: list[tuple[str, list[str]]],
    footer: str,
) -> list[discord.Embed]:
    embeds: list[discord.Embed] = []
    current = make_base_embed(title, description)
    field_count = 0
    approximate_chars = len(title) + len(description)

    for group_name, lines in grouped_lines:
        parts = chunks_by_length(lines, 1000) or ["No records"]
        for index, part in enumerate(parts, start=1):
            field_name = (
                group_name
                if len(parts) == 1
                else f"{group_name} ({index}/{len(parts)})"
            )
            extra_chars = len(field_name) + len(part)
            if field_count >= 25 or approximate_chars + extra_chars > 5600:
                current.set_footer(text=footer)
                embeds.append(current)
                current = make_base_embed(f"{title} — continued", description)
                field_count = 0
                approximate_chars = len(title) + len(description)

            current.add_field(
                name=truncate(field_name, 256),
                value=part,
                inline=False,
            )
            field_count += 1
            approximate_chars += extra_chars

    current.set_footer(text=footer)
    embeds.append(current)
    return embeds


class EmbedPaginator(discord.ui.View):
    def __init__(
        self,
        embeds: list[discord.Embed],
        owner_id: int,
        *,
        timeout: float = 300,
    ) -> None:
        super().__init__(timeout=timeout)
        self.embeds = embeds
        self.owner_id = owner_id
        self.cursor = PageCursor(len(embeds))
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        self.previous_page.disabled = not self.cursor.has_previous
        self.next_page.disabled = not self.cursor.has_next
        self.page_number.label = self.cursor.label

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            "Run the command yourself to control your own results.",
            ephemeral=True,
        )
        return False

    async def _show_page(self, interaction: discord.Interaction) -> None:
        self._refresh_buttons()
        await interaction.response.edit_message(
            embed=self.embeds[self.cursor.index],
            view=self,
        )

    @discord.ui.button(
        label="Previous",
        style=discord.ButtonStyle.secondary,
        custom_id="fleetbot:previous",
    )
    async def previous_page(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        self.cursor.previous()
        await self._show_page(interaction)

    @discord.ui.button(
        label="Page 1/1",
        style=discord.ButtonStyle.secondary,
        disabled=True,
        custom_id="fleetbot:page",
    )
    async def page_number(
        self,
        _interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        return

    @discord.ui.button(
        label="Next",
        style=discord.ButtonStyle.primary,
        custom_id="fleetbot:next",
    )
    async def next_page(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        self.cursor.next()
        await self._show_page(interaction)


async def send_pages(
    interaction: discord.Interaction,
    pages: list[discord.Embed],
    *,
    ephemeral: bool = False,
) -> None:
    if not pages:
        pages = [make_base_embed("Fleet results", "No records were returned.")]
    view = (
        EmbedPaginator(pages, interaction.user.id)
        if len(pages) > 1
        else None
    )
    if interaction.response.is_done():
        await interaction.followup.send(
            embed=pages[0],
            view=view,
            ephemeral=ephemeral,
        )
    else:
        await interaction.response.send_message(
            embed=pages[0],
            view=view,
            ephemeral=ephemeral,
        )


class FleetSearchModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        action: str,
        title: str,
        label: str,
        placeholder: str,
        handler: SearchHandler,
    ) -> None:
        super().__init__(title=title, timeout=300)
        self.action = action
        self.handler = handler
        self.query = discord.ui.TextInput(
            label=label,
            placeholder=placeholder,
            min_length=1,
            max_length=80,
        )
        self.add_item(self.query)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        await self.handler(
            interaction,
            self.action,
            str(self.query.value),
            True,
        )


class FleetDashboard(discord.ui.View):
    def __init__(self, owner_id: int, handler: SearchHandler) -> None:
        super().__init__(timeout=900)
        self.owner_id = owner_id
        self.handler = handler

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            "Run `/fleet` to open your own dashboard.",
            ephemeral=True,
        )
        return False

    async def _open_search(
        self,
        interaction: discord.Interaction,
        *,
        action: str,
        title: str,
        label: str,
        placeholder: str,
    ) -> None:
        await interaction.response.send_modal(
            FleetSearchModal(
                action=action,
                title=title,
                label=label,
                placeholder=placeholder,
                handler=self.handler,
            )
        )

    @discord.ui.button(label="Airport", emoji="🛬", style=discord.ButtonStyle.primary)
    async def airport(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        await self._open_search(
            interaction,
            action="location",
            title="Find aircraft at an airport",
            label="Airport ICAO code",
            placeholder="KLFI",
        )

    @discord.ui.button(label="Aircraft", emoji="✈️", style=discord.ButtonStyle.primary)
    async def aircraft(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        await self._open_search(
            interaction,
            action="airframe",
            title="Find an aircraft",
            label="Registration, tail number, or name",
            placeholder="04-4071",
        )

    @discord.ui.button(label="Type", emoji="🔎", style=discord.ButtonStyle.secondary)
    async def aircraft_type(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        await self._open_search(
            interaction,
            action="type",
            title="Find an aircraft type",
            label="Aircraft ICAO or type",
            placeholder="F22",
        )

    @discord.ui.button(label="Wing", emoji="🛡️", style=discord.ButtonStyle.secondary)
    async def wing(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        await self._open_search(
            interaction,
            action="wing",
            title="Find a wing",
            label="Wing name or code",
            placeholder="192nd",
        )

    @discord.ui.button(label="Fleet Status", emoji="📊", style=discord.ButtonStyle.success)
    async def fleet_status(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        await self.handler(interaction, "status", None, True)
