from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any

from fastapi import Body, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from .bases import BASES
from .config import settings
from .detection import ZONES
from .live_delta import build_live_delta, compact_live_payload
from .vatsim import VatsimMonitor

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

STATIC = Path(__file__).parent / "static"
APP_VERSION = "1.4.8"
UI_BUILD_ID = "v1.4.8-deep-audit-reliability"


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: set[WebSocket] = set()
        self.client_ids: dict[WebSocket, str] = {}
        self.last_live_payload: dict[str, Any] | None = None
        self.live_broadcast_count = 0
        # One lock protects both revision-baseline updates and socket sends.
        # This prevents overlapping workflow/feed broadcasts from reaching a
        # browser out of order or writing concurrently to the same ASGI socket.
        self._send_lock = asyncio.Lock()

    @property
    def viewer_count(self) -> int:
        """Return unique active browser consoles, not raw WebSocket count."""
        return len(set(self.client_ids.values()))

    @staticmethod
    def _normalize_client_id(websocket: WebSocket, client_id: str | None) -> str:
        value = str(client_id or "").strip()[:128]
        return value or f"anonymous-{id(websocket)}"

    @staticmethod
    def _freeze(payload: dict[str, Any]) -> dict[str, Any]:
        """Detach a payload from mutable LiveState collections."""
        return json.loads(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))

    async def connect(
        self,
        websocket: WebSocket,
        client_id: str | None = None,
        initial_payload: dict[str, Any] | None = None,
    ) -> None:
        """Accept a console and send its full baseline before live deltas.

        The socket is not added to the broadcast set until the baseline has
        completed, so a feed update cannot race or send a delta first.
        """
        frozen_initial = (
            self._freeze(compact_live_payload(initial_payload))
            if initial_payload is not None
            else None
        )
        await websocket.accept()
        async with self._send_lock:
            if frozen_initial is not None:
                baseline = self.last_live_payload or frozen_initial
                await asyncio.wait_for(
                    websocket.send_text(json.dumps(baseline, separators=(",", ":"), ensure_ascii=False)),
                    timeout=2.0,
                )
                if self.last_live_payload is None:
                    self.last_live_payload = self._freeze(baseline)
            self.connections.add(websocket)
            self.client_ids[websocket] = self._normalize_client_id(websocket, client_id)
        await self.broadcast_presence()

    def _remove(self, websocket: WebSocket) -> None:
        self.connections.discard(websocket)
        self.client_ids.pop(websocket, None)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._send_lock:
            previous = self.viewer_count
            self._remove(websocket)
            changed = self.viewer_count != previous
        if changed:
            await self.broadcast_presence()

    async def _send_unlocked(self, payload: dict[str, Any]) -> bool:
        """Send one ordered payload; caller must hold ``_send_lock``."""
        if not self.connections:
            return False
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

        async def send(websocket: WebSocket) -> tuple[WebSocket, bool]:
            try:
                await asyncio.wait_for(websocket.send_text(encoded), timeout=2.0)
                return websocket, True
            except Exception:
                return websocket, False

        previous = self.viewer_count
        results = await asyncio.gather(*(send(ws) for ws in list(self.connections)))
        for websocket, ok in results:
            if not ok:
                self._remove(websocket)
        return self.viewer_count != previous

    async def broadcast(self, payload: dict[str, Any]) -> None:
        refresh_presence = False
        async with self._send_lock:
            outgoing = payload
            if payload.get("type") == "live":
                compact = compact_live_payload(payload)
                self.live_broadcast_count += 1
                delta = build_live_delta(self.last_live_payload, compact) if settings.enable_live_deltas else None
                force_full = self.live_broadcast_count % max(1, settings.delta_full_snapshot_interval) == 0
                if delta is not None and not force_full:
                    full_size = len(json.dumps(compact, separators=(",", ":"), ensure_ascii=False))
                    delta_size = len(json.dumps(delta, separators=(",", ":"), ensure_ascii=False))
                    outgoing = delta if delta_size < full_size else compact
                else:
                    outgoing = compact
                self.last_live_payload = self._freeze(compact)
            refresh_presence = await self._send_unlocked(outgoing)
        if refresh_presence:
            await self.broadcast_presence()

    def record_full_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return a detached compact snapshot without changing delta state."""
        return self._freeze(compact_live_payload(payload))

    async def broadcast_presence(self) -> None:
        async with self._send_lock:
            await self._send_unlocked(
                {"type": "presence", "viewer_count": self.viewer_count}
            )


manager = ConnectionManager()
monitor = VatsimMonitor(manager.broadcast)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await monitor.start()
    yield
    await monitor.stop()


app = FastAPI(title=settings.app_name, version=APP_VERSION, lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)

@app.middleware("http")
async def request_safety_headers(request: Request, call_next):
    """Apply browser hardening and block cross-site shared-state mutations.

    This is not authentication; OAuth remains required before the public can
    safely receive manual NORDO and intercept-workflow permissions.
    """
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin:
            parsed_origin = urlsplit(origin)
            origin_host = (parsed_origin.hostname or "").lower()
            request_host = (request.url.hostname or str(request.headers.get("host") or "").split(":", 1)[0]).lower()
            if origin_host and origin_host != request_host:
                return JSONResponse({"ok": False, "error": "cross_origin_mutation_blocked"}, status_code=403)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers["X-VNG-ADOC-Version"] = APP_VERSION
    response.headers["X-VNG-ADOC-UI-Build"] = UI_BUILD_ID
    if request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, max-age=0, must-revalidate"
    elif request.url.path.startswith("/static/"):
        # Static URLs are build-versioned in index.html. They can be cached for a
        # year without risking the stale-deployment problem that v1.3.36 fixed.
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response

app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(
        STATIC / "index.html",
        headers={"Cache-Control": "no-cache, max-age=0, must-revalidate"},
    )


@app.get("/health")
async def health() -> JSONResponse:
    feed_age = (
        max(0, int(time.time() - monitor.state.last_success_epoch))
        if monitor.state.last_success_epoch is not None
        else None
    )
    if monitor.state.error:
        status = "degraded"
    elif feed_age is None:
        status = "initializing"
    elif feed_age >= settings.feed_stale_critical_seconds:
        status = "stale"
    else:
        status = "ok"
    return JSONResponse(
        {
            "status": status,
            "version": APP_VERSION,
            "ui_build": UI_BUILD_ID,
            "updated_at": monitor.state.updated_at,
            "feed_updated_at": monitor.state.feed_updated_at,
            "processing_ms": monitor.state.processing_ms,
            "processing_breakdown": monitor.state.processing_breakdown,
            "revision": monitor.state.revision,
            "error": monitor.state.error,
            "feed_age_seconds": feed_age,
            "automatic_alerts_paused": status in {"degraded", "stale"},
        },
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/version")
async def version_info() -> JSONResponse:
    return JSONResponse(
        {
            "version": APP_VERSION,
            "ui_build": UI_BUILD_ID,
            "artcc_focus": True,
            "legacy_track_overlay": False,
            "live_deltas": settings.enable_live_deltas,
            "persistent_workflow": True,
            "spatial_index": True,
            "alert_evidence": True,
            "alert_timeline": True,
            "temporary_exemptions": True,
            "handoff_visualization": True,
            "mass_alert_independent_verification": True,
            "atc_automatic_flag_dismissal": True,
            "vsoa_self_dispatch": True,
            "atc_full_aircraft_details": True,
            "blackjack_recognition": True,
            "dca_heli_route_reference": True,
            "dca_heli_chart_effective": "2026-07-09",
            "legacy_hover_overlay": False,
            "compact_docked_map_menu": True,
            "scope_hud_removed": True,
            "pre_scramble_denial_window_seconds": settings.pre_scramble_warning_seconds,
        },
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/presence")
async def presence() -> JSONResponse:
    return JSONResponse(
        {"viewer_count": manager.viewer_count},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/live")
async def live_state() -> JSONResponse:
    return JSONResponse(monitor.state.live_payload(), headers={"Cache-Control": "no-store"})


@app.get("/api/tracks/{callsign}")
async def track_detail(callsign: str) -> JSONResponse:
    normalized = str(callsign or "").upper().strip()
    pilot = next(
        (item for item in monitor.state.pilots if str(item.get("callsign") or "").upper() == normalized),
        None,
    )
    if pilot is None:
        return JSONResponse({"ok": False, "error": "track_not_found", "callsign": normalized}, status_code=404, headers={"Cache-Control": "no-store"})
    return JSONResponse(
        {"ok": True, "pilot": pilot, "history": monitor.get_track_history(normalized), "revision": monitor.state.revision},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/state")
async def state() -> JSONResponse:
    """Backward-compatible full state endpoint."""
    return JSONResponse(monitor.state.full_payload(), headers={"Cache-Control": "no-store"})


@app.get("/api/bootstrap")
async def bootstrap() -> JSONResponse:
    return JSONResponse(
        {
            "version": APP_VERSION,
            "ui_build": UI_BUILD_ID,
            "zones": ZONES,
            "bases": BASES,
            "atc_revision": monitor.state.atc_revision,
            "atc_coverage": monitor.state.atc_coverage,
            "center_boundary_revision": monitor.state.center_boundary_revision,
            "center_boundary_count": len(monitor.state.center_boundaries),
            "boundary_status": monitor.state.boundary_status,
            "sua_status": monitor.state.sua_status,
            "monitor_canada": settings.monitor_canada,
            "poll_seconds": settings.poll_seconds,
            "http_fallback_seconds": settings.http_fallback_seconds,
            "feed_stale_warning_seconds": settings.feed_stale_warning_seconds,
            "feed_stale_critical_seconds": settings.feed_stale_critical_seconds,
            "console_presence_heartbeat_seconds": settings.console_presence_heartbeat_seconds,
            "viewer_count": manager.viewer_count,
        },
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/atc")
async def atc_coverage() -> JSONResponse:
    return JSONResponse(
        {
            "revision": monitor.state.atc_revision,
            "status": monitor.state.boundary_status,
            "count": len(monitor.state.atc_coverage),
            "coverage": monitor.state.atc_coverage,
        },
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/center-boundaries")
async def center_boundaries() -> JSONResponse:
    return JSONResponse(
        {
            "revision": monitor.state.center_boundary_revision,
            "status": monitor.state.boundary_status,
            "count": len(monitor.state.center_boundaries),
            "boundaries": monitor.state.center_boundaries,
            "source": "VATSpy Data Project / VATSIM",
        },
        headers={"Cache-Control": "public, max-age=21600"},
    )


@app.get("/api/tracks/{callsign}/history")
async def track_history(callsign: str) -> JSONResponse:
    points = monitor.get_track_history(callsign)
    return JSONResponse(
        {
            "callsign": callsign.upper(),
            "count": len(points),
            "retention_minutes": 60,
            "points": points,
        },
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/bases")
async def bases() -> JSONResponse:
    return JSONResponse(BASES, headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/sua")
async def special_use_airspace() -> JSONResponse:
    return JSONResponse(
        {
            "status": monitor.sua.status,
            "updated_at": monitor.state.sua_updated_at,
            "count": len(monitor.sua.areas),
            "areas": monitor.sua.areas,
        },
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/alerts/{alert_id}/ack")
async def acknowledge(alert_id: str) -> JSONResponse:
    found = await monitor.acknowledge_alert(alert_id)
    return JSONResponse(
        {
            "ok": True,
            "id": alert_id,
            "status": "acknowledged_on_console",
            "found": found,
            "revision": monitor.state.revision,
            "scope": "client-local",
        },
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/pre-scramble/{callsign}/deny")
async def deny_pre_scramble(callsign: str, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    actor = payload.get("console_label") or payload.get("actor") or payload.get("console_id") or "ATC CONSOLE"
    reason = payload.get("reason") or "Denied during the 30-second pre-scramble review"
    found, record, error = await monitor.deny_pre_scramble(
        callsign,
        payload.get("case_id"),
        actor=str(actor),
        reason=str(reason),
    )
    status_code = 200 if found else 409 if error == "stale_case" else 404
    return JSONResponse(
        {
            "ok": found,
            "callsign": callsign.upper(),
            "status": "pre_scramble_denied" if found else "not_denied",
            "record": record,
            "error": error,
            "revision": monitor.state.revision,
            "scope": "shared_current_communications_case",
        },
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/alerts/{alert_id}/dismiss")
async def dismiss(alert_id: str, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    actor = payload.get("console_label") or payload.get("actor") or payload.get("console_id") or "ATC CONSOLE"
    reason = payload.get("reason") or "Operator reviewed and dismissed automatic flag"
    found = await monitor.dismiss_alert(alert_id, actor=actor, reason=reason)
    return JSONResponse(
        {
            "ok": True,
            "id": alert_id,
            "status": "dismissed",
            "found": found,
            "revision": monitor.state.revision,
        },
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/tracks/{callsign}/manual-nordo")
async def mark_manual_nordo(callsign: str) -> JSONResponse:
    found, record = await monitor.set_manual_nordo(callsign, True)
    return JSONResponse(
        {
            "ok": found,
            "callsign": callsign.upper(),
            "status": "manual_nordo_active" if found else "track_not_found",
            "record": record,
            "revision": monitor.state.revision,
            "scope": "shared",
        },
        status_code=200 if found else 404,
        headers={"Cache-Control": "no-store"},
    )


@app.delete("/api/tracks/{callsign}/manual-nordo")
async def clear_manual_nordo(callsign: str) -> JSONResponse:
    found, _ = await monitor.set_manual_nordo(callsign, False)
    return JSONResponse(
        {
            "ok": found,
            "callsign": callsign.upper(),
            "status": "manual_nordo_cleared" if found else "designation_not_found",
            "revision": monitor.state.revision,
            "scope": "shared",
        },
        status_code=200 if found else 404,
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/exemptions")
async def list_temporary_exemptions() -> JSONResponse:
    monitor._sync_temporary_exemptions()
    return JSONResponse(
        {"ok": True, "exemptions": monitor.state.temporary_exemptions, "revision": monitor.state.revision},
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/exemptions")
async def create_temporary_exemption(payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    found, record, error = await monitor.create_temporary_exemption(
        str(payload.get("callsign") or ""),
        payload.get("minutes") or settings.temporary_exemption_default_minutes,
        str(payload.get("reason") or "Operational coordination"),
        str(payload.get("console_label") or payload.get("console_id") or "CONSOLE"),
    )
    return JSONResponse(
        {"ok": found, "exemption": record, "error": error, "revision": monitor.state.revision, "scope": "shared"},
        status_code=200 if found else 404 if error == "track_not_found" else 400,
        headers={"Cache-Control": "no-store"},
    )


@app.delete("/api/exemptions/{exemption_id}")
async def delete_temporary_exemption(exemption_id: str, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    found, record = await monitor.remove_temporary_exemption(
        exemption_id,
        str(payload.get("console_label") or payload.get("console_id") or "CONSOLE"),
    )
    return JSONResponse(
        {"ok": found, "exemption": record, "revision": monitor.state.revision, "scope": "shared"},
        status_code=200 if found else 404,
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/intercepts/manual/batch")
async def assign_manual_intercepts_batch(payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    raw = payload.get("interceptor_callsigns") or []
    interceptor_callsigns = raw if isinstance(raw, list) else [raw]
    found, assignments, errors, error = await monitor.assign_manual_intercepts(
        [str(value or "") for value in interceptor_callsigns],
        str(payload.get("target_callsign") or ""),
        str(payload.get("console_label") or payload.get("console_id") or "CONSOLE"),
    )
    status_code = 200 if found else 404 if error in {"interceptor_not_found", "target_not_found"} else 400
    return JSONResponse(
        {
            "ok": found,
            "assignments": assignments,
            "errors": errors,
            "error": error,
            "revision": monitor.state.revision,
            "scope": "shared",
        },
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/intercepts/recalculate")
async def recalculate_intercepts(payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    result = await monitor.recalculate_intercepts(
        str(payload.get("console_label") or payload.get("console_id") or "CONSOLE")
    )
    assignments = list(result)
    summary = dict(result.summary)
    return JSONResponse(
        {
            "ok": True,
            "assignments": assignments,
            "count": len(assignments),
            "active_count": summary["active_intercepts"],
            "revision": monitor.state.revision,
            "feed_sequence": monitor.state.feed_sequence,
            "recalculated_at": summary["recalculated_at"],
            "summary": summary,
            "scope": "shared",
        },
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/intercepts/manual")
async def assign_manual_intercept(payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    found, assignment, error = await monitor.assign_manual_intercept(
        str(payload.get("interceptor_callsign") or ""),
        str(payload.get("target_callsign") or ""),
        str(payload.get("console_label") or payload.get("console_id") or "CONSOLE"),
    )
    status_code = 200 if found else 404 if error in {"interceptor_not_found", "target_not_found"} else 400
    return JSONResponse(
        {
            "ok": found,
            "assignment": assignment,
            "error": error,
            "revision": monitor.state.revision,
            "scope": "shared",
        },
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/intercepts/targets/{target_callsign}/control")
async def set_intercept_target_control(
    target_callsign: str,
    payload: dict[str, Any] = Body(default={}),
) -> JSONResponse:
    found, control, error = await monitor.set_intercept_target_control(
        target_callsign,
        str(payload.get("console_label") or payload.get("console_id") or "CONSOLE"),
        response_status=payload.get("response_status"),
        atc_status=payload.get("atc_status"),
        command_status=payload.get("command_status"),
        note=payload.get("note") if "note" in payload else None,
    )
    status_code = 200 if found else 404 if error == "target_not_found" else 400
    return JSONResponse(
        {
            "ok": found,
            "control": control,
            "error": error,
            "revision": monitor.state.revision,
            "scope": "shared",
        },
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


@app.delete("/api/intercepts/targets/{target_callsign}")
async def clear_target_intercepts(
    target_callsign: str,
    payload: dict[str, Any] = Body(default={}),
) -> JSONResponse:
    found, assignments = await monitor.clear_target_intercepts(
        target_callsign,
        str(payload.get("console_label") or payload.get("console_id") or "CONSOLE"),
    )
    return JSONResponse(
        {
            "ok": found,
            "assignments": assignments,
            "revision": monitor.state.revision,
            "scope": "shared",
        },
        status_code=200 if found else 404,
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/intercepts/manual/{interceptor_callsign}/response")
async def set_manual_intercept_response(
    interceptor_callsign: str,
    payload: dict[str, Any] = Body(default={}),
) -> JSONResponse:
    found, assignment, error = await monitor.set_manual_intercept_response(
        interceptor_callsign,
        str(payload.get("status") or ""),
        str(payload.get("console_label") or payload.get("console_id") or "CONSOLE"),
    )
    status_code = 200 if found else 404 if error == "assignment_not_found" else 400
    return JSONResponse(
        {
            "ok": found,
            "assignment": assignment,
            "error": error,
            "revision": monitor.state.revision,
            "scope": "shared",
        },
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


@app.delete("/api/intercepts/manual/{interceptor_callsign}")
async def clear_manual_intercept(
    interceptor_callsign: str,
    payload: dict[str, Any] = Body(default={}),
) -> JSONResponse:
    found, assignment = await monitor.clear_manual_intercept(
        interceptor_callsign,
        str(payload.get("console_label") or payload.get("console_id") or "CONSOLE"),
    )
    return JSONResponse(
        {
            "ok": found,
            "assignment": assignment,
            "revision": monitor.state.revision,
            "scope": "shared",
        },
        status_code=200 if found else 404,
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/operations/{alert_id}/target-response")
async def set_operation_target_response(
    alert_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> JSONResponse:
    found, operation, error = await monitor.set_operation_target_response(
        alert_id,
        str(payload.get("status") or ""),
        str(payload.get("console_label") or payload.get("console_id") or "CONSOLE"),
    )
    status_code = 200 if found else 404 if error == "operation_not_found" else 400
    return JSONResponse(
        {
            "ok": found,
            "operation": operation,
            "error": error,
            "revision": monitor.state.revision,
            "scope": "shared",
        },
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/operations/{alert_id}/accept")
async def accept_operation(alert_id: str, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    found, operation = await monitor.accept_operation(
        alert_id,
        str(payload.get("console_id") or ""),
        str(payload.get("console_label") or ""),
    )
    return JSONResponse(
        {
            "ok": found,
            "id": alert_id,
            "operation": operation,
            "revision": monitor.state.revision,
            "scope": "shared",
        },
        status_code=200 if found else 404,
        headers={"Cache-Control": "no-store"},
    )


@app.delete("/api/operations/{alert_id}/accept/{console_id}")
async def release_operation(alert_id: str, console_id: str) -> JSONResponse:
    found, operation = await monitor.release_operation(alert_id, console_id)
    return JSONResponse(
        {
            "ok": found,
            "id": alert_id,
            "operation": operation,
            "revision": monitor.state.revision,
            "scope": "shared",
        },
        status_code=200 if found else 404,
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/operations/{alert_id}/phases/{phase_id}")
async def set_operation_phase(
    alert_id: str,
    phase_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> JSONResponse:
    found, operation = await monitor.set_operation_phase(
        alert_id,
        phase_id,
        bool(payload.get("complete", True)),
        str(payload.get("console_label") or payload.get("console_id") or "CONSOLE"),
    )
    return JSONResponse(
        {
            "ok": found,
            "id": alert_id,
            "phase": phase_id,
            "operation": operation,
            "revision": monitor.state.revision,
            "scope": "shared",
        },
        status_code=200 if found else 404,
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/operations/{alert_id}/{stage}")
async def advance_operation(alert_id: str, stage: str) -> JSONResponse:
    found = await monitor.advance_operation(alert_id, stage)
    return JSONResponse(
        {
            "ok": found,
            "id": alert_id,
            "stage": stage,
            "revision": monitor.state.revision,
        },
        status_code=200 if found else 404,
        headers={"Cache-Control": "no-store"},
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    try:
        await manager.connect(
            websocket,
            websocket.query_params.get("client_id"),
            monitor.state.live_payload(),
        )
        while True:
            # Browser heartbeat messages keep Railway/proxy connections alive.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await manager.disconnect(websocket)
