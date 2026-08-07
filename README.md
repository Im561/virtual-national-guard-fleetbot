# Virtual National Guard Fleet Discord Bot

## Version 1.1.1

Railway-ready Discord bot that reads Virtual National Guard aircraft locations from the phpVMS API.

### What is new

- Hotfix: user commands return last-known-good data immediately instead of waiting through background API retries.
- Hotfix: `/location` still works when the optional airport-detail endpoint is slow or unavailable.
- Hotfix: dashboard, modal, and pagination errors now clear Discord's loading state with a useful response.

- `/fleet` interactive dashboard with Airport, Aircraft, Type, Wing, and Fleet Status buttons.
- Search buttons open Discord forms; users no longer need to remember every command option.
- Previous and Next buttons paginate long fleet results instead of silently cutting them off.
- User-specific controls prevent another member from changing someone else's result page.
- Automatic phpVMS retries with exponential backoff for timeouts, rate limits, and server errors.
- Last-known-good fleet data remains available as clearly marked `STALE DATA` when phpVMS is unavailable.
- Optional disk persistence restores the last-known-good cache after a Railway restart.
- Background refresh and expanded `/health` diagnostics.
- Command cooldowns protect the phpVMS API.
- `/refresh` and `/apistatus` both require Discord **Manage Server** permission.
- The original single-file implementation is split into maintainable modules with regression tests.

## Commands

- `/fleet` — open the interactive button dashboard.
- `/location airport:KLFI` — aircraft currently at an airport, grouped by wing.
- `/airframe query:04-4071` — find an aircraft by registration, tail number, or name.
- `/type aircraft:F22` — show every matching aircraft type and its current airport.
- `/wing wing:192nd` — show aircraft assigned to a wing, grouped by airport.
- `/fleetstatus` — fleet totals, locations, aircraft groups, and data state.
- `/refresh` — staff-only forced phpVMS refresh.
- `/apistatus` — staff-only API and cache health check.
- `/fleethelp` — command guide.

Long result sets display one page at a time with **Previous** and **Next** controls.

## Discord setup

1. Open the Discord Developer Portal.
2. Create or select the application.
3. Open **Bot**, create the bot, and copy its token.
4. Under installation/OAuth scopes, enable `bot` and `applications.commands`.
5. Grant View Channels, Send Messages, Embed Links, and Use Application Commands.
6. Invite the bot to the Virtual National Guard server.
7. Enable Discord Developer Mode, right-click the server, and copy its Server ID.

Never place the bot token in this repository.

## phpVMS setup

A phpVMS user API key is required. The bot sends it in the `X-API-Key` request header.

Required endpoint access:

- `/api/fleet`
- `/api/airlines`
- `/api/airports/{ICAO}`

Use a dedicated service account when possible. Never post the key in Discord or commit it to GitHub.

## Railway variables

```env
DISCORD_TOKEN=your_discord_bot_token
DISCORD_GUILD_ID=your_discord_server_id
PHPVMS_BASE_URL=https://virtualnationalguard.com
PHPVMS_API_KEY=your_phpvms_api_key
CACHE_TTL_SECONDS=300
BACKGROUND_REFRESH_SECONDS=60
STATE_FILE_PATH=/app/data/fleetbot-state.json
LOG_LEVEL=INFO
```

`STATE_FILE_PATH` is optional. For persistence across deployments, attach a Railway volume at `/app/data`. Without a volume, the bot still works, but the saved cache disappears when Railway replaces the container.

The web server binds to Railway's injected `PORT` on `0.0.0.0`. The included `railway.json` checks `/health`.

## Health states

- `LIVE DATA` — the current request refreshed phpVMS successfully.
- `CACHED DATA` — the bot served a recent in-memory snapshot.
- `STALE DATA` — live refresh failed and the bot safely served its last-known-good snapshot.
- `NO DATA` — phpVMS has not succeeded and no persistent cache exists.

`/health` reports Discord readiness, fleet data state, cache age, refresh timestamps, API latency, and the last safe API error.

## First test

After Railway deploys, check its logs for successful command synchronization and then run:

```text
/fleet
/apistatus
/location airport:KLFI
```

## Local checks

```text
python -m unittest discover -s tests -v
python -m compileall bot.py fleetbot tests
```

## Troubleshooting

### Commands do not appear

- Confirm `DISCORD_GUILD_ID` is correct.
- Confirm the bot was invited with `bot` and `applications.commands` scopes.
- Restart the Railway deployment.

### HTTP 401 or 403

The API key is invalid, expired, or lacks access to a required phpVMS endpoint. Replace the key in Railway and redeploy.

### Results show STALE DATA

The bot retained its last successful fleet snapshot because phpVMS could not be refreshed. Staff can use `/apistatus` for the safe error summary and check Railway logs for detailed diagnostics.
