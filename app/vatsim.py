from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

import httpx

from .airports import AirportResolver
from .atc_boundaries import AtcBoundaryStore
from .config import settings
from .detection import DetectionEngine, ZONES
from .geometry import haversine_nm, is_enabled_region
from .persistence import OperationalStateStore
from .sua import SpecialUseAirspaceStore
from .track_signature import intercept_pair_signature

log = logging.getLogger("vng-adoc")


INTERCEPT_PHASES: tuple[tuple[str, str], ...] = (
    ("alert_received", "Alert received"),
    ("qra_accepted", "QRA response accepted / inbound"),
    ("scramble_ordered", "Scramble ordered"),
    ("fighters_airborne", "Fighters airborne"),
    ("target_located", "Target located"),
    ("radar_contact", "Radar contact established"),
    ("visual_contact", "Visual contact established"),
    ("identification_complete", "Aircraft identification complete"),
    ("escort_in_progress", "Escort / shadow in progress"),
    ("communications_restored", "Communications restored"),
    ("intercept_complete", "Intercept complete"),
    ("returned_to_base", "Interceptor returned to base"),
)
INTERCEPT_PHASE_LABELS = dict(INTERCEPT_PHASES)
TARGET_RESPONSE_STATUSES = {"UNKNOWN", "RESPONDING", "NOT_RESPONDING", "COMMS_RESTORED"}
ATC_COORDINATION_STATUSES = {"UNCOORDINATED", "ATC_NOTIFIED", "COORDINATING", "INTERCEPT_APPROVED", "HANDOFF_COMPLETE"}
INTERCEPT_COMMAND_STATUSES = {"MONITOR", "ATTEMPT_CONTACT", "IDENTIFY", "ESCORT_SHADOW", "BREAK_OFF", "RETURN_TO_BASE"}


class InterceptRecalculationResult(list[dict[str, Any]]):
    """Assignment list that also exposes recalculation summary metadata.

    Older callers consumed a summary mapping while newer callers iterate the
    refreshed assignments. Supporting both keeps the API compatible across the
    merged operator, ATC, and reliability branches.
    """

    def __init__(
        self,
        assignments: list[dict[str, Any]],
        *,
        actor: str,
        recalculated_at: str | None,
        active_intercepts: int,
    ) -> None:
        super().__init__(assignments)
        self.summary: dict[str, Any] = {
            "actor": actor,
            "recalculated_at": recalculated_at,
            "manual_intercepts": len(assignments),
            "active_intercepts": active_intercepts,
        }

    def __getitem__(self, key: int | slice | str):
        if isinstance(key, str):
            return self.summary[key]
        return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:
        return self.summary.get(key, default)


class LiveState:
    def __init__(self) -> None:
        self.revision = 0
        self.feed_sequence = 0
        self.updated_at: str | None = None
        self.feed_updated_at: str | None = None
        self.processing_ms: int = 0
        self.processing_breakdown: dict[str, int] = {}
        self.intercept_recalculated_at: str | None = None
        self.pilots: list[dict[str, Any]] = []
        self.alerts: list[dict[str, Any]] = []
        self.operations: list[dict[str, Any]] = []
        self.manual_intercepts: list[dict[str, Any]] = []
        self.intercept_controls: list[dict[str, Any]] = []
        self.temporary_exemptions: list[dict[str, Any]] = []
        self.mass_alert_guard: dict[str, Any] = {"active": False, "pending": 0}
        self.automatic_flag_dismissals: list[dict[str, Any]] = []
        self.pre_scramble_denials: list[dict[str, Any]] = []
        self.controllers: list[dict[str, Any]] = []
        self.atc_coverage: list[dict[str, Any]] = []
        self.atc_revision: str = "pending"
        self.center_boundaries: list[dict[str, Any]] = []
        self.center_boundary_revision: str = "pending"
        self.boundary_status: str = "NOT LOADED"
        self.sua_status: str = "NOT LOADED"
        self.sua_count: int = 0
        self.sua_updated_at: str | None = None
        self.scramble_alarm_confidence: int = settings.scramble_alarm_confidence
        self.error: str | None = None
        self.connected_clients: int = 0
        self.last_success_epoch: float | None = None

    def touch(self) -> None:
        self.revision += 1
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def _stats(self) -> dict[str, Any]:
        return {
            "us_aircraft": sum(1 for p in self.pilots if p.get("region") == "UNITED STATES"),
            "canada_aircraft": sum(1 for p in self.pilots if p.get("region") == "CANADA"),
            "monitored_aircraft": len(self.pilots),
            "centers_online": sum(1 for c in self.atc_coverage if c.get("facility") == "CTR"),
            "terminal_online": sum(1 for c in self.atc_coverage if c.get("facility") in {"APP", "DEP", "TWR", "GND", "DEL"}),
            "alerts": len(self.alerts),
            "red_alerts": sum(1 for a in self.alerts if a.get("severity") == "red"),
            "mandatory_ack": sum(1 for a in self.alerts if a.get("requires_ack")),
            "nordo_watches": sum(1 for p in self.pilots if p.get("nordo_watch")),
            "frequency_mismatches": sum(1 for p in self.pilots if p.get("frequency_mismatch_active")),
            "vsoa_tracks": sum(1 for p in self.pilots if p.get("vsoa")),
            "active_intercepts": sum(1 for p in self.pilots if p.get("active_intercept")),
            "manual_intercepts": len(self.manual_intercepts),
            "temporary_exemptions": len(self.temporary_exemptions),
            "mass_alert_verifying": int(self.mass_alert_guard.get("pending") or 0),
            "intercept_targets": len({item.get("target_callsign") for item in self.manual_intercepts if item.get("target_callsign")}),
            "operations": len(self.operations),
            "sua_areas": self.sua_count,
        }

    def live_payload(self) -> dict[str, Any]:
        """Small payload used for WebSocket and frequent HTTP refreshes.

        ATC polygons and the SUA database are intentionally excluded. Those
        large reference layers are fetched separately only when their revision
        changes, preventing multi-megabyte redraws every feed cycle.
        """
        return {
            "type": "live",
            "revision": self.revision,
            "feed_sequence": self.feed_sequence,
            "updated_at": self.updated_at,
            "feed_updated_at": self.feed_updated_at,
            "processing_ms": self.processing_ms,
            "processing_breakdown": self.processing_breakdown,
            "intercept_recalculated_at": self.intercept_recalculated_at,
            "pilots": self.pilots,
            "alerts": self.alerts,
            "operations": self.operations,
            "manual_intercepts": self.manual_intercepts,
            "intercept_controls": self.intercept_controls,
            "temporary_exemptions": self.temporary_exemptions,
            "mass_alert_guard": self.mass_alert_guard,
            "automatic_flag_dismissals": self.automatic_flag_dismissals,
            "pre_scramble_denials": self.pre_scramble_denials,
            "controllers": self.controllers,
            "atc_revision": self.atc_revision,
            "center_boundary_revision": self.center_boundary_revision,
            "center_boundary_count": len(self.center_boundaries),
            "boundary_status": self.boundary_status,
            "sua_status": self.sua_status,
            "sua_count": self.sua_count,
            "sua_updated_at": self.sua_updated_at,
            "scramble_alarm_confidence": self.scramble_alarm_confidence,
            "error": self.error,
            "last_success_epoch": self.last_success_epoch,
            "feed_age_seconds": (
                max(0, int(time.time() - self.last_success_epoch))
                if self.last_success_epoch is not None
                else None
            ),
            "connected_clients": self.connected_clients,
            "coverage": "UNITED STATES + CANADA" if settings.monitor_canada else "UNITED STATES",
            "monitor_canada": settings.monitor_canada,
            "stats": self._stats(),
        }

    def full_payload(self) -> dict[str, Any]:
        payload = self.live_payload()
        payload.update({
            "atc_coverage": self.atc_coverage,
            "center_boundaries": self.center_boundaries,
            "center_boundary_revision": self.center_boundary_revision,
            "zones": ZONES,
        })
        return payload


