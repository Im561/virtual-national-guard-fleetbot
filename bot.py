from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import aiohttp
import discord
from aiohttp import web
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv


load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("vng-fleet-bot")


class ConfigurationError(RuntimeError):
    pass


class PhpVmsApiError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Aircraft:
    id: str
    registration: str
    tail_number: str
    name: str
    icao: str
    type_name: str
    airport_id: str
    active: bool
    wing_id: str
    wing_name: str
    wing_code: str
    updated_at: str

    @property
    def display_tail(self) -> str:
        if self.tail_number and self.registration:
            if self.tail_number.casefold() != self.registration.casefold():
                return f"{self.registration} / {self.tail_number}"
        return self.registration or self.tail_number or self.name or self.id

    @property
    def display_type(self) -> str:
        return self.icao or self.type_name or "Unknown"


@dataclass(slots=True)
class FleetSnapshot:
    aircraft: list[Aircraft]
    fetched_at: datetime


class PhpVmsClient:
    def __init__(self, base_url: str, api_key: str, cache_ttl: int = 300) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.api_key = api_key
        self.cache_ttl = max(15, cache_ttl)
        self._session: aiohttp.ClientSession | None = None
        self._snapshot: FleetSnapshot | None = None
        self._airlines: dict[str, dict[str, Any]] = {}
        self._cache_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    "X-API-Key": self.api_key,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": "VirtualNationalGuard-FleetBot/1.0",
                },
            )

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _safe_url(self, path_or_url: str) -> str:
        candidate = (
            path_or_url
            if path_or_url.startswith(("http://", "https://"))
            else urljoin(self.base_url, path_or_url.lstrip("/"))
        )
        base = urlparse(self.base_url)
        target = urlparse(candidate)
        if target.scheme not in {"http", "https"} or target.netloc != base.netloc:
            raise PhpVmsApiError("phpVMS returned an unexpected pagination URL.")
        return candidate

    async def _request_json(
        self,
        path_or_url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        await self.start()
        assert self._session is not None

        url = self._safe_url(path_or_url)
        try:
            async with self._session.get(url, params=params) as response:
                body = await response.text()
                if response.status == 401:
                    raise PhpVmsApiError(
                        "phpVMS rejected the API key (HTTP 401). Check PHPVMS_API_KEY."
                    )
                if response.status == 403:
                    raise PhpVmsApiError(
                        "The phpVMS account does not have permission to access this API endpoint (HTTP 403)."
                    )
                if response.status == 404:
                    raise PhpVmsApiError(
                        f"phpVMS endpoint was not found: {url} (HTTP 404)."
                    )
                if response.status >= 400:
                    compact = " ".join(body.split())[:300]
                    raise PhpVmsApiError(
                        f"phpVMS request failed with HTTP {response.status}: {compact}"
                    )
                try:
                    payload = json_loads(body)
                except ValueError as exc:
                    raise PhpVmsApiError(
                        "phpVMS returned non-JSON data. Confirm the base URL and API availability."
                    ) from exc
                if not isinstance(payload, dict):
                    raise PhpVmsApiError("phpVMS returned an unexpected JSON response.")
                return payload
        except asyncio.TimeoutError as exc:
            raise PhpVmsApiError("The phpVMS request timed out.") from exc
        except aiohttp.ClientError as exc:
            raise PhpVmsApiError(f"Could not connect to phpVMS: {exc}") from exc

    async def _get_all_pages(self, path: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        next_url: str | None = path
        params: dict[str, Any] | None = {"page": 1, "per_page": 100}
        visited: set[str] = set()

        while next_url:
            url_key = self._safe_url(next_url)
            if url_key in visited:
                raise PhpVmsApiError("phpVMS pagination loop detected.")
            visited.add(url_key)

            payload = await self._request_json(next_url, params=params)
            params = None

            data = payload.get("data", [])
            if isinstance(data, list):
                items.extend(item for item in data if isinstance(item, dict))
            elif isinstance(data, dict):
                items.append(data)

            links = payload.get("links") or {}
            candidate = links.get("next") if isinstance(links, dict) else None
            next_url = candidate if isinstance(candidate, str) and candidate else None

            # Some customized phpVMS installations omit links.next but retain meta.
            if not next_url:
                meta = payload.get("meta") or {}
                if isinstance(meta, dict):
                    current_page = int(meta.get("current_page") or 1)
                    last_page = int(meta.get("last_page") or current_page)
                    if current_page < last_page:
                        next_url = path
                        params = {"page": current_page + 1, "per_page": 100}

        return items

    async def get_airport(self, icao: str) -> dict[str, Any] | None:
        normalized = normalize(icao)
        try:
            payload = await self._request_json(f"/api/airports/{normalized}")
        except PhpVmsApiError as exc:
            if "HTTP 404" in str(exc):
                return None
            raise
        data = payload.get("data")
        return data if isinstance(data, dict) else None

    async def _load_airlines(self) -> dict[str, dict[str, Any]]:
        records = await self._get_all_pages("/api/airlines")
        return {str(record.get("id", "")): record for record in records}

    async def get_fleet(self, *, force: bool = False) -> FleetSnapshot:
        if not force and self._snapshot is not None:
            age = (datetime.now(timezone.utc) - self._snapshot.fetched_at).total_seconds()
            if age < self.cache_ttl:
                return self._snapshot

        async with self._cache_lock:
            if not force and self._snapshot is not None:
                age = (datetime.now(timezone.utc) - self._snapshot.fetched_at).total_seconds()
                if age < self.cache_ttl:
                    return self._snapshot

            airlines_task = asyncio.create_task(self._load_airlines())
            fleet_task = asyncio.create_task(self._get_all_pages("/api/fleet"))
            airlines, subfleets = await asyncio.gather(airlines_task, fleet_task)
            self._airlines = airlines

            flattened: list[Aircraft] = []
            for subfleet in subfleets:
                airline_id = str(subfleet.get("airline_id") or "")
                airline = subfleet.get("airline")
                if not isinstance(airline, dict):
                    airline = airlines.get(airline_id, {})

                wing_name = clean(
                    airline.get("name")
                    or subfleet.get("airline_name")
                    or f"Wing {airline_id or 'Unknown'}"
                )
                wing_code = clean(airline.get("icao") or airline.get("iata") or "")
                type_icao = clean(subfleet.get("type") or "")
                type_name = clean(subfleet.get("name") or "")

                aircraft_list = subfleet.get("aircraft") or []
                if not isinstance(aircraft_list, list):
                    continue

                for record in aircraft_list:
                    if not isinstance(record, dict):
                        continue
                    flattened.append(
                        Aircraft(
                            id=clean(record.get("id")),
                            registration=clean(record.get("registration")),
                            tail_number=clean(record.get("tail_number")),
                            name=clean(record.get("name")),
                            icao=clean(record.get("icao") or type_icao).upper(),
                            type_name=type_name,
                            airport_id=clean(record.get("airport_id")).upper(),
                            active=bool(record.get("active", True)),
                            wing_id=airline_id,
                            wing_name=wing_name,
                            wing_code=wing_code.upper(),
                            updated_at=clean(record.get("updated_at")),
                        )
                    )

            flattened.sort(
                key=lambda item: (
                    item.airport_id or "ZZZZ",
                    item.wing_name.casefold(),
                    item.display_type.casefold(),
                    item.display_tail.casefold(),
                )
            )
            self._snapshot = FleetSnapshot(
                aircraft=flattened,
                fetched_at=datetime.now(timezone.utc),
            )
            log.info(
                "Fleet cache refreshed: %s aircraft across %s subfleets",
                len(flattened),
                len(subfleets),
            )
            return self._snapshot


def json_loads(value: str) -> Any:
    import json

    return json.loads(value)


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize(value: str) -> str:
    return "".join(character for character in value.upper().strip() if character.isalnum())


def truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


def chunks_by_length(lines: Iterable[str], max_length: int = 1000) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0

    for line in lines:
        added = len(line) + (1 if current else 0)
        if current and current_length + added > max_length:
            chunks.append("\n".join(current))
            current = [line]
            current_length = len(line)
        else:
            current.append(line)
            current_length += added

    if current:
        chunks.append("\n".join(current))
    return chunks


def aircraft_line(item: Aircraft) -> str:
    status = "" if item.active else " · **Inactive**"
    return f"• **{item.display_type}** — `{item.display_tail}`{status}"


def format_timestamp(timestamp: datetime) -> str:
    return discord.utils.format_dt(timestamp, style="R")


class FleetBot(commands.Bot):
    def __init__(self, api: PhpVmsClient, guild_id: int | None) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.api = api
        self.guild_id = guild_id
        self.health_runner: web.AppRunner | None = None
        self.started_at = datetime.now(timezone.utc)

    async def setup_hook(self) -> None:
        await self.api.start()
        await self.start_health_server()

        if self.guild_id:
            guild = discord.Object(id=self.guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %s guild commands to %s", len(synced), self.guild_id)
        else:
            synced = await self.tree.sync()
            log.info("Synced %s global commands", len(synced))

    async def on_ready(self) -> None:
        assert self.user is not None
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="/location",
            )
        )
        log.info("Logged in as %s (%s)", self.user, self.user.id)

    async def start_health_server(self) -> None:
        port = int(os.getenv("PORT", "8080"))
        app = web.Application()
        app.router.add_get("/", self.health)
        app.router.add_get("/health", self.health)

        self.health_runner = web.AppRunner(app)
        await self.health_runner.setup()
        site = web.TCPSite(self.health_runner, "0.0.0.0", port)
        await site.start()
        log.info("Health server listening on 0.0.0.0:%s", port)

    async def health(self, _request: web.Request) -> web.Response:
        snapshot = self.api._snapshot
        return web.json_response(
            {
                "status": "ok",
                "discord_ready": self.is_ready(),
                "bot_user": str(self.user) if self.user else None,
                "cached_aircraft": len(snapshot.aircraft) if snapshot else 0,
                "cache_updated_at": (
                    snapshot.fetched_at.isoformat() if snapshot else None
                ),
                "started_at": self.started_at.isoformat(),
            }
        )

    async def close(self) -> None:
        await self.api.close()
        if self.health_runner is not None:
            await self.health_runner.cleanup()
        await super().close()


def make_base_embed(title: str, description: str | None = None) -> discord.Embed:
    return discord.Embed(
        title=title,
        description=description,
        colour=discord.Colour.from_rgb(34, 67, 128),
        timestamp=datetime.now(timezone.utc),
    )


def add_grouped_fields(
    embeds: list[discord.Embed],
    title: str,
    description: str,
    grouped_lines: list[tuple[str, list[str]]],
    footer: str,
) -> None:
    current = make_base_embed(title, description)
    field_count = 0
    approximate_chars = len(title) + len(description)

    for group_name, lines in grouped_lines:
        parts = chunks_by_length(lines, 1000)
        for index, part in enumerate(parts, start=1):
            field_name = group_name if len(parts) == 1 else f"{group_name} ({index}/{len(parts)})"
            extra_chars = len(field_name) + len(part)
            if field_count >= 25 or approximate_chars + extra_chars > 5600:
                current.set_footer(text=footer)
                embeds.append(current)
                current = make_base_embed(f"{title} — continued", description)
                field_count = 0
                approximate_chars = len(title) + len(description)

            current.add_field(
                name=truncate(field_name, 256),
                value=part or "No records",
                inline=False,
            )
            field_count += 1
            approximate_chars += extra_chars

    current.set_footer(text=footer)
    embeds.append(current)


def footer_for(snapshot: FleetSnapshot) -> str:
    return (
        f"Fleet data cached {format_timestamp(snapshot.fetched_at)}"
        " · Source: Virtual National Guard phpVMS"
    )


def exact_or_partial(
    fleet: list[Aircraft],
    query: str,
    fields: tuple[str, ...],
) -> list[Aircraft]:
    needle = normalize(query)
    exact: list[Aircraft] = []
    partial: list[Aircraft] = []

    for item in fleet:
        values = [normalize(getattr(item, field)) for field in fields]
        if needle in values:
            exact.append(item)
        elif any(needle and needle in value for value in values):
            partial.append(item)

    return exact or partial


def require_manage_guild(interaction: discord.Interaction) -> bool:
    permissions = interaction.permissions
    return bool(permissions and permissions.manage_guild)


def register_commands(bot: FleetBot) -> None:
    @bot.tree.command(name="location", description="Show all airframes currently at an airport.")
    @app_commands.describe(airport="ICAO airport code, for example KLFI")
    async def location(interaction: discord.Interaction, airport: str) -> None:
        await interaction.response.defer(thinking=True)
        icao = normalize(airport)
        if len(icao) not in {3, 4}:
            await interaction.followup.send(
                "Enter a valid 3- or 4-character airport code, such as `KLFI`.",
                ephemeral=True,
            )
            return

        snapshot, airport_info = await asyncio.gather(
            bot.api.get_fleet(),
            bot.api.get_airport(icao),
        )
        matches = [item for item in snapshot.aircraft if item.airport_id == icao]

        airport_name = ""
        if airport_info:
            airport_name = clean(airport_info.get("name"))
        description = (
            f"**{airport_name}**\n" if airport_name else ""
        ) + f"{len(matches)} airframe{'s' if len(matches) != 1 else ''} currently listed at `{icao}`."

        if not matches:
            embed = make_base_embed(f"Airframes at {icao}", description)
            embed.add_field(
                name="No aircraft found",
                value=(
                    "The fleet API currently has no aircraft assigned to this airport. "
                    "Use `/refresh` if the website was just updated."
                ),
                inline=False,
            )
            embed.set_footer(text=footer_for(snapshot))
            await interaction.followup.send(embed=embed)
            return

        grouped: dict[str, list[Aircraft]] = defaultdict(list)
        for item in matches:
            label = item.wing_name
            if item.wing_code:
                label = f"{label} ({item.wing_code})"
            grouped[label].append(item)

        fields = [
            (
                wing,
                [aircraft_line(item) for item in sorted(items, key=lambda x: (x.display_type, x.display_tail))],
            )
            for wing, items in sorted(grouped.items(), key=lambda entry: entry[0].casefold())
        ]
        embeds: list[discord.Embed] = []
        add_grouped_fields(
            embeds,
            f"Airframes at {icao}",
            description,
            fields,
            footer_for(snapshot),
        )
        await interaction.followup.send(embeds=embeds[:10])

    @bot.tree.command(name="airframe", description="Find an airframe by registration or tail number.")
    @app_commands.describe(query="Registration, tail number, or aircraft name")
    async def airframe(interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer(thinking=True)
        snapshot = await bot.api.get_fleet()
        matches = exact_or_partial(
            snapshot.aircraft,
            query,
            ("registration", "tail_number", "name", "id"),
        )

        if not matches:
            await interaction.followup.send(
                f"No airframe matched `{truncate(query, 80)}`.",
                ephemeral=True,
            )
            return

        matches = matches[:20]
        embed = make_base_embed(
            f"Airframe search: {truncate(query, 80)}",
            f"Showing {len(matches)} matching result{'s' if len(matches) != 1 else ''}.",
        )
        for item in matches:
            location_text = f"`{item.airport_id}`" if item.airport_id else "Unknown"
            wing = item.wing_name + (f" ({item.wing_code})" if item.wing_code else "")
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
        embed.set_footer(text=footer_for(snapshot))
        await interaction.followup.send(embed=embed)

    @bot.tree.command(name="type", description="Show where a type of aircraft is currently located.")
    @app_commands.describe(aircraft="Aircraft ICAO/type, for example F22 or F16")
    async def aircraft_type(interaction: discord.Interaction, aircraft: str) -> None:
        await interaction.response.defer(thinking=True)
        snapshot = await bot.api.get_fleet()
        matches = exact_or_partial(
            snapshot.aircraft,
            aircraft,
            ("icao", "type_name", "name"),
        )

        if not matches:
            await interaction.followup.send(
                f"No aircraft type matched `{truncate(aircraft, 80)}`.",
                ephemeral=True,
            )
            return

        grouped: dict[str, list[Aircraft]] = defaultdict(list)
        for item in matches:
            grouped[item.airport_id or "UNKNOWN"].append(item)

        fields = [
            (
                airport,
                [
                    f"• `{item.display_tail}` — {item.wing_name}"
                    + ("" if item.active else " · **Inactive**")
                    for item in sorted(items, key=lambda x: (x.wing_name.casefold(), x.display_tail))
                ],
            )
            for airport, items in sorted(grouped.items())
        ]

        embeds: list[discord.Embed] = []
        add_grouped_fields(
            embeds,
            f"Aircraft type: {truncate(aircraft.upper(), 100)}",
            f"{len(matches)} matching airframe{'s' if len(matches) != 1 else ''}.",
            fields,
            footer_for(snapshot),
        )
        await interaction.followup.send(embeds=embeds[:10])

    @bot.tree.command(name="wing", description="Show all aircraft assigned to a wing.")
    @app_commands.describe(wing="Wing name or phpVMS airline code")
    async def wing(interaction: discord.Interaction, wing: str) -> None:
        await interaction.response.defer(thinking=True)
        snapshot = await bot.api.get_fleet()
        matches = exact_or_partial(
            snapshot.aircraft,
            wing,
            ("wing_name", "wing_code"),
        )

        if not matches:
            await interaction.followup.send(
                f"No wing matched `{truncate(wing, 80)}`.",
                ephemeral=True,
            )
            return

        grouped: dict[str, list[Aircraft]] = defaultdict(list)
        for item in matches:
            grouped[item.airport_id or "UNKNOWN"].append(item)

        wing_names = sorted({item.wing_name for item in matches})
        title_name = wing_names[0] if len(wing_names) == 1 else truncate(wing, 100)
        fields = [
            (
                airport,
                [aircraft_line(item) for item in sorted(items, key=lambda x: (x.display_type, x.display_tail))],
            )
            for airport, items in sorted(grouped.items())
        ]

        embeds: list[discord.Embed] = []
        add_grouped_fields(
            embeds,
            f"Wing fleet: {title_name}",
            f"{len(matches)} matching airframe{'s' if len(matches) != 1 else ''}.",
            fields,
            footer_for(snapshot),
        )
        await interaction.followup.send(embeds=embeds[:10])

    @bot.tree.command(name="fleetstatus", description="Show a summary of the current fleet.")
    async def fleetstatus(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        snapshot = await bot.api.get_fleet()
        total = len(snapshot.aircraft)
        active = sum(item.active for item in snapshot.aircraft)
        airport_counts = Counter(
            item.airport_id or "UNKNOWN" for item in snapshot.aircraft
        )
        type_counts = Counter(item.display_type for item in snapshot.aircraft)

        embed = make_base_embed(
            "Virtual National Guard Fleet Status",
            f"Current phpVMS fleet snapshot contains **{total}** airframes.",
        )
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
        embed.set_footer(text=footer_for(snapshot))
        await interaction.followup.send(embed=embed)

    @bot.tree.command(name="refresh", description="Force the bot to reload phpVMS fleet data.")
    async def refresh(interaction: discord.Interaction) -> None:
        if not require_manage_guild(interaction):
            await interaction.response.send_message(
                "You need the **Manage Server** permission to use this command.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        snapshot = await bot.api.get_fleet(force=True)
        await interaction.followup.send(
            f"Fleet cache refreshed. Loaded **{len(snapshot.aircraft)}** aircraft.",
            ephemeral=True,
        )

    @bot.tree.command(name="apistatus", description="Check the phpVMS connection and fleet count.")
    async def apistatus(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        started = time.perf_counter()
        snapshot = await bot.api.get_fleet(force=True)
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        await interaction.followup.send(
            (
                "phpVMS connection successful.\n"
                f"Aircraft loaded: **{len(snapshot.aircraft)}**\n"
                f"Response and parsing time: **{elapsed_ms} ms**"
            ),
            ephemeral=True,
        )

    @bot.tree.command(name="fleethelp", description="Show the fleet bot command guide.")
    async def fleethelp(interaction: discord.Interaction) -> None:
        embed = make_base_embed(
            "Virtual National Guard Fleet Bot",
            "Searches the current aircraft locations stored in phpVMS.",
        )
        embed.add_field(
            name="/location",
            value="`/location airport:KLFI` — all airframes currently at an airport.",
            inline=False,
        )
        embed.add_field(
            name="/airframe",
            value="`/airframe query:04-4071` — find a tail or registration.",
            inline=False,
        )
        embed.add_field(
            name="/type",
            value="`/type aircraft:F22` — locations of an aircraft type.",
            inline=False,
        )
        embed.add_field(
            name="/wing",
            value="`/wing wing:192nd` — aircraft assigned to a wing.",
            inline=False,
        )
        embed.add_field(
            name="/fleetstatus",
            value="Fleet totals, busiest locations, and largest aircraft groups.",
            inline=False,
        )
        embed.add_field(
            name="/refresh",
            value="Staff-only forced refresh for newly updated phpVMS data.",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


def load_configuration() -> tuple[str, str, str, int | None, int]:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    api_key = os.getenv("PHPVMS_API_KEY", "").strip()
    base_url = os.getenv(
        "PHPVMS_BASE_URL",
        "https://virtualnationalguard.com",
    ).strip()
    guild_raw = os.getenv("DISCORD_GUILD_ID", "").strip()
    cache_raw = os.getenv("CACHE_TTL_SECONDS", "300").strip()

    missing = [
        name
        for name, value in {
            "DISCORD_TOKEN": token,
            "PHPVMS_API_KEY": api_key,
            "PHPVMS_BASE_URL": base_url,
        }.items()
        if not value
    ]
    if missing:
        raise ConfigurationError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    guild_id: int | None = None
    if guild_raw:
        try:
            guild_id = int(guild_raw)
        except ValueError as exc:
            raise ConfigurationError("DISCORD_GUILD_ID must be numeric.") from exc

    try:
        cache_ttl = int(cache_raw)
    except ValueError as exc:
        raise ConfigurationError("CACHE_TTL_SECONDS must be an integer.") from exc

    return token, api_key, base_url, guild_id, cache_ttl


async def main() -> None:
    token, api_key, base_url, guild_id, cache_ttl = load_configuration()
    api = PhpVmsClient(base_url, api_key, cache_ttl)
    bot = FleetBot(api, guild_id)
    register_commands(bot)

    @bot.tree.error
    async def on_app_command_error(
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        original = getattr(error, "original", error)
        log.exception("Application command failed", exc_info=original)

        if isinstance(original, PhpVmsApiError):
            message = f"Fleet API error: {original}"
        else:
            message = "The command failed unexpectedly. Check the Railway deployment logs."

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ConfigurationError as exc:
        log.critical("%s", exc)
        sys.exit(2)
