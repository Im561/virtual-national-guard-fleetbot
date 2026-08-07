from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import discord
from aiohttp import web
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

from .api import PhpVmsClient
from .commands import register_commands
from .domain import PhpVmsApiError


load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("vng-fleet-bot")


class ConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Settings:
    token: str
    api_key: str
    base_url: str
    guild_id: int | None
    cache_ttl: int
    state_file_path: str
    background_refresh_seconds: int


def _integer_setting(name: str, default: int, *, minimum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc
    return max(minimum, value)


def load_configuration() -> Settings:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    api_key = os.getenv("PHPVMS_API_KEY", "").strip()
    base_url = os.getenv(
        "PHPVMS_BASE_URL",
        "https://virtualnationalguard.com",
    ).strip()
    guild_raw = os.getenv("DISCORD_GUILD_ID", "").strip()

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

    return Settings(
        token=token,
        api_key=api_key,
        base_url=base_url,
        guild_id=guild_id,
        cache_ttl=_integer_setting("CACHE_TTL_SECONDS", 300, minimum=15),
        state_file_path=os.getenv("STATE_FILE_PATH", "").strip(),
        background_refresh_seconds=_integer_setting(
            "BACKGROUND_REFRESH_SECONDS",
            60,
            minimum=30,
        ),
    )


class FleetBot(commands.Bot):
    def __init__(
        self,
        api: PhpVmsClient,
        guild_id: int | None,
        background_refresh_seconds: int,
    ) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=discord.Intents.default(),
        )
        self.api = api
        self.guild_id = guild_id
        self.health_runner: web.AppRunner | None = None
        self.started_at = datetime.now(timezone.utc)
        self.background_refresh.change_interval(
            seconds=background_refresh_seconds
        )

    async def setup_hook(self) -> None:
        await self.api.start()
        await self.start_health_server()
        try:
            await self.api.get_fleet(force=True)
        except PhpVmsApiError as exc:
            log.warning("Initial phpVMS refresh failed: %s", exc)

        if not self.background_refresh.is_running():
            self.background_refresh.start()

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
                name="/fleet",
            )
        )
        log.info("Logged in as %s (%s)", self.user, self.user.id)

    @tasks.loop(seconds=60)
    async def background_refresh(self) -> None:
        try:
            snapshot = await self.api.get_fleet()
        except PhpVmsApiError as exc:
            log.error("Background fleet refresh failed: %s", exc)
        else:
            if snapshot.stale:
                log.warning("Background refresh is serving stale fleet data")

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
        snapshot = self.api.snapshot
        return web.json_response(
            {
                "status": "ok" if not snapshot or not snapshot.stale else "degraded",
                "discord_ready": self.is_ready(),
                "bot_user": str(self.user) if self.user else None,
                "fleet_data_state": snapshot.state_label if snapshot else "NO DATA",
                "cached_aircraft": len(snapshot.aircraft) if snapshot else 0,
                "cache_updated_at": snapshot.fetched_at.isoformat() if snapshot else None,
                "cache_age_seconds": snapshot.age_seconds if snapshot else None,
                "last_refresh_attempt_at": (
                    self.api.last_refresh_attempt_at.isoformat()
                    if self.api.last_refresh_attempt_at
                    else None
                ),
                "last_refresh_success_at": (
                    self.api.last_refresh_success_at.isoformat()
                    if self.api.last_refresh_success_at
                    else None
                ),
                "last_api_error": self.api.last_api_error,
                "last_response_ms": self.api.last_response_ms,
                "started_at": self.started_at.isoformat(),
            }
        )

    async def close(self) -> None:
        if self.background_refresh.is_running():
            self.background_refresh.cancel()
        await self.api.close()
        if self.health_runner is not None:
            await self.health_runner.cleanup()
        await super().close()


async def main() -> None:
    settings = load_configuration()
    api = PhpVmsClient(
        settings.base_url,
        settings.api_key,
        settings.cache_ttl,
        state_file_path=settings.state_file_path,
    )
    bot = FleetBot(
        api,
        settings.guild_id,
        settings.background_refresh_seconds,
    )
    register_commands(bot)

    @bot.tree.error
    async def on_app_command_error(
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        original = getattr(error, "original", error)
        if isinstance(error, app_commands.CommandOnCooldown):
            message = (
                "That command is cooling down. Try again in "
                f"**{error.retry_after:.1f} seconds**."
            )
        elif isinstance(original, PhpVmsApiError):
            message = f"Fleet API error: {original}"
        else:
            log.exception("Application command failed", exc_info=original)
            message = "The command failed unexpectedly. Check the Railway logs."

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    async with bot:
        await bot.start(settings.token)
