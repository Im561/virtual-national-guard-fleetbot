from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import aiohttp

from .domain import Aircraft, FleetSnapshot, PhpVmsApiError, clean, normalize
from .persistence import load_snapshot, save_snapshot


log = logging.getLogger("vng-fleet-bot.api")


class PhpVmsClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        cache_ttl: int = 300,
        *,
        state_file_path: str = "",
        retry_attempts: int = 3,
        retry_base_seconds: float = 0.75,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.api_key = api_key
        self.cache_ttl = max(15, cache_ttl)
        self.state_file_path = state_file_path.strip()
        self.retry_attempts = max(1, retry_attempts)
        self.retry_base_seconds = max(0.1, retry_base_seconds)
        self._session: aiohttp.ClientSession | None = None
        self._snapshot: FleetSnapshot | None = None
        self._airlines: dict[str, dict[str, Any]] = {}
        self._airports: dict[str, dict[str, Any] | None] = {}
        self._cache_lock = asyncio.Lock()
        self._state_loaded = False
        self.last_refresh_attempt_at: datetime | None = None
        self.last_refresh_success_at: datetime | None = None
        self.last_api_error: str | None = None
        self.last_response_ms: int | None = None

    @property
    def snapshot(self) -> FleetSnapshot | None:
        return self._snapshot

    async def start(self) -> None:
        if not self._state_loaded:
            self._state_loaded = True
            if self.state_file_path:
                try:
                    cached = await asyncio.to_thread(
                        load_snapshot,
                        self.state_file_path,
                    )
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    log.warning("Could not load persistent fleet cache: %s", exc)
                else:
                    if cached is not None:
                        self._snapshot = cached
                        log.info(
                            "Loaded %s aircraft from persistent cache",
                            len(cached.aircraft),
                        )

        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    "X-API-Key": self.api_key,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": "VirtualNationalGuard-FleetBot/1.1.0",
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

    def _retry_delay(self, attempt: int, retry_after: str | None = None) -> float:
        if retry_after:
            try:
                return min(10.0, max(0.1, float(retry_after)))
            except ValueError:
                pass
        return min(8.0, self.retry_base_seconds * (2 ** max(0, attempt - 1)))

    async def _request_json(
        self,
        path_or_url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        await self.start()
        assert self._session is not None
        url = self._safe_url(path_or_url)
        started = time.perf_counter()

        for attempt in range(1, self.retry_attempts + 1):
            try:
                async with self._session.get(url, params=params) as response:
                    body = await response.text()
                    status = response.status

                    if status == 401:
                        raise PhpVmsApiError(
                            "phpVMS rejected the API key (HTTP 401). Check PHPVMS_API_KEY."
                        )
                    if status == 403:
                        raise PhpVmsApiError(
                            "The phpVMS account cannot access this endpoint (HTTP 403)."
                        )
                    if status == 404:
                        raise PhpVmsApiError(
                            f"phpVMS endpoint was not found: {url} (HTTP 404)."
                        )
                    if status == 429 or status >= 500:
                        if attempt < self.retry_attempts:
                            delay = self._retry_delay(
                                attempt,
                                response.headers.get("Retry-After"),
                            )
                            log.warning(
                                "phpVMS HTTP %s; retrying in %.2fs (%s/%s)",
                                status,
                                delay,
                                attempt,
                                self.retry_attempts,
                            )
                            await asyncio.sleep(delay)
                            continue
                        raise PhpVmsApiError(
                            f"phpVMS is temporarily unavailable (HTTP {status})."
                        )
                    if status >= 400:
                        compact = " ".join(body.split())[:300]
                        log.error("phpVMS HTTP %s response: %s", status, compact)
                        raise PhpVmsApiError(
                            f"phpVMS request failed (HTTP {status})."
                        )

                    try:
                        payload = json.loads(body)
                    except ValueError as exc:
                        raise PhpVmsApiError(
                            "phpVMS returned non-JSON data. Check the configured base URL."
                        ) from exc
                    if not isinstance(payload, dict):
                        raise PhpVmsApiError(
                            "phpVMS returned an unexpected JSON response."
                        )
                    self.last_response_ms = round(
                        (time.perf_counter() - started) * 1000
                    )
                    return payload
            except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                if attempt < self.retry_attempts:
                    delay = self._retry_delay(attempt)
                    log.warning(
                        "phpVMS connection failed; retrying in %.2fs (%s/%s): %s",
                        delay,
                        attempt,
                        self.retry_attempts,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    continue
                if isinstance(exc, asyncio.TimeoutError):
                    raise PhpVmsApiError(
                        "The phpVMS request timed out after multiple attempts."
                    ) from exc
                raise PhpVmsApiError(
                    "Could not connect to phpVMS after multiple attempts."
                ) from exc

        raise PhpVmsApiError("phpVMS request failed unexpectedly.")

    async def _get_all_pages(self, path: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        request_target = path
        params: dict[str, Any] | None = {"page": 1, "per_page": 100}
        visited_requests: set[tuple[str, tuple[tuple[str, str], ...]]] = set()

        for _ in range(500):
            canonical_url = self._safe_url(request_target)
            parameter_key = tuple(
                sorted((str(key), str(value)) for key, value in (params or {}).items())
            )
            request_key = (canonical_url, parameter_key)
            if request_key in visited_requests:
                raise PhpVmsApiError(
                    "phpVMS repeated a pagination request. The server may be ignoring its page parameter."
                )
            visited_requests.add(request_key)

            payload = await self._request_json(request_target, params=params)
            data = payload.get("data", [])
            if isinstance(data, list):
                items.extend(item for item in data if isinstance(item, dict))
            elif isinstance(data, dict):
                items.append(data)

            meta = payload.get("meta")
            if isinstance(meta, dict):
                try:
                    current_page = int(meta.get("current_page") or 1)
                    last_page = int(meta.get("last_page") or current_page)
                    per_page = int(meta.get("per_page") or 100)
                except (TypeError, ValueError) as exc:
                    raise PhpVmsApiError(
                        "phpVMS returned invalid pagination metadata."
                    ) from exc
                if current_page < last_page:
                    request_target = path
                    params = {
                        "page": current_page + 1,
                        "per_page": max(1, min(per_page, 100)),
                    }
                    continue
                return items

            links = payload.get("links") or {}
            candidate = links.get("next") if isinstance(links, dict) else None
            if isinstance(candidate, str) and candidate:
                request_target = candidate
                params = None
                continue
            return items

        raise PhpVmsApiError("phpVMS pagination exceeded 500 pages.")

    async def get_airport(self, icao: str) -> dict[str, Any] | None:
        normalized = normalize(icao)
        if normalized in self._airports:
            return self._airports[normalized]
        try:
            payload = await self._request_json(f"/api/airports/{normalized}")
        except PhpVmsApiError as exc:
            if "HTTP 404" in str(exc):
                self._airports[normalized] = None
                return None
            raise
        data = payload.get("data")
        airport = data if isinstance(data, dict) else None
        self._airports[normalized] = airport
        return airport

    async def _load_airlines(self) -> dict[str, dict[str, Any]]:
        records = await self._get_all_pages("/api/airlines")
        return {str(record.get("id", "")): record for record in records}

    def _flatten_fleet(
        self,
        subfleets: list[dict[str, Any]],
        airlines: dict[str, dict[str, Any]],
    ) -> tuple[Aircraft, ...]:
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
        return tuple(flattened)

    async def get_fleet(self, *, force: bool = False) -> FleetSnapshot:
        if not force and self._snapshot is not None:
            if not self._snapshot.stale and self._snapshot.age_seconds < self.cache_ttl:
                return self._snapshot.as_cached()

        async with self._cache_lock:
            if not force and self._snapshot is not None:
                if not self._snapshot.stale and self._snapshot.age_seconds < self.cache_ttl:
                    return self._snapshot.as_cached()

            self.last_refresh_attempt_at = datetime.now(timezone.utc)
            try:
                airlines_task = asyncio.create_task(self._load_airlines())
                fleet_task = asyncio.create_task(self._get_all_pages("/api/fleet"))
                airlines, subfleets = await asyncio.gather(airlines_task, fleet_task)
                self._airlines = airlines
                snapshot = FleetSnapshot(
                    aircraft=self._flatten_fleet(subfleets, airlines),
                    fetched_at=datetime.now(timezone.utc),
                    source="live",
                )
            except PhpVmsApiError as exc:
                self.last_api_error = str(exc)
                if self._snapshot is not None:
                    self._snapshot = self._snapshot.as_stale(str(exc))
                    log.error(
                        "Live fleet refresh failed; serving %s cached aircraft: %s",
                        len(self._snapshot.aircraft),
                        exc,
                    )
                    return self._snapshot
                raise

            self._snapshot = snapshot
            self.last_refresh_success_at = snapshot.fetched_at
            self.last_api_error = None
            log.info(
                "Fleet cache refreshed: %s aircraft across %s subfleets",
                len(snapshot.aircraft),
                len(subfleets),
            )
            if self.state_file_path:
                try:
                    await asyncio.to_thread(
                        save_snapshot,
                        self.state_file_path,
                        snapshot,
                    )
                except OSError as exc:
                    log.warning("Could not save persistent fleet cache: %s", exc)
            return snapshot
