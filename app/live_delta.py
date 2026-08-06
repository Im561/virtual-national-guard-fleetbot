from __future__ import annotations

from typing import Any, Callable

COLLECTION_KEYS: dict[str, Callable[[dict[str, Any]], str]] = {
    "pilots": lambda item: str(item.get("callsign") or "").upper(),
    "alerts": lambda item: str(item.get("id") or item.get("callsign") or "").upper(),
    "operations": lambda item: str(item.get("id") or item.get("callsign") or ""),
    "manual_intercepts": lambda item: str(item.get("assignment_id") or item.get("interceptor_callsign") or "").upper(),
    "intercept_controls": lambda item: str(item.get("target_callsign") or "").upper(),
    "temporary_exemptions": lambda item: str(item.get("id") or ""),
    "controllers": lambda item: str(item.get("callsign") or "").upper(),
}


def _index(items: list[dict[str, Any]] | None, key_fn: Callable[[dict[str, Any]], str]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items or []:
        key = key_fn(item)
        if key:
            result[key] = item
    return result


def build_live_delta(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any] | None:
    """Return a revision-safe live-state delta.

    A caller should fall back to a full snapshot when this returns ``None``.
    Collections are keyed so browsers can update, add, and remove tracks without
    parsing and replacing every item in the live state.
    """
    if not previous or previous.get("type") != "live" or current.get("type") != "live":
        return None
    previous_revision = previous.get("revision")
    current_revision = current.get("revision")
    if not isinstance(previous_revision, int) or not isinstance(current_revision, int):
        return None
    if current_revision <= previous_revision:
        return None

    scalar_changes: dict[str, Any] = {}
    ignored = set(COLLECTION_KEYS) | {"type", "revision"}
    for key, value in current.items():
        if key in ignored:
            continue
        if previous.get(key) != value:
            scalar_changes[key] = value

    collection_changes: dict[str, dict[str, Any]] = {}
    for name, key_fn in COLLECTION_KEYS.items():
        before = _index(previous.get(name), key_fn)
        after = _index(current.get(name), key_fn)
        before_order = list(before)
        after_order = list(after)
        upserted = [value for key, value in after.items() if before.get(key) != value]
        removed = [key for key in before if key not in after]
        order_changed = before_order != after_order
        if upserted or removed or order_changed:
            patch: dict[str, Any] = {"upsert": upserted, "remove": removed}
            if order_changed:
                patch["order"] = after_order
            collection_changes[name] = patch

    return {
        "type": "delta",
        "base_revision": previous_revision,
        "revision": current_revision,
        "changes": scalar_changes,
        "collections": collection_changes,
    }

HEAVY_PILOT_FIELDS = {
    "context",
    "observations",
    "reasons",
    "controller_candidates",
    "active_artcc_frequencies",
    "center_frequencies",
    "advisory_frequency_matches",
    "early_unicom_handoff_detail",
}


def compact_live_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip selection-only pilot detail from a WebSocket snapshot.

    Alerts retain their evidence, and the full pilot record remains available
    through the track-detail endpoint. This keeps map updates lightweight while
    preserving all operational fields needed for filtering and intercept logic.
    """
    if payload.get("type") != "live":
        return payload
    compact = dict(payload)
    compact["pilots"] = [
        {key: value for key, value in pilot.items() if key not in HEAVY_PILOT_FIELDS}
        for pilot in payload.get("pilots") or []
    ]
    compact["payload_mode"] = "compact"
    return compact