class VatsimMonitor:
    def __init__(self, broadcaster: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        self.state = LiveState()
        self.airports = AirportResolver()
        self.engine = DetectionEngine(self.airports)
        self.boundaries = AtcBoundaryStore()
        self.sua = SpecialUseAirspaceStore()
        self.broadcaster = broadcaster
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": settings.user_agent,
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Accept": "application/json",
            },
            timeout=30,
            follow_redirects=True,
        )
        self.feed_task: asyncio.Task | None = None
        self.reference_task: asyncio.Task | None = None
        self.airport_task: asyncio.Task | None = None
        self.last_network: dict[str, Any] | None = None
        self.last_transceivers: list[dict[str, Any]] | None = None
        self.last_processed_feed_timestamp: str | None = None
        self.operations: dict[str, dict[str, Any]] = {}
        self.manual_intercepts: dict[str, dict[str, Any]] = {}
        self.intercept_controls: dict[str, dict[str, Any]] = {}
        self.temporary_exemptions: dict[str, dict[str, Any]] = {}
        self.engine.temporary_exemptions = self.temporary_exemptions
        self.scramble_incidents: dict[str, dict[str, Any]] = {}
        self.mass_alert_verifications: dict[str, dict[str, Any]] = {}
        self.automatic_flag_dismissals: dict[str, dict[str, Any]] = {}
        self.pre_scramble_denials = self.engine.pre_scramble_denials
        self.track_history: dict[str, list[dict[str, Any]]] = {}
        self.process_lock = asyncio.Lock()
        self.center_boundary_source_refresh: float = -1.0
        self._manual_intercept_cache: dict[str, tuple[tuple[Any, ...], dict[str, Any], str]] = {}
        self.persistence = OperationalStateStore(settings.state_db_path)
        self.persistence_task: asyncio.Task | None = None
        self._last_persisted_signature: str | None = None

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _operational_snapshot(self) -> dict[str, Any]:
        return {
            "operations": list(self.operations.values()),
            "manual_intercepts": list(self.manual_intercepts.values()),
            "intercept_controls": list(self.intercept_controls.values()),
            "temporary_exemptions": list(self.temporary_exemptions.values()),
            "scramble_incidents": self.scramble_incidents,
            "manual_nordo": self.engine.manual_nordo,
            "acknowledged": sorted(self.engine.acknowledged),
            "dismissed": sorted(self.engine.dismissed),
            "automatic_flag_dismissals": list(self.automatic_flag_dismissals.values()),
            "pre_scramble_denials": list(self.pre_scramble_denials.values()),
        }

    async def _persist_operational_state(self, *, force: bool = False) -> None:
        snapshot = self._operational_snapshot()
        encoded = json.dumps(snapshot, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
        signature = hashlib.sha1(encoded.encode()).hexdigest()
        if not force and signature == self._last_persisted_signature:
            return
        await asyncio.to_thread(self.persistence.save, snapshot, self._utc_now())
        self._last_persisted_signature = signature

    async def _persist_after_delay(self) -> None:
        try:
            await asyncio.sleep(max(0.0, settings.state_persist_debounce_seconds))
            await self._persist_operational_state()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Operational-state persistence failed")

    def _schedule_persist(self) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        if self.persistence_task and not self.persistence_task.done():
            self.persistence_task.cancel()
        self.persistence_task = asyncio.create_task(self._persist_after_delay(), name="persist-operational-state")

    def _touch_workflow(self) -> None:
        self.state.touch()
        self._schedule_persist()

    async def _restore_operational_state(self) -> None:
        try:
            snapshot = await asyncio.to_thread(self.persistence.load)
        except Exception:
            log.exception("Operational-state restore failed")
            return
        if not snapshot:
            return
        self.operations = {
            str(item.get("id") or item.get("alert_id") or item.get("callsign") or ""): item
            for item in snapshot.get("operations") or []
            if item.get("id") or item.get("alert_id") or item.get("callsign")
        }
        self.manual_intercepts = {
            str(item.get("interceptor_callsign") or "").upper(): item
            for item in snapshot.get("manual_intercepts") or []
            if item.get("interceptor_callsign")
        }
        self.intercept_controls = {
            str(item.get("target_callsign") or "").upper(): item
            for item in snapshot.get("intercept_controls") or []
            if item.get("target_callsign")
        }
        self.temporary_exemptions = {
            str(item.get("id") or ""): item
            for item in snapshot.get("temporary_exemptions") or []
            if item.get("id")
        }
        self.engine.temporary_exemptions = self.temporary_exemptions
        self._sync_temporary_exemptions()
        incidents = snapshot.get("scramble_incidents")
        self.scramble_incidents = incidents if isinstance(incidents, dict) else {}
        manual_nordo = snapshot.get("manual_nordo")
        self.engine.manual_nordo = manual_nordo if isinstance(manual_nordo, dict) else {}
        self.engine.acknowledged = set(snapshot.get("acknowledged") or [])
        self.engine.dismissed = set(snapshot.get("dismissed") or [])
        self.automatic_flag_dismissals = {
            str(item.get("alert_id") or ""): item
            for item in snapshot.get("automatic_flag_dismissals") or []
            if item.get("alert_id")
        }
        self.state.automatic_flag_dismissals = list(self.automatic_flag_dismissals.values())
        self.pre_scramble_denials.clear()
        self.pre_scramble_denials.update({
            str(item.get("case_id") or ""): item
            for item in snapshot.get("pre_scramble_denials") or []
            if item.get("case_id")
        })
        self.state.pre_scramble_denials = list(self.pre_scramble_denials.values())
        self.state.operations = sorted(self.operations.values(), key=lambda item: item.get("updated_at") or "", reverse=True)[:50]
        self._sync_intercept_controls_state()
        encoded = json.dumps(self._operational_snapshot(), separators=(",", ":"), sort_keys=True, ensure_ascii=False)
        self._last_persisted_signature = hashlib.sha1(encoded.encode()).hexdigest()
        log.info("Restored %d operations and %d manual intercept assignments", len(self.operations), len(self.manual_intercepts))

    def _sync_temporary_exemptions(self) -> None:
        now = time.time()
        for exemption_id, record in list(self.temporary_exemptions.items()):
            if float(record.get("expires_at_epoch") or 0.0) <= now:
                self.temporary_exemptions.pop(exemption_id, None)
        self.engine.temporary_exemptions = self.temporary_exemptions
        self.state.temporary_exemptions = sorted(
            (dict(item) for item in self.temporary_exemptions.values()),
            key=lambda item: item.get("expires_at_epoch") or 0,
        )

    async def create_temporary_exemption(
        self,
        callsign: str,
        minutes: int,
        reason: str,
        actor: str,
    ) -> tuple[bool, dict[str, Any] | None, str | None]:
        callsign = str(callsign or "").strip().upper()[:32]
        actor = str(actor or "CONSOLE").strip()[:80] or "CONSOLE"
        reason = str(reason or "Operational coordination").strip()[:240] or "Operational coordination"
        try:
            requested = int(minutes)
        except (TypeError, ValueError):
            requested = settings.temporary_exemption_default_minutes
        duration = max(1, min(settings.temporary_exemption_max_minutes, requested))
        if not any(str(item.get("callsign") or "").upper() == callsign for item in self.state.pilots):
            return False, None, "track_not_found"
        now_epoch = time.time()
        created_at = self._utc_now()
        expires_epoch = now_epoch + duration * 60
        exemption_id = hashlib.sha1(f"{callsign}|{created_at}|{actor}".encode()).hexdigest()[:16]
        record = {
            "id": exemption_id,
            "callsign": callsign,
            "scope": "COMMUNICATIONS_ALERTS",
            "reason": reason,
            "created_at": created_at,
            "created_at_epoch": now_epoch,
            "expires_at": datetime.fromtimestamp(expires_epoch, timezone.utc).isoformat(),
            "expires_at_epoch": expires_epoch,
            "created_by": actor,
            "duration_minutes": duration,
        }
        self.temporary_exemptions[exemption_id] = record
        self._sync_temporary_exemptions()
        for operation in self.operations.values():
            if str(operation.get("callsign") or "").upper() == callsign:
                self._append_event(
                    operation,
                    f"TEMP_EXEMPTION_CREATED_{exemption_id}",
                    "Temporary communications exemption created",
                    f"{duration} minutes · {reason} · {actor}",
                )
        self._touch_workflow()
        await self.broadcaster(self.state.live_payload())
        return True, record, None

    async def remove_temporary_exemption(self, exemption_id: str, actor: str) -> tuple[bool, dict[str, Any] | None]:
        record = self.temporary_exemptions.pop(str(exemption_id or "").strip(), None)
        if record is None:
            return False, None
        actor = str(actor or "CONSOLE").strip()[:80] or "CONSOLE"
        self._sync_temporary_exemptions()
        for operation in self.operations.values():
            if str(operation.get("callsign") or "").upper() == str(record.get("callsign") or "").upper():
                self._append_event(
                    operation,
                    f"TEMP_EXEMPTION_REMOVED_{record.get('id')}_{len(operation.get('events', []))}",
                    "Temporary communications exemption removed",
                    f"Removed by {actor}",
                )
        self._touch_workflow()
        await self.broadcaster(self.state.live_payload())
        return True, record

    def _append_event(self, operation: dict[str, Any], code: str, label: str, detail: str | None = None) -> None:
        if any(event.get("code") == code for event in operation.get("events", [])):
            return
        event = {"time": self._utc_now(), "code": code, "label": label}
        if detail:
            event["detail"] = detail
        operation.setdefault("events", []).append(event)
        operation["updated_at"] = event["time"]

    @staticmethod
    def _scramble_incident_key(alert: dict[str, Any]) -> str | None:
        reason_codes = {str(item.get("code") or "") for item in alert.get("reasons") or []}
        if "AUTO_SCRAMBLE_FREQ_MISMATCH" not in reason_codes:
            return None
        center = str(alert.get("center") or "").upper()
        for raw in center.split("/"):
            callsign = raw.strip()
            parts = [part for part in callsign.split("_") if part]
            if len(parts) >= 2 and parts[-1] == "CTR" and parts[0].isalpha():
                return f"{parts[0]}_CTR"
        return None

    def _group_scramble_incidents(self, alerts: list[dict[str, Any]]) -> None:
        """Make one audible automatic communications incident per ARTCC.

        Every qualifying aircraft remains in the alert list. Additional tracks
        are tagged as grouped and excluded from the mandatory audio/modal queue.
        The first alert id remains the incident primary until the ARTCC has been
        clear for the configured reset period, preventing a second alarm when
        the original primary track disconnects before the other tracks clear.
        """
        now = time.time()
        groups: dict[str, list[dict[str, Any]]] = {}
        for alert in alerts:
            alert["alarm_group_key"] = None
            alert["alarm_primary"] = True
            alert["alarm_suppressed"] = False
            alert["alarm_suppression_reason"] = None
            key = self._scramble_incident_key(alert)
            if key and int(alert.get("confidence") or 0) >= settings.scramble_alarm_confidence:
                groups.setdefault(key, []).append(alert)

        for key, incident in list(self.scramble_incidents.items()):
            if key in groups:
                incident["empty_since"] = None
                continue
            empty_since = incident.get("empty_since")
            if empty_since is None:
                incident["empty_since"] = now
            elif now - float(empty_since) >= settings.scramble_incident_reset_seconds:
                self.scramble_incidents.pop(key, None)

        for key, group in groups.items():
            group.sort(key=lambda item: (-int(item.get("confidence") or 0), -int(item.get("score") or 0), str(item.get("callsign") or "")))
            incident = self.scramble_incidents.get(key)
            if incident is None:
                incident = {
                    "key": key,
                    "primary_alert_id": group[0].get("id"),
                    "created_at": self._utc_now(),
                    "last_seen": now,
                    "empty_since": None,
                }
                self.scramble_incidents[key] = incident
            else:
                incident["last_seen"] = now
                incident["empty_since"] = None

            primary_id = str(incident.get("primary_alert_id") or "")
            for alert in group:
                alert_id = str(alert.get("id") or "")
                is_primary = alert_id == primary_id
                alert["alarm_group_key"] = key
                alert["alarm_primary"] = is_primary
                alert["alarm_suppressed"] = not is_primary
                if not is_primary:
                    alert["alarm_suppression_reason"] = (
                        f"Additional automatic frequency-mismatch track grouped under {key}; "
                        f"primary alert {primary_id or 'already sounded'}"
                    )
                    alert["requires_ack"] = False

    def _sync_pre_scramble_denials(self) -> None:
        """Prune expired case-scoped denials and publish their shared state."""
        now = time.time()
        ttl = max(60, int(settings.pre_scramble_denial_record_ttl_seconds))
        for case_id, record in list(self.pre_scramble_denials.items()):
            denied_epoch = float(record.get("denied_at_epoch") or 0.0)
            expires_epoch = float(record.get("expires_at_epoch") or (denied_epoch + ttl))
            if expires_epoch <= now:
                self.pre_scramble_denials.pop(case_id, None)
        self.state.pre_scramble_denials = sorted(
            (dict(item) for item in self.pre_scramble_denials.values()),
            key=lambda item: item.get("denied_at_epoch") or 0,
            reverse=True,
        )

    def _apply_pre_scramble_denials(
        self,
        pilots: list[dict[str, Any]],
        alerts: list[dict[str, Any]],
    ) -> None:
        """Suppress only case-matched automatic communications escalation."""
        self._sync_pre_scramble_denials()
        pilot_by_call = {str(item.get("callsign") or "").upper(): item for item in pilots}
        suppressed_alert_ids: set[str] = set()

        for callsign, pilot in pilot_by_call.items():
            case_id = str(pilot.get("pre_scramble_case_id") or "")
            denial = self.pre_scramble_denials.get(case_id) if case_id else None
            if not denial:
                continue
            pilot["pre_scramble_denied"] = True
            pilot["pre_scramble_denial"] = dict(denial)
            pilot["pre_scramble_warning"] = None
            alert_id = str(
                pilot.get("automatic_alert_id")
                or pilot.get("alert_id")
                or denial.get("alert_id")
                or ""
            )
            if alert_id:
                suppressed_alert_ids.add(alert_id)
            if pilot.get("auto_scramble_flag") and not pilot.get("manual_nordo"):
                pilot["auto_scramble_flag"] = None
            pilot["requires_ack"] = False

        if suppressed_alert_ids or self.pre_scramble_denials:
            alerts[:] = [
                alert for alert in alerts
                if not (
                    self._automatic_comms_only_alert(alert)
                    and (
                        str(alert.get("id") or "") in suppressed_alert_ids
                        or self.pre_scramble_denials.get(
                            str((pilot_by_call.get(str(alert.get("callsign") or "").upper()) or {}).get("pre_scramble_case_id") or "")
                        )
                    )
                )
            ]

    @staticmethod
    def _automatic_comms_only_alert(alert: dict[str, Any]) -> bool:
        codes = {str(item.get("code") or "") for item in alert.get("reasons") or []}
        if "AUTO_SCRAMBLE_FREQ_MISMATCH" not in codes:
            return False
        # Independent emergencies and manual confirmations must never be delayed
        # by a simultaneous communications-anomaly burst.
        bypass_codes = {
            "GENERAL_EMERGENCY", "RADIO_FAILURE", "UNLAWFUL_INTERFERENCE",
            "MANUAL_NORDO", "MANUAL_NORDO_CONFIRMED", "SQUAWK_7700",
            "SQUAWK_7600", "SQUAWK_7500",
        }
        return not bool(codes & bypass_codes) and not bool(alert.get("manual_nordo"))

    @staticmethod
    def _mass_alert_signature(alert: dict[str, Any], pilot: dict[str, Any] | None) -> str:
        pilot = pilot or {}
        value = {
            "center": alert.get("center") or pilot.get("center"),
            "frequencies": sorted(float(item) for item in (pilot.get("frequencies") or [])),
            "active": sorted(float(item) for item in (pilot.get("active_artcc_frequencies") or [])),
            "controller": (pilot.get("auto_scramble_flag") or {}).get("controller"),
            "mismatch": bool(pilot.get("frequency_mismatch_active")),
        }
        return hashlib.sha1(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]

    def _apply_mass_alert_verification(
        self,
        pilots: list[dict[str, Any]],
        alerts: list[dict[str, Any]],
    ) -> None:
        """Require independent re-verification during simultaneous auto-flag bursts.

        Possible NORDO watches remain visible immediately. Only automatic
        scramble/intercept escalation is held, and only for frequency-mismatch
        flags without an independent emergency or manual NORDO confirmation.
        """
        now = time.time()
        pilot_by_call = {str(item.get("callsign") or "").upper(): item for item in pilots}
        candidates = [item for item in alerts if self._automatic_comms_only_alert(item)]
        candidate_ids = {str(item.get("id") or "") for item in candidates}

        # Remove expired metadata and dismissal audit records after the underlying
        # occurrence has cleared. The detection engine controls occurrence scope.
        ttl = max(60, int(settings.mass_alert_guard_record_ttl_seconds))
        for alert_id, record in list(self.mass_alert_verifications.items()):
            last_seen = float(record.get("last_seen_epoch") or record.get("first_seen_epoch") or 0)
            if alert_id not in candidate_ids and now - last_seen > ttl:
                self.mass_alert_verifications.pop(alert_id, None)
        for alert_id in list(self.automatic_flag_dismissals):
            if alert_id not in self.engine.dismissed:
                self.automatic_flag_dismissals.pop(alert_id, None)

        new_ids: list[str] = []
        for alert in candidates:
            alert_id = str(alert.get("id") or "")
            callsign = str(alert.get("callsign") or "").upper()
            pilot = pilot_by_call.get(callsign)
            signature = self._mass_alert_signature(alert, pilot)
            record = self.mass_alert_verifications.get(alert_id)
            if record is None:
                record = {
                    "alert_id": alert_id,
                    "callsign": callsign,
                    "first_seen_epoch": now,
                    "verification_started_epoch": now,
                    "last_seen_epoch": now,
                    "last_feed_sequence": self.state.feed_sequence + 1,
                    "stable_snapshots": 1,
                    "signature": signature,
                    "verification_required": False,
                    "verified": False,
                    "burst_id": None,
                }
                self.mass_alert_verifications[alert_id] = record
                new_ids.append(alert_id)
            else:
                record["last_seen_epoch"] = now
                next_sequence = self.state.feed_sequence + 1
                if record.get("last_feed_sequence") != next_sequence:
                    if record.get("signature") == signature:
                        record["stable_snapshots"] = int(record.get("stable_snapshots") or 0) + 1
                    else:
                        record["signature"] = signature
                        record["stable_snapshots"] = 1
                        record["verification_started_epoch"] = now
                        record["verified"] = False
                    record["last_feed_sequence"] = next_sequence

        # A burst is two or more newly appearing automatic communications flags in
        # the configured window, even when they belong to different ARTCCs.
        window = max(10, int(settings.mass_alert_guard_window_seconds))
        recent_unverified = [
            record for record in self.mass_alert_verifications.values()
            if record.get("alert_id") in candidate_ids
            and not record.get("verified")
            and now - float(record.get("first_seen_epoch") or now) <= window
        ]
        if len(recent_unverified) >= max(2, int(settings.mass_alert_guard_threshold)):
            existing_burst = next((str(item.get("burst_id")) for item in recent_unverified if item.get("burst_id")), None)
            burst_id = existing_burst or f"BURST-{int(now)}"
            for record in recent_unverified:
                if not record.get("verification_required"):
                    record["verification_started_epoch"] = now
                    record["stable_snapshots"] = 1
                record["verification_required"] = True
                record["burst_id"] = burst_id

        verify_seconds = max(0, int(settings.mass_alert_guard_verify_seconds))
        min_snapshots = max(2, int(settings.mass_alert_guard_min_snapshots))
        pending_ids: set[str] = set()
        verified_ids: set[str] = set()
        for alert in candidates:
            alert_id = str(alert.get("id") or "")
            record = self.mass_alert_verifications.get(alert_id) or {}
            if record.get("verification_required") and not record.get("verified"):
                elapsed = max(0.0, now - float(record.get("verification_started_epoch") or now))
                if int(record.get("stable_snapshots") or 0) >= min_snapshots and elapsed >= verify_seconds:
                    record["verified"] = True
                    record["verified_at"] = self._utc_now()
                else:
                    pending_ids.add(alert_id)
            if record.get("verified"):
                verified_ids.add(alert_id)

            callsign = str(alert.get("callsign") or "").upper()
            pilot = pilot_by_call.get(callsign)
            if not pilot:
                continue
            if alert_id in pending_ids:
                snapshots = int(record.get("stable_snapshots") or 0)
                elapsed = max(0, int(now - float(record.get("verification_started_epoch") or now)))
                remaining = max(0, verify_seconds - elapsed)
                detail = {
                    "active": True,
                    "status": "VERIFYING",
                    "burst_id": record.get("burst_id"),
                    "stable_snapshots": snapshots,
                    "required_snapshots": min_snapshots,
                    "elapsed_seconds": elapsed,
                    "remaining_seconds": remaining,
                    "reason": "Multiple automatic communications flags appeared together; independently re-verifying this track",
                }
                pilot["mass_alert_verification"] = detail
                pilot["mass_alert_verification_pending"] = True
                pilot["automatic_alert_id"] = alert_id
                pilot["requires_ack"] = False
                if isinstance(pilot.get("auto_scramble_flag"), dict):
                    pilot["auto_scramble_flag"]["verification_pending"] = True
                    pilot["auto_scramble_flag"]["verification"] = detail
                watch = pilot.get("nordo_watch")
                if isinstance(watch, dict) and not pilot.get("manual_nordo"):
                    watch["title"] = "POSSIBLE NORDO — VERIFYING"
                    watch["kind"] = "MASS_ALERT_INDEPENDENT_VERIFICATION"
                    watch["detail"] = (
                        f"Independent verification {snapshots}/{min_snapshots} fresh snapshots; "
                        f"minimum hold {remaining}s remaining before automatic escalation"
                    )
                    watch["confidence"] = min(int(watch.get("confidence") or 40), 55)
                alert["alarm_suppressed"] = True
                alert["alarm_suppression_reason"] = "Simultaneous automatic-flag burst; independent verification pending"
                alert["requires_ack"] = False
            elif alert_id in verified_ids:
                pilot["mass_alert_verification"] = {
                    "active": False,
                    "status": "VERIFIED",
                    "burst_id": record.get("burst_id"),
                    "stable_snapshots": int(record.get("stable_snapshots") or 0),
                    "required_snapshots": min_snapshots,
                    "verified_at": record.get("verified_at"),
                }
                pilot["mass_alert_verification_pending"] = False
                pilot["automatic_alert_id"] = alert_id
                alert["mass_alert_independently_verified"] = True

        # Pending tracks stay in the COMMS/NORDO watch rail but are not placed in
        # the intercept alert queue and cannot sound the automatic scramble alarm.
        if pending_ids:
            alerts[:] = [item for item in alerts if str(item.get("id") or "") not in pending_ids]

        # Apply operator dismissals to the live track while preserving the watch.
        for pilot in pilots:
            alert_id = str(pilot.get("automatic_alert_id") or pilot.get("alert_id") or "")
            dismissal = self.automatic_flag_dismissals.get(alert_id)
            if not dismissal or not pilot.get("auto_scramble_flag"):
                continue
            pilot["automatic_flag_dismissed"] = True
            pilot["automatic_flag_dismissal"] = dict(dismissal)
            pilot["requires_ack"] = False
            pilot["automatic_alert_id"] = alert_id
            pilot["auto_scramble_flag"]["dismissed"] = True
            pilot["auto_scramble_flag"]["dismissal"] = dict(dismissal)
            watch = pilot.get("nordo_watch")
            if isinstance(watch, dict) and not pilot.get("manual_nordo"):
                watch["title"] = "POSSIBLE NORDO — FLAG DISMISSED / MONITOR"
                watch["detail"] = f"Automatic flag dismissed by {dismissal.get('dismissed_by', 'ATC console')}: {dismissal.get('reason', 'operator review')}"

        pending_records = [
            dict(record) for record in self.mass_alert_verifications.values()
            if record.get("alert_id") in pending_ids
        ]
        self.state.mass_alert_guard = {
            "active": bool(pending_records),
            "pending": len(pending_records),
            "threshold": int(settings.mass_alert_guard_threshold),
            "verify_seconds": verify_seconds,
            "required_snapshots": min_snapshots,
            "burst_ids": sorted({str(item.get("burst_id")) for item in pending_records if item.get("burst_id")}),
        }
        self.state.automatic_flag_dismissals = sorted(
            (dict(item) for item in self.automatic_flag_dismissals.values()),
            key=lambda item: item.get("dismissed_at") or "",
            reverse=True,
        )

    @staticmethod
    def _new_phase_list(now_iso: str) -> list[dict[str, Any]]:
        phases = [
            {
                "id": phase_id,
                "label": label,
                "complete": phase_id == "alert_received",
                "completed_at": now_iso if phase_id == "alert_received" else None,
                "completed_by": "SYSTEM" if phase_id == "alert_received" else None,
            }
            for phase_id, label in INTERCEPT_PHASES
        ]
        return phases

    @staticmethod
    def _refresh_operation_counts(operation: dict[str, Any]) -> None:
        accepted = operation.setdefault("accepted_consoles", {})
        operation["accepted_count"] = len(accepted)
        operation["accepted_console_list"] = sorted(
            accepted.values(),
            key=lambda item: item.get("accepted_at") or "",
        )

    def _expire_stale_responders(self, operation: dict[str, Any], now: datetime) -> None:
        accepted = operation.setdefault("accepted_consoles", {})
        expired: list[tuple[str, dict[str, Any]]] = []
        for console_id, record in list(accepted.items()):
            raw = record.get("updated_at") or record.get("accepted_at")
            try:
                updated = datetime.fromisoformat(str(raw))
            except (TypeError, ValueError):
                updated = datetime.fromtimestamp(0, timezone.utc)
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            if (now - updated).total_seconds() > settings.console_presence_timeout_seconds:
                expired.append((console_id, accepted.pop(console_id)))
        for console_id, record in expired:
            label = str(record.get("label") or console_id)
            self._append_event(
                operation,
                f"CONSOLE_PRESENCE_EXPIRED_{console_id}_{len(operation.get('events', []))}",
                f"{label} console presence expired",
                "Responder no longer counted inbound after missed heartbeat",
            )

    def _phase_record(self, operation: dict[str, Any], phase_id: str) -> dict[str, Any] | None:
        return next(
            (phase for phase in operation.setdefault("phases", self._new_phase_list(self._utc_now())) if phase.get("id") == phase_id),
            None,
        )

    def _set_phase(
        self,
        operation: dict[str, Any],
        phase_id: str,
        complete: bool,
        actor: str,
    ) -> bool:
        phase = self._phase_record(operation, phase_id)
        if phase is None or bool(phase.get("complete")) == bool(complete):
            return phase is not None
        phase["complete"] = bool(complete)
        phase["completed_at"] = self._utc_now() if complete else None
        phase["completed_by"] = actor if complete else None
        operation["updated_at"] = self._utc_now()
        action = "completed" if complete else "reopened"
        self._append_event(
            operation,
            f"PHASE_{phase_id.upper()}_{action.upper()}_{len(operation.get('events', []))}",
            f"{INTERCEPT_PHASE_LABELS.get(phase_id, phase_id)} {action}",
            f"Console {actor}",
        )
        if complete:
            operation["stage"] = phase_id
            operation["status"] = INTERCEPT_PHASE_LABELS.get(phase_id, phase_id).upper()
            if phase_id == "intercept_complete":
                operation["completed"] = True
        elif phase_id == "intercept_complete":
            operation["completed"] = False
        return True

    def _sync_operations(self, alerts: list[dict[str, Any]], pilots: list[dict[str, Any]]) -> None:
        now = datetime.now(timezone.utc)
        active_ids = {alert["id"] for alert in alerts}
        pilot_by_call = {pilot["callsign"]: pilot for pilot in pilots}
        for alert in alerts:
            operation = self.operations.get(alert["id"])
            if operation is None:
                created_at = self._utc_now()
                operation = {
                    "id": alert["id"],
                    "callsign": alert["callsign"],
                    "status": "ALERT GENERATED",
                    "stage": "alert_received",
                    "acknowledged": False,
                    "active": True,
                    "completed": False,
                    "created_at": created_at,
                    "updated_at": created_at,
                    "events": [],
                    "accepted_consoles": {},
                    "accepted_count": 0,
                    "accepted_console_list": [],
                    "phases": self._new_phase_list(created_at),
                    "occurrence": 1,
                    "target_response_status": "UNKNOWN",
                    "target_response_updated_at": None,
                    "target_response_updated_by": None,
                }
                self.operations[alert["id"]] = operation
                self._append_event(operation, "ALERT_GENERATED", "Alert generated", alert.get("title"))
            elif not operation.get("active"):
                # A new occurrence using the same callsign/alert hash must not
                # inherit the prior occurrence's responders, checklist, or status.
                occurrence = int(operation.get("occurrence") or 1) + 1
                created_at = self._utc_now()
                operation.clear()
                operation.update({
                    "id": alert["id"],
                    "callsign": alert["callsign"],
                    "status": "ALERT GENERATED",
                    "stage": "alert_received",
                    "acknowledged": False,
                    "active": True,
                    "completed": False,
                    "occurrence": occurrence,
                    "created_at": created_at,
                    "updated_at": created_at,
                    "events": [],
                    "accepted_consoles": {},
                    "accepted_count": 0,
                    "accepted_console_list": [],
                    "phases": self._new_phase_list(created_at),
                    "target_response_status": "UNKNOWN",
                    "target_response_updated_at": None,
                    "target_response_updated_by": None,
                })
                self._append_event(operation, "ALERT_GENERATED", "New alert occurrence generated", alert.get("title"))
            operation.update(
                {
                    "active": True,
                    "callsign": alert["callsign"],
                    "title": alert.get("title"),
                    "confidence": alert.get("confidence"),
                    "severity": alert.get("severity"),
                    "lat": alert.get("lat"),
                    "lon": alert.get("lon"),
                    "recommended_base": alert.get("recommended_base"),
                    "active_interceptors": alert.get("active_interceptors") or [],
                    "detector_codes": [str(item.get("code") or "") for item in alert.get("reasons") or [] if item.get("code")],
                    "alarm_group_key": alert.get("alarm_group_key"),
                    "alarm_primary": alert.get("alarm_primary", True),
                    "alarm_suppressed": alert.get("alarm_suppressed", False),
                    "alarm_suppression_reason": alert.get("alarm_suppression_reason"),
                }
            )
            if alert.get("alarm_suppressed"):
                self._append_event(
                    operation,
                    "ALERT_GROUPED",
                    "Additional track grouped under existing ARTCC incident",
                    alert.get("alarm_suppression_reason"),
                )
            if alert.get("confidence", 0) >= settings.scramble_alarm_confidence and not alert.get("alarm_suppressed"):
                self._append_event(
                    operation,
                    "SCRAMBLE_RECOMMENDED",
                    "Scramble recommended",
                    f"Confidence {alert.get('confidence', 0)}%",
                )
                if not operation.get("acknowledged") and operation.get("stage") in {"alert", "alert_received"}:
                    operation["status"] = "SCRAMBLE RECOMMENDED"
            pilot = pilot_by_call.get(alert.get("callsign")) or {}
            evidence = {
                "center": pilot.get("center"),
                "radios": tuple(pilot.get("frequencies") or []),
                "mismatch": bool(pilot.get("frequency_mismatch_active")),
                "case_status": pilot.get("frequency_mismatch_case_status"),
                "handoff": (pilot.get("online_center_handoff_detail") or {}).get("downstream_controller"),
                "temporary_exemption": (pilot.get("temporary_exemption_detail") or {}).get("id"),
                "cooldown": bool(pilot.get("communications_cooldown_active")),
            }
            previous_evidence = operation.get("evidence_snapshot") or {}
            if evidence["radios"] and tuple(previous_evidence.get("radios") or []) != evidence["radios"]:
                self._append_event(
                    operation,
                    f"RADIOS_{'_'.join(str(value) for value in evidence['radios'])}_{len(operation.get('events', []))}",
                    "Reported radio assignment changed",
                    ", ".join(f"{float(value):.3f}" for value in evidence["radios"]),
                )
            if evidence["center"] and previous_evidence.get("center") != evidence["center"]:
                self._append_event(
                    operation,
                    f"ATC_OWNER_{evidence['center']}_{len(operation.get('events', []))}",
                    "Controlling ATC candidate changed",
                    str(evidence["center"]),
                )
            if evidence["mismatch"] and not previous_evidence.get("mismatch"):
                self._append_event(operation, f"MISMATCH_STARTED_{operation.get('occurrence', 1)}", "Frequency mismatch timer started")
            if evidence["handoff"] and previous_evidence.get("handoff") != evidence["handoff"]:
                detail = pilot.get("online_center_handoff_detail") or {}
                self._append_event(
                    operation,
                    f"HANDOFF_{evidence['handoff']}_{len(operation.get('events', []))}",
                    "Online Center handoff verified",
                    f"{detail.get('current_artcc') or 'CURRENT'} → {detail.get('downstream_artcc') or evidence['handoff']} · {detail.get('boundary_distance_nm', '—')} NM",
                )
            if evidence["temporary_exemption"] and previous_evidence.get("temporary_exemption") != evidence["temporary_exemption"]:
                detail = pilot.get("temporary_exemption_detail") or {}
                self._append_event(
                    operation,
                    f"TEMP_EXEMPTION_ACTIVE_{evidence['temporary_exemption']}",
                    "Temporary exemption suppressing automatic escalation",
                    str(detail.get("reason") or "Operational exemption"),
                )
            if evidence["cooldown"] and not previous_evidence.get("cooldown"):
                self._append_event(
                    operation,
                    f"COOLDOWN_ACTIVE_{len(operation.get('events', []))}",
                    "Post-handoff stability cooldown active",
                    f"{pilot.get('communications_cooldown_remaining_seconds', 0)} seconds remaining",
                )
            operation["evidence_snapshot"] = evidence

            for interceptor in alert.get("active_interceptors") or []:
                code = f"INTERCEPTOR_{interceptor.get('callsign')}"
                self._append_event(
                    operation,
                    code,
                    f"Interceptor {interceptor.get('callsign')} detected",
                    "Squawk 7777 active intercept",
                )

        for operation_id, operation in list(self.operations.items()):
            if operation_id not in active_ids and operation.get("active"):
                operation["active"] = False
                self._append_event(operation, "CONDITION_CLEARED", "Alert condition cleared")
                if not operation.get("completed"):
                    operation["status"] = "MONITORING COMPLETE"
            updated = datetime.fromisoformat(operation["updated_at"])
            if now - updated > timedelta(hours=6):
                self.operations.pop(operation_id, None)

        for operation in self.operations.values():
            operation.setdefault("phases", self._new_phase_list(operation.get("created_at") or self._utc_now()))
            operation.setdefault("target_response_status", "UNKNOWN")
            operation.setdefault("target_response_updated_at", None)
            operation.setdefault("target_response_updated_by", None)
            operation.setdefault("accepted_consoles", {})
            self._expire_stale_responders(operation, now)
            self._refresh_operation_counts(operation)

        self.state.operations = sorted(
            self.operations.values(),
            key=lambda item: item.get("updated_at") or "",
            reverse=True,
        )[:50]

    async def accept_operation(
        self,
        alert_id: str,
        console_id: str,
        console_label: str | None = None,
    ) -> tuple[bool, dict[str, Any] | None]:
        operation = self.operations.get(alert_id)
        console_id = str(console_id or "").strip()[:80]
        if operation is None or not console_id:
            return False, None
        label = str(console_label or console_id).strip()[:80] or console_id
        accepted = operation.setdefault("accepted_consoles", {})
        accepted[console_id] = {
            "console_id": console_id,
            "label": label,
            "status": "INBOUND",
            "accepted_at": accepted.get(console_id, {}).get("accepted_at") or self._utc_now(),
            "updated_at": self._utc_now(),
        }
        self._set_phase(operation, "qra_accepted", True, label)
        self._append_event(
            operation,
            f"CONSOLE_ACCEPTED_{console_id}",
            f"{label} accepted intercept",
            "Responder marked inbound",
        )
        if operation.get("stage") in {"alert", "alert_received", "qra_accepted"}:
            operation["status"] = "QRA RESPONSE ACCEPTED"
        self._refresh_operation_counts(operation)
        self.state.operations = sorted(self.operations.values(), key=lambda item: item.get("updated_at") or "", reverse=True)[:50]
        self._touch_workflow()
        await self.broadcaster(self.state.live_payload())
        return True, operation

    async def release_operation(self, alert_id: str, console_id: str) -> tuple[bool, dict[str, Any] | None]:
        operation = self.operations.get(alert_id)
        console_id = str(console_id or "").strip()[:80]
        if operation is None or not console_id:
            return False, None
        accepted = operation.setdefault("accepted_consoles", {})
        record = accepted.pop(console_id, None)
        if record is None:
            return False, operation
        label = str(record.get("label") or console_id)
        self._append_event(
            operation,
            f"CONSOLE_RELEASED_{console_id}_{len(operation.get('events', []))}",
            f"{label} released intercept",
            "Responder no longer inbound",
        )
        if not accepted:
            self._set_phase(operation, "qra_accepted", False, label)
            if operation.get("active") and not operation.get("completed"):
                operation["status"] = "SCRAMBLE RECOMMENDED"
        self._refresh_operation_counts(operation)
        self.state.operations = sorted(self.operations.values(), key=lambda item: item.get("updated_at") or "", reverse=True)[:50]
        self._touch_workflow()
        await self.broadcaster(self.state.live_payload())
        return True, operation

    async def set_operation_phase(
        self,
        alert_id: str,
        phase_id: str,
        complete: bool,
        actor: str,
    ) -> tuple[bool, dict[str, Any] | None]:
        operation = self.operations.get(alert_id)
        if operation is None or phase_id not in INTERCEPT_PHASE_LABELS:
            return False, None
        actor = str(actor or "CONSOLE").strip()[:80] or "CONSOLE"
        found = self._set_phase(operation, phase_id, complete, actor)
        self._refresh_operation_counts(operation)
        self.state.operations = sorted(self.operations.values(), key=lambda item: item.get("updated_at") or "", reverse=True)[:50]
        self._touch_workflow()
        await self.broadcaster(self.state.live_payload())
        return found, operation

    async def advance_operation(self, alert_id: str, stage: str) -> bool:
        compatibility = {
            "airborne": "fighters_airborne",
            "radar_contact": "radar_contact",
            "intercept_complete": "intercept_complete",
        }
        phase_id = compatibility.get(stage, stage)
        found, _ = await self.set_operation_phase(alert_id, phase_id, True, "LEGACY CONSOLE")
        return found

    @staticmethod
    def _assignment_track_summary(pilot: dict[str, Any]) -> dict[str, Any]:
        return {
            "callsign": pilot.get("callsign"),
            "aircraft": pilot.get("aircraft"),
            "aircraft_type": pilot.get("aircraft_type"),
            "lat": pilot.get("lat"),
            "lon": pilot.get("lon"),
            "altitude": int(pilot.get("altitude") or 0),
            "groundspeed": int(pilot.get("groundspeed") or 0),
            "heading": int(round(float(pilot.get("heading") or 0))) % 360,
            "squawk": pilot.get("squawk"),
            "on_ground": bool(pilot.get("on_ground")),
            "vsoa": bool(pilot.get("vsoa")),
        }

    def _ensure_intercept_control(self, target_callsign: str) -> dict[str, Any]:
        target_callsign = str(target_callsign or "").strip().upper()[:32]
        existing = self.intercept_controls.get(target_callsign)
        if existing is not None:
            return existing
        now_iso = self._utc_now()
        control = {
            "target_callsign": target_callsign,
            "target_response_status": "UNKNOWN",
            "atc_coordination_status": "UNCOORDINATED",
            "command_status": "MONITOR",
            "coordination_note": "",
            "updated_at": now_iso,
            "updated_by": "SYSTEM",
        }
        self.intercept_controls[target_callsign] = control
        return control

    def _sync_intercept_controls_state(self) -> None:
        active_targets = {
            str(item.get("target_callsign") or "").upper()
            for item in self.manual_intercepts.values()
            if item.get("target_callsign")
        }
        active_targets.update(
            str(item.get("callsign") or "").upper()
            for item in self.operations.values()
            if item.get("active") and item.get("callsign")
        )
        for target in active_targets:
            if target:
                self._ensure_intercept_control(target)
        self.state.intercept_controls = sorted(
            (dict(value) for value in self.intercept_controls.values()),
            key=lambda item: item.get("updated_at") or "",
            reverse=True,
        )[:100]

    def _apply_manual_intercepts(
        self,
        pilots: list[dict[str, Any]],
        alerts: list[dict[str, Any]],
        *,
        force_recalculate: bool = False,
    ) -> None:
        now_epoch = time.time()
        now_iso = self._utc_now()
        pilot_by_call = {str(item.get("callsign") or "").upper(): item for item in pilots}
        alert_by_call = {str(item.get("callsign") or "").upper(): item for item in alerts}
        rendered: list[dict[str, Any]] = []
        expired: list[str] = []

        for interceptor_callsign, record in list(self.manual_intercepts.items()):
            target_callsign = str(record.get("target_callsign") or "").upper()
            interceptor = pilot_by_call.get(interceptor_callsign)
            target = pilot_by_call.get(target_callsign)
            control = self._ensure_intercept_control(target_callsign)

            if interceptor is None or target is None:
                missing = []
                if interceptor is None:
                    missing.append("INTERCEPTOR")
                if target is None:
                    missing.append("TARGET")
                missing_since = float(record.setdefault("missing_since_epoch", now_epoch))
                record["status"] = "TRACK LOST"
                record["updated_at"] = now_iso
                rendered.append({
                    **record,
                    "assignment_id": f"{interceptor_callsign}->{target_callsign}",
                    "live": False,
                    "calculated_at": now_iso,
                    "missing": missing,
                    "missing_seconds": int(max(0.0, now_epoch - missing_since)),
                    "target_response_status": control.get("target_response_status", record.get("target_response_status", "UNKNOWN")),
                    "atc_coordination_status": control.get("atc_coordination_status", "UNCOORDINATED"),
                    "command_status": control.get("command_status", "MONITOR"),
                    "coordination_note": control.get("coordination_note", ""),
                    "target_control": dict(control),
                })
                if now_epoch - missing_since > 300:
                    expired.append(interceptor_callsign)
                continue

            record.pop("missing_since_epoch", None)

            # A manual assignment overrides only this interceptor's automatic
            # pairing. Other interceptors and automatic assignments remain intact.
            for item in pilots:
                item["active_interceptors"] = [
                    value for value in (item.get("active_interceptors") or [])
                    if str(value.get("callsign") or "").upper() != interceptor_callsign
                ]
            for alert in alerts:
                alert["active_interceptors"] = [
                    value for value in (alert.get("active_interceptors") or [])
                    if str(value.get("callsign") or "").upper() != interceptor_callsign
                ]

            assignment_id = f"{interceptor_callsign}->{target_callsign}"
            signature = intercept_pair_signature(interceptor, target)
            cached = self._manual_intercept_cache.get(assignment_id)
            if cached and cached[0] == signature and not force_recalculate:
                solution = dict(cached[1])
                calculated_at = cached[2]
            else:
                solution = self.engine._track_intercept_solution(interceptor, target)
                calculated_at = now_iso
                self._manual_intercept_cache[assignment_id] = (signature, dict(solution), calculated_at)
            solution.update({
                "assignment_id": assignment_id,
                "assignment_source": "manual",
                "manual": True,
                "calculated_at": calculated_at,
                "assigned_at": record.get("assigned_at"),
                "assigned_by": record.get("assigned_by"),
                "updated_at": now_iso,
                "target_response_status": control.get("target_response_status", record.get("target_response_status", "UNKNOWN")),
                "atc_coordination_status": control.get("atc_coordination_status", "UNCOORDINATED"),
                "command_status": control.get("command_status", "MONITOR"),
                "coordination_note": control.get("coordination_note", ""),
                "target_control": dict(control),
            })
            record["status"] = "ACTIVE" if solution.get("estimated_intercept_minutes") is not None else "NO CURRENT SOLUTION"
            record["target_response_status"] = control.get("target_response_status", record.get("target_response_status", "UNKNOWN"))
            record["atc_coordination_status"] = control.get("atc_coordination_status", "UNCOORDINATED")
            record["command_status"] = control.get("command_status", "MONITOR")
            record["coordination_note"] = control.get("coordination_note", "")
            record["updated_at"] = now_iso

            interceptor["active_intercept"] = True
            interceptor["manual_intercept"] = True
            interceptor["display_class"] = "fighter"
            interceptor["track_color"] = "yellow"
            interceptor["operational_status"] = "MANUAL INTERCEPT"
            interceptor["intercept_assignment"] = solution
            interceptor.setdefault("context", [])
            manual_context = f"Manually assigned by {record.get('assigned_by') or 'CONSOLE'} to intercept {target_callsign}"
            if manual_context not in interceptor["context"]:
                interceptor["context"].append(manual_context)

            target.setdefault("active_interceptors", []).append({
                "callsign": interceptor_callsign,
                **solution,
            })
            target.setdefault("context", [])
            target_context = f"Manual interceptor {interceptor_callsign} assigned by {record.get('assigned_by') or 'CONSOLE'}"
            if target_context not in target["context"]:
                target["context"].append(target_context)
            alert = alert_by_call.get(target_callsign)
            if alert is not None:
                alert.setdefault("active_interceptors", []).append({
                    "callsign": interceptor_callsign,
                    **solution,
                })

            rendered.append({
                **record,
                **solution,
                "interceptor_callsign": interceptor_callsign,
                "target_callsign": target_callsign,
                "live": True,
                "interceptor": self._assignment_track_summary(interceptor),
                "target": self._assignment_track_summary(target),
            })

        for callsign in expired:
            removed = self.manual_intercepts.pop(callsign, None)
            if removed:
                self._manual_intercept_cache.pop(f"{callsign}->{str(removed.get('target_callsign') or '').upper()}", None)

        active_assignment_ids = {
            f"{callsign}->{str(record.get('target_callsign') or '').upper()}"
            for callsign, record in self.manual_intercepts.items()
        }
        self._manual_intercept_cache = {
            key: value for key, value in self._manual_intercept_cache.items() if key in active_assignment_ids
        }

        self.state.manual_intercepts = sorted(
            rendered,
            key=lambda item: item.get("assigned_at") or "",
            reverse=True,
        )
        self._sync_intercept_controls_state()

    async def recalculate_intercepts(
        self,
        actor: str,
    ) -> InterceptRecalculationResult:
        """Rebuild every current intercept solution from the latest live tracks.

        The normal VATSIM feed path already performs this calculation whenever a
        fresh network snapshot arrives. This explicit action gives operators a
        safe way to refresh the displayed solution immediately after changing an
        assignment or while confirming that every selected interceptor is using
        the same latest track state.
        """
        actor = str(actor or "CONSOLE").strip()[:80] or "CONSOLE"
        async with self.process_lock:
            self._rebuild_current_intercepts(force_recalculate=True)
            self._sync_operations(self.state.alerts, self.state.pilots)
            self._sync_intercept_controls_state()
            self._touch_workflow()
            payload = self.state.live_payload()
        await self.broadcaster(payload)
        log.info("Intercept solutions manually recalculated by %s", actor)
        active_count = sum(
            1
            for pilot in self.state.pilots
            if pilot.get("active_intercept") and pilot.get("intercept_assignment")
        )
        return InterceptRecalculationResult(
            list(self.state.manual_intercepts),
            actor=actor,
            recalculated_at=self.state.intercept_recalculated_at or self.state.updated_at,
            active_intercepts=active_count,
        )

    def _rebuild_current_intercepts(self, *, force_recalculate: bool = False) -> None:
        self.state.intercept_recalculated_at = self._utc_now()
        pilots = self.state.pilots
        alerts = self.state.alerts
        for pilot in pilots:
            pilot["active_interceptors"] = []
            pilot["intercept_assignment"] = None
            pilot["manual_intercept"] = False
            squawk_intercept = str(pilot.get("squawk") or "").zfill(4) == "7777"
            pilot["active_intercept"] = squawk_intercept
            pilot["operational_status"] = "ACTIVE INTERCEPT" if squawk_intercept else None
            pilot["display_class"] = "fighter" if squawk_intercept or pilot.get("aircraft_category") == "fighter" else "standard"
            if squawk_intercept:
                pilot["track_color"] = "yellow"
            elif pilot.get("manual_nordo"):
                pilot["track_color"] = "red"
            else:
                pilot["track_color"] = (pilot.get("nordo_watch") or {}).get("level") or pilot.get("severity") or "green"
        for alert in alerts:
            alert["active_interceptors"] = []
        self.engine._associate_interceptors(pilots, alerts)
        self._apply_manual_intercepts(pilots, alerts, force_recalculate=force_recalculate)

    async def assign_manual_intercepts(
        self,
        interceptor_callsigns: list[str],
        target_callsign: str,
        actor: str,
    ) -> tuple[bool, list[dict[str, Any]], dict[str, str], str | None]:
        target_callsign = str(target_callsign or "").strip().upper()[:32]
        actor = str(actor or "CONSOLE").strip()[:80] or "CONSOLE"
        normalized: list[str] = []
        for raw in interceptor_callsigns or []:
            value = str(raw or "").strip().upper()[:32]
            if value and value not in normalized:
                normalized.append(value)
        if not target_callsign or not normalized:
            return False, [], {}, "callsigns_required"
        if target_callsign in normalized:
            return False, [], {target_callsign: "same_track"}, "same_track"
        live_callsigns = {str(item.get("callsign") or "").upper() for item in self.state.pilots}
        if target_callsign not in live_callsigns:
            return False, [], {}, "target_not_found"
        errors = {callsign: "interceptor_not_found" for callsign in normalized if callsign not in live_callsigns}
        valid = [callsign for callsign in normalized if callsign in live_callsigns and callsign != target_callsign]
        if not valid:
            return False, [], errors, "interceptor_not_found"

        now_iso = self._utc_now()
        control = self._ensure_intercept_control(target_callsign)
        for interceptor_callsign in valid:
            existing = self.manual_intercepts.get(interceptor_callsign)
            same_target = bool(existing and existing.get("target_callsign") == target_callsign)
            self.manual_intercepts[interceptor_callsign] = {
                "interceptor_callsign": interceptor_callsign,
                "target_callsign": target_callsign,
                "assigned_at": existing.get("assigned_at") if same_target else now_iso,
                "assigned_by": actor,
                "updated_at": now_iso,
                "status": "ASSIGNED",
                "target_response_status": control.get("target_response_status", "UNKNOWN"),
                "target_response_updated_at": existing.get("target_response_updated_at") if same_target else None,
                "target_response_updated_by": existing.get("target_response_updated_by") if same_target else None,
                "atc_coordination_status": control.get("atc_coordination_status", "UNCOORDINATED"),
                "command_status": control.get("command_status", "MONITOR"),
                "coordination_note": control.get("coordination_note", ""),
            }

        self._rebuild_current_intercepts()
        self._sync_operations(self.state.alerts, self.state.pilots)
        operation = next(
            (item for item in self.operations.values() if item.get("callsign") == target_callsign and item.get("active")),
            None,
        )
        if operation is not None:
            for interceptor_callsign in valid:
                self._append_event(
                    operation,
                    f"MANUAL_ASSIGN_{interceptor_callsign}_{len(operation.get('events', []))}",
                    f"{interceptor_callsign} manually assigned",
                    f"Assigned by {actor}",
                )
            self.state.operations = sorted(self.operations.values(), key=lambda item: item.get("updated_at") or "", reverse=True)[:50]
        self._sync_intercept_controls_state()
        self._touch_workflow()
        await self.broadcaster(self.state.live_payload())
        assignments = [
            item for item in self.state.manual_intercepts
            if item.get("interceptor_callsign") in set(valid)
        ]
        return True, assignments, errors, None

    async def assign_manual_intercept(
        self,
        interceptor_callsign: str,
        target_callsign: str,
        actor: str,
    ) -> tuple[bool, dict[str, Any] | None, str | None]:
        found, assignments, errors, error = await self.assign_manual_intercepts(
            [interceptor_callsign], target_callsign, actor
        )
        normalized = str(interceptor_callsign or "").strip().upper()[:32]
        if not found:
            return False, None, errors.get(normalized) or error
        assignment = next((item for item in assignments if item.get("interceptor_callsign") == normalized), None)
        return True, assignment, None

    async def set_manual_intercept_response(
        self,
        interceptor_callsign: str,
        status: str,
        actor: str,
    ) -> tuple[bool, dict[str, Any] | None, str | None]:
        interceptor_callsign = str(interceptor_callsign or "").strip().upper()[:32]
        status = str(status or "").strip().upper()
        actor = str(actor or "CONSOLE").strip()[:80] or "CONSOLE"
        if status not in TARGET_RESPONSE_STATUSES:
            return False, None, "invalid_status"
        record = self.manual_intercepts.get(interceptor_callsign)
        if record is None:
            return False, None, "assignment_not_found"
        now_iso = self._utc_now()
        target_callsign = str(record.get("target_callsign") or "").upper()
        control = self._ensure_intercept_control(target_callsign)
        control["target_response_status"] = status
        control["updated_at"] = now_iso
        control["updated_by"] = actor
        record["target_response_status"] = status
        record["target_response_updated_at"] = now_iso
        record["target_response_updated_by"] = actor
        record["updated_at"] = now_iso
        operation = next(
            (item for item in self.operations.values() if item.get("callsign") == target_callsign and item.get("active")),
            None,
        )
        if operation is not None:
            operation["target_response_status"] = status
            operation["target_response_updated_at"] = now_iso
            operation["target_response_updated_by"] = actor
            self._append_event(
                operation,
                f"TARGET_RESPONSE_{status}_{len(operation.get('events', []))}",
                f"Target response marked {status.replace('_', ' ').lower()}",
                f"Updated by {actor}",
            )
        self._rebuild_current_intercepts()
        self._sync_operations(self.state.alerts, self.state.pilots)
        self._touch_workflow()
        await self.broadcaster(self.state.live_payload())
        assignment = next(
            (item for item in self.state.manual_intercepts if item.get("interceptor_callsign") == interceptor_callsign),
            record,
        )
        return True, assignment, None

    async def set_operation_target_response(
        self,
        alert_id: str,
        status: str,
        actor: str,
    ) -> tuple[bool, dict[str, Any] | None, str | None]:
        status = str(status or "").strip().upper()
        actor = str(actor or "CONSOLE").strip()[:80] or "CONSOLE"
        if status not in TARGET_RESPONSE_STATUSES:
            return False, None, "invalid_status"
        operation = self.operations.get(alert_id)
        if operation is None:
            return False, None, "operation_not_found"
        now_iso = self._utc_now()
        target_callsign = str(operation.get("callsign") or "").upper()
        control = self._ensure_intercept_control(target_callsign)
        control["target_response_status"] = status
        control["updated_at"] = now_iso
        control["updated_by"] = actor
        operation["target_response_status"] = status
        operation["target_response_updated_at"] = now_iso
        operation["target_response_updated_by"] = actor
        self._append_event(
            operation,
            f"TARGET_RESPONSE_{status}_{len(operation.get('events', []))}",
            f"Target response marked {status.replace('_', ' ').lower()}",
            f"Updated by {actor}",
        )
        for record in self.manual_intercepts.values():
            if str(record.get("target_callsign") or "").upper() != target_callsign:
                continue
            record["target_response_status"] = status
            record["target_response_updated_at"] = now_iso
            record["target_response_updated_by"] = actor
            record["updated_at"] = now_iso
        self._rebuild_current_intercepts()
        self._sync_operations(self.state.alerts, self.state.pilots)
        self._touch_workflow()
        await self.broadcaster(self.state.live_payload())
        return True, operation, None

    async def set_intercept_target_control(
        self,
        target_callsign: str,
        actor: str,
        *,
        response_status: str | None = None,
        atc_status: str | None = None,
        command_status: str | None = None,
        note: str | None = None,
    ) -> tuple[bool, dict[str, Any] | None, str | None]:
        target_callsign = str(target_callsign or "").strip().upper()[:32]
        actor = str(actor or "CONSOLE").strip()[:80] or "CONSOLE"
        live_callsigns = {str(item.get("callsign") or "").upper() for item in self.state.pilots}
        has_assignment = any(str(item.get("target_callsign") or "").upper() == target_callsign for item in self.manual_intercepts.values())
        has_operation = any(str(item.get("callsign") or "").upper() == target_callsign for item in self.operations.values())
        if not target_callsign or (target_callsign not in live_callsigns and not has_assignment and not has_operation):
            return False, None, "target_not_found"
        response = str(response_status or "").strip().upper() if response_status is not None else None
        atc = str(atc_status or "").strip().upper() if atc_status is not None else None
        command = str(command_status or "").strip().upper() if command_status is not None else None
        if response is not None and response not in TARGET_RESPONSE_STATUSES:
            return False, None, "invalid_response_status"
        if atc is not None and atc not in ATC_COORDINATION_STATUSES:
            return False, None, "invalid_atc_status"
        if command is not None and command not in INTERCEPT_COMMAND_STATUSES:
            return False, None, "invalid_command_status"
        control = self._ensure_intercept_control(target_callsign)
        now_iso = self._utc_now()
        if response is not None:
            control["target_response_status"] = response
        if atc is not None:
            control["atc_coordination_status"] = atc
        if command is not None:
            control["command_status"] = command
        if note is not None:
            control["coordination_note"] = str(note).strip()[:500]
        control["updated_at"] = now_iso
        control["updated_by"] = actor
        for record in self.manual_intercepts.values():
            if str(record.get("target_callsign") or "").upper() != target_callsign:
                continue
            if response is not None:
                record["target_response_status"] = response
                record["target_response_updated_at"] = now_iso
                record["target_response_updated_by"] = actor
            record["atc_coordination_status"] = control.get("atc_coordination_status")
            record["command_status"] = control.get("command_status")
            record["coordination_note"] = control.get("coordination_note")
            record["updated_at"] = now_iso
        operation = next((item for item in self.operations.values() if str(item.get("callsign") or "").upper() == target_callsign), None)
        if operation is not None:
            if response is not None:
                operation["target_response_status"] = response
                operation["target_response_updated_at"] = now_iso
                operation["target_response_updated_by"] = actor
            operation["atc_coordination_status"] = control.get("atc_coordination_status")
            operation["command_status"] = control.get("command_status")
            operation["coordination_note"] = control.get("coordination_note")
            details = []
            if response is not None:
                details.append(f"response {response.replace('_', ' ').lower()}")
            if atc is not None:
                details.append(f"ATC {atc.replace('_', ' ').lower()}")
            if command is not None:
                details.append(f"command {command.replace('_', ' ').lower()}")
            if note is not None:
                details.append("coordination note updated")
            self._append_event(
                operation,
                f"INTERCEPT_CONTROL_{len(operation.get('events', []))}",
                "Intercept control updated",
                f"{actor}: " + ", ".join(details),
            )
        self._rebuild_current_intercepts()
        self._sync_operations(self.state.alerts, self.state.pilots)
        self._sync_intercept_controls_state()
        self._touch_workflow()
        await self.broadcaster(self.state.live_payload())
        return True, dict(control), None

    async def clear_target_intercepts(
        self,
        target_callsign: str,
        actor: str,
    ) -> tuple[bool, list[dict[str, Any]]]:
        target_callsign = str(target_callsign or "").strip().upper()[:32]
        actor = str(actor or "CONSOLE").strip()[:80] or "CONSOLE"
        removed: list[dict[str, Any]] = []
        for interceptor_callsign, record in list(self.manual_intercepts.items()):
            if str(record.get("target_callsign") or "").upper() != target_callsign:
                continue
            removed.append(self.manual_intercepts.pop(interceptor_callsign))
        if not removed:
            return False, []
        self._rebuild_current_intercepts()
        self._sync_operations(self.state.alerts, self.state.pilots)
        operation = next((item for item in self.operations.values() if str(item.get("callsign") or "").upper() == target_callsign), None)
        if operation is not None:
            self._append_event(
                operation,
                f"ALL_INTERCEPTORS_RELEASED_{len(operation.get('events', []))}",
                "All manual interceptors released",
                f"Cleared by {actor}",
            )
        self._sync_intercept_controls_state()
        self._touch_workflow()
        await self.broadcaster(self.state.live_payload())
        return True, removed

    async def clear_manual_intercept(
        self,
        interceptor_callsign: str,
        actor: str,
    ) -> tuple[bool, dict[str, Any] | None]:
        interceptor_callsign = str(interceptor_callsign or "").strip().upper()[:32]
        actor = str(actor or "CONSOLE").strip()[:80] or "CONSOLE"
        record = self.manual_intercepts.pop(interceptor_callsign, None)
        if record is None:
            return False, None
        target_callsign = str(record.get("target_callsign") or "").upper()
        self._rebuild_current_intercepts()
        self._sync_operations(self.state.alerts, self.state.pilots)
        operation = next(
            (item for item in self.operations.values() if item.get("callsign") == target_callsign and item.get("active")),
            None,
        )
        if operation is not None:
            self._append_event(
                operation,
                f"MANUAL_RELEASE_{interceptor_callsign}_{len(operation.get('events', []))}",
                f"{interceptor_callsign} manual assignment cleared",
                f"Cleared by {actor}",
            )
            self.state.operations = sorted(self.operations.values(), key=lambda item: item.get("updated_at") or "", reverse=True)[:50]
        self._touch_workflow()
        await self.broadcaster(self.state.live_payload())
        return True, record

    async def start(self) -> None:
        await self._restore_operational_state()
        if self.feed_task is None:
            self.feed_task = asyncio.create_task(self._feed_loop(), name="vatsim-feed")
        if self.reference_task is None:
            self.reference_task = asyncio.create_task(self._reference_loop(), name="reference-data")

    async def stop(self) -> None:
        if self.persistence_task and not self.persistence_task.done():
            self.persistence_task.cancel()
            try:
                await self.persistence_task
            except asyncio.CancelledError:
                pass
        try:
            await self._persist_operational_state(force=True)
        except Exception:
            log.exception("Final operational-state persistence failed")
        for task in (self.feed_task, self.reference_task, self.airport_task):
            if task:
                task.cancel()
        for task in (self.feed_task, self.reference_task, self.airport_task):
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        await self.client.aclose()

    async def acknowledge_alert(self, alert_id: str) -> bool:
        """Compatibility endpoint: acknowledgment is intentionally console-local.

        The browser stores acknowledgment state. Returning success without
        mutating the shared feed prevents one operator from clearing another
        operator's popup.
        """
        return any(alert.get("id") == alert_id for alert in self.state.alerts)

    async def deny_pre_scramble(
        self,
        callsign: str,
        case_id: str | None,
        actor: str = "ATC CONSOLE",
        reason: str = "Denied during the 30-second pre-scramble review",
    ) -> tuple[bool, dict[str, Any] | None, str | None]:
        callsign = str(callsign or "").strip().upper()[:32]
        requested_case_id = str(case_id or "").strip()
        actor = str(actor or "ATC CONSOLE").strip()[:80] or "ATC CONSOLE"
        reason = str(reason or "Denied during the 30-second pre-scramble review").strip()[:240]
        pilot = next(
            (item for item in self.state.pilots if str(item.get("callsign") or "").upper() == callsign),
            None,
        )
        if pilot is None:
            return False, None, "track_not_found"
        current_case_id = str(pilot.get("pre_scramble_case_id") or "").strip()
        warning = pilot.get("pre_scramble_warning")
        if not current_case_id or not isinstance(warning, dict) or not warning.get("active"):
            return False, None, "warning_not_active"
        if requested_case_id and requested_case_id != current_case_id:
            return False, None, "stale_case"

        now_epoch = time.time()
        alert_id = str(warning.get("alert_id") or pilot.get("automatic_alert_id") or pilot.get("alert_id") or "")
        record = {
            "case_id": current_case_id,
            "callsign": callsign,
            "alert_id": alert_id,
            "reason": reason,
            "denied_by": actor,
            "denied_at": self._utc_now(),
            "denied_at_epoch": now_epoch,
            "expires_at_epoch": now_epoch + max(60, int(settings.pre_scramble_denial_record_ttl_seconds)),
            "scope": "current_communications_case",
        }
        self.pre_scramble_denials[current_case_id] = record
        self._apply_pre_scramble_denials(self.state.pilots, self.state.alerts)
        self._sync_operations(self.state.alerts, self.state.pilots)
        self._touch_workflow()
        await self.broadcaster(self.state.live_payload())
        return True, dict(record), None

    async def dismiss_alert(
        self,
        alert_id: str,
        actor: str = "ATC CONSOLE",
        reason: str = "Operator reviewed and dismissed automatic flag",
    ) -> bool:
        alert_id = str(alert_id or "").strip()
        actor = str(actor or "ATC CONSOLE").strip()[:80] or "ATC CONSOLE"
        reason = str(reason or "Operator reviewed and dismissed automatic flag").strip()[:240]
        active_alert = next((item for item in self.state.alerts if item.get("id") == alert_id), None)
        pilot = next(
            (
                item for item in self.state.pilots
                if item.get("alert_id") == alert_id or item.get("automatic_alert_id") == alert_id
            ),
            None,
        )
        is_automatic = bool(
            (active_alert and self._automatic_comms_only_alert(active_alert))
            or (pilot and pilot.get("auto_scramble_flag"))
        )
        found = bool(active_alert or pilot or alert_id in self.engine.dismissed)
        self.engine.dismiss(alert_id)
        if is_automatic:
            record = {
                "alert_id": alert_id,
                "callsign": str((active_alert or pilot or {}).get("callsign") or "").upper(),
                "reason": reason,
                "dismissed_by": actor,
                "dismissed_at": self._utc_now(),
            }
            self.automatic_flag_dismissals[alert_id] = record
            operation = self.operations.get(alert_id)
            if operation:
                self._append_event(
                    operation,
                    f"AUTOMATIC_FLAG_DISMISSED_{int(time.time())}",
                    "Automatic communications flag dismissed",
                    f"{reason} · {actor}",
                )
                operation["status"] = "AUTOMATIC FLAG DISMISSED — MONITOR"
                operation["active"] = False
                operation["completed"] = True
                operation["resolution"] = "AUTOMATIC_FLAG_DISMISSED"
                operation["resolved_by"] = actor
                operation["resolved_at"] = self._utc_now()
        before = len(self.state.alerts)
        self.state.alerts = [a for a in self.state.alerts if a.get("id") != alert_id]
        for item in self.state.pilots:
            if item.get("alert_id") == alert_id or item.get("automatic_alert_id") == alert_id:
                item["requires_ack"] = False
                if is_automatic:
                    item["automatic_flag_dismissed"] = True
                    item["automatic_flag_dismissal"] = dict(self.automatic_flag_dismissals[alert_id])
        self.state.operations = sorted(self.operations.values(), key=lambda item: item.get("updated_at") or "", reverse=True)[:50]
        self.state.automatic_flag_dismissals = list(self.automatic_flag_dismissals.values())
        self._touch_workflow()
        await self.broadcaster(self.state.live_payload())
        return found or len(self.state.alerts) != before

    async def set_manual_nordo(self, callsign: str, active: bool) -> tuple[bool, dict[str, Any] | None]:
        callsign = str(callsign or "").upper().strip()
        if not callsign:
            return False, None
        live_track = next(
            (pilot for pilot in self.state.pilots if str(pilot.get("callsign") or "").upper() == callsign),
            None,
        )
        if active and live_track is None:
            return False, None

        if active:
            session_key = f"{live_track.get('cid') or 'NO-CID'}:{live_track.get('logon_time') or 'NO-LOGON'}"
            record = self.engine.mark_manual_nordo(callsign, session_key=session_key)
        else:
            existed = self.engine.clear_manual_nordo(callsign)
            record = None
            if not existed and live_track is None:
                return False, None

        if self.last_network is not None and self.last_transceivers is not None:
            await self.process(self.last_network, self.last_transceivers, force=True)
        else:
            self._touch_workflow()
            await self.broadcaster(self.state.live_payload())
        return True, record

    async def _feed_loop(self) -> None:
        while True:
            started = time.perf_counter()
            try:
                network_response, tx_response = await asyncio.gather(
                    self.client.get(settings.vatsim_data_url),
                    self.client.get(settings.vatsim_transceiver_url),
                )
                network_response.raise_for_status()
                tx_response.raise_for_status()
                network, transceivers = network_response.json(), tx_response.json()
                self.last_network = network
                self.last_transceivers = transceivers
                await self.process(network, transceivers)
                self.state.error = None
            except Exception as exc:
                log.exception("VATSIM refresh failed")
                self.state.error = f"Live feed refresh failed: {type(exc).__name__}: {exc}"
                self.state.processing_ms = int((time.perf_counter() - started) * 1000)
                self.state.touch()
                await self.broadcaster(self.state.live_payload())
            elapsed = time.perf_counter() - started
            await asyncio.sleep(max(1.0, settings.poll_seconds - elapsed))

    async def _reference_loop(self) -> None:
        """Refresh heavy geometry independently of the live track feed."""
        while True:
            try:
                before = (self.boundaries.last_refresh, self.sua.last_refresh)
                await asyncio.gather(
                    self.boundaries.refresh(self.client),
                    self.sua.refresh(self.client),
                )
                after = (self.boundaries.last_refresh, self.sua.last_refresh)
                self.state.boundary_status = self.boundaries.status
                self._sync_center_boundaries()
                self.state.sua_status = self.sua.status
                self.state.sua_count = len(self.sua.areas)
                self.state.sua_updated_at = (
                    datetime.fromtimestamp(self.sua.last_refresh, timezone.utc).isoformat()
                    if self.sua.last_refresh
                    else None
                )
                if before != after and self.last_network is not None and self.last_transceivers is not None:
                    await self.process(self.last_network, self.last_transceivers, force=True)
                elif before != after:
                    self.state.touch()
                    await self.broadcaster(self.state.live_payload())
            except Exception as exc:
                log.warning("Reference-data refresh failed: %s", exc)
            await asyncio.sleep(60)

    def _schedule_airport_lookup(self, codes: set[str]) -> None:
        if self.airport_task and not self.airport_task.done():
            return
        self.airport_task = asyncio.create_task(
            self.airports.ensure(codes, self.client), name="airport-lookup"
        )

    def _record_track_history(self, pilots: list[dict[str, Any]]) -> None:
        """Keep a compact shared breadcrumb trail without bloating live payloads.

        History is retained in server memory for up to one hour and is fetched
        only when a user hovers or selects a specific track. This survives page
        refreshes and is shared by all connected consoles, but intentionally
        resets when the Railway service restarts or redeploys.
        """
        now = time.time()
        active_callsigns: set[str] = set()
        for pilot in pilots:
            callsign = str(pilot.get("callsign") or "").upper()
            if not callsign:
                continue
            active_callsigns.add(callsign)
            lat = float(pilot.get("lat") or 0)
            lon = float(pilot.get("lon") or 0)
            altitude = int(pilot.get("altitude") or 0)
            history = self.track_history.setdefault(callsign, [])
            last = history[-1] if history else None
            moved_nm = (
                haversine_nm(float(last["lat"]), float(last["lon"]), lat, lon)
                if last
                else 999.0
            )
            if not last or moved_nm >= 0.25 or now - float(last["time"]) >= 45:
                history.append(
                    {
                        "lat": round(lat, 5),
                        "lon": round(lon, 5),
                        "altitude": altitude,
                        "time": round(now, 1),
                    }
                )
            cutoff = now - 3600
            self.track_history[callsign] = [
                point for point in history[-160:] if float(point.get("time") or 0) >= cutoff
            ]

        # Remove trails that have been inactive for more than 90 minutes.
        stale_cutoff = now - 5400
        for callsign, history in list(self.track_history.items()):
            if callsign in active_callsigns:
                continue
            if not history or float(history[-1].get("time") or 0) < stale_cutoff:
                self.track_history.pop(callsign, None)

    def get_track_history(self, callsign: str) -> list[dict[str, Any]]:
        return list(self.track_history.get(str(callsign or "").upper(), []))

    @staticmethod
    def _atc_revision(coverage: list[dict[str, Any]]) -> str:
        signature = [
            (
                item.get("callsign"),
                item.get("facility"),
                tuple(item.get("frequencies") or []),
                item.get("boundary_id"),
                round(float(item.get("lat") or 0), 3),
                round(float(item.get("lon") or 0), 3),
                round(float(item.get("radius_nm") or 0), 1),
                bool(item.get("geometry")),
            )
            for item in coverage
        ]
        raw = json.dumps(signature, separators=(",", ":"), sort_keys=False)
        return hashlib.sha1(raw.encode()).hexdigest()[:12]

    @staticmethod
    def _center_boundary_revision(boundaries: list[dict[str, Any]]) -> str:
        signature = [
            (
                item.get("id"),
                item.get("country"),
                item.get("oceanic"),
                hashlib.sha1(
                    json.dumps(item.get("geometry"), separators=(",", ":"), sort_keys=True).encode()
                ).hexdigest()[:10],
            )
            for item in boundaries
        ]
        raw = json.dumps(signature, separators=(",", ":"), sort_keys=False)
        return hashlib.sha1(raw.encode()).hexdigest()[:12]

    def _sync_center_boundaries(self, force: bool = False) -> None:
        source_refresh = float(self.boundaries.last_refresh or 0.0)
        if (
            not force
            and self.center_boundary_source_refresh == source_refresh
            and self.state.center_boundary_revision != "pending"
        ):
            return
        center_boundaries = self.boundaries.center_boundaries()
        self.state.center_boundaries = center_boundaries
        self.state.center_boundary_revision = self._center_boundary_revision(center_boundaries)
        self.center_boundary_source_refresh = source_refresh

    async def process(
        self,
        network: dict[str, Any],
        transceivers: list[dict[str, Any]],
        *,
        force: bool = False,
    ) -> None:
        async with self.process_lock:
            await self._process_locked(network, transceivers, force=force)

    async def _process_locked(
        self,
        network: dict[str, Any],
        transceivers: list[dict[str, Any]],
        *,
        force: bool = False,
    ) -> None:
        started = time.perf_counter()
        feed_timestamp = str((network.get("general") or {}).get("update_timestamp") or "")
        if not force and feed_timestamp and feed_timestamp == self.last_processed_feed_timestamp:
            return

        stage_started = time.perf_counter()
        audio: dict[str, list[dict[str, Any]]] = {
            str(item.get("callsign") or "").upper(): item.get("transceivers") or []
            for item in transceivers
            if isinstance(item, dict)
        }
        raw_pilots = [
            pilot
            for pilot in network.get("pilots", [])
            if pilot.get("latitude") is not None
            and pilot.get("longitude") is not None
            and is_enabled_region(
                float(pilot["latitude"]),
                float(pilot["longitude"]),
                settings.monitor_canada,
            )
        ]

        airport_codes: set[str] = set()
        for pilot in raw_pilots:
            flight_plan = pilot.get("flight_plan") or {}
            airport_codes.update(
                {
                    str(flight_plan.get("departure") or "").upper(),
                    str(flight_plan.get("arrival") or "").upper(),
                }
            )
        self._schedule_airport_lookup(airport_codes)
        filter_ms = int((time.perf_counter() - stage_started) * 1000)

        stage_started = time.perf_counter()
        atc_coverage = self.boundaries.build_coverage(network.get("controllers", []), audio)
        coverage_ms = int((time.perf_counter() - stage_started) * 1000)
        stage_started = time.perf_counter()
        self._sync_temporary_exemptions()
        self._sync_pre_scramble_denials()
        display_pilots, alerts = self.engine.evaluate(
            raw_pilots,
            network.get("controllers", []),
            audio,
            atc_coverage,
            self.sua.areas,
        )
        detection_ms = int((time.perf_counter() - stage_started) * 1000)

        controllers = [
            {
                "callsign": item["callsign"],
                "facility": item["facility"],
                "lat": item["lat"],
                "lon": item["lon"],
                "frequency": item["frequency"],
                "frequencies": item["frequencies"],
                "radius_nm": item["radius_nm"],
                "has_boundary": bool(item["geometry"]),
                "source": item["source"],
            }
            for item in atc_coverage
        ]

        stage_started = time.perf_counter()
        self._record_track_history(display_pilots)
        self._apply_pre_scramble_denials(display_pilots, alerts)
        self._apply_mass_alert_verification(display_pilots, alerts)
        self._apply_manual_intercepts(display_pilots, alerts)
        self._group_scramble_incidents(alerts)
        live_callsigns = {str(item.get("callsign") or "").upper() for item in display_pilots}
        for callsign, record in list(self.engine.manual_nordo.items()):
            if callsign in live_callsigns:
                continue
            marked = float(record.get("marked_at_epoch") or 0)
            if time.time() - marked > settings.manual_nordo_stale_seconds:
                self.engine.manual_nordo.pop(callsign, None)
        self._sync_operations(alerts, display_pilots)
        workflow_ms = int((time.perf_counter() - stage_started) * 1000)

        self.state.feed_sequence += 1
        self.state.feed_updated_at = feed_timestamp or None
        self.state.connected_clients = int((network.get("general") or {}).get("connected_clients") or 0)
        self.state.pilots = display_pilots
        self.state.alerts = alerts
        self.state.controllers = controllers
        self.state.atc_coverage = atc_coverage
        self.state.atc_revision = self._atc_revision(atc_coverage)
        self._sync_center_boundaries()
        self.state.boundary_status = self.boundaries.status
        self.state.sua_status = self.sua.status
        self.state.sua_count = len(self.sua.areas)
        self.state.sua_updated_at = (
            datetime.fromtimestamp(self.sua.last_refresh, timezone.utc).isoformat()
            if self.sua.last_refresh
            else None
        )
        self.state.processing_ms = int((time.perf_counter() - started) * 1000)
        self.state.processing_breakdown = {
            "filter_ms": filter_ms,
            "coverage_ms": coverage_ms,
            "detection_ms": detection_ms,
            "workflow_ms": workflow_ms,
        }
        self.state.error = None
        self.state.last_success_epoch = time.time()
        self.state.touch()
        self.last_processed_feed_timestamp = feed_timestamp or self.last_processed_feed_timestamp
        await self.broadcaster(self.state.live_payload())
