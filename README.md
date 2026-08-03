# Virtual National Guard Fleet Discord Bot

## Version 1.0.1

- Corrected phpVMS pagination handling for fleet and airline endpoints.
- Page numbers are now tracked with their query parameters, preventing false
  `pagination loop detected` errors.

Railway-ready Discord bot that reads Virtual National Guard aircraft locations from the phpVMS API.

## Commands

- `/location airport:KLFI` — aircraft currently at an airport, grouped by wing.
- `/airframe query:04-4071` — find an aircraft by registration, tail number, or name.
- `/type aircraft:F22` — show every matching aircraft type and its current airport.
- `/wing wing:192nd` — show aircraft assigned to a wing, grouped by airport.
- `/fleetstatus` — fleet totals and the most populated locations/types.
- `/refresh` — staff-only forced phpVMS refresh.
- `/apistatus` — test the API and report the number of aircraft loaded.
- `/fleethelp` — command guide.

## 1. Discord setup

1. Open the Discord Developer Portal.
2. Create or select the application.
3. Open **Bot**, create the bot, and reset/copy its token.
4. Under installation/OAuth scopes, enable:
   - `bot`
   - `applications.commands`
5. Give it these permissions:
   - View Channels
   - Send Messages
   - Embed Links
   - Use Application Commands
6. Invite it to the Virtual National Guard server.
7. In Discord, enable **Developer Mode**, then right-click the server and copy its Server ID.

Do not place the bot token in this repository.

## 2. phpVMS setup

A phpVMS user API key is required. The bot sends it in the `X-API-Key` request header.

Required endpoint access:

- `/api/fleet`
- `/api/airlines`
- `/api/airports/{ICAO}`

Use a dedicated service/bot account where possible. Do not post the API key in Discord or commit it to GitHub.

## 3. Deploy on Railway

### GitHub method

1. Create a new GitHub repository.
2. Upload every file from this project except `.env`.
3. In Railway, create a project and choose **Deploy from GitHub repo**.
4. Select the repository.
5. Open the Railway service's **Variables** tab and add:

```env
DISCORD_TOKEN=your_discord_bot_token
DISCORD_GUILD_ID=1526321807580463114
DISCORD_APPLICATION_ID=1533637941275001022
PHPVMS_BASE_URL=https://virtualnationalguard.com
PHPVMS_API_KEY=your_phpvms_api_key
CACHE_TTL_SECONDS=300
LOG_LEVEL=INFO
```

6. Deploy the staged changes.
7. Under **Settings → Networking**, generate a public domain.
8. The included `railway.json` configures `/health` as the deployment healthcheck.

The bot web server binds to Railway's injected `PORT` on `0.0.0.0`.

## 4. First test

Check the Railway logs for:

```text
Logged in as ...
Synced ... guild commands
Health server listening ...
```

Then run:

```text
/apistatus
/location airport:KLFI
```

## Troubleshooting

### Commands do not appear

- Confirm `DISCORD_GUILD_ID` is the correct server ID.
- Confirm the bot was invited with both `bot` and `applications.commands`.
- Restart/redeploy the Railway service.

### HTTP 401 from phpVMS

The API key is missing, expired, or incorrect. Regenerate the key and replace `PHPVMS_API_KEY` in Railway.

### HTTP 403 from phpVMS

The phpVMS account does not have access to the fleet, airlines, or airport API endpoint.

### `/location` returns no aircraft

The bot reports the current `airport_id` stored on each phpVMS aircraft record. Confirm that the website has an aircraft assigned to that airport, then run `/refresh`.

### Wing names are wrong

The bot maps each fleet subfleet's `airline_id` to `/api/airlines`. If the fighter wings are represented differently in the customized Virtual National Guard installation, run `/apistatus` and inspect the logs. The parser can then be adjusted to the site's custom fields.
